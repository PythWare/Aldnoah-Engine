# Aldnoah_Logic/aldnoah_repacks.py

import os, mmap, re

from .aldnoah_unpack import (
    looks_like_classic_split_zlib,
    looks_like_split_zlib_pairtable_wrapper,
    looks_like_mdlk_blob,
    looks_like_embedded_mdlk_blob,
    looks_like_kshl_blob,
    rebuild_classic_split_zlib_from_folder,
    rebuild_split_zlib_wrapper_from_folder,
    rebuild_mdlk_from_folder,
    rebuild_embedded_mdlk_from_folder,
    rebuild_kshl_from_folder,
    rebuild_subcontainer_from_folder,
    read_universal_subcontainer_layout,
)
from .aldnoah_taildata import find_manifest_for_file, normalize_key


# Natural numeric sort for chunk filenames like 0.kvs/00000.kvs/entry_00000.kvs, etc
# Ensures repack order matches the original sequential unpack order even when digit widths vary
_NUM_RE = re.compile(r"(\d+)")

def natural_kvs_sort_key(name: str):
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

def inherit_taildata_record(base_file_path: str | None, out_path: str | None, game_id: str, status) -> bool:
    """
    Give a rebuilt file the same IDX slot as the file it was rebuilt from
    """
    if not (base_file_path and out_path and game_id):
        return False

    manifest = find_manifest_for_file(base_file_path, game_id)
    if manifest is None:
        return False

    record = None
    for key in manifest.candidate_keys(base_file_path):
        if key in manifest.files:
            record = manifest.files[key]
            break
    if record is None:
        return False

    try:
        out_key = normalize_key(os.path.relpath(os.path.abspath(out_path), str(manifest.root)))
    except ValueError:
        out_key = normalize_key(os.path.basename(out_path))

    inherited = dict(record)
    try:
        inherited["unpacked_size"] = os.path.getsize(out_path)
    except OSError:
        pass
    inherited["ext"] = os.path.splitext(out_path)[1]
    inherited["rebuilt_from"] = normalize_key(os.path.basename(base_file_path))
    manifest.files[out_key] = inherited

    try:
        manifest.save()
    except Exception as exc:
        status(f"Rebuilt file written but its taildata record could not be saved: {exc}", "red")
        return False

    status(f"Recorded taildata for {os.path.basename(out_path)} in {manifest.path.name}.", "blue")
    return True


def repack_from_folder(
    folder_path: str,
    base_file_path: str | None = None,
    status_callback=None,
    progress_callback=None,
    game_id: str = "",
) -> str | None:
    """
    Rebuild a subcontainer folder, then hand the result the base file's taildata
    record so it is ready to package
    """
    out_path = run_repack(folder_path, base_file_path, status_callback, progress_callback)
    if out_path:
        def status(msg: str, color: str = "blue"):
            if status_callback is not None:
                status_callback(msg, color)

        inherit_taildata_record(base_file_path, out_path, game_id, status)
    return out_path


def run_repack(
    folder_path: str,
    base_file_path: str | None = None,
    status_callback=None,
    progress_callback=None,
) -> str | None:
    """
    Entry point for GUI:

    Examine the selected folder
    If it contains any .kvs files, treat it as a KVS chunk folder and repack to
    a single sequential .kvs container

    Otherwise, rebuild it as a universal non-KVS subcontainer by reusing the
    original unpacked source file's TOC structure

    The rebuilt file inherits the base file's taildata record in the manifest, so
    it can be packaged straight away

    Returns the output file path or None on failure
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

    all_files = [
        f for f in os.listdir(folder_path)
        if os.path.isfile(os.path.join(folder_path, f))
    ]

    if not all_files:
        status(f"No files found in folder: {folder_path}", "red")
        return None

    if base_file_path:
        base_file_path = os.path.abspath(base_file_path)
        try:
            with open(base_file_path, "rb") as handle:
                base_blob = handle.read()
        except OSError as e:
            status(f"Could not read base file: {e}", "red")
            return None
    else:
        base_blob = b""

    base_raw_for_detect = base_blob

    # Decide type:
    # presence of .kvs files => KVS repack
    # otherwise => universal non-KVS subcontainer rebuild
    kvs_files = [f for f in all_files if f.lower().endswith(".kvs")]

    if kvs_files:
        status(f"Detected KVS chunk folder: {base_name}", "blue")
        out_path = os.path.join(parent_dir, f"{base_name}.kvs")
        return repack_kvs_folder(
            folder_path,
            kvs_files,
            out_path,
            status,
            progress,
        )
    else:
        if not base_file_path:
            status("A base unpacked source file is required for universal subcontainer rebuilds.", "red")
            return None
        if looks_like_mdlk_blob(base_raw_for_detect):
            status(f"Detected MDLK folder: {base_name}", "blue")
            try:
                out_path, detail = rebuild_mdlk_from_folder(folder_path, base_file_path)
                status(detail, "green")
                if progress is not None:
                    progress(1, 1, "MDLK rebuild complete")
                return out_path
            except Exception as e:
                status(f"MDLK rebuild failed: {e}", "red")
                return None
        if looks_like_kshl_blob(base_raw_for_detect):
            status(f"Detected KSHL folder: {base_name}", "blue")
            try:
                out_path, detail = rebuild_kshl_from_folder(folder_path, base_file_path)
                status(detail, "green")
                if progress is not None:
                    progress(1, 1, "KSHL rebuild complete")
                return out_path
            except Exception as e:
                status(f"KSHL rebuild failed: {e}", "red")
                return None
        if looks_like_split_zlib_pairtable_wrapper(base_raw_for_detect):
            status(f"Detected split-zlib wrapper folder: {base_name}", "blue")
            try:
                out_path, detail = rebuild_split_zlib_wrapper_from_folder(folder_path, base_file_path)
                status(detail, "green")
                if progress is not None:
                    progress(1, 1, "Split-zlib wrapper rebuild complete")
                return out_path
            except Exception as e:
                status(f"Split-zlib wrapper rebuild failed: {e}", "red")
                return None
        if looks_like_classic_split_zlib(base_raw_for_detect):
            status(f"Detected classic split-zlib folder: {base_name}", "blue")
            try:
                out_path, detail = rebuild_classic_split_zlib_from_folder(folder_path, base_file_path)
                status(detail, "green")
                if progress is not None:
                    progress(1, 1, "Classic split-zlib rebuild complete")
                return out_path
            except Exception as e:
                status(f"Classic split-zlib rebuild failed: {e}", "red")
                return None
        if read_universal_subcontainer_layout(base_raw_for_detect) is not None:
            status(f"Detected universal subcontainer folder: {base_name}", "blue")
            try:
                out_path, detail = rebuild_subcontainer_from_folder(folder_path, base_file_path)
                status(detail, "green")
                if progress is not None:
                    progress(1, 1, "Universal rebuild complete")
                return out_path
            except Exception as e:
                status(f"Universal rebuild failed: {e}", "red")
                return None
        if looks_like_embedded_mdlk_blob(base_raw_for_detect):
            status(f"Detected embedded MDLK wrapper folder: {base_name}", "blue")
            try:
                out_path, detail = rebuild_embedded_mdlk_from_folder(folder_path, base_file_path)
                status(detail, "green")
                if progress is not None:
                    progress(1, 1, "Embedded MDLK rebuild complete")
                return out_path
            except Exception as e:
                status(f"Embedded MDLK rebuild failed: {e}", "red")
                return None
        status(f"Detected universal subcontainer folder: {base_name}", "blue")
        try:
            out_path, detail = rebuild_subcontainer_from_folder(folder_path, base_file_path)
            status(detail, "green")
            if progress is not None:
                progress(1, 1, "Universal rebuild complete")
            return out_path
        except Exception as e:
            status(f"Universal rebuild failed: {e}", "red")
            return None


def repack_kvs_folder(
    folder_path: str,
    kvs_files: list[str],
    out_path: str,
    status,
    progress,
) -> str | None:
    """
    Repack a folder of KOVS chunks (*.kvs) into a single sequential KVS container

    For each input file:
    
      Expect b"KOVS" at the start and at least 32 bytes header
      Read size from bytes 4-7
      Write header and size bytes of data
      Then pad with 0x00 until the end of that chunk is 16 byte aligned

    The output is written clean, its taildata record is added to the manifest by
    the caller
    """

    # Stable order, natural numeric sort (works for 0.kvs, 00000.kvs, entry_00000.kvs, etc)
    kvs_files = sorted(kvs_files, key=natural_kvs_sort_key)
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
                    # Clamp to available data but warn
                    status(
                        f"{name}: header size exceeds file length, clamping.",
                        "red",
                    )
                    data_end = len(blob)

                # Write KOVS header/data, no trailing pad from source file
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

        status(f"KVS repack complete: {out_path}", "green")
        return out_path

    except OSError as e:
        status(f"Error writing KVS file: {e}", "red")
        return None
