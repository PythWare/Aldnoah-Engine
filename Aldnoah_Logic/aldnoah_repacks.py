# Aldnoah_Logic/aldnoah_repacks.py

import os, mmap, re

def _align_up(value: int, alignment: int = 16) -> int:
    """
    Align value upwards to the next multiple of alignment (default 16)
    """
    return (value + (alignment - 1)) & ~(alignment - 1)


# Natural numeric sort for chunk filenames like 0.kvs/00000.kvs/entry_00000.kvs, etc
# Ensures repack order matches the original sequential unpack order even when digit widths vary
_NUM_RE = re.compile(r"(\d+)")

def _natural_kvs_sort_key(name: str):
    stem = os.path.splitext(name)[0]
    nums = _NUM_RE.findall(stem)
    if nums:
        # Use the last numeric group in the stem (handles prefixes like entry_00012)
        try:
            num = int(nums[-1])
        except ValueError:
            num = None
        return (0, num, stem.lower(), name.lower())
    return (1, stem.lower(), name.lower())

def repack_from_folder(
    folder_path: str,
    base_file_path: str | None = None,
    status_callback=None,
    progress_callback=None,
) -> str | None:
    """
    Entry point for GUI:

    Examine the selected folder
    If it contains any .kvs files, treat it as a KVS-chunk folder and
      repack to a single sequential .kvs container
      
    Otherwise, treat it as a g1pack1/g1pack2 folder and repack accordingly (.g1pack1 or .g1pack2)

    If base_file_path is provided, read its last 6 bytes as taildata and
      append those 6 bytes to the repacked output file (for mod manager use)

    Returns the output file path, or None on failure
    """

    def status(msg: str, color: str = "blue"):
        if status_callback is not None:
            status_callback(msg, color)

    def progress(done: int, total: int, note: str | None = None):
        if progress_callback is not None:
            progress_callback(done, total, note or "Repacking")

    folder_path = os.path.abspath(folder_path)
    if not os.path.isdir(folder_path):
        status(f"Selected path is not a folder: {folder_path}", "red")
        return None

    base_name = os.path.basename(folder_path)
    parent_dir = os.path.dirname(folder_path)

    # Collect files in folder (no recursion)
    all_files = [
        f for f in os.listdir(folder_path)
        if os.path.isfile(os.path.join(folder_path, f))
    ]

    if not all_files:
        status(f"No files found in folder: {folder_path}", "red")
        return None

    # Read taildata (last 6 bytes) from base file if provided
    taildata: bytes | None = None
    if base_file_path:
        base_file_path = os.path.abspath(base_file_path)
        try:
            with open(base_file_path, "rb") as bf:
                bf.seek(0, os.SEEK_END)
                size = bf.tell()
                if size >= 6:
                    bf.seek(size - 6)
                    taildata = bf.read(6)
                else:
                    status(
                        f"Base file too small for 6 byte taildata: {base_file_path}",
                        "red",
                    )
        except OSError as e:
            status(f"Could not open base file for taildata: {e}", "red")

    # Decide type:
    # presence of .kvs files => KVS repack
    # otherwise: choose g1pack1 vs g1pack2 based on base_file_path extension if provided,
    # or by checking for a sibling original file in parent_dir with the same basename
    kvs_files = [f for f in all_files if f.lower().endswith(".kvs")]

    if kvs_files:
        status(f"Detected KVS chunk folder: {base_name}", "blue")
        out_path = os.path.join(parent_dir, f"{base_name}.kvs")
        return _repack_kvs_folder(
            folder_path,
            kvs_files,
            out_path,
            status,
            progress,
            taildata,
        )
    else:
        desired_ext: str | None = None

        if base_file_path:
            low = base_file_path.lower()
            if low.endswith(".g1pack1"):
                desired_ext = ".g1pack1"
            elif low.endswith(".g1pack2"):
                desired_ext = ".g1pack2"

        if desired_ext is None:
            # If an original file exists next to the folder, prefer its extension
            if os.path.isfile(os.path.join(parent_dir, f"{base_name}.g1pack1")):
                desired_ext = ".g1pack1"
            else:
                desired_ext = ".g1pack2"

        if desired_ext == ".g1pack1":
            status(f"Detected g1pack1 folder: {base_name}", "blue")
            out_path = os.path.join(parent_dir, f"{base_name}.g1pack1")
            return _repack_g1pack1_folder(
                folder_path,
                all_files,
                out_path,
                status,
                progress,
                taildata,
                base_file_path,
            )
        else:
            status(f"Detected g1pack2 folder: {base_name}", "blue")
            out_path = os.path.join(parent_dir, f"{base_name}.g1pack2")
            return _repack_g1pack2_folder(
                folder_path,
                all_files,
                out_path,
                status,
                progress,
                taildata,
            )

def _repack_kvs_folder(
    folder_path: str,
    kvs_files: list[str],
    out_path: str,
    status,
    progress,
    taildata: bytes | None = None,
) -> str | None:
    """
    Repack a folder of KOVS chunks (*.kvs) into a single sequential KVS container

    For each input file:
    
      Expect b"KOVS" at the start and at least 32 bytes header
      Read size from bytes 4-7
      Write header (32 bytes) + size bytes of data
      Then pad with 0x00 until the end of that chunk is 16 byte aligned

    After all chunks are written append 6-byte taildata if provided
    """

    # Stable order: natural numeric sort (works for 0.kvs, 00000.kvs, entry_00000.kvs, etc)
    kvs_files = sorted(kvs_files, key=_natural_kvs_sort_key)
    total = len(kvs_files)
    if total == 0:
        status("No .kvs files inside folder to repack.", "red")
        return None

    status(f"Repacking {total} KOVS chunks into {os.path.basename(out_path)}", "blue")

    try:
        with open(out_path, "wb") as out_f:
            for idx, name in enumerate(kvs_files):
                in_path = os.path.join(folder_path, name)
                try:
                    with open(in_path, "rb") as fin:
                        blob = fin.read()
                except OSError:
                    status(f"Could not read {name}, skipping.", "red")
                    continue

                if len(blob) < 32 or not blob.startswith(b"KOVS"):
                    status(f"{name} is not a valid KOVS file, skipping.", "red")
                    continue

                size = int.from_bytes(blob[4:8], "little", signed=False)
                if size <= 0:
                    status(f"{name} has non-positive data size, skipping.", "red")
                    continue

                data_start = 32
                data_end = data_start + size
                if data_end > len(blob):
                    # Clamp to available data, but warn.
                    status(
                        f"{name}: header size exceeds file length, clamping.",
                        "red",
                    )
                    data_end = len(blob)

                # Write KOVS header + data (no trailing pad from source file)
                chunk = blob[:data_end]
                out_f.write(chunk)

                # Pad up to 16 byte boundary
                cur_pos = out_f.tell()
                pad_len = (-cur_pos) % 16
                if pad_len:
                    out_f.write(b"\x00" * pad_len)

                if progress is not None:
                    progress(
                        idx + 1,
                        total,
                        f"KVS repack: {idx + 1}/{total}",
                    )

            # After all KOVS chunks, append taildata if present
            if taildata and len(taildata) == 6:
                out_f.write(taildata)

        status(f"KVS repack complete: {out_path}", "green")
        return out_path

    except OSError as e:
        status(f"Error writing KVS file: {e}", "red")
        return None


def _natural_entry_sort_key(name: str):
    """Natural numeric sort for g1pack inner files like 000.dds, entry_00012.bin, etc"""
    stem = os.path.splitext(name)[0]
    nums = _NUM_RE.findall(stem)
    if nums:
        try:
            num = int(nums[0]) if stem[:1].isdigit() else int(nums[-1])
        except ValueError:
            num = None
        return (0, num, stem.lower(), name.lower())
    return (1, stem.lower(), name.lower())

def _infer_g1pack1_alignment_from_base(base_blob: bytes) -> int | None:
    """Try to infer how the original g1pack1 positioned its data_start after the size-only TOC"""
    try:
        if len(base_blob) < 8:
            return None
        count = int.from_bytes(base_blob[0:4], "little", signed=False)
        if count <= 0 or count > 200000:
            return None
        toc_end = 4 + count * 4
        if toc_end > len(base_blob):
            return None
        sizes = [
            int.from_bytes(base_blob[4 + i * 4: 8 + i * 4], "little", signed=False)
            for i in range(count)
        ]

        def _choose_data_start(blob: bytes, toc_end_: int, sizes_: list[int]) -> int:
            # Copied from unpacker logic: best effort to pick data start even if first file begins with zeros
            need = sum(sizes_)
            n = len(blob)
            if toc_end_ + need > n:
                return toc_end_

            candidates = [toc_end_]
            scan_limit = min(n, toc_end_ + 0x4000)
            for off in range(toc_end_, scan_limit, 4):
                if off + 4 > n:
                    break
                if blob[off:off + 4] != b"\x00\x00\x00\x00":
                    candidates.append(off)
                    break

            best = toc_end_
            best_score = -1
            for cand in candidates:
                if cand < toc_end_:
                    continue
                if cand + need > n:
                    continue
                score = 0
                cur = cand
                for sz in sizes_[:min(6, len(sizes_))]:
                    if sz <= 0 or cur + sz > n:
                        break
                    try:
                        # Local import to avoid circular import at module load time
                        from .aldnoah_unpack import detect_ext
                        ext = detect_ext(blob[cur:cur + min(sz, 256)])
                    except Exception:
                        ext = ".bin"
                    if ext != ".bin":
                        score += 1
                    cur += sz
                if score > best_score:
                    best_score = score
                    best = cand
            return best

        data_start = _choose_data_start(base_blob, toc_end, sizes)

        # Find the smallest power-of-two alignment that explains base_data_start as align_up(base_toc_end, alignment)
        for a in (4, 8, 16, 32, 64, 128, 256, 512, 1024, 2048, 4096):
            if _align_up(toc_end, a) == data_start:
                return a

        # Fallback: respect common alignment if it at least matches divisibility
        if data_start % 16 == 0:
            return 16
        if data_start % 4 == 0:
            return 4
        return None
    except Exception:
        return None

def _repack_g1pack1_folder(
    folder_path: str,
    all_files: list[str],
    out_path: str,
    status,
    progress,
    taildata: bytes | None = None,
    base_file_path: str | None = None,
) -> str | None:
    """
    Repack a folder of loose files into a g1pack1-style subcontainer.

    g1pack1 layout (little endian):
      00-03 : file count (N)
      04-onward : N dwords: absolute size of file i (no offsets)
      padding (optional, usually zero dwords)
      data: N files stored sequentially, exactly as per sizes in TOC

    Notes:
      We do not insert per-file alignment padding between inner files (sizes define boundaries)
      We optionally preserve the original data start alignment if base_file_path is provided
      After all data is written, append 6 byte taildata if provided (for mod manager use)
    """

    # Filter to regular files only, sort naturally so 000.* comes before 010.* etc
    files = [f for f in all_files if os.path.isfile(os.path.join(folder_path, f))]
    files = sorted(files, key=_natural_entry_sort_key)
    total = len(files)
    if total == 0:
        status("No files found to repack into g1pack1.", "red")
        return None

    status(f"Repacking {total} files into g1pack1: {os.path.basename(out_path)}", "blue")

    # Precompute sizes
    sizes: list[int] = []
    for name in files:
        full = os.path.join(folder_path, name)
        try:
            sz = os.path.getsize(full)
        except OSError:
            sz = 0
        sizes.append(sz)

    file_count = total
    toc_end = 4 + file_count * 4

    # Decide padding/alignment between TOC and first file
    alignment = 16
    if base_file_path:
        try:
            with open(base_file_path, "rb") as bf:
                base_blob = bf.read()
            inferred = _infer_g1pack1_alignment_from_base(base_blob)
            if inferred in (4, 8, 16, 32, 64, 128, 256, 512, 1024, 2048, 4096):
                alignment = inferred
        except Exception:
            pass

    data_start = _align_up(toc_end, alignment)
    pad_len = max(0, data_start - toc_end)

    try:
        with open(out_path, "wb") as out_f:
            # Header + TOC (sizes only)
            out_f.write(file_count.to_bytes(4, "little", signed=False))
            for sz in sizes:
                out_f.write(int(sz).to_bytes(4, "little", signed=False))

            # Optional padding to match typical/observed layout
            if pad_len:
                out_f.write(b"\x00" * pad_len)

            # Write each file sequentially
            for idx, (name, sz) in enumerate(zip(files, sizes)):
                in_path = os.path.join(folder_path, name)

                if sz > 0:
                    try:
                        with open(in_path, "rb") as fin:
                            while True:
                                chunk = fin.read(65536)
                                if not chunk:
                                    break
                                out_f.write(chunk)
                    except OSError:
                        status(f"Could not read {name}; writing zeros instead.", "red")
                        out_f.write(b"\x00" * sz)

                if progress is not None:
                    progress(idx + 1, total, f"g1pack1 repack: {idx + 1}/{total}")

            # Append taildata if present
            if taildata and len(taildata) == 6:
                out_f.write(taildata)

        status(f"g1pack1 repack complete: {out_path}", "green")
        return out_path

    except OSError as e:
        status(f"Error writing g1pack1 file: {e}", "red")
        return None


def _repack_g1pack2_folder(
    folder_path: str,
    all_files: list[str],
    out_path: str,
    status,
    progress,
    taildata: bytes | None = None,
) -> str | None:
    """
    Repack a folder of loose files into a g1pack2-style subcontainer:

      00-03 : file count (N)
      04-onward : N TOC entries:
                4 bytes: offset (from start of container)
                4 bytes: size
      data: each file's raw data at its offset, each file's end aligned to 16

    Files are packed in sorted filename order (entry_000, 000.dds, etc)

    After all data is written and aligned, append 6 byte taildata if provided
    """

    # Filter to regular files only, sort for stable order
    files = [
        f for f in all_files
        if os.path.isfile(os.path.join(folder_path, f))
    ]
    files = sorted(files, key=lambda s: s.lower())
    total = len(files)

    if total == 0:
        status("No files found to repack into g1pack2.", "red")
        return None

    status(
        f"Repacking {total} files into g1pack2: {os.path.basename(out_path)}",
        "blue",
    )

    # Precompute sizes
    sizes: list[int] = []
    for name in files:
        full = os.path.join(folder_path, name)
        try:
            sz = os.path.getsize(full)
        except OSError:
            sz = 0
        sizes.append(sz)

    # Compute offsets
    # Header = 4 bytes (count) + 8 bytes per file (offset + size)
    file_count = total
    header_size = 4 + file_count * 8

    offsets: list[int] = []
    pos = _align_up(header_size, 16)

    for sz in sizes:
        offsets.append(pos)
        pos = _align_up(pos + sz, 16)

    try:
        with open(out_path, "wb") as out_f:
            # Write header
            out_f.write(file_count.to_bytes(4, "little", signed=False))
            for off, sz in zip(offsets, sizes):
                out_f.write(off.to_bytes(4, "little", signed=False))
                out_f.write(sz.to_bytes(4, "little", signed=False))

            # After header, pad up to first data offset if needed
            cur = out_f.tell()  # should be header_size
            if offsets and offsets[0] > cur:
                pad_len = offsets[0] - cur
                out_f.write(b"\x00" * pad_len)

            # Now write each file at its planned offset, zero filling gaps
            for idx, (name, sz, off) in enumerate(zip(files, sizes, offsets)):
                in_path = os.path.join(folder_path, name)

                # Ensure we're at the right offset (fill zeros if necessary)
                cur_pos = out_f.tell()
                if cur_pos < off:
                    out_f.write(b"\x00" * (off - cur_pos))
                elif cur_pos > off:
                    # Should not normally happen but don't crash if it does
                    status(
                        f"Warning: overrun before writing {name} "
                        f"(cur=0x{cur_pos:X}, off=0x{off:X}).",
                        "red",
                    )

                # Write actual file data
                if sz > 0:
                    try:
                        with open(in_path, "rb") as fin:
                            while True:
                                chunk = fin.read(65536)
                                if not chunk:
                                    break
                                out_f.write(chunk)
                    except OSError:
                        status(f"Could not read {name}; writing zeros instead.", "red")
                        out_f.write(b"\x00" * sz)

                # Pad to 16 byte boundary after this file
                cur_pos = out_f.tell()
                pad_len = (-cur_pos) % 16
                if pad_len:
                    out_f.write(b"\x00" * pad_len)

                if progress is not None:
                    progress(
                        idx + 1,
                        total,
                        f"g1pack2 repack: {idx + 1}/{total}",
                    )

            # After all file data and per-file padding, append taildata if present
            if taildata and len(taildata) == 6:
                out_f.write(taildata)

        status(f"g1pack2 repack complete: {out_path}", "green")
        return out_path

    except OSError as e:
        status(f"Error writing g1pack2 file: {e}", "red")
        return None

def update_kvs_metadata(
    game_id: str,
    kvs_subcontainer_path: str,
    metadata_bin_path: str,
    status_callback=None,
    progress_callback=None,
) -> None:
    """
    Update (overwrite) the offset/size TOC inside a paired KVS metadata .bin file

    Currently only supports Warriors Orochi 3 (WO3)

    Metadata layout (little endian):
      00-03 : total kvs files (N)
      04-07 : unknown/reserved
      08-on : N entries, each 8 bytes:
              4 bytes absolute offset to a b'KOVS' chunk within the KVS subcontainer
              4 bytes size of that chunk (header + data)

    KVS subcontainer layout:
      sequential b'KOVS' chunks (32 byte header + data_size bytes), with optional padding
      and optional 6 byte taildata at end

    This function does NOT resize the metadata file, it only overwrites the TOC entries though
    in the future we could look into adding more audio files than what the game supports by default
    """

    def status(msg: str, color: str = "blue"):
        if status_callback is not None:
            status_callback(msg, color)

    def progress(done: int, total: int, note: str | None = None):
        if progress_callback is not None:
            progress_callback(done, total, note or "Updating KVS metadata")

    if (game_id or "").upper() != "WO3":
        raise NotImplementedError("Only Warriors Orochi 3 (WO3) is supported for KVS metadata updates.")

    kvs_subcontainer_path = os.path.abspath(kvs_subcontainer_path)
    metadata_bin_path = os.path.abspath(metadata_bin_path)

    if not os.path.isfile(kvs_subcontainer_path):
        raise FileNotFoundError(f"KVS subcontainer not found: {kvs_subcontainer_path}")
    if not os.path.isfile(metadata_bin_path):
        raise FileNotFoundError(f"Metadata file not found: {metadata_bin_path}")

    # Read metadata header to learn expected entry count
    with open(metadata_bin_path, "rb") as mf:
        header = mf.read(8)
        if len(header) < 8:
            raise ValueError("Metadata file too small (missing 8 byte header).")
        expected = int.from_bytes(header[0:4], "little", signed=False)
        toc_start = 8
        toc_len = expected * 8
        mf.seek(0, os.SEEK_END)
        meta_size = mf.tell()
        if expected <= 0:
            raise ValueError("Metadata has non-positive entry count.")
        if toc_start + toc_len > meta_size:
            raise ValueError(
                f"Metadata TOC points beyond file size "
                f"(expected toc_end=0x{toc_start + toc_len:X}, file=0x{meta_size:X})."
            )

    status(f"Scanning KVS for KOVS headers (expecting {expected} entries)", "blue")
    progress(0, max(1, expected), "Scanning KVS")

    offsets: list[int] = []
    sizes: list[int] = []

    with open(kvs_subcontainer_path, "rb") as kf:
        mm = mmap.mmap(kf.fileno(), 0, access=mmap.ACCESS_READ)
        try:
            n = len(mm)
            pos = 0
            idx = 0

            while idx < expected:
                found = mm.find(b"KOVS", pos)
                if found < 0:
                    break
                if found + 8 > n:
                    break

                data_size = int.from_bytes(mm[found + 4:found + 8], "little", signed=False)
                chunk_size = 32 + data_size

                # Sanity checks, resync if implausible
                if data_size <= 0 or chunk_size <= 32 or found + chunk_size > n:
                    pos = found + 4
                    continue

                offsets.append(found)
                sizes.append(chunk_size)

                idx += 1
                pos = found + chunk_size

                if idx % 512 == 0 or idx == expected:
                    progress(idx, expected, f"Scanning KVS {idx}/{expected}")

        finally:
            try:
                mm.close()
            except Exception:
                pass

    found_n = len(offsets)
    if found_n == 0:
        raise ValueError("No b'KOVS' headers found in the selected KVS subcontainer.")

    status(f"Found {found_n}/{expected} KOVS entries. Writing metadata TOC", "blue")
    progress(0, max(1, expected), "Updating metadata")

    with open(metadata_bin_path, "r+b") as mf:
        for i, (off, sz) in enumerate(zip(offsets, sizes)):
            ent_pos = 8 + i * 8
            mf.seek(ent_pos)
            mf.write(off.to_bytes(4, "little", signed=False))
            mf.write(sz.to_bytes(4, "little", signed=False))

            if (i + 1) % 512 == 0 or (i + 1) == found_n:
                progress(i + 1, expected, f"Updating metadata {i + 1}/{expected}")

    if found_n != expected:
        status(
            f"Warning: metadata expects {expected} entries but found {found_n} in KVS. "
            f"Updated {found_n} entries; remaining TOC entries were left unchanged.",
            "red",
        )
    else:
        status("KVS metadata updated successfully.", "green")
        progress(expected, expected, "Metadata update complete.")
