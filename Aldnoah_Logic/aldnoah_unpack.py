# Aldnoah_Logic/aldnoah_unpack.py

import os, mmap, threading

from .aldnoah_codecs import (
    decompress as codec_decompress,
    decompress_split_zlib_streams,
)


def _log_comp_failure(log_dir: str, message: str):
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


def looks_like_split_zlib(raw: bytes) -> bool:
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


def _normalize_endian(v: str) -> str:
    v = (v or "little").strip().lower()
    if v in ("le", "little", "l"):
        return "little"
    if v in ("be", "big", "b"):
        return "big"
    return "little"


def _parse_idx_entry(chunk: bytes, raw_vars, field_size: int, endian: str):
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


def unpack_from_config(
    cfg: dict,
    base_dir: str,
    status_callback=None,
    progress_callback=None,
):
    """
    Generic unpacker driven entirely by a .ref config dict + base directory

    """

    def update_status(text, color="blue"):
        if status_callback is not None:
            status_callback(text, color)

    def update_progress(done, total, note=None):
        if progress_callback is not None:
            progress_callback(done, total, note)

    game_name = cfg.get("Game", "Unknown Game")
    containers = cfg.get("Containers", [])
    idx_files = cfg.get("IDX_Files", [])
    out_root = cfg.get("Main_Unpack_Folder", "Unpacked_Files")

    raw_vars = cfg.get("Raw_Variables", [])
    field_size = cfg.get("Length_Per_Raw_Variables", 0)
    entry_size_cfg = cfg.get("IDX_Chunk_Read", None)

    # normalize lists
    if isinstance(containers, str):
        containers = [containers]
    if isinstance(idx_files, str):
        idx_files = [idx_files]

    if isinstance(field_size, str):
        try:
            field_size = int(field_size.strip())
        except ValueError:
            field_size = 0
    if isinstance(entry_size_cfg, str):
        try:
            entry_size_cfg = int(entry_size_cfg.strip())
        except ValueError:
            entry_size_cfg = None

    entry_size_calc = 0
    if raw_vars and field_size > 0:
        entry_size_calc = len(raw_vars) * field_size

    if isinstance(entry_size_cfg, int) and entry_size_cfg > 0:
        entry_size = entry_size_cfg
    elif entry_size_calc > 0:
        entry_size = entry_size_calc
    else:
        entry_size = 32

    vars_to_shift = cfg.get("Raw_Variables_To_Shift", [])
    if isinstance(vars_to_shift, str):
        vars_to_shift = [v.strip() for v in vars_to_shift.split(",") if v.strip()]
    elif not isinstance(vars_to_shift, list):
        vars_to_shift = []

    # Support both Raw_Shift_Bits and Bit_Shift_to_left but default is 0 for PC only
    shift_bits = cfg.get("Raw_Shift_Bits", None)
    if shift_bits is None:
        shift_bits = cfg.get("Bit_Shift_to_left", None)

    if isinstance(shift_bits, str):
        try:
            shift_bits = int(shift_bits.strip())
        except ValueError:
            shift_bits = None

    # If there is a shift but no explicit list of variables, assume Offset-like fields
    if shift_bits is not None and not vars_to_shift and raw_vars:
        lower_map = {name.lower(): name for name in raw_vars}
        auto_targets = [
            orig for key, orig in lower_map.items()
            if "offset" in key
        ]
        if auto_targets:
            vars_to_shift = auto_targets

    if shift_bits is None:
        shift_bits = 0  # PC only: never auto shift like PS2 sectors

    endian = _normalize_endian(str(cfg.get("Endian", "little")))

    compression_cfg = cfg.get("Compression", "auto")
    # allow list aligned to idx files
    if isinstance(compression_cfg, str):
        compression_list = [compression_cfg] * max(1, len(idx_files))
    elif isinstance(compression_cfg, list):
        compression_list = [str(c) for c in compression_cfg]
        if len(compression_list) < len(idx_files):
            compression_list.extend(
                [compression_list[-1]] * (len(idx_files) - len(compression_list))
            )
    else:
        compression_list = ["auto"] * max(1, len(idx_files))

    has_start_from = ("Start_From_Offset" in cfg)
    start_from_offset = cfg.get("Start_From_Offset", 0)
    if isinstance(start_from_offset, str):
        try:
            start_from_offset = int(start_from_offset.strip())
        except ValueError:
            start_from_offset = 0

    if not containers or not idx_files:
        update_status("No Containers or IDX_Files defined in config.", "red")
        return

    if not os.path.isdir(out_root):
        os.makedirs(out_root, exist_ok=True)

    update_status(
        f"Unpacking {game_name} (entry size: {entry_size} bytes, PC-only)...",
        "blue",
    )

    # Case 1: one IDX, multiple containers
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

        _unpack_multi_containers(
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

    # Case 2: normal 1:1 pairing
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

            _unpack_pair(
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


def _append_taildata(
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


def _unpack_pair(
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

    Compression is selected by ref (Compression key).
    """

    update_status(f"Reading IDX: {os.path.basename(idx_path)}", "blue")

    with open(idx_path, "rb") as f_idx:
        idx_data_full = f_idx.read()

    if entry_size <= 0:
        update_status("Invalid entry_size, must be > 0.", "red")
        return

    # If Start_From_Offset present, use it else use full IDX
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

                vals = _parse_idx_entry(chunk, raw_vars, field_size, endian)

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
                    # We'll skip non-physical "entries".
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

                # PC compressed (flag==1): ref-driven, keep split-zlib detection
                if compressed_sz > 0 and flag == 1:
                    try:
                        # If ref explicitly says split, force split first
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
                _append_taildata(
                    out_path,
                    idx_marker,
                    entry_off_abs,
                    1 if did_decompress else 0,
                    endian,
                )

                if ext == ".g1pack1":
                    unpack_g1pack1(out_path)
                if ext == ".g1pack2":
                    unpack_g1pack2(out_path)
                if ext == ".kvs":
                    unpack_kvs(out_path)

                file_index += 1

                if used_raw and raw_error:
                    msg = f"{raw_error}; wrote raw to {out_name}"
                    log_root = os.path.dirname(pair_out_dir)
                    _log_comp_failure(log_root, msg)

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


def _unpack_multi_containers(
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

    Compression is ref-driven
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
    last_offset = -1

    def advance_container():
        nonlocal current_idx, current_map, current_size, last_offset
        if current_idx + 1 >= len(bin_maps):
            return False
        current_idx += 1
        current_map = bin_maps[current_idx]
        current_size = bin_sizes[current_idx]
        last_offset = -1
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

            vals = _parse_idx_entry(chunk, raw_vars, field_size, endian)

            if shift_bits:
                for name in vars_to_shift:
                    if name in vals:
                        vals[name] = vals[name] << shift_bits

            offset = vals.get("Offset", 0)
            original_sz = vals.get("Original_Size", vals.get("Full_Size", 0))
            compressed_sz = vals.get("Compressed_Size", 0)
            flag = vals.get("Compression_Marker", 0)

            if last_offset >= 0 and offset < last_offset:
                advance_container()
            last_offset = offset

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

            # PC compressed (flag==1): ref-driven, keep split-zlib detection
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

            # taildata: absolute IDX entry offset
            entry_off_abs = start_from_offset + start
            _append_taildata(
                out_path,
                idx_marker,
                entry_off_abs,
                1 if did_decompress else 0,
                endian,
            )

            if ext == ".g1pack2":
                unpack_g1pack2(out_path)
            if ext == ".kvs":
                unpack_kvs(out_path)

            container_counts[current_idx] += 1

            if used_raw and raw_error:
                msg = (
                    f"{raw_error}; wrote raw to Pack_{current_idx:02d}/{out_name}"
                )
                _log_comp_failure(out_root, msg)

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
    head = data[:64]
    n = len(data)

    # Exact prefix matches
    prefix64 = (
        (b"\x89PNG\r\n\x1a\n", ".png"),
        (b"DDS ", ".dds"),
        (b"OggS", ".ogg"),
        (b"KOVS", ".kvs"),
        (b"\x5F\x4C\x31\x47", ".g1l"),
        (b"\x5F\x44\x42\x57", ".wbd"),
        (b"\x5F\x48\x42\x57", ".wbh"),
        (b"[glo", ".ini"),
        (b"\x58\x46\x31\x47", ".g1f"),
        (b"\x5F\x4E\x31\x47", ".g1n"),
        (b"\x5F\x41\x31\x47", ".g1a"),
        (b"\x4D\x45\x31\x47", ".g1e"),
    )
    for sig, ext in prefix64:
        if head.startswith(sig):
            return ext

    # Special cased RIFF logic
    if head.startswith(b"RIFF"):
        return ".wav" if b"WAVEfmt" in head else ".riff"

    # 2) Short/alternate prefix matches
    head4 = head[:4]
    head3 = head[:3]
    head2 = head[:2]
    
    if head4 == b"\x89\x50\x4E\x47":
        return ".png"
    if head4 == b"\x58\x4B\x4D":
        return ".xkm"
    if head3 == b"\x58\x46\x54":
        return ".xft"
    if head2 == b"\x42\x4D":
        return ".bmp"

    # Contains in header checks
    if b"\x4A\x46\x49\x46" in head:  # JFIF
        return ".jpg"
    if head.startswith(b"\x54\x49\x4D\x32") or b"\x54\x49\x4D\x32" in head:
        return ".tm2"

    # Non-head checks
    if data.startswith(b"SShd"):
        return ".ss2"
    if data.startswith(b"SSbd"):
        return ".ss2bd"
    if data.startswith(b"IECSsreV"):
        return ".vagbank"

    # Small header matches
    if head4 == b"\x45\x4D\x06\x00":
        return ".EM"
    if head2 == b"XL":
        return ".XL"
    if head4 == b"MESC":
        return ".MESC"
    if head4 == b"ipu2":
        return ".ipu2"
    if head4 == b"\x5F\x4C\x31\x47":
        return ".g1l"
    if head3 == b"GT1":
        return ".g1t"
    if head4 == b"\x5F\x4D\x31\x47":
        return ".g1m"
    if head4 == b"\x5F\x41\x31\x47":
        return ".g1a"
    if head4 == b"LHSK":
        return ".g1s"
    # Seems to be either a container for map G1Ms meant to be read as 1 file ingame
    # or merely stores pieces
    if head4 == b"MDLK":
        return ".KLDM"
    if head4 == b"\x00\x20\xAF\x30":
        return ".tm2"
    if n >= 0x4000:  # arbitrary large enough to be container guard
        scan_start = 0xC   # skip tiny header/TOC area
        scan_end   = min(n, 500_000)

        slice_ = data[scan_start:scan_end]

        # for varying header/tocs g1pack1 is used
        if b"\x5F\x4D\x31\x47" in slice_:
            return ".g1pack1"
        # for simple header/tocs g1pack2 is used such as sequential tocs
        if b"\x47\x54\x31\x47" in slice_:
            return ".g1pack2"
    return ".bin"


def unpack_g1pack1(path: str) -> None:
    """
    Asynchronously unpack a g1pack1 style subcontainer into a folder named after the file

    Layout (little endian):
      00-03 : file count (N)
      04-onward : TOC entries, each:
                4 bytes: absolute size of file i (no offsets)

    After the TOC, there may be padding (usually 0x00 dwords)
    We locate the start of sequential file storage by scanning in 4 byte steps, then unpack N files
    sequentially using the sizes from the TOC.

    Notes:
    This is a best effort unpacker, some inner files may have unknown signatures
      We rely on detect_ext() and fall back to .bin when unsure
    """

    def _choose_data_start(blob: bytes, toc_end: int, sizes: list[int]) -> int:
        # Minimum bytes required for payload (ignoring optional taildata)
        need = sum(sizes)
        n = len(blob)
        if toc_end + need > n:
            return toc_end

        # Candidate offsets: always include toc_end, then include first non-zero dword offsets
        # in a bounded scan window
        candidates = [toc_end]
        scan_limit = min(n, toc_end + 0x4000)  # don't scan forever
        for off in range(toc_end, scan_limit, 4):
            if off + 4 > n:
                break
            if blob[off:off+4] != b"\x00\x00\x00\x00":
                candidates.append(off)
                break  # per spec, first non-null is assumed start

        # If spec-derived candidate doesn't fit, fall back to toc_end
        best = toc_end
        best_score = -1

        # Score a candidate by how many of the first few files look like known formats
        # This helps when the first file begins with zeros (candidate should remain toc_end)
        for cand in candidates:
            if cand < toc_end:
                continue
            if cand + need > n:
                continue
            score = 0
            cur = cand
            for i, sz in enumerate(sizes[:min(6, len(sizes))]):
                if sz <= 0 or cur + sz > n:
                    break
                ext = detect_ext(blob[cur:cur+min(sz, 256)])
                if ext != ".bin":
                    score += 1
                cur += sz
            if score > best_score:
                best_score = score
                best = cand

        return best

    def _worker():
        try:
            with open(path, "rb") as f:
                blob = f.read()

            if len(blob) < 8:
                return

            count = int.from_bytes(blob[0:4], "little", signed=False)
            if count <= 0 or count > 200000:
                return

            toc_end = 4 + count * 4
            if toc_end > len(blob):
                return

            sizes: list[int] = []
            for i in range(count):
                off = 4 + i * 4
                sz = int.from_bytes(blob[off:off+4], "little", signed=False)
                sizes.append(sz)

            data_start = _choose_data_start(blob, toc_end, sizes)

            base_dir, fname = os.path.split(path)
            name_no_ext, _ = os.path.splitext(fname)
            out_dir = os.path.join(base_dir, name_no_ext)
            os.makedirs(out_dir, exist_ok=True)

            cur = data_start
            for i, sz in enumerate(sizes):
                if sz <= 0:
                    # still emit empty placeholder file to preserve indexing
                    out_name = f"{i:03d}.bin"
                    out_path = os.path.join(out_dir, out_name)
                    try:
                        with open(out_path, "wb") as fout:
                            fout.write(b"")
                    except OSError:
                        pass
                    continue

                if cur + sz > len(blob):
                    # Stop if TOC goes out of bounds
                    break

                chunk = blob[cur:cur+sz]
                cur += sz

                try:
                    inner_ext = detect_ext(chunk)
                except Exception:
                    inner_ext = ".bin"

                # Safety: if something claims to be text but contains NULs early, treat as binary
                if inner_ext in (".ini", ".txt"):
                    if b"\x00" in chunk[:64]:
                        inner_ext = ".bin"

                out_name = f"{i:03d}{inner_ext}"
                out_path = os.path.join(out_dir, out_name)
                try:
                    with open(out_path, "wb") as fout:
                        fout.write(chunk)
                except OSError:
                    continue

        except Exception:
            # Silent fail, runs in background thread
            return

    t = threading.Thread(target=_worker, daemon=True)
    t.start()


def unpack_g1pack2(path: str) -> None:
    """
    Asynchronously unpack a subcontainer into a folder named after the file, used for simple subcontainers

    Layout (little endian):
      00-03 : file count (N)
      04-onward : TOC entries, each:
                4 bytes: offset (from start of file)
                4 bytes: size

    After the TOC, at each offset there is a G1T or other files
    The main file is left as is, we just create a sibling folder and dump
    the inner files there
    """

    def _worker():
        try:
            if not os.path.isfile(path):
                return

            with open(path, "rb") as f:
                blob = f.read()

            if len(blob) < 4:
                return

            # Number of inner files
            count = int.from_bytes(blob[0:4], "little", signed=False)
            if count <= 0:
                return

            toc_start = 4
            toc_len = count * 8
            if toc_start + toc_len > len(blob):
                # TOC points beyond file, probably not a valid subcontainer file
                return

            base_dir, fname = os.path.split(path)
            name_no_ext, _ = os.path.splitext(fname)

            # Folder named after the entry (basename, no extension)
            out_dir = os.path.join(base_dir, name_no_ext)
            os.makedirs(out_dir, exist_ok=True)

            for i in range(count):
                ent_off = toc_start + i * 8
                off = int.from_bytes(blob[ent_off:ent_off + 4], "little", signed=False)
                size = int.from_bytes(blob[ent_off + 4:ent_off + 8], "little", signed=False)

                # Basic check
                if size <= 0:
                    continue
                if off < 0 or off + size > len(blob):
                    continue

                chunk = blob[off:off + size]

                # Try to guess extension, default to .bin if unknown
                try:
                    inner_ext = detect_ext(chunk)
                except Exception:
                    inner_ext = ".bin"

                out_name = f"{i:03d}{inner_ext}"
                out_path = os.path.join(out_dir, out_name)

                try:
                    with open(out_path, "wb") as fout:
                        fout.write(chunk)
                except OSError:
                    # If we can't write one file skip it and move on
                    continue

        except Exception:
            # Silent fail, this runs in a background thread and should not
            # interfere with the main Tkinter GUI
            return

    # Fire off a background thread to keep Tkinter responsive
    t = threading.Thread(target=_worker, daemon=True)
    t.start()

def unpack_kvs(path: str) -> None:
    """
    Asynchronously unpack a KVS subcontainer (sequential KOVS chunks) into a folder
    named after the .kvs file

    KOVS chunk layout (little endian):

      00-03 : b"KOVS"
      04-07 : size (file data length)
      08-27 : 24 bytes which is the remaining header (kept for future repack, ignored here)
      28-onward : file data (size bytes)

    After each file data:
      If the end of file data is not on a 16 byte boundary, pad forward to the
        next multiple of 16
      Then read in 4 byte steps until a new KOVS header is detected
      Repeat until no further KOVS is found
    """

    def _worker():
        try:
            if not os.path.isfile(path):
                return

            with open(path, "rb") as f:
                blob = f.read()

            n = len(blob)
            if n < 32:
                return

            base_dir, fname = os.path.split(path)
            name_no_ext, _ = os.path.splitext(fname)

            # Folder named after the KVS file (basename without extension)
            out_dir = os.path.join(base_dir, name_no_ext)
            os.makedirs(out_dir, exist_ok=True)

            pos = 0
            index = 0

            while True:
                # If not enough bytes left for a header we're done
                if pos + 32 > n:
                    break

                # Ensure we're on a KOVS header, if not then search forward in 4 byte steps
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
                        break  # no more KOVS headers anywhere
                    # fall through to parse the header at new pos

                if pos + 32 > n:
                    break  # not enough room for size + header

                size = int.from_bytes(blob[pos + 4:pos + 8], "little", signed=False)
                if size <= 0:
                    break

                data_start = pos + 32
                data_end = data_start + size
                if data_end > n:
                    break

                # include the whole KOVS chunk: 32 byte header + file data
                chunk = blob[pos:data_end]

                # Extension: this will now detect as .kvs (because of the KOVS magic)
                try:
                    inner_ext = detect_ext(chunk)
                except Exception:
                    inner_ext = ".kvs"

                if inner_ext == ".bin":
                    inner_ext = ".kvs"

                out_name = f"{index:05d}{inner_ext}"
                out_path = os.path.join(out_dir, out_name)
                with open(out_path, "wb") as fout:
                    fout.write(chunk)

                index += 1

                # Move past this KOVS block's data
                pos = data_end

                # Align to next 16 byte boundary
                if pos % 16 != 0:
                    pos = (pos + 15) & ~0x0F

                # On next loop, we'll either see a KOVS header immediately or
                # search forward in 4 byte increments as described above

        except Exception:
            # Silent fail, this runs in a background thread and should not
            # interfere with the main Tkinter GUI
            return

    # Fire off a background thread to keep Tkinter responsive
    t = threading.Thread(target=_worker, daemon=True)
    t.start()
