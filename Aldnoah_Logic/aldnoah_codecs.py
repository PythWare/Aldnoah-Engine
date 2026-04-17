"""
aldnoah_codecs.py

Central compression/decompression hub for Aldnoah Engine

Supported kinds (case-insensitive):

zlib: Plain zlib stream (no extra header)
zlib_header: Omega-style zlib: 4 byte compressed_size + zlib stream
zlib_split: Omega-style split zlib stream container (G1M/G1T, etc)
lzma: Standard Python lzma stream
gzip: Standard gzip stream
none/raw: No compression, returns input as is
"""

import zlib, lzma, gzip
from typing import Optional


# Helpers for split zlib stream containers (G1M/G1T etc)

def u16_le(buf: bytes, off: int) -> int:
    return buf[off] | (buf[off + 1] << 8)


def u32_le(buf: bytes, off: int) -> int:
    return (
        buf[off]
        | (buf[off + 1] << 8)
        | (buf[off + 2] << 16)
        | (buf[off + 3] << 24)
    )


def align_up(value: int, alignment: int) -> int:
    return (value + (alignment - 1)) & ~(alignment - 1)


def decompress_omega_zlib_anywhere(blob: bytes) -> bytes:
    """
    Decompress an Omega-style zlib_header block that may be located
    anywhere inside the given blob

    Normal layout at the true location:
        4 byte compressed_size, zlib stream

    Plan:
         Try legacy behavior, assume header is at offset 0
      
         If that fails, scan for a valid zlib header (0x78 xx with correct FLG)
         and if found use the 4 bytes immediately before it as compressed_size
         
         If the size based attempt fails, as a last resort try zlib.decompress()
         from that header until EOF
    """
    n = len(blob)

    # Legacy case, header at offset 0
    if n >= 6:
        size0 = int.from_bytes(blob[0:4], "little")
        if size0 > 0 and 4 + size0 <= n:
            comp0 = blob[4:4 + size0]
            try:
                return zlib.decompress(comp0)
            except Exception:
                # fall back to scanning
                pass

    # Scan for an internal zlib header
    # Valid zlib headers: cmf=0x78 and (cmf<<8 | flg) % 31 == 0
    for i in range(0, n - 1):
        if blob[i] != 0x78:
            continue
        cmf = blob[i]
        flg = blob[i + 1]
        if ((cmf << 8) | flg) % 31 != 0:
            continue  # not a valid zlib header

        # a plausible zlib header at offset i

        # If there are 4 bytes right before it treat them as compressed size
        if i >= 4:
            size = int.from_bytes(blob[i - 4:i], "little")
            if size > 0 and i + size <= n:
                comp = blob[i:i + size]
                try:
                    return zlib.decompress(comp)
                except Exception:
                    # fall back to trying until end
                    pass

        # As a fallback, try decompressing from this header to the end
        try:
            return zlib.decompress(blob[i:])
        except Exception:
            # Not a real stream, keep scanning
            continue

    raise ValueError("Could not find a valid Omega-style zlib_header stream in blob")


# file_type at 0x02, extension for merged file
SPLIT_FILE_TYPE_EXT = {
    0x0001: ".g1m",
    0x0010: ".g1t",
}


# Core API

def decompress(data: bytes, kind: str) -> bytes:
    """
    Generic decompression entry point

    data : bytes blob (exact bytes from the container)
    
    kind : one of:
        zlib
        zlib_header (4 byte size + zlib)
        zlib_split/omega_split
        lzma
        gzip
        none/raw

    Returns: decompressed bytes
    """
    k = kind.lower()

    if k == "zlib":
        # data is a raw zlib stream, header/deflate
        return zlib.decompress(data)

    elif k in ("zlib_split", "omega_split"):
        merged, _ = decompress_split_zlib_streams(data)
        return merged

    elif k in ("zlib_header", "ozlib", "omega_zlib"):
        return decompress_omega_zlib_anywhere(data)

    elif k == "lzma":
        return lzma.decompress(data)

    elif k in ("gzip", "gz"):
        return gzip.decompress(data)

    elif k in ("none", "raw"):
        return data

    else:
        raise ValueError(f"Unsupported compression kind (PC only build): {kind}")


def compress(
    data: bytes,
    kind: str,
    *,
    zlib_level: Optional[int] = None,
) -> bytes:
    """
    Generic compression entry point

    data : bytes to compress
    kind : one of:
        zlib
        zlib_header
        lzma
        gzip
        none/raw

    zlib_level: optional zlib compression level (0-9) for zlib kinds

    Returns: bytes suitable to write back into container
    """
    k = kind.lower()

    if k == "zlib":
        if zlib_level is None:
            return zlib.compress(data)
        return zlib.compress(data, level=zlib_level)

    elif k in ("zlib_header", "ozlib", "omega_zlib"):
        if zlib_level is None:
            z_stream = zlib.compress(data)
        else:
            z_stream = zlib.compress(data, level=zlib_level)

        comp_size = len(z_stream)
        header = comp_size.to_bytes(4, "little")
        return header + z_stream

    elif k == "lzma":
        return lzma.compress(data)

    elif k in ("gzip", "gz"):
        return gzip.compress(data)

    elif k in ("none", "raw"):
        return data

    else:
        raise ValueError(f"Unsupported compression kind (PC-only build): {kind}")


# Simple auto detect

def decompress_auto(data: bytes) -> bytes:
    """
    Best effort auto detect based on magic/header

    Heuristics:
    gzip magic (1F 8B)
    zlib_header: looks like little endian size + zlib header at offset 4
    zlib: looks like a zlib header at offset 0
    """
    # GZIP
    if data[:2] == b"\x1f\x8b":
        return decompress(data, "gzip")

    # Try zlib_header, 4 bytes length + zlib header (78 xx, etc)
    if len(data) > 6:
        size = int.from_bytes(data[0:4], "little")
        if size > 0 and 4 + size <= len(data):
            # 2 byte zlib header at offset 4
            z0, z1 = data[4], data[5]
            if (z0 & 0x0f) == 8:  # compression method = Deflaete
                try:
                    return decompress(data, "zlib_header")
                except Exception:
                    pass

    # Try plain zlib
    try:
        return decompress(data, "zlib")
    except Exception:
        pass

    # Fallback, raw
    return data


def decompress_classic_split_zlib_streams(data: bytes) -> tuple[bytes, str]:
    """
    Omega-style split zlib stream format used for large G1M/G1T/etc assets

    Layout:
      00-01 : unk0
      02-03 : file_type (0x0001 = G1M, 0x0010 = G1T, others unknown => .bin)
      04-05 : chunk_count (number of compressed zlib chunks)
      06-07 : unk1
      08-0B : total_uncompressed_size (sum of all chunks, merged)

      0C-onward : chunk_count * 4-byte chunk_sizes
              each chunk_size = 4 + inner_zlib_size

      Then padding with 0x00 until next 0x80 boundary
      
      Then for each chunk i:

        4 byte inner_size_i + inner_size_i bytes of zlib stream
        next chunk starts at align_up(end_i, 0x80)

    Returns:
      (merged_bytes, extension_str)
    """
    if len(data) < 0x0C:
        raise ValueError("split zlib stream: data too small for header")

    _ = u16_le(data, 0x00)  # unk0
    file_type   = u16_le(data, 0x02)
    chunk_count = u16_le(data, 0x04)
    _ = u16_le(data, 0x06)  # unk1
    total_unc   = u32_le(data, 0x08)

    if chunk_count <= 0:
        raise ValueError(f"split zlib stream: invalid chunk_count={chunk_count}")

    header_end = 0x0C + 4 * chunk_count
    if header_end > len(data):
        raise ValueError("split zlib stream: truncated size table")

    sizes = []
    off = 0x0C
    for _ in range(chunk_count):
        sizes.append(u32_le(data, off))
        off += 4

    ptr = align_up(header_end, 0x80)

    merged = bytearray()
    for idx, chunk_size in enumerate(sizes):
        if ptr + 4 > len(data):
            raise ValueError(f"split zlib stream: EOF before chunk {idx} size")

        inner_size = u32_le(data, ptr)
        if inner_size + 4 != chunk_size:
            # Not fatal just suspicious
            pass

        data_start = ptr + 4
        data_end = data_start + inner_size
        if data_end > len(data):
            raise ValueError(f"split zlib stream: truncated chunk {idx}")

        comp_stream = data[data_start:data_end]

        try:
            decomp = zlib.decompress(comp_stream)
        except zlib.error as e:
            raise ValueError(f"split zlib stream: zlib error on chunk {idx}: {e}")

        merged.extend(decomp)

        # next chunk
        ptr = align_up(data_end, 0x80)

    if total_unc and len(merged) != total_unc:
        # Not fatal but worth noting
        pass

    ext = SPLIT_FILE_TYPE_EXT.get(file_type, ".bin")
    return bytes(merged), ext


def read_pairtable_split_zlib_wrapper(data: bytes, *, max_count: int = 4096):
    if len(data) < 20:
        return None

    count = u32_le(data, 0x00)
    if count < 2 or count > max_count:
        return None

    table_end = 4 + count * 8
    if table_end > len(data):
        return None

    entries = []
    previous_end = table_end
    for index in range(count):
        ent_off = 4 + index * 8
        payload_off = u32_le(data, ent_off)
        payload_size = u32_le(data, ent_off + 4)
        if payload_size <= 0:
            return None
        if payload_off < table_end or payload_off + payload_size > len(data):
            return None
        if payload_off != previous_end:
            return None
        entries.append((payload_off, payload_size))
        previous_end = payload_off + payload_size

    tail_len = len(data) - previous_end
    if tail_len not in (0, 6):
        return None

    return entries


def decompress_pairtable_split_zlib_wrapper(data: bytes) -> tuple[bytes, str]:
    """
    Variation seen in some PC bins where the outer blob is a contiguous pairtable
    of normal split-zlib members, each payload is decompressed with the classic
    splitter and the results are concatenated in entry order
    """
    entries = read_pairtable_split_zlib_wrapper(data)
    if not entries:
        raise ValueError("pairtable split-zlib wrapper: structure did not match")

    merged = bytearray()
    exts = []
    for index, (payload_off, payload_size) in enumerate(entries):
        payload = data[payload_off:payload_off + payload_size]
        try:
            inner_merged, inner_ext = decompress_classic_split_zlib_streams(payload)
        except Exception as exc:
            raise ValueError(f"pairtable split-zlib wrapper: payload {index} is not a classic split-zlib member: {exc}") from exc
        merged.extend(inner_merged)
        exts.append(inner_ext)

    non_bin_exts = [ext for ext in exts if ext != ".bin"]
    ext = non_bin_exts[0] if non_bin_exts else (exts[0] if exts else ".bin")
    return bytes(merged), ext


def decompress_split_zlib_streams(data: bytes) -> tuple[bytes, str]:
    """
    Additive split-zlib entry point

    The classic Omega chunked layout remains the primary path, if that fails
    try the rarer contiguous pairtable wrapper that stores several classic
    split-zlib members back to back
    """
    classic_error: Exception | None = None
    try:
        return decompress_classic_split_zlib_streams(data)
    except Exception as exc:
        classic_error = exc

    try:
        return decompress_pairtable_split_zlib_wrapper(data)
    except Exception as wrapper_error:
        if classic_error is not None:
            raise ValueError(f"classic split-zlib failed: {classic_error}; wrapper split-zlib failed: {wrapper_error}") from wrapper_error
        raise
