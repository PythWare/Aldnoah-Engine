# Aldnoah_Logic/aldnoah_unpack.py

import mmap, os, re, struct, zlib

from .aldnoah_codecs import (
    decompress as codec_decompress,
    decompress_split_zlib_streams,
)
from .aldnoah_energy import EXT2, EXT3, EXT4, GameSchema


def log_comp_failure(log_dir: str, message: str):
    """
    Append a decompression failure message to comp_log.txt in the given folder
    """
    try:
        os.makedirs(log_dir, exist_ok=True)
        log_path = os.path.join(log_dir, "comp_log.txt")
        with open(log_path, "a", encoding="utf-8") as f:
            f.write(message + "\n")
    except Exception:
        pass


def looks_like_classic_split_zlib(raw: bytes) -> bool:
    """
    Heuristic to decide if raw looks like a split zlib container (G1M/G1T)

    I don't trust file_type, check structure + first chunk's zlib header
    """
    n = len(raw)
    if n < 0x20:
        return False

    chunk_count = int.from_bytes(raw[0x04:0x06], "little")
    if chunk_count <= 0 or chunk_count > 0x1000:
        return False

    header_end = 0x0C + 4 * chunk_count
    if header_end + 4 > n:
        return False

    first_chunk_size = int.from_bytes(raw[0x0C:0x10], "little")
    if first_chunk_size <= 0 or first_chunk_size > n:
        return False

    ptr = (header_end + 0x7F) & ~0x7F
    if ptr + 4 + 2 > n:
        return False

    inner_size = int.from_bytes(raw[ptr:ptr + 4], "little")
    if inner_size <= 0 or ptr + 4 + inner_size > n:
        return False

    cmf = raw[ptr + 4]
    flg = raw[ptr + 5]
    if cmf != 0x78:
        return False
    if ((cmf << 8) | flg) % 31 != 0:
        return False

    return True


def looks_like_split_zlib(raw: bytes) -> bool:
    return looks_like_classic_split_zlib(raw) or looks_like_split_zlib_pairtable_wrapper(raw)


def looks_like_split_zlib_pairtable_wrapper(raw: bytes, *, max_count: int = 4096) -> bool:
    """
    Outer blob is a contiguous pairtable of classic split zlib members
    """
    n = len(raw)
    if n < 20:
        return False

    count = int.from_bytes(raw[0:4], "little")
    if count < 2 or count > max_count:
        return False

    table_end = 4 + count * 8
    if table_end > n:
        return False

    prev_end = table_end
    for idx in range(count):
        ent_off = 4 + idx * 8
        payload_off = int.from_bytes(raw[ent_off:ent_off + 4], "little")
        payload_size = int.from_bytes(raw[ent_off + 4:ent_off + 8], "little")
        if payload_size <= 0 or payload_off < table_end or payload_off + payload_size > n:
            return False
        if payload_off != prev_end:
            return False
        if not looks_like_classic_split_zlib(raw[payload_off:payload_off + payload_size]):
            return False
        prev_end = payload_off + payload_size

    tail_len = n - prev_end
    return tail_len in (0, 6)


def looks_like_nested_subcontainer_structure(raw: bytes, *, max_count: int = 100_000) -> bool:
    """
    Shallow structural probe for nested subcontainers, this intentionally avoids
    the heavier signature scoring so outer wrappers with inner .bin payloads can
    still be recognized as valid subcontainers
    """
    n = len(raw)
    if n < 12:
        return False

    try:
        count = struct.unpack_from("<I", raw, 0)[0]
    except struct.error:
        return False

    if 1 <= count <= max_count:
        pair_table_end = 4 + count * 8
        if pair_table_end <= n:
            positive = 0
            last_off = -1
            valid = True
            for idx in range(count):
                ent_off = 4 + idx * 8
                off = int.from_bytes(raw[ent_off:ent_off + 4], "little", signed=False)
                sz = int.from_bytes(raw[ent_off + 4:ent_off + 8], "little", signed=False)
                if sz <= 0:
                    continue
                if off < pair_table_end or off + sz > n or off < last_off:
                    valid = False
                    break
                last_off = off
                positive += 1
            if valid and positive > 0:
                return True

    if count >= 2:
        toc_table_end = 4 + count * 4
        if toc_table_end <= n:
            offsets = [int.from_bytes(raw[4 + idx * 4:8 + idx * 4], "little", signed=False) for idx in range(count)]
            valid_offsets = [off for off in offsets if toc_table_end <= off < n]
            if len(valid_offsets) >= 2:
                return True

            sizes = offsets
            if sum(sizes) > 0 and toc_table_end + sum(sizes) <= n:
                return True

    return False


def payload_looks_meaningful(raw: bytes, *, allow_split_wrapper: bool = False) -> bool:
    if not raw:
        return False
    if detect_ext(raw) != ".bin":
        return True
    if looks_like_nested_subcontainer_structure(raw):
        return True
    if allow_split_wrapper and (looks_like_split_zlib(raw) or looks_like_split_zlib_pairtable_wrapper(raw)):
        return True
    return False


NUM_RE = re.compile(r"(\d+)")


def match_known_signature(data: bytes, off: int):
    if off < 0 or off + 4 > len(data):
        return None

    tail = data[off:]
    sig4 = data[off:off + 4]
    hit = EXT4.get(sig4)
    if hit:
        return hit

    if off + 3 <= len(data):
        sig3 = data[off:off + 3]
        hit = EXT3.get(sig3)
        if hit:
            return hit

    if off + 2 <= len(data):
        sig2 = data[off:off + 2]
        hit = EXT2.get(sig2)
        if hit:
            return hit

    if off + 12 <= len(data):
        try:
            total_out, csize = struct.unpack_from("<II", data, off)
            if 0 < total_out <= 0x40000000 and 0 < csize <= (len(data) - (off + 8)):
                if is_zlib_header(data[off + 8:off + 10]):
                    return "zl"
        except struct.error:
            pass

    if looks_like_split_zlib(tail) or looks_like_nested_subcontainer_structure(tail):
        return ".bin"

    return None


def read_subcontainer_toc(data: bytes, *, max_count: int = 100_000):
    """
    Reads: u32 count, then count u32 offsets
    Returns count, offsets, table_end, or None
    """
    n = len(data)
    if n < 8:
        return None

    try:
        count = struct.unpack_from("<I", data, 0)[0]
    except struct.error:
        return None

    if count < 2 or count > max_count:
        return None

    table_end = 4 + count * 4
    if table_end > n:
        return None

    try:
        offsets = list(struct.unpack_from("<" + "I" * count, data, 4))
    except struct.error:
        return None

    return count, offsets, table_end


def is_real_subcontainer(raw_data: bytes, offsets: list[int], table_end: int, probe_limit: int = 8) -> bool:
    """
    Treat as a real subcontainer only if several offsets point at recognizable inner resources
    """
    uniq = sorted(set(off for off in offsets if table_end <= off < len(raw_data)))
    if len(uniq) < 2:
        return False

    hits = 0
    for off in uniq[:probe_limit]:
        if match_known_signature(raw_data, off):
            hits += 1

    return hits >= 2


def is_zlib_header(blob: bytes) -> bool:
    if len(blob) < 2:
        return False
    cmf, flg = blob[0], blob[1]
    if (cmf & 0x0F) != 8 or (cmf >> 4) > 7:
        return False
    return ((cmf << 8) + flg) % 31 == 0


def decompress_zl_bytes(buf: bytes) -> bytes:
    if len(buf) < 8:
        raise ValueError("ZL buffer too small")

    total_out, csize = struct.unpack_from("<II", buf, 0)
    off = 8
    out = bytearray()
    chunk_idx = 0

    if csize > len(buf) - off and is_zlib_header(buf[4:6]):
        return zlib.decompress(buf[4:])

    while len(out) < total_out:
        if csize <= 0:
            raise ValueError(f"ZL chunk {chunk_idx}: invalid comp_size={csize}")
        if off + csize > len(buf):
            raise ValueError(f"ZL chunk {chunk_idx}: comp_size overruns file")

        comp = buf[off:off + csize]
        if not is_zlib_header(comp[:2]):
            break

        out.extend(zlib.decompress(comp))
        off += csize
        chunk_idx += 1

        if len(out) >= total_out:
            break
        if off + 4 > len(buf):
            break

        csize = struct.unpack_from("<I", buf, off)[0]
        off += 4

    if len(out) < total_out:
        raise ValueError(f"ZL decompressed short: got {len(out)} expected {total_out}")
    return bytes(out[:total_out])


def subcontainer_file_sort_key(path: str):
    stem = os.path.splitext(os.path.basename(path))[0]
    nums = NUM_RE.findall(stem)
    if nums:
        try:
            return (0, int(nums[-1]), stem.lower())
        except ValueError:
            pass
    return (1, stem.lower())


def next_available_output_path(path: str) -> str:
    if not os.path.exists(path):
        return path

    root, ext = os.path.splitext(path)
    counter = 1
    while True:
        candidate = f"{root}_{counter}{ext}"
        if not os.path.exists(candidate):
            return candidate
        counter += 1


def align_up(value: int, alignment: int = 16) -> int:
    return (value + (alignment - 1)) & ~(alignment - 1)


def choose_sequential_data_start(blob: bytes, table_end: int, sizes: list[int]) -> int:
    need = sum(sizes)
    n = len(blob)
    if table_end + need > n:
        return table_end

    candidates = [table_end]
    scan_limit = min(n, table_end + 0x4000)
    for off in range(table_end, scan_limit, 4):
        if off + 4 > n:
            break
        if blob[off:off + 4] != b"\x00\x00\x00\x00":
            candidates.append(off)
            break

    best = table_end
    best_score = -1
    for cand in candidates:
        if cand < table_end or cand + need > n:
            continue
        score = 0
        cur = cand
        for sz in sizes[:min(6, len(sizes))]:
            if sz <= 0 or cur + sz > n:
                break
            if payload_looks_meaningful(blob[cur:cur + sz]):
                score += 1
            cur += sz
        if score > best_score:
            best_score = score
            best = cand
    return best


def read_sequential_subcontainer_layout(blob: bytes, *, max_count: int = 100_000):
    n = len(blob)
    if n < 8:
        return None

    try:
        count = struct.unpack_from("<I", blob, 0)[0]
    except struct.error:
        return None
    if count < 2 or count > max_count:
        return None

    table_end = 4 + count * 4
    if table_end > n:
        return None

    sizes = []
    for idx in range(count):
        off = 4 + idx * 4
        sizes.append(int.from_bytes(blob[off:off + 4], "little", signed=False))

    if sum(sizes) <= 0:
        return None

    data_start = choose_sequential_data_start(blob, table_end, sizes)
    if data_start + sum(sizes) > n:
        return None

    hits = 0
    cur = data_start
    checked = 0
    nonzero = 0
    for sz in sizes:
        if sz <= 0:
            continue
        nonzero += 1
        if cur + sz > n:
            return None
        if checked < 8:
            if payload_looks_meaningful(blob[cur:cur + sz]):
                hits += 1
            checked += 1
        cur += sz

    if nonzero < 2 or hits < 2:
        return None

    return {
        "kind": "sequential",
        "count": count,
        "sizes": sizes,
        "table_end": table_end,
        "data_start": data_start,
    }


def read_pairtable_subcontainer_layout(blob: bytes, *, max_count: int = 100_000):
    n = len(blob)
    if n < 12:
        return None

    try:
        count = struct.unpack_from("<I", blob, 0)[0]
    except struct.error:
        return None
    if count < 1 or count > max_count:
        return None

    table_end = 4 + count * 8
    if table_end > n:
        return None

    entries = []
    checked = 0
    hits = 0
    positive_indices = []
    last_off = -1

    for idx in range(count):
        ent_off = 4 + idx * 8
        off = int.from_bytes(blob[ent_off:ent_off + 4], "little", signed=False)
        sz = int.from_bytes(blob[ent_off + 4:ent_off + 8], "little", signed=False)
        entries.append((off, sz))

        if sz <= 0:
            continue
        if off < table_end or off + sz > n:
            return None
        if last_off > off:
            return None
        last_off = off
        positive_indices.append(idx)

        if checked < 8:
            if payload_looks_meaningful(blob[off:off + sz]):
                hits += 1
            checked += 1

    if len(positive_indices) <= 0:
        return None
    if len(positive_indices) == 1:
        off, sz = entries[positive_indices[0]]
        if not payload_looks_meaningful(blob[off:off + sz]):
            return None
    elif hits < 2:
        return None

    return {
        "kind": "pairtable",
        "count": count,
        "entries": entries,
        "table_end": table_end,
        "positive_indices": positive_indices,
    }


def read_relative_pair_block(blob: bytes, start: int, block_end: int, *, max_count: int = 100_000):
    if start < 0 or block_end > len(blob) or start + 12 > block_end:
        return None

    try:
        declared_count = struct.unpack_from("<I", blob, start)[0]
        payload_base_rel = struct.unpack_from("<I", blob, start + 4)[0]
    except struct.error:
        return None

    if declared_count <= 1 or declared_count > max_count:
        return None
    if payload_base_rel < 12 or start + payload_base_rel > block_end:
        return None

    table_bytes = payload_base_rel - 12
    if table_bytes <= 0 or table_bytes % 8 != 0:
        return None

    entry_count = table_bytes // 8
    if entry_count <= 0:
        return None
    if declared_count not in (entry_count, entry_count + 1):
        return None

    entries = []
    payloads = []
    positive = 0
    hits = 0
    checked = 0
    payload_base_abs = start + payload_base_rel
    for idx in range(entry_count):
        ent_off = start + 8 + idx * 8
        rel = struct.unpack_from("<I", blob, ent_off)[0]
        sz = struct.unpack_from("<I", blob, ent_off + 4)[0]
        abs_off = payload_base_abs + rel
        if sz > 0:
            if abs_off < payload_base_abs or abs_off + sz > block_end:
                return None
            positive += 1
            payloads.append((abs_off, sz))
            if checked < 6:
                if payload_looks_meaningful(blob[abs_off:abs_off + sz]):
                    hits += 1
                checked += 1
        entries.append((rel, sz, abs_off))

    if positive <= 0:
        return None
    if checked > 0 and hits <= 0:
        return None

    reserved_start = start + 8 + entry_count * 8
    reserved = blob[reserved_start:payload_base_abs]
    return {
        "kind": "relpairblock",
        "start": start,
        "end": block_end,
        "declared_count": declared_count,
        "entry_count": entry_count,
        "payload_base_rel": payload_base_rel,
        "payload_base_abs": payload_base_abs,
        "entries": entries,
        "payloads": payloads,
        "reserved": reserved,
        "raw_bytes": blob[start:block_end],
    }


def read_relative_pairtable_block(blob: bytes, start: int, block_end: int, *, max_count: int = 100_000):
    if start < 0 or block_end > len(blob) or start + 12 > block_end:
        return None

    try:
        count = struct.unpack_from("<I", blob, start)[0]
    except struct.error:
        return None
    if count <= 0 or count > max_count:
        return None

    table_end = start + 4 + count * 8
    if table_end > block_end:
        return None

    entries = []
    last_abs = -1
    positive = 0
    hits = 0
    checked = 0
    max_payload_end = table_end
    for idx in range(count):
        ent_off = start + 4 + idx * 8
        rel = struct.unpack_from("<I", blob, ent_off)[0]
        sz = struct.unpack_from("<I", blob, ent_off + 4)[0]
        abs_off = start + rel
        if sz > 0:
            if abs_off < table_end or abs_off + sz > block_end:
                return None
            if abs_off < last_abs:
                return None
            last_abs = abs_off
            positive += 1
            max_payload_end = max(max_payload_end, abs_off + sz)
            if checked < 6:
                if payload_looks_meaningful(blob[abs_off:abs_off + sz]):
                    hits += 1
                checked += 1
        entries.append((rel, sz, abs_off))

    trailing = block_end - max_payload_end
    if positive <= 0:
        return None
    if trailing > 0x40:
        return None
    if checked > 0 and hits <= 0 and count > 1:
        return None

    return {
        "kind": "relpairtableblock",
        "start": start,
        "end": block_end,
        "count": count,
        "table_end": table_end,
        "entries": entries,
        "raw_bytes": blob[start:block_end],
    }


def read_bounded_simple_block(blob: bytes, start: int, block_end: int, *, max_count: int = 100_000):
    n = len(blob)
    if start < 0 or start + 8 > n or block_end > n or start >= block_end:
        return None

    try:
        count = struct.unpack_from("<I", blob, start)[0]
    except struct.error:
        return None
    if count <= 0 or count > min(max_count, 4096):
        return None

    entries = []
    payloads = []
    cursor = start + 4
    positive = 0
    hits = 0
    checked = 0
    for _idx in range(count):
        if cursor + 4 > block_end:
            return None
        sz = struct.unpack_from("<I", blob, cursor)[0]
        cursor += 4
        if sz < 0 or cursor + sz > block_end:
            return None
        entries.append((cursor, sz))
        if sz > 0:
            positive += 1
            payloads.append((cursor, sz))
            if checked < 6:
                if payload_looks_meaningful(blob[cursor:cursor + sz]):
                    hits += 1
                checked += 1
        cursor += sz

    trailing = block_end - cursor
    if positive <= 0 or trailing > 0x40:
        return None
    if checked > 0 and hits <= 0:
        return None

    return {
        "kind": "simpleblock",
        "start": start,
        "count": count,
        "entries": entries,
        "end": cursor,
        "block_end": block_end,
    }


def read_multiblock_subcontainer_layout(blob: bytes, *, max_count: int = 100_000):
    n = len(blob)
    if n < 0x20:
        return None

    try:
        block_count = struct.unpack_from("<I", blob, 0)[0]
        primary_block_off = struct.unpack_from("<I", blob, 4)[0]
    except struct.error:
        return None
    if block_count <= 0 or block_count > min(max_count, 4096):
        return None
    if primary_block_off < 0x10 or primary_block_off > n:
        return None

    dynamic_header_end = 8 + block_count * 4
    if dynamic_header_end > primary_block_off:
        return None

    later_block_offsets = []
    for idx in range(block_count):
        off = struct.unpack_from("<I", blob, 8 + idx * 4)[0]
        if off <= primary_block_off or off >= n:
            return None
        later_block_offsets.append(off)

    if later_block_offsets != sorted(later_block_offsets):
        return None

    tail_field_off = dynamic_header_end if dynamic_header_end + 4 <= primary_block_off else None
    last_block_span = None
    if tail_field_off is not None:
        last_block_span = struct.unpack_from("<I", blob, tail_field_off)[0]
        if last_block_span <= 0 or later_block_offsets[-1] + last_block_span > n:
            last_block_span = None

    candidate_primary_ends = sorted(set(off for off in later_block_offsets if off > primary_block_off) | {n})
    primary_block = None
    primary_block_end = None
    for candidate_end in candidate_primary_ends:
        primary_block = read_relative_pairtable_block(blob, primary_block_off, candidate_end, max_count=max_count)
        if primary_block:
            primary_block_end = candidate_end
            break
    if not primary_block:
        primary_block_end = later_block_offsets[0]
        primary_block = read_relative_pair_block(blob, primary_block_off, primary_block_end, max_count=max_count)
    if not primary_block:
        trailing_primary = read_relative_pairtable_block(blob, primary_block_off, n, max_count=max_count)
        trailer_start = min(later_block_offsets) if later_block_offsets else n
        if trailing_primary and trailer_start < n and all(b == 0 for b in blob[trailer_start:n]):
            anchor_original = int(trailing_primary["end"])
            return {
                "kind": "multiblock",
                "outer_count": block_count,
                "primary_block_off": primary_block_off,
                "tail_field_off": tail_field_off,
                "last_block_span": last_block_span,
                "later_block_offsets": later_block_offsets,
                "header_offset_deltas": [anchor_original - off for off in later_block_offsets],
                "primary_block": trailing_primary,
                "later_blocks": [],
                "wrapper_trailer": blob[anchor_original:n],
            }
        return None

    later_blocks = []
    active_later_offsets = [off for off in later_block_offsets if off >= int(primary_block["end"])]
    for idx, start in enumerate(active_later_offsets):
        if idx + 1 < len(active_later_offsets):
            end = active_later_offsets[idx + 1]
        elif last_block_span is not None:
            end = min(n, start + last_block_span)
        else:
            end = n
        if end <= start:
            return None

        block = read_relative_pairtable_block(blob, start, end, max_count=max_count)
        if not block:
            block = read_relative_pair_block(blob, start, end, max_count=max_count)
        if not block:
            block = read_bounded_simple_block(blob, start, end, max_count=max_count)
        if not block:
            if start < n and end <= n and all(b == 0 for b in blob[start:end]):
                continue
            block = {
                "kind": "rawblock",
                "start": start,
                "end": end,
                "entries": [],
                "raw_bytes": blob[start:end],
            }
        later_blocks.append(block)

    return {
        "kind": "multiblock",
        "outer_count": block_count,
        "primary_block_off": primary_block_off,
        "tail_field_off": tail_field_off,
        "last_block_span": last_block_span,
        "later_block_offsets": later_block_offsets,
        "header_offset_deltas": [
            (active_later_offsets[0] if active_later_offsets else int(primary_block["end"])) - off
            for off in later_block_offsets
        ],
        "primary_block": primary_block,
        "later_blocks": later_blocks,
        "wrapper_trailer": blob[int(primary_block["end"]):n] if not later_blocks and int(primary_block["end"]) < n and all(b == 0 for b in blob[int(primary_block["end"]):n]) else b"",
    }


def read_universal_subcontainer_layout(blob: bytes):
    multiblock_layout = read_multiblock_subcontainer_layout(blob)
    if multiblock_layout:
        return multiblock_layout

    pair_layout = read_pairtable_subcontainer_layout(blob)
    if pair_layout:
        return pair_layout

    toc_info = read_subcontainer_toc(blob)
    if toc_info:
        count, offsets, table_end = toc_info
        if is_real_subcontainer(blob, offsets, table_end):
            unique_offsets = sorted(set(off for off in offsets if table_end <= off < len(blob)))
            if len(unique_offsets) >= 2:
                return {
                    "kind": "offsets",
                    "count": count,
                    "offsets": offsets,
                    "table_end": table_end,
                    "unique_offsets": unique_offsets,
                }

    return read_sequential_subcontainer_layout(blob)


def infer_sequential_alignment_from_original(blob: bytes, table_end: int, sizes: list[int]) -> int | None:
    try:
        data_start = choose_sequential_data_start(blob, table_end, sizes)
        for alignment in (4, 8, 16, 32, 64, 128, 256, 512, 1024, 2048, 4096):
            if align_up(table_end, alignment) == data_start:
                return alignment
        if data_start % 16 == 0:
            return 16
        if data_start % 4 == 0:
            return 4
    except Exception:
        pass
    return None


def infer_pairtable_alignment_from_original(entries: list[tuple[int, int]], table_end: int) -> int | None:
    try:
        first_off = None
        for off, sz in entries:
            if sz > 0:
                first_off = off
                break
        if first_off is None:
            return 16

        for alignment in (4, 8, 16, 32, 64, 128, 256, 512, 1024, 2048, 4096):
            if align_up(table_end, alignment) == first_off:
                return alignment
        if first_off % 16 == 0:
            return 16
        if first_off % 4 == 0:
            return 4
    except Exception:
        pass
    return None


def infer_relpair_alignment_from_original(entries: list[tuple[int, int, int]]) -> int:
    positive_rels = [rel for rel, sz, _abs_off in entries if sz > 0]
    if not positive_rels:
        return 4
    for alignment in (64, 32, 16, 8, 4):
        if all(rel % alignment == 0 for rel in positive_rels):
            return alignment
    return 4


def compute_positive_entry_gaps(entries: list[tuple], *, off_index: int = 0, size_index: int = 1) -> dict[int, int]:
    gaps: dict[int, int] = {}
    previous_end: int | None = None
    for idx, entry in enumerate(entries):
        off = int(entry[off_index])
        sz = int(entry[size_index])
        if sz <= 0:
            continue
        if previous_end is None:
            gaps[idx] = max(0, off)
        else:
            gaps[idx] = max(0, off - previous_end)
        previous_end = off + sz
    return gaps


def block_entry_offsets(block: dict) -> list[tuple[int, int]]:
    kind = block.get("kind")
    if kind in {"relpairblock", "relpairtableblock"}:
        return [(abs_off, sz) for _rel, sz, abs_off in block["entries"]]
    if kind == "simpleblock":
        return list(block["entries"])
    return []


def build_relative_pair_block(layout: dict, chunks: list[bytes]) -> bytes:
    entry_count = layout["entry_count"]
    if len(chunks) != entry_count:
        raise ValueError("Relative pair block rebuild received the wrong number of payload chunks.")

    payload_base_rel = int(layout["payload_base_rel"])
    original_entries = list(layout["entries"])
    positive_rels = [rel for rel, sz, _abs_off in original_entries if sz > 0]
    min_rel = min(positive_rels, default=0)
    preserve_layout = False
    last_end = -1
    for rel, sz, _abs_off in sorted(original_entries, key=lambda item: item[0]):
        if sz <= 0:
            continue
        if rel < last_end:
            preserve_layout = True
            break
        last_end = rel + sz

    new_entries: list[tuple[int, int]] = []
    if preserve_layout:
        for (rel, _old_sz, _abs_off), chunk in zip(original_entries, chunks):
            new_entries.append((rel if chunk else 0, len(chunk)))
    else:
        gap_before = compute_positive_entry_gaps(original_entries, off_index=0, size_index=1)
        previous_end_new: int | None = None
        for idx, chunk in enumerate(chunks):
            if chunk:
                rel_cursor = gap_before.get(idx, min_rel if previous_end_new is None else 0) if previous_end_new is None else previous_end_new + gap_before.get(idx, 0)
                new_entries.append((rel_cursor, len(chunk)))
                previous_end_new = rel_cursor + len(chunk)
            else:
                new_entries.append((0, 0))

    reserved = layout.get("reserved", b"")
    rebuilt = bytearray(layout.get("raw_bytes", b""))
    minimum_header = payload_base_rel
    if len(rebuilt) < minimum_header:
        rebuilt.extend(b"\x00" * (minimum_header - len(rebuilt)))

    struct.pack_into("<I", rebuilt, 0, int(layout["declared_count"]))
    struct.pack_into("<I", rebuilt, 4, payload_base_rel)
    for idx, (rel_off, sz) in enumerate(new_entries):
        struct.pack_into("<I", rebuilt, 8 + idx * 8, int(rel_off))
        struct.pack_into("<I", rebuilt, 8 + idx * 8 + 4, int(sz))

    reserved_start = 8 + len(new_entries) * 8
    if reserved_start + len(reserved) > len(rebuilt):
        rebuilt.extend(b"\x00" * (reserved_start + len(reserved) - len(rebuilt)))
    rebuilt[reserved_start:reserved_start + len(reserved)] = reserved
    if len(rebuilt) < payload_base_rel:
        rebuilt.extend(b"\x00" * (payload_base_rel - len(rebuilt)))
    elif len(rebuilt) > payload_base_rel:
        pass

    written_ranges: list[tuple[int, int]] = []
    for (rel_off, old_sz, _old_abs_off), chunk in zip(original_entries, chunks):
        if old_sz > len(chunk):
            abs_off = payload_base_rel + rel_off
            zero_start = abs_off + len(chunk)
            zero_end = abs_off + old_sz
            if len(rebuilt) < zero_end:
                rebuilt.extend(b"\x00" * (zero_end - len(rebuilt)))
            rebuilt[zero_start:zero_end] = b"\x00" * max(0, zero_end - zero_start)

    for (rel_off, _sz), chunk in zip(new_entries, chunks):
        if not chunk:
            continue
        abs_off = payload_base_rel + rel_off
        if len(rebuilt) < abs_off + len(chunk):
            rebuilt.extend(b"\x00" * (abs_off + len(chunk) - len(rebuilt)))
        for prev_start, prev_end in written_ranges:
            overlap_start = max(abs_off, prev_start)
            overlap_end = min(abs_off + len(chunk), prev_end)
            if overlap_start < overlap_end:
                chunk_slice = chunk[overlap_start - abs_off:overlap_end - abs_off]
                rebuilt_slice = rebuilt[overlap_start:overlap_end]
                if chunk_slice != rebuilt_slice:
                    raise ValueError(
                        "Rebuild conflict: overlapping relative-pair payloads now contain different bytes."
                    )
        rebuilt[abs_off:abs_off + len(chunk)] = chunk
        written_ranges.append((abs_off, abs_off + len(chunk)))

    return bytes(rebuilt)


def build_relative_pairtable_block(layout: dict, chunks: list[bytes]) -> bytes:
    count = layout["count"]
    if len(chunks) != count:
        raise ValueError("Relative pair-table block rebuild received the wrong number of payload chunks.")

    new_entries: list[tuple[int, int]] = []
    gap_before = compute_positive_entry_gaps(layout["entries"], off_index=0, size_index=1)
    previous_end_new: int | None = None
    for idx, ((rel, _old_sz, _abs_off), chunk) in enumerate(zip(layout["entries"], chunks)):
        if chunk:
            rel_off = gap_before.get(idx, rel) if previous_end_new is None else previous_end_new + gap_before.get(idx, 0)
            new_entries.append((rel_off, len(chunk)))
            previous_end_new = rel_off + len(chunk)
        else:
            new_entries.append((0, 0))

    rebuilt = bytearray(layout.get("raw_bytes", b""))
    minimum_header = 4 + count * 8
    if len(rebuilt) < minimum_header:
        rebuilt.extend(b"\x00" * (minimum_header - len(rebuilt)))

    struct.pack_into("<I", rebuilt, 0, int(count))
    for idx, (rel_off, sz) in enumerate(new_entries):
        struct.pack_into("<I", rebuilt, 4 + idx * 8, int(rel_off))
        struct.pack_into("<I", rebuilt, 4 + idx * 8 + 4, int(sz))

    written_ranges: list[tuple[int, int]] = []
    for (rel_off, old_sz, _old_abs_off), chunk in zip(layout["entries"], chunks):
        if old_sz > len(chunk):
            zero_start = rel_off + len(chunk)
            zero_end = rel_off + old_sz
            if len(rebuilt) < zero_end:
                rebuilt.extend(b"\x00" * (zero_end - len(rebuilt)))
            rebuilt[zero_start:zero_end] = b"\x00" * max(0, zero_end - zero_start)

    for (rel_off, _sz), chunk in zip(new_entries, chunks):
        if not chunk:
            continue
        if len(rebuilt) < rel_off + len(chunk):
            rebuilt.extend(b"\x00" * (rel_off + len(chunk) - len(rebuilt)))
        for prev_start, prev_end in written_ranges:
            overlap_start = max(rel_off, prev_start)
            overlap_end = min(rel_off + len(chunk), prev_end)
            if overlap_start < overlap_end:
                chunk_slice = chunk[overlap_start - rel_off:overlap_end - rel_off]
                rebuilt_slice = rebuilt[overlap_start:overlap_end]
                if chunk_slice != rebuilt_slice:
                    raise ValueError(
                        "Rebuild conflict: overlapping relative pair-table payloads now contain different bytes."
                    )
        rebuilt[rel_off:rel_off + len(chunk)] = chunk
        written_ranges.append((rel_off, rel_off + len(chunk)))

    return bytes(rebuilt)


def build_simple_block(chunks: list[bytes]) -> bytes:
    rebuilt = bytearray()
    rebuilt.extend(int(len(chunks)).to_bytes(4, "little", signed=False))
    for chunk in chunks:
        rebuilt.extend(int(len(chunk)).to_bytes(4, "little", signed=False))
        rebuilt.extend(chunk)
    return bytes(rebuilt)


def try_unpack_subcontainer_blob(blob: bytes, out_dir: str) -> bool:
    if looks_like_split_zlib_pairtable_wrapper(blob):
        return False
    layout = read_universal_subcontainer_layout(blob)
    if not layout:
        return False

    os.makedirs(out_dir, exist_ok=True)
    if layout["kind"] == "multiblock":
        out_index = 0
        for abs_off, sz in block_entry_offsets(layout["primary_block"]):
            if sz <= 0:
                out_path = os.path.join(out_dir, f"{out_index:03d}.bin")
                with open(out_path, "wb") as fout:
                    fout.write(b"")
                out_index += 1
                continue
            chunk = blob[abs_off:abs_off + sz]
            inner_ext = detect_ext(chunk)
            if inner_ext in (".ini", ".txt") and b"\x00" in chunk[:64]:
                inner_ext = ".bin"
            out_path = os.path.join(out_dir, f"{out_index:03d}{inner_ext}")
            with open(out_path, "wb") as fout:
                fout.write(chunk)
            out_index += 1

        for block in layout["later_blocks"]:
            for start, sz in block_entry_offsets(block):
                if sz <= 0:
                    out_path = os.path.join(out_dir, f"{out_index:03d}.bin")
                    with open(out_path, "wb") as fout:
                        fout.write(b"")
                    out_index += 1
                    continue
                chunk = blob[start:start + sz]
                inner_ext = detect_ext(chunk)
                if inner_ext in (".ini", ".txt") and b"\x00" in chunk[:64]:
                    inner_ext = ".bin"
                out_path = os.path.join(out_dir, f"{out_index:03d}{inner_ext}")
                with open(out_path, "wb") as fout:
                    fout.write(chunk)
                out_index += 1
    elif layout["kind"] == "offsets":
        unique_offsets = layout["unique_offsets"]
        for idx, start in enumerate(unique_offsets):
            end = unique_offsets[idx + 1] if idx + 1 < len(unique_offsets) else len(blob)
            if end <= start:
                continue
            chunk = blob[start:end]
            inner_ext = detect_ext(chunk)
            if inner_ext == ".riff" and b"WAVEfmt" in chunk[:64]:
                inner_ext = ".wav"
            out_path = os.path.join(out_dir, f"entry_{idx:03d}{inner_ext}")
            with open(out_path, "wb") as fout:
                fout.write(chunk)
    elif layout["kind"] == "sequential":
        cur = layout["data_start"]
        for idx, sz in enumerate(layout["sizes"]):
            if sz <= 0:
                out_path = os.path.join(out_dir, f"{idx:03d}.bin")
                with open(out_path, "wb") as fout:
                    fout.write(b"")
                continue
            if cur + sz > len(blob):
                break
            chunk = blob[cur:cur + sz]
            cur += sz
            inner_ext = detect_ext(chunk)
            if inner_ext in (".ini", ".txt") and b"\x00" in chunk[:64]:
                inner_ext = ".bin"
            out_path = os.path.join(out_dir, f"{idx:03d}{inner_ext}")
            with open(out_path, "wb") as fout:
                fout.write(chunk)
    else:
        for idx, (off, sz) in enumerate(layout["entries"]):
            if sz <= 0:
                continue
            if off + sz > len(blob):
                break
            chunk = blob[off:off + sz]
            inner_ext = detect_ext(chunk)
            if inner_ext in (".ini", ".txt") and b"\x00" in chunk[:64]:
                inner_ext = ".bin"
            out_path = os.path.join(out_dir, f"{idx:03d}{inner_ext}")
            with open(out_path, "wb") as fout:
                fout.write(chunk)
    return True


def unpack_kvs_blob(blob: bytes, out_dir: str) -> bool:
    n = len(blob)
    if n < 32 or blob[:4] != b"KOVS":
        return False

    os.makedirs(out_dir, exist_ok=True)
    pos = 0
    index = 0
    while True:
        if pos + 32 > n:
            break

        if blob[pos:pos + 4] != b"KOVS":
            found = False
            scan = pos
            while scan + 4 <= n:
                if blob[scan:scan + 4] == b"KOVS":
                    pos = scan
                    found = True
                    break
                scan += 4
            if not found:
                break

        if pos + 32 > n:
            break

        size = int.from_bytes(blob[pos + 4:pos + 8], "little", signed=False)
        if size <= 0:
            break

        data_start = pos + 32
        data_end = data_start + size
        if data_end > n:
            break

        chunk = blob[pos:data_end]
        out_path = os.path.join(out_dir, f"{index:05d}.kvs")
        with open(out_path, "wb") as fout:
            fout.write(chunk)

        index += 1
        pos = data_end
        if pos % 16 != 0:
            pos = (pos + 15) & ~0x0F

    return index > 0


def unpack_nested_resource(path: str, blob: bytes | None = None) -> bool:
    if not os.path.isfile(path):
        return False

    if blob is None:
        with open(path, "rb") as handle:
            blob = handle.read()

    base_dir, fname = os.path.split(path)
    name_no_ext, _ = os.path.splitext(fname)
    out_dir = os.path.join(base_dir, name_no_ext)

    if unpack_kvs_blob(blob, out_dir):
        return True
    return try_unpack_subcontainer_blob(blob, out_dir)


def rebuild_subcontainer_from_folder(folder_path: str, original_subcontainer_path: str, output_path: str | None = None):
    if not os.path.isdir(folder_path):
        raise ValueError("Selected subcontainer folder does not exist.")
    if not os.path.isfile(original_subcontainer_path):
        raise ValueError("Selected original subcontainer file does not exist.")

    with open(original_subcontainer_path, "rb") as handle:
        original_blob = handle.read()
    if len(original_blob) < 6:
        raise ValueError("Original subcontainer is missing the 6-byte Aldnoah taildata.")

    original_raw = original_blob[:-6]
    taildata_bytes = original_blob[-6:]

    layout = read_universal_subcontainer_layout(original_raw)
    if not layout:
        raise ValueError("Original file does not look like a supported universal subcontainer.")

    folder_files = [
        os.path.join(folder_path, name)
        for name in os.listdir(folder_path)
        if os.path.isfile(os.path.join(folder_path, name))
    ]
    folder_files.sort(key=subcontainer_file_sort_key)

    if not folder_files:
        raise ValueError("Selected subcontainer folder does not contain any files to rebuild.")
    if layout["kind"] == "multiblock":
        total_slots = len(block_entry_offsets(layout["primary_block"])) + sum(
            len(block_entry_offsets(block)) for block in layout["later_blocks"]
        )
        if len(folder_files) != total_slots:
            raise ValueError(
                f"Subcontainer file count mismatch. Folder has {len(folder_files)} file(s), "
                f"but the original multi-block layout maps to {total_slots} payload slot(s)."
            )

        file_iter = iter(folder_files)
        primary_chunks = []
        for _entry in block_entry_offsets(layout["primary_block"]):
            file_path = next(file_iter)
            with open(file_path, "rb") as handle:
                primary_chunks.append(handle.read())

        later_chunk_groups = []
        for block in layout["later_blocks"]:
            block_chunks = []
            for _entry in block_entry_offsets(block):
                file_path = next(file_iter)
                with open(file_path, "rb") as handle:
                    block_chunks.append(handle.read())
            later_chunk_groups.append(block_chunks)

        rebuilt = bytearray(original_raw[:layout["primary_block_off"]])
        if layout["primary_block"]["kind"] == "relpairtableblock":
            primary_bytes = build_relative_pairtable_block(layout["primary_block"], primary_chunks)
        else:
            primary_bytes = build_relative_pair_block(layout["primary_block"], primary_chunks)
        rebuilt.extend(primary_bytes)

        later_offsets = []
        for block, block_chunks in zip(layout["later_blocks"], later_chunk_groups):
            block_start = align_up(len(rebuilt), 4)
            original_start = int(block.get("start", block_start))
            if original_start >= block_start:
                block_start = original_start
            if len(rebuilt) < block_start:
                rebuilt.extend(b"\x00" * (block_start - len(rebuilt)))
            later_offsets.append(block_start)
            if block["kind"] == "rawblock":
                rebuilt.extend(block.get("raw_bytes", b""))
            elif block["kind"] == "simpleblock":
                rebuilt.extend(build_simple_block(block_chunks))
            elif block["kind"] == "relpairtableblock":
                rebuilt.extend(build_relative_pairtable_block(block, block_chunks))
            else:
                rebuilt.extend(build_relative_pair_block(block, block_chunks))

        struct.pack_into("<I", rebuilt, 0, int(layout["outer_count"]))
        struct.pack_into("<I", rebuilt, 4, int(layout["primary_block_off"]))
        anchor_new = later_offsets[0] if later_offsets else len(rebuilt)
        for idx, delta in enumerate(layout.get("header_offset_deltas", [])):
            struct.pack_into("<I", rebuilt, 8 + idx * 4, int(anchor_new - delta))
        wrapper_trailer = layout.get("wrapper_trailer", b"")
        if wrapper_trailer and not later_offsets:
            rebuilt.extend(wrapper_trailer)
        tail_field_off = layout.get("tail_field_off")
        if tail_field_off is not None:
            header_offsets = [
                int.from_bytes(rebuilt[8 + idx * 4:12 + idx * 4], "little", signed=False)
                for idx in range(int(layout["outer_count"]))
            ]
            last_header_offset = max(header_offsets) if header_offsets else anchor_new
            tail_span = len(rebuilt) - last_header_offset
            struct.pack_into("<I", rebuilt, tail_field_off, int(tail_span))

        rebuilt_blob = bytes(rebuilt) + taildata_bytes
    elif layout["kind"] == "offsets":
        unique_offsets = layout["unique_offsets"]
        if len(folder_files) != len(unique_offsets):
            raise ValueError(
                f"Subcontainer file count mismatch. Folder has {len(folder_files)} file(s), "
                f"but the original TOC maps to {len(unique_offsets)} unique payload slot(s)."
            )

        prefix_end = unique_offsets[0] if unique_offsets else layout["table_end"]
        rebuilt_prefix = bytearray(original_raw[:prefix_end])
        rebuilt_payload = bytearray()
        new_unique_offsets = []

        cursor = prefix_end
        for file_path in folder_files:
            with open(file_path, "rb") as handle:
                chunk = handle.read()
            new_unique_offsets.append(cursor)
            rebuilt_payload.extend(chunk)
            cursor += len(chunk)

        offset_map = {old_offset: new_offset for old_offset, new_offset in zip(unique_offsets, new_unique_offsets)}
        struct.pack_into("<I", rebuilt_prefix, 0, layout["count"])
        for idx, old_offset in enumerate(layout["offsets"]):
            struct.pack_into("<I", rebuilt_prefix, 4 + idx * 4, offset_map.get(old_offset, old_offset))

        rebuilt_blob = bytes(rebuilt_prefix) + bytes(rebuilt_payload) + taildata_bytes
    elif layout["kind"] == "sequential":
        sizes = layout["sizes"]
        if len(folder_files) != len(sizes):
            raise ValueError(
                f"Subcontainer file count mismatch. Folder has {len(folder_files)} file(s), "
                f"but the original sequential TOC maps to {len(sizes)} slot(s)."
            )

        data_start = int(layout["data_start"])
        pad_len = max(0, data_start - layout["table_end"])
        new_sizes = []
        payload_parts = []
        for file_path in folder_files:
            with open(file_path, "rb") as handle:
                chunk = handle.read()
            payload_parts.append(chunk)
            new_sizes.append(len(chunk))

        rebuilt = bytearray()
        rebuilt.extend(int(layout["count"]).to_bytes(4, "little", signed=False))
        for sz in new_sizes:
            rebuilt.extend(int(sz).to_bytes(4, "little", signed=False))
        if pad_len:
            rebuilt.extend(b"\x00" * pad_len)
        for chunk in payload_parts:
            rebuilt.extend(chunk)
        rebuilt_blob = bytes(rebuilt) + taildata_bytes
    else:
        entries = layout["entries"]
        positive_indices = layout["positive_indices"]
        if len(folder_files) not in (len(positive_indices), len(entries)):
            raise ValueError(
                f"Subcontainer file count mismatch. Folder has {len(folder_files)} file(s), "
                f"but the original pair-table TOC maps to {len(positive_indices)} populated slot(s) "
                f"or {len(entries)} total slot(s)."
            )

        use_all_slots = len(folder_files) == len(entries)
        payload_by_slot = {}

        if use_all_slots:
            slot_indices = list(range(len(entries)))
        else:
            slot_indices = list(positive_indices)

        for slot_idx, file_path in zip(slot_indices, folder_files):
            with open(file_path, "rb") as handle:
                payload_by_slot[slot_idx] = handle.read()

        header_size = 4 + len(entries) * 8
        gap_before = compute_positive_entry_gaps(entries, off_index=0, size_index=1)
        offsets = []
        sizes = []
        previous_end_new: int | None = None
        for idx, (_old_off, old_sz) in enumerate(entries):
            chunk = payload_by_slot.get(idx)
            if chunk is None:
                if old_sz > 0:
                    chunk = b""
                else:
                    chunk = b""
            sz = len(chunk)
            sizes.append(sz)
            if sz > 0:
                off = gap_before.get(idx, header_size) if previous_end_new is None else previous_end_new + gap_before.get(idx, 0)
                offsets.append(off)
                previous_end_new = off + sz
            else:
                offsets.append(0)

        rebuilt = bytearray()
        rebuilt.extend(int(layout["count"]).to_bytes(4, "little", signed=False))
        for off, sz in zip(offsets, sizes):
            rebuilt.extend(int(off).to_bytes(4, "little", signed=False))
            rebuilt.extend(int(sz).to_bytes(4, "little", signed=False))

        if offsets:
            first_positive = next((off for off, sz in zip(offsets, sizes) if sz > 0), 0)
            cur = len(rebuilt)
            if first_positive > cur:
                rebuilt.extend(b"\x00" * (first_positive - cur))

        for idx, chunk in sorted(payload_by_slot.items()):
            sz = len(chunk)
            if sz <= 0:
                continue
            target_off = offsets[idx]
            cur = len(rebuilt)
            if cur < target_off:
                rebuilt.extend(b"\x00" * (target_off - cur))
            rebuilt.extend(chunk)

        rebuilt_blob = bytes(rebuilt) + taildata_bytes

    if output_path is None:
        src_dir = os.path.dirname(original_subcontainer_path)
        src_name = os.path.basename(original_subcontainer_path)
        base, ext = os.path.splitext(src_name)
        output_path = os.path.join(src_dir, f"{base}_rebuilt{ext}")
    output_path = next_available_output_path(output_path)

    with open(output_path, "wb") as handle:
        handle.write(rebuilt_blob)

    return output_path, f"Rebuilt subcontainer with {len(folder_files)} payload(s)."


def normalize_endian(v: str) -> str:
    v = (v or "little").strip().lower()
    if v in ("le", "little", "l"):
        return "little"
    if v in ("be", "big", "b"):
        return "big"
    return "little"


def parse_idx_entry(chunk: bytes, raw_vars, field_size: int, endian: str):
    """
    Interpret one IDX entry chunk using Raw_Variables and field_size
    
    Returns dict: {var_name: int_value}
    """
    values = {}
    if not raw_vars or field_size <= 0:
        return values

    for i, name in enumerate(raw_vars):
        start = i * field_size
        end = start + field_size
        if end > len(chunk):
            break
        field_bytes = chunk[start:end]
        values[name] = int.from_bytes(field_bytes, endian, signed=False)
    return values


def unpack_from_schema(
    schema: GameSchema,
    base_dir: str,
    status_callback=None,
    progress_callback=None,
):
    """
    Unpacker driven by an incode Aldnoah game schema plus a chosen base directory
    """

    def update_status(text, color="blue"):
        if status_callback is not None:
            status_callback(text, color)

    def update_progress(done, total, note=None):
        if progress_callback is not None:
            progress_callback(done, total, note)

    game_name = schema.display_name or schema.game_id
    containers = list(schema.containers)
    idx_files = list(schema.idx_files)
    out_root = schema.unpack_folder or "Unpacked_Files"

    raw_vars = list(schema.raw_variables)
    field_size = int(schema.field_size or 0)
    entry_size_cfg = int(schema.idx_chunk_read or 0)

    entry_size_calc = 0
    if raw_vars and field_size > 0:
        entry_size_calc = len(raw_vars) * field_size

    if isinstance(entry_size_cfg, int) and entry_size_cfg > 0:
        entry_size = entry_size_cfg
    elif entry_size_calc > 0:
        entry_size = entry_size_calc
    else:
        entry_size = 32

    vars_to_shift = list(schema.vars_to_shift or ())

    shift_bits = int(schema.shift_bits or 0)

    # If there is a shift but no explicit list of variables assume Offset-like fields
    if shift_bits is not None and not vars_to_shift and raw_vars:
        lower_map = {name.lower(): name for name in raw_vars}
        auto_targets = [
            orig for key, orig in lower_map.items()
            if "offset" in key
        ]
        if auto_targets:
            vars_to_shift = auto_targets

    if shift_bits is None:
        shift_bits = 0  # PC only, never auto shift like PS2 sectors

    endian = normalize_endian(schema.endian)

    compression_cfg = str(schema.compression or "auto")
    compression_list = [compression_cfg] * max(1, len(idx_files))

    start_from_offset = int(schema.start_from_offset or 0)
    has_start_from = start_from_offset > 0

    if not containers or not idx_files:
        update_status("No containers or IDX files are defined in the selected schema.", "red")
        return

    if not os.path.isdir(out_root):
        os.makedirs(out_root, exist_ok=True)

    update_status(
        f"Unpacking {game_name} (entry size: {entry_size} bytes, schema-driven)",
        "blue",
    )

    # One IDX, multiple containers
    if len(idx_files) == 1 and len(containers) > 1:
        idx_path = os.path.join(base_dir, idx_files[0])
        if not os.path.isfile(idx_path):
            update_status(f"Missing IDX: {idx_path}", "red")
            return

        bin_paths = []
        for c in containers:
            p = os.path.join(base_dir, c)
            if not os.path.isfile(p):
                update_status(f"Missing container: {p}", "red")
            else:
                bin_paths.append(p)

        if not bin_paths:
            update_status("No valid containers found for single-IDX mode.", "red")
            return

        unpack_multi_containers(
            bin_paths,
            idx_path,
            out_root,
            entry_size,
            raw_vars,
            field_size,
            update_status,
            update_progress,
            vars_to_shift,
            shift_bits,
            start_from_offset,
            has_start_from,
            idx_marker=0,
            endian=endian,
            compression_kind=compression_list[0],
        )

    # Normal 1:1 pairing
    elif len(containers) == len(idx_files):
        for pair_index, (bin_name, idx_name) in enumerate(
            zip(containers, idx_files)
        ):
            bin_path = os.path.join(base_dir, bin_name)
            idx_path = os.path.join(base_dir, idx_name)

            if not os.path.isfile(bin_path):
                update_status(f"Missing container: {bin_path}", "red")
                continue
            if not os.path.isfile(idx_path):
                update_status(f"Missing IDX: {idx_path}", "red")
                continue

            pair_out_dir = os.path.join(out_root, f"Pack_{pair_index:02d}")
            os.makedirs(pair_out_dir, exist_ok=True)

            compression_kind = (
                compression_list[pair_index]
                if pair_index < len(compression_list)
                else compression_list[-1]
            )

            unpack_pair(
                bin_path,
                idx_path,
                pair_out_dir,
                entry_size,
                raw_vars,
                field_size,
                update_status,
                update_progress,
                vars_to_shift,
                shift_bits,
                start_from_offset,
                has_start_from,
                idx_marker=pair_index,
                endian=endian,
                compression_kind=compression_kind,
            )

    else:
        update_status(
            f"Unsupported combination: {len(containers)} Containers vs "
            f"{len(idx_files)} IDX_Files.",
            "red",
        )
        return

    update_status(f"Finished unpacking {game_name}.", "green")


def append_taildata(
    out_path: str,
    idx_marker: int,
    entry_off: int,
    comp_marker: int,
    endian: str,
):
    """
    Taildata: 1 byte idx_marker, 4 byte entry_offset (endian from ref), 1 byte compression_marker
    comp_marker: 0x01 only if decompression actually occurred else 0x00
    """
    try:
        with open(out_path, "ab") as f:
            f.write(bytes([idx_marker & 0xFF]))
            f.write(int(entry_off).to_bytes(4, endian, signed=False))
            f.write(bytes([comp_marker & 0xFF]))
    except Exception:
        pass


def unpack_pair(
    bin_path,
    idx_path,
    pair_out_dir,
    entry_size,
    raw_vars,
    field_size,
    update_status,
    update_progress,
    vars_to_shift,
    shift_bits,
    start_from_offset,
    has_start_from,
    *,
    idx_marker: int,
    endian: str,
    compression_kind: str,
):
    """
    Unpack a single BIN/IDX pair
    """

    update_status(f"Reading IDX: {os.path.basename(idx_path)}", "blue")

    with open(idx_path, "rb") as f_idx:
        idx_data_full = f_idx.read()

    if entry_size <= 0:
        update_status("Invalid entry_size, must be > 0.", "red")
        return

    # If Start_From_Offset present use it else use full IDX
    if has_start_from and start_from_offset > 0:
        if start_from_offset >= len(idx_data_full):
            update_status(
                f"Start_From_Offset {start_from_offset} is beyond IDX size "
                f"{len(idx_data_full)}.",
                "red",
            )
            return
        idx_data = idx_data_full[start_from_offset:]
    else:
        idx_data = idx_data_full
        start_from_offset = 0  # important so taildata math stays correct

        if len(idx_data) % entry_size != 0:
            update_status(
                f"Warning: IDX size {len(idx_data)} not a multiple of "
                f"entry_size ({entry_size}).",
                "red",
            )

    total_entries = len(idx_data) // entry_size
    update_status(f"IDX entries: {total_entries}", "blue")

    if update_progress is not None:
        update_progress(
            0,
            total_entries,
            f"{os.path.basename(bin_path)}: starting…",
        )

    compression_kind = str(compression_kind or "auto").lower()

    with open(bin_path, "rb") as f_bin:
        mm = mmap.mmap(f_bin.fileno(), 0, access=mmap.ACCESS_READ)
        try:
            file_index = 0

            for i in range(total_entries):
                start = i * entry_size
                end = start + entry_size
                chunk = idx_data[start:end]
                if len(chunk) < entry_size:
                    continue

                vals = parse_idx_entry(chunk, raw_vars, field_size, endian)

                if shift_bits:
                    for name in vars_to_shift:
                        if name in vals:
                            vals[name] = vals[name] << shift_bits

                offset = vals.get("Offset", 0)
                original_sz = vals.get("Original_Size", vals.get("Full_Size", 0))
                compressed_sz = vals.get("Compressed_Size", 0)
                flag = vals.get("Compression_Marker", 0)

                if original_sz == 0 and compressed_sz == 0:
                    # genuine dummy
                    continue

                # PC only size_to_read selection
                if compressed_sz == 0:
                    # Skip non-physical entries
                    continue

                size_to_read = original_sz
                if compressed_sz > 0 and flag == 1:
                    size_to_read = compressed_sz

                if size_to_read <= 0:
                    continue

                if offset + size_to_read > len(mm):
                    update_status(
                        f"Entry {i} out of range "
                        f"(offset=0x{offset:X}, size=0x{size_to_read:X}) "
                        f"in {os.path.basename(bin_path)}; skipping.",
                        "red",
                    )
                    continue

                raw = mm[offset:offset + size_to_read]

                data = raw
                ext_hint = None
                used_raw = False
                raw_error = None
                did_decompress = False

                # PC compressed (flag==1)
                if compressed_sz > 0 and flag == 1:
                    try:
                        # If explicitly says split force split first
                        if compression_kind in ("zlib_split", "omega_split"):
                            try:
                                data, ext_hint = decompress_split_zlib_streams(raw)
                                did_decompress = True
                            except Exception:
                                # fallback to omega zlib_header
                                data = codec_decompress(raw, "zlib_header")
                                did_decompress = True

                        # If ref says zlib_header/zlib/auto, allow mixed PC behavior:
                        # split if it structurally looks like split else header
                        elif compression_kind in (
                            "zlib_header",
                            "ozlib",
                            "omega_zlib",
                            "zlib",
                            "auto",
                            "pc_mixed",
                        ):
                            if looks_like_split_zlib(raw):
                                try:
                                    data, ext_hint = decompress_split_zlib_streams(raw)
                                    did_decompress = True
                                except Exception:
                                    data = codec_decompress(raw, "zlib_header")
                                    did_decompress = True
                            else:
                                data = codec_decompress(raw, "zlib_header")
                                did_decompress = True

                        # none/raw means really don't decompress
                        elif compression_kind in ("none", "raw"):
                            data = raw

                        # Any other explicit kind (lzma/gzip/etc)
                        else:
                            data = codec_decompress(raw, compression_kind)
                            did_decompress = True

                    except Exception as e:
                        used_raw = True
                        raw_error = (
                            f"{compression_kind} decompress failed at IDX entry {i} "
                            f"(BIN={os.path.basename(bin_path)}, "
                            f"offset=0x{offset:X}, size=0x{size_to_read:X}): {e}"
                        )
                        data = raw

                else:
                    # Uncompressed/non-flagged entries

                    # Some PC split-zlib containers are not flagged as compressed
                    if compression_kind in (
                        "zlib_split",
                        "omega_split",
                        "zlib_header",
                        "ozlib",
                        "omega_zlib",
                        "zlib",
                        "auto",
                        "pc_mixed",
                    ) and looks_like_split_zlib(raw):
                        try:
                            data, ext_hint = decompress_split_zlib_streams(raw)
                            did_decompress = True
                        except Exception as e:
                            used_raw = True
                            raw_error = (
                                f"split-zlib fallback failed at IDX entry {i} "
                                f"(BIN={os.path.basename(bin_path)}, "
                                f"offset=0x{offset:X}, size=0x{size_to_read:X}): {e}"
                            )
                            data = raw

                ext = detect_ext(data)

                if ext == ".bin" and ext_hint:
                    if ext_hint == ".g1m" and data.startswith(b"\x5F\x4D\x31\x47"):
                        ext = ".g1m"
                    elif ext_hint == ".g1t" and data[:3] == b"GT1":
                        ext = ".g1t"
                    else:
                        ext = ".bin"

                out_name = f"entry_{file_index:05d}{ext}"
                out_path = os.path.join(pair_out_dir, out_name)

                with open(out_path, "wb") as fout:
                    fout.write(data)

                # Taildata wants the absolute entry offset in the IDX file
                entry_off_abs = start_from_offset + start
                append_taildata(
                    out_path,
                    idx_marker,
                    entry_off_abs,
                    1 if did_decompress else 0,
                    endian,
                )

                if ext == ".kvs":
                    unpack_kvs(out_path, blob=data)
                else:
                    unpack_nested_resource(out_path, blob=data)

                file_index += 1

                if used_raw and raw_error:
                    msg = f"{raw_error}; wrote raw to {out_name}"
                    log_root = os.path.dirname(pair_out_dir)
                    log_comp_failure(log_root, msg)

                if update_progress is not None:
                    if (i & 31) == 0 or i + 1 == total_entries:
                        update_progress(
                            i + 1,
                            total_entries,
                            f"{os.path.basename(bin_path)}: "
                            f"{i + 1}/{total_entries}",
                        )
        finally:
            mm.close()

    update_status(
        f"Unpacked {total_entries} IDX entries from {os.path.basename(bin_path)}",
        "green",
    )


def unpack_multi_containers(
    bin_paths,
    idx_path,
    out_root,
    entry_size,
    raw_vars,
    field_size,
    update_status,
    update_progress,
    vars_to_shift,
    shift_bits,
    start_from_offset,
    has_start_from,
    *,
    idx_marker: int,
    endian: str,
    compression_kind: str,
):
    """
    Single IDX describing data spread across multiple containers
    Taildata is appended to each output file
    """

    if not bin_paths:
        update_status("No container paths provided for multi-container unpack.", "red")
        return

    update_status(
        f"Reading IDX (multi-container mode): {os.path.basename(idx_path)}",
        "blue",
    )

    with open(idx_path, "rb") as f_idx:
        idx_data_full = f_idx.read()

    if entry_size <= 0:
        update_status("Invalid entry_size; must be > 0.", "red")
        return

    if has_start_from and start_from_offset > 0:
        if start_from_offset >= len(idx_data_full):
            update_status(
                f"Start_From_Offset {start_from_offset} is beyond IDX size "
                f"{len(idx_data_full)}.",
                "red",
            )
            return
        idx_data = idx_data_full[start_from_offset:]
    else:
        idx_data = idx_data_full
        start_from_offset = 0

        if len(idx_data) % entry_size != 0:
            update_status(
                f"Warning: IDX size {len(idx_data)} not a multiple of "
                f"entry_size ({entry_size}).",
                "red",
            )

    total_entries = len(idx_data) // entry_size
    update_status(f"IDX entries: {total_entries}", "blue")

    if update_progress is not None:
        update_progress(0, total_entries, "Multi-container IDX: starting…")

    compression_kind = str(compression_kind or "auto").lower()

    # map all containers
    bin_files = []
    bin_maps = []
    bin_sizes = []
    for p in bin_paths:
        try:
            f = open(p, "rb")
            mm = mmap.mmap(f.fileno(), 0, access=mmap.ACCESS_READ)
        except OSError:
            update_status(f"Could not open or mmap container: {p}", "red")
            continue
        bin_files.append(f)
        bin_maps.append(mm)
        bin_sizes.append(len(mm))

    if not bin_files:
        update_status(
            "Failed to open any containers for multi-container unpack.", "red"
        )
        return

    container_counts = [0] * len(bin_files)
    current_idx = 0
    current_map = bin_maps[current_idx]
    current_size = bin_sizes[current_idx]
    def advance_container():
        nonlocal current_idx, current_map, current_size
        if current_idx + 1 >= len(bin_maps):
            return False
        current_idx += 1
        current_map = bin_maps[current_idx]
        current_size = bin_sizes[current_idx]
        update_status(
            f"Switching to next container [{current_idx}/{len(bin_maps) - 1}]: "
            f"{os.path.basename(bin_paths[current_idx])}",
            "blue",
        )
        return True

    try:
        for i in range(total_entries):
            start = i * entry_size
            end = start + entry_size
            chunk = idx_data[start:end]
            if len(chunk) < entry_size:
                continue

            vals = parse_idx_entry(chunk, raw_vars, field_size, endian)

            if shift_bits:
                for name in vars_to_shift:
                    if name in vals:
                        vals[name] = vals[name] << shift_bits

            offset = vals.get("Offset", 0)
            original_sz = vals.get("Original_Size", vals.get("Full_Size", 0))
            compressed_sz = vals.get("Compressed_Size", 0)
            flag = vals.get("Compression_Marker", 0)

            if offset == 0 and container_counts[current_idx] > 0:
                if not advance_container():
                    update_status(
                        f"Entry {i} resets to offset 0, but there is no next "
                        f"container available; skipping.",
                        "red",
                    )
                    continue

            if original_sz == 0 and compressed_sz == 0:
                continue

            # PC only size_to_read selection
            if compressed_sz == 0:
                continue

            size_to_read = original_sz
            if compressed_sz > 0 and flag == 1:
                size_to_read = compressed_sz

            if size_to_read <= 0:
                continue

            while offset + size_to_read > current_size:
                if not advance_container():
                    update_status(
                        f"Entry {i} (offset {offset}, size {size_to_read}) "
                        f"does not fit in remaining containers; skipping.",
                        "red",
                    )
                    size_to_read = 0
                    break
            if size_to_read <= 0:
                continue

            if offset + size_to_read > current_size:
                update_status(
                    f"Entry {i} out of range in "
                    f"{os.path.basename(bin_paths[current_idx])} "
                    f"(offset=0x{offset:X}, size=0x{size_to_read:X}); skipping.",
                    "red",
                )
                continue

            raw = current_map[offset:offset + size_to_read]
            data = raw
            ext_hint = None
            used_raw = False
            raw_error = None
            did_decompress = False

            # PC compressed (flag==1)
            if compressed_sz > 0 and flag == 1:
                try:
                    if compression_kind in ("zlib_split", "omega_split"):
                        try:
                            data, ext_hint = decompress_split_zlib_streams(raw)
                            did_decompress = True
                        except Exception:
                            data = codec_decompress(raw, "zlib_header")
                            did_decompress = True

                    elif compression_kind in (
                        "zlib_header",
                        "ozlib",
                        "omega_zlib",
                        "zlib",
                        "auto",
                        "pc_mixed",
                    ):
                        if looks_like_split_zlib(raw):
                            try:
                                data, ext_hint = decompress_split_zlib_streams(raw)
                                did_decompress = True
                            except Exception:
                                data = codec_decompress(raw, "zlib_header")
                                did_decompress = True
                        else:
                            data = codec_decompress(raw, "zlib_header")
                            did_decompress = True

                    elif compression_kind in ("none", "raw"):
                        data = raw

                    else:
                        data = codec_decompress(raw, compression_kind)
                        did_decompress = True

                except Exception as e:
                    used_raw = True
                    raw_error = (
                        f"{compression_kind} decompress failed at IDX entry {i} "
                        f"(BIN={os.path.basename(bin_paths[current_idx])}, "
                        f"offset=0x{offset:X}, size=0x{size_to_read:X}): {e}"
                    )
                    data = raw
            else:
                # Uncompressed/non-flagged entries

                if compression_kind in (
                    "zlib_split",
                    "omega_split",
                    "zlib_header",
                    "ozlib",
                    "omega_zlib",
                    "zlib",
                    "auto",
                    "pc_mixed",
                ) and looks_like_split_zlib(raw):
                    try:
                        data, ext_hint = decompress_split_zlib_streams(raw)
                        did_decompress = True
                    except Exception as e:
                        used_raw = True
                        raw_error = (
                            f"split-zlib fallback failed at IDX entry {i} "
                            f"(BIN={os.path.basename(bin_paths[current_idx])}, "
                            f"offset=0x{offset:X}, size=0x{size_to_read:X}): {e}"
                        )
                        data = raw

            ext = detect_ext(data)

            if ext == ".bin" and ext_hint:
                if ext_hint == ".g1m" and data.startswith(b"\x5F\x4D\x31\x47"):
                    ext = ".g1m"
                elif ext_hint == ".g1t" and data[:3] == b"GT1":
                    ext = ".g1t"
                else:
                    ext = ".bin"

            container_out_dir = os.path.join(out_root, f"Pack_{current_idx:02d}")
            if not os.path.isdir(container_out_dir):
                os.makedirs(container_out_dir, exist_ok=True)

            local_index = container_counts[current_idx]
            out_name = f"entry_{local_index:05d}{ext}"
            out_path = os.path.join(container_out_dir, out_name)

            with open(out_path, "wb") as fout:
                fout.write(data)

            # taildata, absolute IDX entry offset
            entry_off_abs = start_from_offset + start
            append_taildata(
                out_path,
                current_idx,
                entry_off_abs,
                1 if did_decompress else 0,
                endian,
            )

            if ext == ".kvs":
                unpack_kvs(out_path, blob=data)
            else:
                unpack_nested_resource(out_path, blob=data)

            container_counts[current_idx] += 1

            if used_raw and raw_error:
                msg = (
                    f"{raw_error}; wrote raw to Pack_{current_idx:02d}/{out_name}"
                )
                log_comp_failure(out_root, msg)

            if update_progress is not None:
                if (i & 31) == 0 or i + 1 == total_entries:
                    update_progress(
                        i + 1,
                        total_entries,
                        f"Multi-container: {i + 1}/{total_entries}",
                    )

    finally:
        for mm in bin_maps:
            try:
                mm.close()
            except Exception:
                pass
        for f in bin_files:
            try:
                f.close()
            except Exception:
                pass

    update_status(
        f"Unpacked {total_entries} IDX entries across {len(bin_files)} containers.",
        "green",
    )


def detect_ext(data: bytes) -> str:
    """Best effort extension guess from magic bytes"""
    if not data:
        return ".bin"

    head = data[:64]
    head4 = head[:4]
    head3 = head[:3]
    head2 = head[:2]

    ext = EXT4.get(head4)
    if ext:
        if ext == ".riff":
            return ".wav" if b"WAVEfmt" in head else ".riff"
        return ext

    ext = EXT3.get(head3)
    if ext:
        return ext

    ext = EXT2.get(head2)
    if ext:
        return ext

    if head.startswith(b"\x89PNG\r\n\x1a\n"):
        return ".png"
    if b"JFIF" in head:
        return ".jpg"
    if head.startswith(b"TIM2") or b"TIM2" in head or head4 == b"\x00\x20\xAF\x30":
        return ".tm2"
    if data.startswith(b"SShd"):
        return ".ss2"
    if data.startswith(b"SSbd"):
        return ".ss2bd"
    if data.startswith(b"IECSsreV"):
        return ".vagbank"
    if head.startswith(b"[glo"):
        return ".ini"
    if head4 == b"\x58\x4B\x4D":
        return ".xkm"
    if head4 == b"\x45\x4D\x06\x00":
        return ".EM"

    return ".bin"
def unpack_kvs(path: str, blob: bytes | None = None) -> None:
    unpack_nested_resource(path, blob=blob)
