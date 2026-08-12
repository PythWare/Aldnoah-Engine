# Aldnoah_Logic/aldnoah_taildata.py
"""
External taildata manifest
"""
from __future__ import annotations

import json, os, struct
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional, Tuple

TAILDATA_FORMAT = "aldnoah-taildata"
TAILDATA_VERSION = 1

# idx_marker, entry_off, comp_marker
TAILDATA_STRUCT = struct.Struct("<BIB")
TAILDATA_LEN = TAILDATA_STRUCT.size

MAX_IDX_MARKER = 16

def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")

def manifest_filename(game_id: str) -> str:
    return f"aldnoah_taildata_{game_id}.json"

def parse_taildata(file_data: bytes) -> Optional[dict]:
    """Read the trailing 6 byte record from a blob that still carries one"""
    if len(file_data) < TAILDATA_LEN:
        return None
    idx_marker, entry_off, comp_marker = TAILDATA_STRUCT.unpack(file_data[-TAILDATA_LEN:])
    return {
        "idx_marker": idx_marker,
        "entry_off": entry_off,
        "comp_marker": comp_marker,
        "key": (idx_marker, entry_off),
    }

def has_plausible_taildata(tail_info: Optional[dict], entry_size: int = 32) -> bool:
    """
    Sanity filter for a parsed trailer
    """
    if not tail_info:
        return False
    if not (0 <= tail_info["idx_marker"] <= MAX_IDX_MARKER):
        return False
    if tail_info["comp_marker"] not in (0, 1):
        return False
    if tail_info["entry_off"] <= 0:
        return False
    if entry_size > 0 and (tail_info["entry_off"] % entry_size) != 0:
        return False
    return True


def parse_valid_taildata(file_data: bytes, entry_size: int = 32) -> Optional[dict]:
    tail_info = parse_taildata(file_data)
    return tail_info if has_plausible_taildata(tail_info, entry_size) else None


def pack_record(record: dict) -> bytes:
    """Serialise a manifest record into the trailer form packages carry"""
    return TAILDATA_STRUCT.pack(
        int(record["idx_marker"]) & 0xFF,
        int(record["entry_off"]) & 0xFFFFFFFF,
        1 if record.get("comp_marker") else 0,
    )


def normalize_key(path) -> str:
    return str(path).replace("\\", "/").strip("/")

class TaildataManifest:
    """Records for one game, keyed by unpacked path relative to the project root"""

    def __init__(self, game_id: str, root="."):
        self.game_id = game_id
        self.root = Path(root)
        self.path = self.root / manifest_filename(game_id)
        self.files: Dict[str, dict] = {}
        self.containers: Dict[str, str] = {}
        self.created_utc: Optional[str] = None

    def load(self) -> "TaildataManifest":
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return self
        if not isinstance(data, dict) or data.get("format") != TAILDATA_FORMAT:
            return self
        if data.get("game") != self.game_id:
            return self
        files = data.get("files")
        if isinstance(files, dict):
            self.files = files
        containers = data.get("containers")
        if isinstance(containers, dict):
            self.containers = containers
        self.created_utc = data.get("created_utc")
        return self

    def save(self) -> Path:
        payload = {
            "format": TAILDATA_FORMAT,
            "version": TAILDATA_VERSION,
            "game": self.game_id,
            "created_utc": self.created_utc or utc_now(),
            "updated_utc": utc_now(),
            "note": (
                "Taildata for the Aldnoah mod tools. Keys are unpacked file paths "
                "relative to the folder holding this file. Keep this file next to "
                "the unpack folder so the mod creator can find it."
            ),
            "containers": self.containers,
            "files": self.files,
        }
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(self.path.suffix + ".tmp")
        tmp.write_text(json.dumps(payload, indent=1), encoding="utf-8")
        os.replace(tmp, self.path)
        return self.path

    def add(self, rel_path, record: dict) -> str:
        key = normalize_key(rel_path)
        self.files[key] = record
        return key

    def set_container(self, idx_marker: int, container_path: str) -> None:
        self.containers[str(idx_marker)] = container_path

    def drop_container(self, idx_marker: int) -> int:
        """Forget every record for one container, so a re-unpack starts clean"""
        removed = [
            key for key, record in self.files.items()
            if int(record.get("idx_marker", -1)) == idx_marker
        ]
        for key in removed:
            del self.files[key]
        return len(removed)

    def get(self, rel_path) -> Optional[dict]:
        return self.files.get(normalize_key(rel_path))

    def candidate_keys(self, file_path) -> List[str]:
        """
        Keys to try for a file the user picked in a dialog
        """
        file_path = Path(file_path).resolve()
        keys: List[str] = []

        try:
            keys.append(normalize_key(file_path.relative_to(self.root.resolve())))
        except ValueError:
            pass

        parts = file_path.parts
        for depth in range(min(len(parts), 12), 1, -1):
            tail = normalize_key("/".join(parts[-depth:]))
            if tail not in keys:
                keys.append(tail)
        return keys

    def resolve(self, file_path, file_data: Optional[bytes] = None) -> Tuple[Optional[dict], bytes]:
        """Find the record for a file, reading its bytes only if a record matched"""
        for key in self.candidate_keys(file_path):
            record = self.files.get(key)
            if record is None:
                continue
            if file_data is None:
                try:
                    file_data = Path(file_path).read_bytes()
                except OSError:
                    return None, b""
            return record, file_data
        return None, file_data if file_data is not None else b""

def load_manifest(game_id: str, root=".") -> TaildataManifest:
    return TaildataManifest(game_id, root).load()

def find_manifest_for_file(file_path, game_id: str, max_depth: int = 12) -> Optional[TaildataManifest]:
    """
    Walk up from a staged file looking for the manifest of its game
    """
    name = manifest_filename(game_id)
    current = Path(file_path).resolve().parent
    for _ in range(max_depth):
        if (current / name).is_file():
            return TaildataManifest(game_id, current).load()
        if current.parent == current:
            break
        current = current.parent
    return None


def resolve_record(file_path, game_id: str, roots=(), file_data: Optional[bytes] = None):
    """
    Best effort lookup of the record for one staged file
    """
    if file_data is None:
        try:
            file_data = Path(file_path).read_bytes()
        except OSError:
            return None, b"", None

    for root in roots:
        if not root:
            continue
        manifest = load_manifest(game_id, root)
        if not manifest.files:
            continue
        record, payload = manifest.resolve(file_path, file_data)
        if record:
            return record, file_data, "manifest"

    manifest = find_manifest_for_file(file_path, game_id)
    if manifest is not None:
        record, payload = manifest.resolve(file_path, file_data)
        if record:
            return record, file_data, "manifest"

    legacy = parse_valid_taildata(file_data)
    if legacy:
        return legacy, file_data[:-TAILDATA_LEN], "legacy-trailer"

    return None, file_data, None
