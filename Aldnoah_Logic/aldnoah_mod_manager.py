from __future__ import annotations

import ctypes, math, os, json, shutil, hashlib, random
import tkinter as tk
from dataclasses import dataclass, field
from io import BytesIO
from tkinter import ttk, filedialog, messagebox
from typing import Dict, List, Optional, Set, Tuple

from PIL import Image, ImageChops, ImageTk

from .aldnoah_energy import LILAC, apply_lilac_to_root, get_game_schema, schema_to_ref_dict, setup_lilac_styles
from .aldnoah_installer import AldnoahInstallerReader, INSTALLER_EXTENSION
from .aldnoah_mod_manager_extra import (
    CONFLICT_TETHER,
    CONSTELLATION_LINE,
    ENABLED_CHAIN,
    LENS_BG,
    LENS_EDGE,
    LENS_GOLD,
    LENS_PANEL,
    NEBULA_DIM,
    ORRERY_BG,
    ORRERY_BG_2,
    PATCH_LINE,
    REACTOR_CORE,
    SIGNAL_RING,
    SKY_MODE_META,
    TEXT,
    TEXT_DARK,
    TEXT_MUTED,
    build_contextual_conflict_links,
    enabled_chain_links,
    find_target_collisions,
    mod_visual_state,
    signal_matches,
)


PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir))
BASE_MODS_DIR = os.path.join(PROJECT_ROOT, "Mods_Folder")

MOD_PROFILES = {
    "DW7XL": {"display_name": "Dynasty Warriors 7 XL (PC)",      "single_ext": ".DW7XLM", "package_ext": ".DW7XLP", "mods_file": "DW7XL.MODS"},
    "DW8XL": {"display_name": "Dynasty Warriors 8 XL (PC)",      "single_ext": ".DW8XLM", "package_ext": ".DW8XLP", "mods_file": "DW8XL.MODS"},
    "DW8E":  {"display_name": "Dynasty Warriors 8 Empires (PC)", "single_ext": ".DW8EM",  "package_ext": ".DW8EP",  "mods_file": "DW8E.MODS"},
    "WO3":   {"display_name": "Warriors Orochi 3 (PC)",          "single_ext": ".WO3M",   "package_ext": ".WO3P",   "mods_file": "WO3.MODS"},
    "WO4":   {"display_name": "Warriors Orochi 4 (PC)",          "single_ext": ".WO4M",   "package_ext": ".WO4P",   "mods_file": "WO4.MODS"},
    "BN":    {"display_name": "Bladestorm Nightmare (PC)",       "single_ext": ".BNM",    "package_ext": ".BNP",    "mods_file": "BSN.MODS"},
    "WAS":   {"display_name": "Warriors All Stars (PC)",         "single_ext": ".WASM",   "package_ext": ".WASP",   "mods_file": "WAS.MODS"},
}

TAILDATA_LEN = 6
ALIGN = 16
ALDNOAH_SIGNATURE = b"ALDNOAHMOD"
ALDNOAH_FORMAT_VERSION = 3
ALDNOAH_COMPATIBLE_FORMAT_VERSIONS = {2, 3}
DETAIL_PREVIEW_SIZE = (300, 170)
DETAIL_PREVIEW_BG = "#120d18"
INSTALLER_PREVIEW_PAD_COLORS = ((16, 12, 25), (15, 12, 24), (18, 13, 24))

GENRES = ["all", "texture", "model", "text", "overhaul", "misc"]
GENRE_LABELS = {
    "all": "Universal Sky",
    "texture": "Texture Sky",
    "model": "Model Sky",
    "text": "Text Sky",
    "overhaul": "Overhaul Sky",
    "misc": "Auxiliary Sky",
}
GENRE_ID_TO_KEY = {
    0: "all",
    1: "texture",
    2: "model",
    3: "text",
    4: "overhaul",
    5: "misc",
}
GENRE_KEY_TO_LABEL = {
    "all": "All",
    "texture": "Texture",
    "model": "Model",
    "text": "Text",
    "overhaul": "Overhaul",
    "misc": "Misc",
}
GENRE_LABEL_TO_KEY = {label.lower(): key for key, label in GENRE_KEY_TO_LABEL.items()}
GENRE_LABEL_TO_KEY["universal"] = "all"
GENRE_LABEL_TO_KEY["universal sky"] = "all"


def trim_installer_preview_padding(img: Image.Image) -> Image.Image:
    if img.width < 32 or img.height < 32:
        return img

    source = img.convert("RGB")
    best_bbox = None
    best_area = source.width * source.height + 1
    for color in INSTALLER_PREVIEW_PAD_COLORS:
        bg = Image.new("RGB", source.size, color)
        mask = ImageChops.difference(source, bg).convert("L").point(lambda value: 255 if value > 14 else 0)
        bbox = mask.getbbox()
        if not bbox:
            continue
        left, top, right, bottom = bbox
        area = (right - left) * (bottom - top)
        if area < best_area:
            best_area = area
            best_bbox = bbox

    if not best_bbox:
        return img

    left, top, right, bottom = best_bbox
    trimmed_x = left + (source.width - right)
    trimmed_y = top + (source.height - bottom)
    if max(trimmed_x / source.width, trimmed_y / source.height) < 0.04:
        return img

    crop_width = right - left
    crop_height = bottom - top
    if crop_width < source.width * 0.25 or crop_height < source.height * 0.25:
        return img

    margin = 2
    return source.crop(
        (
            max(0, left - margin),
            max(0, top - margin),
            min(source.width, right + margin),
            min(source.height, bottom + margin),
        )
    )


GENRE_CENTERS = {
    "all": (0.0, -1650.0),
    "texture": (-1700.0, -520.0),
    "model": (1700.0, -520.0),
    "text": (-1700.0, 980.0),
    "overhaul": (1700.0, 980.0),
    "misc": (0.0, 2150.0),
}

CONSTELLATION_LIMIT = 12
WORLD_SIZE = 5200

try:
    from ctypes import wintypes

    _winmm = ctypes.WinDLL("winmm", use_last_error=True)
    _PlaySoundW = _winmm.PlaySoundW
    _PlaySoundW.argtypes = [ctypes.c_void_p, wintypes.HMODULE, wintypes.DWORD]
    _PlaySoundW.restype = wintypes.BOOL
except Exception:
    wintypes = None
    _PlaySoundW = None

SND_ASYNC = 0x0001
SND_NODEFAULT = 0x0002
SND_MEMORY = 0x0004
SND_LOOP = 0x0008
SND_PURGE = 0x0040


def is_installer_filename(filename: str) -> bool:
    return os.path.splitext(filename)[1].lower() == INSTALLER_EXTENSION.lower()


def normalize_genre_key(value: str) -> str:
    raw = (value or "").strip().lower()
    if raw in GENRES:
        return raw
    return GENRE_LABEL_TO_KEY.get(raw, "misc")


def setup_lilac_styles_if_needed(root: tk.Misc):
    setup_lilac_styles(root)
    apply_lilac_to_root(root)


def normalize_endian(v: str) -> str:
    v = (v or "little").strip().lower()
    if v in ("le", "little", "l"):
        return "little"
    if v in ("be", "big", "b"):
        return "big"
    return "little"


def ensure_dir(p: str) -> str:
    os.makedirs(p, exist_ok=True)
    return p


def pad_len(pos: int, boundary: int) -> int:
    return (-pos) % boundary


def stable_hash(text: str) -> int:
    return int(hashlib.sha1(text.encode("utf-8", errors="replace")).hexdigest()[:8], 16)


def title_from_filename(name: str) -> str:
    stem = os.path.splitext(name)[0]
    stem = stem.replace("_", " ").replace("-", " ")
    return " ".join(part for part in stem.split() if part) or name


def read_exact(f, n: int, label: str) -> bytes:
    data = f.read(n)
    if len(data) != n:
        raise ValueError(f"Unexpected EOF while reading {label}")
    return data


def read_u8(f, label: str) -> int:
    return int.from_bytes(read_exact(f, 1, label), "little")


def read_u16(f, label: str) -> int:
    return int.from_bytes(read_exact(f, 2, label), "little")


def read_u32(f, label: str) -> int:
    return int.from_bytes(read_exact(f, 4, label), "little")


def read_sized_ut8(f, size_bytes: int, label: str) -> str:
    if size_bytes == 1:
        size = read_u8(f, f"{label} length")
    elif size_bytes == 2:
        size = read_u16(f, f"{label} length")
    else:
        raise ValueError("Unsupported sized string field width")
    return read_exact(f, size, label).decode("utf-8", errors="replace")


@dataclass
class TailData:
    idx_marker: int
    entry_off: int
    comp_marker: int

    @staticmethod
    def parse(raw6: bytes, endian: str = "little") -> "TailData":
        if len(raw6) != 6:
            raise ValueError("taildata must be 6 bytes")
        idx_marker = raw6[0]
        entry_off = int.from_bytes(raw6[1:5], endian, signed=False)
        comp_marker = raw6[5]
        return TailData(idx_marker, entry_off, comp_marker)


@dataclass
class ModFileEntry:
    stored_name: str
    payload: bytes
    tail: TailData


def installer_payload_to_entry(payload) -> ModFileEntry:
    if len(payload.data) < TAILDATA_LEN:
        raise ValueError(f"{payload.stored_name} is missing Aldnoah taildata.")
    tail = TailData.parse(payload.data[-TAILDATA_LEN:], endian="little")
    return ModFileEntry(stored_name=payload.stored_name, payload=payload.data[:-TAILDATA_LEN], tail=tail)


def installer_payloads_to_entries(payloads: List) -> Tuple[List, List[ModFileEntry], List[str]]:
    valid_payloads = []
    entries = []
    invalid = []
    for payload in payloads:
        try:
            entries.append(installer_payload_to_entry(payload))
            valid_payloads.append(payload)
        except Exception as exc:
            invalid.append(str(exc))
    return valid_payloads, entries, invalid


@dataclass
class ModMeta:
    display_name: str
    author: str
    version: str
    description: str
    file_count: int
    genre: str
    build_mode: str
    format_version: int
    preview_count: int = 0
    has_audio: bool = False


@dataclass
class ParsedModPackage:
    meta: ModMeta
    entries: List[ModFileEntry] = field(default_factory=list)
    preview_images: List[bytes] = field(default_factory=list)
    audio_bytes: Optional[bytes] = None


class RefLayout:
    def __init__(self, cfg: dict):
        self.cfg = cfg
        self.endian = normalize_endian(str(cfg.get("Endian", "little")))
        self.raw_vars = cfg.get("Raw_Variables", []) or []
        if isinstance(self.raw_vars, str):
            self.raw_vars = [v.strip() for v in self.raw_vars.split(",") if v.strip()]

        self.field_size = cfg.get("Length_Per_Raw_Variables", 0) or 0
        if isinstance(self.field_size, str):
            try:
                self.field_size = int(self.field_size.strip())
            except ValueError:
                self.field_size = 0

        entry_size_cfg = cfg.get("IDX_Chunk_Read", None)
        if isinstance(entry_size_cfg, str):
            try:
                entry_size_cfg = int(entry_size_cfg.strip())
            except ValueError:
                entry_size_cfg = None

        calc = 0
        if self.raw_vars and self.field_size > 0:
            calc = len(self.raw_vars) * self.field_size
        self.entry_size = int(entry_size_cfg) if isinstance(entry_size_cfg, int) and entry_size_cfg > 0 else (calc if calc > 0 else 32)

        shift_bits = cfg.get("Raw_Shift_Bits", None)
        if shift_bits is None:
            shift_bits = cfg.get("Bit_Shift_to_left", None)
        if isinstance(shift_bits, str):
            try:
                shift_bits = int(shift_bits.strip())
            except ValueError:
                shift_bits = 0
        self.shift_bits = int(shift_bits or 0)

        vars_to_shift = cfg.get("Raw_Variables_To_Shift", [])
        if isinstance(vars_to_shift, str):
            vars_to_shift = [v.strip() for v in vars_to_shift.split(",") if v.strip()]
        if not isinstance(vars_to_shift, list):
            vars_to_shift = []
        self.vars_to_shift = vars_to_shift

        self.offset_field = self.pick_field(["offset"], prefer=["Offset"])
        self.orig_size_field = self.pick_field(["size"], prefer=["Original_Size", "Full_Size", "Size"], reject=["compressed"])
        self.comp_size_field = self.pick_field(["compressed", "csize"], prefer=["Compressed_Size"], allow_none=True)
        self.comp_flag_field = self.pick_field(["compression", "flag", "marker"], prefer=["Compression_Marker"], allow_none=True)

    def pick_field(self, contains_any: List[str], prefer: List[str], reject: Optional[List[str]] = None, allow_none: bool = False) -> Optional[str]:
        reject = reject or []
        for p in prefer:
            if p in self.raw_vars:
                return p
        for name in self.raw_vars:
            l = name.lower()
            if any(k in l for k in contains_any) and not any(r in l for r in reject):
                return name
        return None if allow_none else (prefer[0] if prefer else None)

    def field_span(self, field_name: str) -> Tuple[int, int]:
        if field_name not in self.raw_vars or self.field_size <= 0:
            raise KeyError(f"Field '{field_name}' missing in Raw_Variables")
        idx = self.raw_vars.index(field_name)
        start = idx * self.field_size
        end = start + self.field_size
        return start, end

    def patch_entry_bytes(self, entry_bytes: bytes, *, new_data_off_bytes: int, new_size: int, force_uncompressed: bool = True) -> bytes:
        if len(entry_bytes) < self.entry_size:
            raise ValueError("IDX entry bytes shorter than entry_size")
        b = bytearray(entry_bytes[:self.entry_size])

        def write_int(field: Optional[str], value: int):
            if not field:
                return
            try:
                s, e = self.field_span(field)
            except Exception:
                return
            width = e - s
            b[s:e] = int(value).to_bytes(width, self.endian, signed=False)

        stored_off = int(new_data_off_bytes)
        if self.shift_bits and self.offset_field:
            should_shift = (not self.vars_to_shift) or (self.offset_field in self.vars_to_shift)
            if should_shift:
                stored_off = stored_off >> self.shift_bits

        write_int(self.offset_field, stored_off)
        write_int(self.orig_size_field, int(new_size))
        if self.comp_size_field:
            write_int(self.comp_size_field, int(new_size))
        if self.comp_flag_field and force_uncompressed:
            write_int(self.comp_flag_field, 0)
        return bytes(b)


class ModLedger:
    def __init__(self, path: str):
        self.path = path

    def ensure_exists(self):
        os.makedirs(os.path.dirname(self.path), exist_ok=True)
        if not os.path.isfile(self.path):
            with open(self.path, "ab"):
                pass

    def iter_records(self, want_positions: bool = False):
        if not os.path.exists(self.path):
            return
        last_name = None
        with open(self.path, "rb") as f:
            while True:
                start = f.tell()
                b = f.read(1)
                if not b:
                    break
                nlen = int.from_bytes(b, "little")
                if nlen > 0:
                    last_name = f.read(nlen).decode("utf-8", errors="replace")
                idx_marker_b = f.read(1)
                if not idx_marker_b:
                    break
                idx_marker = idx_marker_b[0]
                entry_off_b = f.read(4)
                if len(entry_off_b) != 4:
                    break
                entry_off = int.from_bytes(entry_off_b, "little")
                entry_size_b = f.read(2)
                if len(entry_size_b) != 2:
                    break
                entry_size = int.from_bytes(entry_size_b, "little")
                entry_bytes = f.read(entry_size)
                if len(entry_bytes) != entry_size:
                    break
                end = f.tell()
                if want_positions:
                    yield (last_name, idx_marker, entry_off, entry_size, entry_bytes, start, end, nlen)
                else:
                    yield (last_name, idx_marker, entry_off, entry_size, entry_bytes)

    def list_unique_mods(self) -> List[str]:
        seen = set()
        out = []
        for name, *_ in self.iter_records():
            if name and name not in seen:
                seen.add(name)
                out.append(name)
        return out

    def is_enabled(self, mod_name: str) -> bool:
        target = (mod_name or "").strip().lower()
        if not target:
            return False
        for name, *_ in self.iter_records():
            if name and name.strip().lower() == target:
                return True
        return False

    def append_record(self, mod_name: str, idx_marker: int, entry_off: int, original_entry: bytes, entry_size: int, *, write_name: bool = True):
        self.ensure_exists()
        with open(self.path, "ab") as f:
            if write_name:
                nb = mod_name.encode("utf-8", errors="replace")
                f.write(len(nb).to_bytes(1, "little"))
                f.write(nb)
            else:
                f.write((0).to_bytes(1, "little"))
            f.write(bytes([idx_marker & 0xFF]))
            f.write(int(entry_off).to_bytes(4, "little", signed=False))
            f.write(int(entry_size).to_bytes(2, "little", signed=False))
            f.write(original_entry[:entry_size])

    def rewrite_without_mod(self, mod_name: str) -> bytes:
        kept = bytearray()
        target = (mod_name or "").strip().lower()
        with open(self.path, "rb") as f:
            for name, idx_marker, entry_off, entry_size, entry_bytes, start, end, nlen in self.iter_records(want_positions=True):
                if name and name.strip().lower() == target:
                    continue
                f.seek(start)
                kept.extend(f.read(end - start))
        return bytes(kept)

    def write_raw(self, blob: bytes):
        self.ensure_exists()
        with open(self.path, "wb") as f:
            f.write(blob)


class ModParser:
    def __init__(self, path: str):
        self.path = path

    def read(self, *, include_payloads: bool = True, include_media: bool = True) -> ParsedModPackage:
        with open(self.path, "rb") as f:
            sig_len = read_u8(f, "signature length")
            signature = read_exact(f, sig_len, "signature")
            if signature != ALDNOAH_SIGNATURE:
                raise ValueError("Unsupported mod signature. This manager expects the current Aldnoah package layout.")

            format_version = read_u8(f, "format version")
            if format_version not in ALDNOAH_COMPATIBLE_FORMAT_VERSIONS:
                raise ValueError(f"Unsupported Aldnoah mod format version: {format_version}")

            build_mode_byte = read_u8(f, "build mode")
            genre_id = read_u8(f, "genre id")
            genre_key = GENRE_ID_TO_KEY.get(genre_id)
            if genre_key is None:
                raise ValueError(f"Unknown genre id: {genre_id}")

            display_name = read_sized_ut8(f, 1, "display name")
            author = read_sized_ut8(f, 1, "author")
            version = read_sized_ut8(f, 1, "version")
            description = read_sized_ut8(f, 2, "description")
            preview_count = read_u8(f, "preview count")
            preview_images: List[bytes] = []
            for idx in range(preview_count):
                blob_size = read_u32(f, f"preview {idx + 1} size")
                if include_media:
                    blob = read_exact(f, blob_size, f"preview {idx + 1} image")
                    preview_images.append(blob)
                else:
                    f.seek(blob_size, os.SEEK_CUR)

            has_audio = bool(read_u8(f, "has audio"))
            audio_bytes: Optional[bytes] = None
            if has_audio:
                audio_size = read_u32(f, "audio size")
                if include_media:
                    blob = read_exact(f, audio_size, "audio bytes")
                    audio_bytes = blob
                else:
                    f.seek(audio_size, os.SEEK_CUR)

            file_count = read_u32(f, "file count")

            meta = ModMeta(
                display_name=display_name,
                author=author,
                version=version,
                description=description,
                file_count=file_count,
                genre=genre_key,
                build_mode="Release" if build_mode_byte else "Debug",
                format_version=format_version,
                preview_count=preview_count,
                has_audio=has_audio,
            )

            entries: List[ModFileEntry] = []
            for idx in range(file_count):
                stored_name = read_sized_ut8(f, 2, f"entry {idx + 1} stored name")
                sz = read_u32(f, f"entry {idx + 1} payload size")
                if not include_payloads:
                    f.seek(sz, os.SEEK_CUR)
                    continue
                blob = read_exact(f, sz, f"entry {idx + 1} payload")
                if sz < TAILDATA_LEN:
                    raise ValueError("A packaged entry is smaller than 6-byte taildata")
                payload = blob[:-TAILDATA_LEN]
                tail_raw = blob[-TAILDATA_LEN:]
                tail = TailData.parse(tail_raw, endian="little")
                entries.append(ModFileEntry(stored_name=stored_name, payload=payload, tail=tail))

            return ParsedModPackage(meta=meta, entries=entries, preview_images=preview_images, audio_bytes=audio_bytes)


@dataclass
class LibraryMod:
    path: str
    filename: str
    display_name: str
    author: str
    version: str
    description: str
    file_count: int
    enabled: bool
    genre: str
    subgroup: str
    build_mode: str = "Debug"
    format_version: int = 0
    preview_count: int = 0
    has_audio: bool = False
    parse_error: str = ""
    is_installer: bool = False
    installer_package_type: str = ""
    installer_asset_count: int = 0
    installer_payload_count: int = 0
    x: float = 0.0
    y: float = 0.0


@dataclass
class Constellation:
    genre: str
    label: str
    cx: float
    cy: float
    mods: List[LibraryMod] = field(default_factory=list)
    id: str = ""


class WinMMAudioPlayer:
    def __init__(self):
        self._buf = None

    def play_loop_bytes(self, wav_bytes: bytes):
        if not _PlaySoundW or not wav_bytes:
            return
        if not (len(wav_bytes) >= 12 and wav_bytes[:4] == b"RIFF" and wav_bytes[8:12] == b"WAVE"):
            return

        self.stop()
        self._buf = ctypes.create_string_buffer(wav_bytes)
        ptr = ctypes.cast(self._buf, ctypes.c_void_p)
        _PlaySoundW(ptr, None, SND_MEMORY | SND_ASYNC | SND_LOOP | SND_NODEFAULT)

    def stop(self):
        if not _PlaySoundW:
            self._buf = None
            return
        _PlaySoundW(None, None, SND_PURGE)
        self._buf = None


class ConstellationCanvas(tk.Canvas):
    def __init__(self, parent: tk.Misc, controller: "ModManagerWindowV2"):
        super().__init__(
            parent,
            bg=ORRERY_BG,
            highlightthickness=0,
            bd=0,
            relief="flat",
        )
        self.controller = controller
        self.camera_x = 0.0
        self.camera_y = 0.0
        self.zoom = 0.22
        self.dragging = False
        self.last_drag_xy = (0, 0)
        self.item_to_mod: Dict[int, LibraryMod] = {}
        self._background_stars = self.make_background_stars()
        self.phase = 0.0

        self.bind("<Configure>", lambda e: self.render())
        self.bind("<ButtonPress-1>", self.on_press)
        self.bind("<B1-Motion>", self.on_drag)
        self.bind("<ButtonRelease-1>", self.on_release)
        self.bind("<Double-Button-1>", self.on_double_click)
        self.bind("<MouseWheel>", self.on_mousewheel)
        self.bind("<Button-4>", lambda e: self.zoom_at(e.x, e.y, 1.12))
        self.bind("<Button-5>", lambda e: self.zoom_at(e.x, e.y, 1 / 1.12))
        self.after(120, self.tick)

    def tick(self):
        self.phase += 0.08
        if self.winfo_exists():
            self.render()
            self.after(120, self.tick)

    def make_background_stars(self) -> List[Tuple[float, float, int]]:
        rnd = random.Random(1337)
        stars = []
        for _ in range(260):
            stars.append((
                rnd.uniform(-WORLD_SIZE, WORLD_SIZE),
                rnd.uniform(-WORLD_SIZE, WORLD_SIZE),
                rnd.choice((1, 1, 1, 2, 2, 3)),
            ))
        return stars

    def fit_overview(self):
        self.camera_x = 0.0
        self.camera_y = 350.0
        self.zoom = 0.22
        self.render()

    def focus_world(self, wx: float, wy: float, zoom: Optional[float] = None):
        self.camera_x = wx
        self.camera_y = wy
        if zoom is not None:
            self.zoom = max(0.15, min(1.8, zoom))
        self.render()

    def world_to_screen(self, x: float, y: float) -> Tuple[float, float]:
        w = max(1, self.winfo_width())
        h = max(1, self.winfo_height())
        sx = (x - self.camera_x) * self.zoom + (w / 2.0)
        sy = (y - self.camera_y) * self.zoom + (h / 2.0)
        return sx, sy

    def screen_to_world(self, x: float, y: float) -> Tuple[float, float]:
        w = max(1, self.winfo_width())
        h = max(1, self.winfo_height())
        wx = (x - (w / 2.0)) / self.zoom + self.camera_x
        wy = (y - (h / 2.0)) / self.zoom + self.camera_y
        return wx, wy

    def zoom_at(self, sx: float, sy: float, factor: float):
        old_zoom = self.zoom
        new_zoom = max(0.15, min(1.8, old_zoom * factor))
        if abs(new_zoom - old_zoom) < 0.0001:
            return
        before_x, before_y = self.screen_to_world(sx, sy)
        self.zoom = new_zoom
        after_x, after_y = self.screen_to_world(sx, sy)
        self.camera_x += before_x - after_x
        self.camera_y += before_y - after_y
        self.render()

    def on_mousewheel(self, event):
        factor = 1.12 if event.delta > 0 else (1 / 1.12)
        self.zoom_at(event.x, event.y, factor)

    def on_press(self, event):
        self.dragging = False
        self.last_drag_xy = (event.x, event.y)

    def on_drag(self, event):
        self.dragging = True
        dx = event.x - self.last_drag_xy[0]
        dy = event.y - self.last_drag_xy[1]
        self.last_drag_xy = (event.x, event.y)
        self.camera_x -= dx / self.zoom
        self.camera_y -= dy / self.zoom
        self.render()

    def on_release(self, event):
        if self.dragging:
            return
        self.pick_item(event.x, event.y, focus_only=False)

    def on_double_click(self, event):
        mod = self.pick_item(event.x, event.y, focus_only=True)
        if mod is not None:
            self.focus_world(mod.x, mod.y, zoom=max(0.7, self.zoom))

    def pick_item(self, sx: float, sy: float, focus_only: bool) -> Optional[LibraryMod]:
        closest = self.find_overlapping(sx - 6, sy - 6, sx + 6, sy + 6)
        for item_id in reversed(closest):
            mod = self.item_to_mod.get(item_id)
            if mod is not None:
                if not focus_only:
                    self.controller.select_mod_record(mod)
                return mod
        if not focus_only:
            self.controller.clear_selection()
        return None

    def render(self):
        self.delete("all")
        self.item_to_mod.clear()
        self.draw_background()
        self.draw_genre_regions()
        self.draw_orrery_links()
        self.draw_constellations()

    def draw_background(self):
        width = max(1, self.winfo_width())
        height = max(1, self.winfo_height())
        self.create_rectangle(0, 0, width, height, fill=ORRERY_BG, outline="")
        self.create_rectangle(0, 0, width, int(height * 0.24), fill=ORRERY_BG_2, outline="")
        meta = SKY_MODE_META.get(self.controller.genre_filter, SKY_MODE_META["overview"])
        for idx in range(12):
            y = int(height * 0.12) + idx * 78
            sway = math.sin(self.phase * 0.7 + idx * 0.6) * 12
            self.create_line(0, y + sway, width, y - sway, fill=meta["field"], width=1)

        core_x, core_y = self.world_to_screen(0.0, 0.0)
        core_r = max(18, 70 * self.zoom)
        for ring_idx in range(3):
            r = core_r + ring_idx * 18 * self.zoom + math.sin(self.phase + ring_idx) * 3
            self.create_oval(core_x - r, core_y - r, core_x + r, core_y + r, outline="#6F568F", width=1)
        self.create_oval(core_x - core_r * 0.34, core_y - core_r * 0.34, core_x + core_r * 0.34, core_y + core_r * 0.34, fill=REACTOR_CORE, outline="")
        if self.controller.base_dir:
            self.create_text(core_x, core_y + core_r + 18, text="Install Reactor", fill="#EBDDA8", font=("Segoe UI", 9, "bold"))

        for x, y, size in self._background_stars:
            sx, sy = self.world_to_screen(x, y)
            if -10 <= sx <= self.winfo_width() + 10 and -10 <= sy <= self.winfo_height() + 10:
                fill = "#A587C6" if self.controller.genre_filter == "overview" else "#6D5D86"
                self.create_oval(sx - size, sy - size, sx + size, sy + size, fill=fill, outline="")

    def draw_genre_regions(self):
        mode = self.controller.genre_filter
        for genre in GENRES:
            cx, cy = GENRE_CENTERS[genre]
            sx, sy = self.world_to_screen(cx, cy)
            focused = mode == "overview" or mode == genre
            radius = (420 if focused else 270) * self.zoom
            self.create_text(
                sx,
                sy - (radius + 26),
                text=GENRE_LABELS[genre],
                fill="#DBC7EF" if focused else "#5B506B",
                font=("Segoe UI", max(11, int(10 + self.zoom * 7)), "bold"),
            )

    def star_fill_for_mod(self, mod: LibraryMod) -> str:
        return mod_visual_state(
            mod,
            selected_filename=self.controller.selected.filename if self.controller.selected else "",
            conflict_names=self.controller.conflict_mod_names,
            signal=self.controller.search_var.get(),
        )["fill"]

    def star_outline_for_mod(self, mod: LibraryMod) -> str:
        return mod_visual_state(
            mod,
            selected_filename=self.controller.selected.filename if self.controller.selected else "",
            conflict_names=self.controller.conflict_mod_names,
            signal=self.controller.search_var.get(),
        )["outline"]

    def mod_matches(self, mod: LibraryMod) -> bool:
        return signal_matches(mod, self.controller.search_var.get())

    def draw_orrery_links(self):
        filename_map = {mod.filename: mod for mod in self.controller.library_mods}
        links = list(self.controller.orrery_links) + enabled_chain_links(self.controller.library_mods)
        for link in links:
            left = filename_map.get(link.left)
            right = filename_map.get(link.right)
            if not left or not right:
                continue
            if self.controller.genre_filter != "overview" and left.genre != self.controller.genre_filter and right.genre != self.controller.genre_filter:
                continue
            if self.controller.search_var.get().strip() and not (self.mod_matches(left) or self.mod_matches(right)):
                continue
            x1, y1 = self.world_to_screen(left.x, left.y)
            x2, y2 = self.world_to_screen(right.x, right.y)
            dash = (6, 4) if link.kind == "conflict" else None
            color = link.color if link.kind != "enabled" else ENABLED_CHAIN
            if link.kind == "conflict":
                wobble = math.sin(self.phase * 2.0 + x1 * 0.01) * 5
                mx = (x1 + x2) / 2 + wobble
                my = (y1 + y2) / 2 - wobble
                self.create_line(x1, y1, mx, my, x2, y2, fill=color, width=link.width, dash=dash, smooth=True)
            else:
                self.create_line(x1, y1, x2, y2, fill=color, width=link.width, dash=dash)

    def draw_constellations(self):
        label_font = ("Segoe UI", max(9, int(9 + self.zoom * 5)), "bold")
        mode = self.controller.genre_filter
        for const in self.controller.constellations:
            focused = mode == "overview" or const.genre == mode

            visible_mods = list(const.mods)
            if not visible_mods:
                continue

            pts = []
            for mod in visible_mods:
                sx, sy = self.world_to_screen(mod.x, mod.y)
                pts.append((mod, sx, sy))

            if len(pts) >= 2:
                for idx in range(len(pts) - 1):
                    _, x1, y1 = pts[idx]
                    _, x2, y2 = pts[idx + 1]
                    self.create_line(x1, y1, x2, y2, fill="#EEE5FF" if focused else NEBULA_DIM, width=max(1, int(self.zoom * 2)))

            if self.zoom >= 0.20 and focused:
                anchor_sx, anchor_sy = self.world_to_screen(const.cx, const.cy)
                self.create_text(anchor_sx, anchor_sy - max(18, 30 * self.zoom), text=const.label, fill="#bba7d0", font=label_font)

            for mod, sx, sy in pts:
                if not (-24 <= sx <= self.winfo_width() + 24 and -24 <= sy <= self.winfo_height() + 24):
                    continue
                visual = mod_visual_state(
                    mod,
                    selected_filename=self.controller.selected.filename if self.controller.selected else "",
                    conflict_names=self.controller.conflict_mod_names,
                    signal=self.controller.search_var.get(),
                )
                dim = (not focused) or visual["alpha_dim"]
                radius = 6 + (2 if visual["enabled"] else 0) + (1 if visual["package"] else 0)
                radius += math.sin(self.phase * 3.0 + sx * 0.02) * (2 if visual["enabled"] else 0)
                fill = "#312944" if dim else visual["fill"]
                outline = NEBULA_DIM if dim else visual["outline"]
                if visual["matched"] and self.controller.search_var.get().strip():
                    ring = radius + 8 + math.sin(self.phase * 2.4) * 3
                    self.create_oval(sx - ring, sy - ring, sx + ring, sy + ring, outline=SIGNAL_RING, width=1)
                if visual["selected"]:
                    for ring_idx in range(3):
                        halo = radius + 8 + ring_idx * 6 + math.sin(self.phase + ring_idx) * 2
                        self.create_oval(sx - halo, sy - halo, sx + halo, sy + halo, outline="#FFF4FF", width=1)
                item = self.create_oval(
                    sx - radius,
                    sy - radius,
                    sx + radius,
                    sy + radius,
                    fill=fill,
                    outline=outline,
                    width=3 if visual["conflict"] else 2,
                )
                self.item_to_mod[item] = mod
                if visual["parse_error"]:
                    crack = self.create_line(sx - radius * 0.5, sy - radius * 0.8, sx + radius * 0.1, sy - 1, sx - radius * 0.2, sy + radius * 0.8, fill="#FFD0D6", width=1)
                    self.item_to_mod[crack] = mod
                if visual["package"]:
                    twin = self.create_oval(sx + radius * 0.55, sy - radius * 0.9, sx + radius * 1.25, sy - radius * 0.2, fill="#EEE5FF" if not dim else "#403650", outline=outline, width=1)
                    self.item_to_mod[twin] = mod
                if visual["installer"]:
                    eclipse = self.create_oval(sx - radius * 0.55, sy - radius * 0.55, sx + radius * 0.55, sy + radius * 0.55, fill=ORRERY_BG, outline="#E8D7FF", width=1)
                    self.item_to_mod[eclipse] = mod
                if self.zoom >= 0.72:
                    self.create_text(sx, sy - 18, text=mod.display_name[:22], fill="#e7daf5" if not dim else "#5D526B", font=("Segoe UI", 9))
                if False and mod.enabled:
                    note = self.create_text(sx + 12, sy - 10, text="✦", fill="#fff4ff", font=("Segoe UI Symbol", 10, "bold"))
                    self.item_to_mod[note] = mod
                elif mod.parse_error:
                    err = self.create_text(sx + 10, sy - 10, text="!", fill="#ffd9d9", font=("Segoe UI", 10, "bold"))
                    self.item_to_mod[err] = mod


class ModManagerWindowV2(tk.Toplevel):
    def __init__(self, parent: tk.Misc, game_id: str, profile: dict):
        super().__init__(parent)
        self.game_id = game_id
        self.profile = profile

        self.configure(bg=LILAC)
        self.title(f"{profile['display_name']} Constellation Manager")
        self.geometry("1600x940")

        setup_lilac_styles_if_needed(self)

        self.base_dir: Optional[str] = None
        self.cfg: Optional[dict] = None
        self.layout: Optional[RefLayout] = None
        self.containers: List[str] = []
        self.idx_files: List[str] = []
        self.container_paths: Dict[int, str] = {}
        self.idx_paths: Dict[int, str] = {}

        self.game_mod_dir = ensure_dir(os.path.join(BASE_MODS_DIR, self.game_id))
        self.ledger_path = os.path.join(self.game_mod_dir, profile["mods_file"])
        self.ledger = ModLedger(self.ledger_path)

        self.orig_sizes_path = os.path.join(self.game_mod_dir, "orig_container_sizes.json")
        self.state_path = os.path.join(self.game_mod_dir, "manager_state.json")
        self.installer_state_path = os.path.join(self.game_mod_dir, "installer_state.json")

        self.search_var = tk.StringVar(value="")
        self.genre_filter = "overview"
        self.audio_muted = tk.BooleanVar(value=False)
        self.status_var = tk.StringVar(value="Ready.")

        self.library_mods: List[LibraryMod] = []
        self.constellations: List[Constellation] = []
        self.mod_targets: Dict[str, Set[Tuple[int, int]]] = {}
        self.mod_target_details: Dict[str, Dict[Tuple[int, int], Set[str]]] = {}
        self.installer_target_cache: Dict[str, Set[Tuple[int, int]]] = {}
        self.installer_target_detail_cache: Dict[str, Dict[Tuple[int, int], Set[str]]] = {}
        self.orrery_links = []
        self.conflict_mod_names = set()
        self.selected: Optional[LibraryMod] = None
        self.detail_position: Optional[Tuple[int, int]] = None
        self.detail_drag_start: Tuple[int, int] = (0, 0)
        self.detail_drag_origin: Tuple[int, int] = (0, 0)
        self.detail_media_cache: Dict[str, Tuple[List[bytes], Optional[bytes]]] = {}
        self.detail_preview_images: List[bytes] = []
        self.detail_audio_bytes: Optional[bytes] = None
        self.detail_preview_index = 0
        self.detail_preview_photo = None
        self.audio_player = WinMMAudioPlayer()

        self.load_state_and_autoset_install()
        self.build_gui()
        self.scan_library()
        self.canvas.fit_overview()
        self.bind("<Configure>", self.on_window_configure)

    def lilac_label(self, parent, **kw):
        try:
            bg = parent.cget("bg")
        except Exception:
            bg = LILAC
        fg = TEXT if str(bg).lower() in {LENS_BG.lower(), ORRERY_BG.lower(), ORRERY_BG_2.lower(), LENS_PANEL.lower()} else "black"
        base = dict(bg=bg, fg=fg, bd=0, relief="flat", highlightthickness=0, takefocus=0)
        base.update(kw)
        return tk.Label(parent, **base)

    def load_state(self) -> dict:
        try:
            if os.path.isfile(self.state_path):
                with open(self.state_path, "r", encoding="utf-8") as f:
                    return json.load(f) or {}
        except Exception:
            pass
        return {}

    def save_state(self, data: dict):
        try:
            os.makedirs(os.path.dirname(self.state_path), exist_ok=True)
            with open(self.state_path, "w", encoding="utf-8") as f:
                json.dump(data or {}, f, indent=2)
        except Exception:
            pass

    def load_installer_state(self) -> dict:
        try:
            if os.path.isfile(self.installer_state_path):
                with open(self.installer_state_path, "r", encoding="utf-8") as f:
                    return json.load(f) or {}
        except Exception:
            pass
        return {}

    def save_installer_state(self, data: dict):
        try:
            os.makedirs(os.path.dirname(self.installer_state_path), exist_ok=True)
            if data:
                with open(self.installer_state_path, "w", encoding="utf-8") as f:
                    json.dump(data, f, indent=2)
            elif os.path.exists(self.installer_state_path):
                os.remove(self.installer_state_path)
        except Exception:
            pass

    def clear_installer_selection_state(self, filename: str):
        state = self.load_installer_state()
        if filename in state:
            state.pop(filename, None)
            self.save_installer_state(state)

    def installer_targets_from_state(self, filename: str) -> Set[Tuple[int, int]]:
        entry = self.load_installer_state().get(filename, {})
        records = entry.get("records", []) if isinstance(entry, dict) else []
        targets: Set[Tuple[int, int]] = set()
        for record in records:
            try:
                targets.add((int(record["idx_marker"]), int(record["entry_off"])))
            except Exception:
                continue
        return targets

    def installer_target_details_from_state(self, filename: str) -> Dict[Tuple[int, int], Set[str]]:
        entry = self.load_installer_state().get(filename, {})
        records = entry.get("records", []) if isinstance(entry, dict) else []
        details: Dict[Tuple[int, int], Set[str]] = {}
        for record in records:
            try:
                target = (int(record["idx_marker"]), int(record["entry_off"]))
            except Exception:
                continue
            stored_name = str(record.get("stored_name") or record.get("source_name") or "installer payload")
            details.setdefault(target, set()).add(stored_name)
        return details

    def installer_targets_from_package(self, path: str) -> Set[Tuple[int, int]]:
        cached = self.installer_target_cache.get(path)
        if cached is not None:
            return cached
        targets: Set[Tuple[int, int]] = set()
        try:
            package = AldnoahInstallerReader().read(
                path,
                include_blobs=False,
                include_asset_blobs=False,
                include_payload_blobs=True,
            )
            for payload in package.payloads:
                if len(payload.data) < TAILDATA_LEN:
                    continue
                tail = TailData.parse(payload.data[-TAILDATA_LEN:], endian="little")
                targets.add((tail.idx_marker, tail.entry_off))
        except Exception:
            targets = set()
        self.installer_target_cache[path] = targets
        return targets

    def installer_target_details_from_package(self, path: str) -> Dict[Tuple[int, int], Set[str]]:
        cached = self.installer_target_detail_cache.get(path)
        if cached is not None:
            return cached
        details: Dict[Tuple[int, int], Set[str]] = {}
        try:
            package = AldnoahInstallerReader().read(
                path,
                include_blobs=False,
                include_asset_blobs=False,
                include_payload_blobs=True,
            )
            for payload in package.payloads:
                if len(payload.data) < TAILDATA_LEN:
                    continue
                tail = TailData.parse(payload.data[-TAILDATA_LEN:], endian="little")
                details.setdefault((tail.idx_marker, tail.entry_off), set()).add(payload.stored_name or payload.source_name or "installer payload")
        except Exception:
            details = {}
        self.installer_target_detail_cache[path] = details
        self.installer_target_cache[path] = set(details.keys())
        return details

    @staticmethod
    def target_details_from_entries(entries: List[ModFileEntry]) -> Dict[Tuple[int, int], Set[str]]:
        details: Dict[Tuple[int, int], Set[str]] = {}
        for entry in entries:
            details.setdefault((entry.tail.idx_marker, entry.tail.entry_off), set()).add(entry.stored_name or "payload")
        return details

    def record_installer_selection(self, filename: str, option_ids: List[str], payloads: List, entries: List[ModFileEntry], package_type: str = "wizard"):
        records = []
        for payload, entry in zip(payloads, entries):
            records.append({
                "payload_id": payload.payload_id,
                "stored_name": payload.stored_name,
                "source_name": payload.source_name,
                "idx_marker": int(entry.tail.idx_marker),
                "entry_off": int(entry.tail.entry_off),
            })
        state = self.load_installer_state()
        state[filename] = {
            "package_type": package_type,
            "selected_option_ids": list(option_ids),
            "payload_ids": [payload.payload_id for payload in payloads],
            "records": records,
        }
        self.save_installer_state(state)

    def load_state_and_autoset_install(self):
        state = self.load_state()
        install = state.get("install_folder")
        if isinstance(install, str) and install and os.path.isdir(install):
            try:
                self.set_install_folder_path(install, silent=True)
            except Exception:
                pass

        cont = state.get("container_paths") or {}
        if isinstance(cont, dict):
            for k, v in cont.items():
                try:
                    ki = int(k)
                    if isinstance(v, str) and os.path.isfile(v):
                        self.container_paths[ki] = v
                except Exception:
                    continue

        idxp = state.get("idx_paths") or {}
        if isinstance(idxp, dict):
            for k, v in idxp.items():
                try:
                    ki = int(k)
                    if isinstance(v, str) and os.path.isfile(v):
                        self.idx_paths[ki] = v
                except Exception:
                    continue

    def set_install_folder_path(self, base: str, *, silent: bool = False):
        if not base or not os.path.isdir(base):
            raise ValueError("Invalid install folder")
        try:
            cfg = schema_to_ref_dict(get_game_schema(self.game_id))
        except Exception as e:
            if not silent:
                messagebox.showerror("Schema Error", f"Failed to load schema for {self.game_id}:\n{e}")
            raise

        self.base_dir = base
        self.cfg = cfg
        self.layout = RefLayout(cfg)

        containers = cfg.get("Containers", [])
        idx_files = cfg.get("IDX_Files", [])
        if isinstance(containers, str):
            containers = [containers]
        if isinstance(idx_files, str):
            idx_files = [idx_files]
        self.containers = list(containers)
        self.idx_files = list(idx_files)

        self.idx_paths.clear()
        for i, idx_name in enumerate(self.idx_files):
            p = os.path.join(self.base_dir, str(idx_name))
            if os.path.isfile(p):
                self.idx_paths[i] = p

        self.capture_original_sizes_from_install()

        state = self.load_state()
        state["install_folder"] = self.base_dir
        state.setdefault("container_paths", {})
        state.setdefault("idx_paths", {})
        self.save_state(state)

    def build_gui(self):
        top = tk.Frame(self, bg=ORRERY_BG_2, height=64)
        top.pack(side=tk.TOP, fill=tk.X)
        top.pack_propagate(False)

        tk.Button(top, text="Set Install Folder", command=self.set_install_folder, width=16).pack(side=tk.LEFT, padx=(10, 6), pady=10)
        tk.Button(top, text="Add Mod Files", command=self.add_mod_files, width=14).pack(side=tk.LEFT, padx=6, pady=10)
        tk.Button(top, text="Rescan Library", command=self.rescan_and_render, width=14).pack(side=tk.LEFT, padx=6, pady=10)
        overview_button = tk.Button(top, text="Overview", command=self.show_overview, width=10)
        overview_button.pack(side=tk.LEFT, padx=6, pady=10)
        tk.Button(top, text="Disable All", command=self.disable_all, width=12).pack(side=tk.LEFT, padx=6, pady=10)

        tk.Label(top, text="Signal:", bg=ORRERY_BG_2, fg=TEXT, bd=0, relief="flat").pack(side=tk.LEFT, padx=(20, 4))
        search = tk.Entry(top, textvariable=self.search_var, width=28)
        search.configure(bg="#0B0811", fg=TEXT, insertbackground=SIGNAL_RING, relief="flat", bd=0, highlightthickness=1, highlightbackground="#4B3A66")
        search.pack(side=tk.LEFT, padx=(0, 8))
        search.bind("<KeyRelease>", lambda e: self.on_search_change())

        self.genre_buttons: Dict[str, tk.Button] = {"overview": overview_button}
        for label, value in [("Universal Sky", "all"), ("Texture Sky", "texture"), ("Model Sky", "model"), ("Text Sky", "text"), ("Overhaul Sky", "overhaul"), ("Misc Sky", "misc")]:
            btn = tk.Button(top, text=label, width=12, command=lambda g=value: self.set_genre_filter(g))
            btn.pack(side=tk.LEFT, padx=2, pady=10)
            self.genre_buttons[value] = btn

        self.mute_cb = tk.Checkbutton(
            top,
            text="Mute Theme Audio",
            variable=self.audio_muted,
            command=self.on_audio_toggle,
            bg=ORRERY_BG_2,
            fg=TEXT,
            activebackground=ORRERY_BG_2,
            activeforeground=TEXT,
            anchor="w",
        )
        self.mute_cb.pack(side=tk.RIGHT, padx=(6, 12), pady=10)

        self.canvas = ConstellationCanvas(self, self)
        self.canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        self.detail = tk.Frame(self, bg=LENS_BG, width=430, highlightthickness=1, highlightbackground=LENS_EDGE)
        self.detail.place_forget()
        self.build_detail_panel()

        bottom = tk.Frame(self, bg=LILAC, height=34)
        bottom.pack(side=tk.BOTTOM, fill=tk.X)
        bottom.pack_propagate(False)
        self.status_label = self.lilac_label(bottom, textvariable=self.status_var, fg="green")
        self.status_label.pack(side=tk.LEFT, padx=10, pady=8)

        self.update_filter_buttons()

    def build_detail_panel(self):
        self.detail_genre_var = tk.StringVar(value="misc")
        self.detail_subgroup_var = tk.StringVar(value="")
        self.preview_counter_var = tk.StringVar(value="0 / 0")
        self.audio_state_var = tk.StringVar(value="Theme Audio: No embedded WAV")

        self.detail_grip = tk.Label(
            self.detail,
            text="Orbital Lens  |  drag",
            bg=LENS_PANEL,
            fg=TEXT_MUTED,
            font=("Segoe UI", 9, "bold"),
            anchor="w",
            cursor="fleur",
            padx=10,
            pady=5,
        )
        self.detail_grip.pack(fill="x", padx=0, pady=(0, 6))
        self.detail_grip.bind("<ButtonPress-1>", self.begin_detail_drag)
        self.detail_grip.bind("<B1-Motion>", self.drag_detail_panel)

        self.detail_title = self.lilac_label(self.detail, text="", font=("Segoe UI", 13, "bold"), fg=LENS_GOLD, wraplength=390, justify="left")
        self.detail_title.pack(fill="x", padx=14, pady=(0, 4))
        self.detail_title.bind("<ButtonPress-1>", self.begin_detail_drag)
        self.detail_title.bind("<B1-Motion>", self.drag_detail_panel)

        self.detail_meta = self.lilac_label(self.detail, text="", fg=TEXT_MUTED, justify="left", anchor="nw")
        self.detail_meta.pack(fill="x", padx=14)

        actions = tk.Frame(self.detail, bg=LENS_BG)
        actions.pack(fill="x", padx=14, pady=(8, 2))
        actions.grid_columnconfigure(0, weight=1)
        actions.grid_columnconfigure(1, weight=1)

        self.enable_btn = tk.Button(actions, text="Enable", command=self.apply_selected_mod)
        self.enable_btn.grid(row=0, column=0, sticky="ew", padx=(0, 6), pady=(0, 6))
        self.disable_btn = tk.Button(actions, text="Disable", command=self.disable_selected)
        self.disable_btn.grid(row=0, column=1, sticky="ew", padx=(6, 0), pady=(0, 6))
        tk.Button(actions, text="Reveal", command=self.reveal_selected_mod).grid(row=1, column=0, sticky="ew", padx=(0, 6), pady=(0, 6))
        tk.Button(actions, text="Close Lens", command=self.clear_selection).grid(row=1, column=1, sticky="ew", padx=(6, 0), pady=(0, 6))
        self.conflict_btn = tk.Button(actions, text="Inspect Conflict", command=self.show_conflict_panel)
        self.conflict_btn.grid(row=2, column=0, columnspan=2, sticky="ew", pady=(0, 6))
        self.conflict_btn.grid_remove()

        form = tk.Frame(self.detail, bg=LENS_BG)
        form.pack(fill="x", padx=14, pady=(4, 8))
        form.grid_columnconfigure(1, weight=1)

        self.lilac_label(form, text="Sky Override:").grid(row=0, column=0, sticky="w", pady=(0, 6))
        self.genre_combo = ttk.Combobox(form, state="readonly", values=GENRES, textvariable=self.detail_genre_var, width=18)
        self.genre_combo.grid(row=0, column=1, sticky="ew", pady=(0, 6))

        self.lilac_label(form, text="Constellation:").grid(row=1, column=0, sticky="w", pady=(0, 6))
        self.subgroup_entry = tk.Entry(form, textvariable=self.detail_subgroup_var)
        self.subgroup_entry.grid(row=1, column=1, sticky="ew", pady=(0, 6))

        tk.Button(form, text="Save Sky Override", command=self.save_selected_classification).grid(row=2, column=0, columnspan=2, sticky="ew")

        preview_card = tk.Frame(self.detail, bg=LENS_PANEL, highlightthickness=1, highlightbackground=LENS_EDGE)
        preview_card.pack(fill="x", padx=14, pady=(12, 10))

        preview_head = tk.Frame(preview_card, bg=LENS_PANEL)
        preview_head.pack(fill="x", padx=10, pady=(10, 6))
        tk.Label(preview_head, text="Preview Gallery", bg=LENS_PANEL, fg=TEXT, font=("Segoe UI", 11, "bold")).pack(side=tk.LEFT)
        tk.Label(preview_head, textvariable=self.preview_counter_var, bg=LENS_PANEL, fg=TEXT_MUTED, font=("Segoe UI", 9)).pack(side=tk.RIGHT)

        self.detail_preview_canvas = tk.Canvas(
            preview_card,
            width=DETAIL_PREVIEW_SIZE[0],
            height=110,
            bg=DETAIL_PREVIEW_BG,
            highlightthickness=0,
            bd=0,
            relief="flat",
        )
        self.detail_preview_canvas.pack(fill="x", padx=10, pady=(0, 8))
        self.detail_preview_canvas.bind("<Configure>", lambda _event: self.render_detail_preview())

        nav = tk.Frame(preview_card, bg=LENS_PANEL)
        nav.pack(fill="x", padx=10, pady=(0, 8))
        self.preview_prev_btn = tk.Button(nav, text="Prev", width=8, command=lambda: self.cycle_detail_preview(-1))
        self.preview_prev_btn.pack(side=tk.LEFT)
        self.preview_next_btn = tk.Button(nav, text="Next", width=8, command=lambda: self.cycle_detail_preview(1))
        self.preview_next_btn.pack(side=tk.LEFT, padx=(6, 0))
        tk.Label(nav, textvariable=self.audio_state_var, bg=LENS_PANEL, fg=TEXT_MUTED, font=("Segoe UI", 9), anchor="e", justify="right").pack(side=tk.RIGHT)

        desc_wrap = tk.Frame(self.detail, bg=LENS_BG)
        desc_wrap.pack(fill="both", expand=False, padx=14)
        tk.Label(desc_wrap, text="Description Fragments", bg=LENS_BG, fg=TEXT, font=("Segoe UI", 10, "bold"), anchor="w").pack(fill="x", pady=(0, 4))
        self.detail_desc = tk.Text(desc_wrap, wrap=tk.WORD, height=3, width=40)
        self.detail_desc.pack(fill="x")
        self.detail_desc.config(state=tk.DISABLED, bg=LENS_PANEL, fg=TEXT, insertbackground=TEXT, relief="flat", bd=0)

        self.render_detail_preview()

    def load_media_for_mod(self, mod: LibraryMod) -> Tuple[List[bytes], Optional[bytes]]:
        cached = self.detail_media_cache.get(mod.path)
        if cached is not None:
            return cached
        if mod.is_installer:
            package = AldnoahInstallerReader().read(
                mod.path,
                include_blobs=False,
                include_asset_blobs=True,
                include_payload_blobs=False,
            )
            preview_roles = {"preview", "banner", "option_preview", "icon"}
            previews = [
                asset.data
                for asset in package.assets
                if asset.role in preview_roles and asset.data and str(asset.mime_type).lower().startswith("image/")
            ]
            audio = next((asset.data for asset in package.assets if asset.role == "audio" and asset.data), None)
            cached = (previews, audio)
            self.detail_media_cache[mod.path] = cached
            return cached
        parsed = ModParser(mod.path).read(include_payloads=False, include_media=True)
        cached = (parsed.preview_images, parsed.audio_bytes)
        self.detail_media_cache[mod.path] = cached
        return cached

    def render_detail_preview(self):
        canvas = self.detail_preview_canvas
        canvas.delete("all")
        width = max(1, canvas.winfo_width())
        if width <= 1:
            width = max(1, int(canvas.cget("width")))
        height = max(1, canvas.winfo_height())
        if height <= 1:
            height = max(1, int(canvas.cget("height")))
        canvas.create_rectangle(0, 0, width, height, fill=DETAIL_PREVIEW_BG, outline="")
        self.detail_preview_photo = None

        total = len(self.detail_preview_images)
        if total <= 0:
            self.preview_counter_var.set("0 / 0")
            self.preview_prev_btn.config(state=tk.DISABLED)
            self.preview_next_btn.config(state=tk.DISABLED)
            canvas.create_text(width // 2, height // 2 - 10, text="No Preview Image", fill="#F4EDFF", font=("Segoe UI", 16, "bold"))
            canvas.create_text(width // 2, height // 2 + 18, text="This mod does not embed preview art.", fill="#CABEE0", font=("Segoe UI", 10))
            return

        self.detail_preview_index %= total
        self.preview_counter_var.set(f"{self.detail_preview_index + 1} / {total}")
        nav_state = tk.NORMAL if total > 1 else tk.DISABLED
        self.preview_prev_btn.config(state=nav_state)
        self.preview_next_btn.config(state=nav_state)

        try:
            with Image.open(BytesIO(self.detail_preview_images[self.detail_preview_index])) as img:
                if img.mode not in ("RGB", "RGBA"):
                    img = img.convert("RGBA" if "A" in img.getbands() else "RGB")
                if img.mode == "RGBA":
                    composite = Image.new("RGBA", img.size, (18, 13, 24, 255))
                    composite.alpha_composite(img)
                    img = composite.convert("RGB")
                else:
                    img = img.convert("RGB")
                if self.selected and self.selected.is_installer:
                    img = trim_installer_preview_padding(img)
                resampling = getattr(getattr(Image, "Resampling", Image), "LANCZOS")
                frame = img.resize((width, height), resampling)
                self.detail_preview_photo = ImageTk.PhotoImage(frame)
                canvas.create_image(0, 0, anchor="nw", image=self.detail_preview_photo)
                canvas.create_rectangle(0, 0, width, height, outline="#B9A7D8")
        except Exception as exc:
            canvas.create_text(width // 2, height // 2, text=f"Preview error:\n{exc}", fill="#FFD2DA", font=("Segoe UI", 10), width=280)

    def cycle_detail_preview(self, delta: int):
        if not self.detail_preview_images:
            return
        self.detail_preview_index = (self.detail_preview_index + delta) % len(self.detail_preview_images)
        self.render_detail_preview()

    def refresh_selected_audio(self):
        if not self.selected:
            self.audio_player.stop()
            self.audio_state_var.set("Theme Audio: No mod selected")
            return

        if not self.detail_audio_bytes:
            self.audio_player.stop()
            self.audio_state_var.set("Theme Audio: No embedded WAV")
            return

        if self.audio_muted.get():
            self.audio_player.stop()
            self.audio_state_var.set("Theme Audio: Muted")
            return

        self.audio_player.play_loop_bytes(self.detail_audio_bytes)
        self.audio_state_var.set("Theme Audio: Playing from memory")

    def on_audio_toggle(self):
        self.refresh_selected_audio()
        if self.audio_muted.get():
            self.set_status("Muted embedded theme audio.", "blue")
        else:
            self.set_status("Theme audio unmuted.", "green")

    def detail_panel_size(self) -> Tuple[int, int]:
        panel_width = 430
        panel_height = 760
        return panel_width, panel_height

    def clamp_detail_position(self, x: int, y: int) -> Tuple[int, int]:
        panel_width, panel_height = self.detail_panel_size()
        canvas_w = max(1, self.canvas.winfo_width())
        canvas_h = max(1, self.canvas.winfo_height())
        max_x = max(12, canvas_w - panel_width - 12)
        max_y = max(12, canvas_h - panel_height - 12)
        return max(12, min(int(x), max_x)), max(12, min(int(y), max_y))

    def default_detail_position(self, mod: LibraryMod) -> Tuple[int, int]:
        panel_width, panel_height = self.detail_panel_size()
        sx, sy = self.canvas.world_to_screen(mod.x, mod.y)
        x = int(sx + 34)
        y = int(sy - panel_height * 0.50)
        if x + panel_width + 12 > self.canvas.winfo_width():
            x = int(sx - panel_width - 34)
        return self.clamp_detail_position(x, y)

    def begin_detail_drag(self, event):
        self.detail_drag_start = (event.x_root, event.y_root)
        self.detail_drag_origin = self.detail_position or self.clamp_detail_position(24, 24)

    def drag_detail_panel(self, event):
        ox, oy = self.detail_drag_origin
        sx, sy = self.detail_drag_start
        self.detail_position = self.clamp_detail_position(ox + event.x_root - sx, oy + event.y_root - sy)
        self.place_detail_panel()

    def place_detail_panel(self):
        if not self.selected or not self.detail.winfo_exists():
            return
        panel_width, panel_height = self.detail_panel_size()
        if self.detail_position is None:
            self.detail_position = self.default_detail_position(self.selected)
        x, y = self.clamp_detail_position(*self.detail_position)
        self.detail_position = (x, y)
        self.detail.place(in_=self.canvas, x=x, y=y, width=panel_width, height=panel_height)
        self.detail.lift()

    def on_window_configure(self, _event=None):
        if self.selected and self.detail.winfo_ismapped():
            if self.detail_position is not None:
                self.detail_position = self.clamp_detail_position(*self.detail_position)
            self.place_detail_panel()

    def set_status(self, text: str, color: str = "green"):
        self.status_var.set(text)
        try:
            self.status_label.config(fg=color)
        except Exception:
            pass

    def update_filter_buttons(self):
        for key, btn in self.genre_buttons.items():
            selected = key == self.genre_filter
            meta = SKY_MODE_META.get(key, SKY_MODE_META["overview"])
            btn.config(
                relief=tk.FLAT,
                bg=meta["accent"] if selected else "#241A35",
                fg=TEXT_DARK if selected else TEXT,
                activebackground=meta["accent"],
                activeforeground=TEXT_DARK,
                highlightthickness=1,
                highlightbackground=meta["accent"] if selected else "#4B3A66",
            )

    def set_genre_filter(self, genre: str):
        self.genre_filter = genre
        self.update_filter_buttons()
        cx, cy = GENRE_CENTERS.get(genre, (0.0, 0.0))
        mode_meta = SKY_MODE_META.get(genre, SKY_MODE_META["overview"])
        self.canvas.focus_world(cx, cy, zoom=max(float(mode_meta.get("zoom", 0.34)), self.canvas.zoom))
        self.canvas.render()
        self.set_status(str(mode_meta.get("status", f"{genre.title()} sky selected.")), "blue")

    def on_search_change(self):
        text = self.search_var.get().strip().lower()
        self.canvas.render()
        if not text:
            self.set_status("Signal cleared. Orrery visible.", "blue")
            return
        matches = [m for m in self.library_mods if signal_matches(m, text)]
        self.set_status(f"Signal scan found {len(matches)} match(es).", "blue")
        if len(matches) == 1:
            m = matches[0]
            self.select_mod_record(m)
            self.canvas.focus_world(m.x, m.y, zoom=max(0.62, self.canvas.zoom))

    def show_overview(self):
        self.genre_filter = "overview"
        self.update_filter_buttons()
        self.canvas.fit_overview()
        self.canvas.render()
        self.set_status(SKY_MODE_META["overview"]["status"], "blue")

    def clear_selection(self):
        self.selected = None
        self.refresh_conflict_context()
        self.detail_preview_images = []
        self.detail_audio_bytes = None
        self.detail_preview_index = 0
        self.audio_player.stop()
        self.audio_state_var.set("Theme Audio: No mod selected")
        self.conflict_btn.grid_remove()
        self.render_detail_preview()
        self.detail.place_forget()
        self.canvas.render()

    def select_mod_record(self, mod: LibraryMod):
        self.selected = mod
        if mod.is_installer and not mod.parse_error:
            state_targets = self.installer_targets_from_state(mod.filename) if mod.enabled else set()
            state_details = self.installer_target_details_from_state(mod.filename) if mod.enabled else {}
            package_details = {} if state_targets else self.installer_target_details_from_package(mod.path)
            self.mod_targets[mod.filename] = state_targets or set(package_details.keys())
            self.mod_target_details[mod.filename] = state_details or package_details
        self.refresh_conflict_context()
        self.detail_title.config(text=mod.display_name)
        if mod.is_installer:
            lines = [
                f"File: {mod.filename}",
                f"Author: {mod.author or 'Unknown'}",
                f"Version: {mod.version or 'Unknown'}",
                f"Type: .Aldnoah Installer",
                f"Sky: {GENRE_KEY_TO_LABEL.get(mod.genre, mod.genre.title())}",
                f"Constellation: {mod.subgroup or '-'}",
                f"Package Type: {mod.installer_package_type or 'wizard'}",
                f"Format: v{mod.format_version}",
                f"Payloads: {mod.installer_payload_count}",
                f"Assets: {mod.installer_asset_count}",
                f"Previews: {mod.preview_count}",
                f"Theme WAV: {'Yes' if mod.has_audio else 'No'}",
                f"Enabled: {'Yes' if mod.enabled else 'No'}",
                f"Conflict Node: {'Yes' if mod.filename in self.conflict_mod_names else 'No'}",
            ]
        else:
            lines = [
                f"File: {mod.filename}",
                f"Author: {mod.author or 'Unknown'}",
                f"Version: {mod.version or 'Unknown'}",
                f"Type: {GENRE_KEY_TO_LABEL.get(mod.genre, mod.genre.title())}",
                f"Constellation: {mod.subgroup or '-'}",
                f"Build: {mod.build_mode}",
                f"Format: v{mod.format_version}",
                f"Entries: {mod.file_count}",
                f"Previews: {mod.preview_count}",
                f"Theme WAV: {'Yes' if mod.has_audio else 'No'}",
                f"Enabled: {'Yes' if mod.enabled else 'No'}",
                f"Conflict Node: {'Yes' if mod.filename in self.conflict_mod_names else 'No'}",
            ]
        if mod.parse_error:
            lines.append(f"Parse Note: {mod.parse_error}")
        if mod.is_installer:
            install_label = "Install Package" if (mod.installer_package_type or "").lower() == "standard" else "Launch Installer"
        else:
            install_label = "Enable"
        self.enable_btn.config(text=install_label)
        self.disable_btn.config(text="Disable Installer" if mod.is_installer else "Disable")
        if mod.filename in self.conflict_mod_names:
            self.conflict_btn.grid()
        else:
            self.conflict_btn.grid_remove()
        self.detail_meta.config(text="\n".join(lines))
        self.detail_desc.config(state=tk.NORMAL)
        self.detail_desc.delete("1.0", tk.END)
        self.detail_desc.insert(tk.END, mod.description or "No description available.")
        self.detail_desc.config(state=tk.DISABLED)
        self.detail_genre_var.set(mod.genre)
        self.detail_subgroup_var.set(mod.subgroup)
        self.detail_preview_index = 0
        try:
            self.detail_preview_images, self.detail_audio_bytes = self.load_media_for_mod(mod)
        except Exception as exc:
            self.detail_preview_images = []
            self.detail_audio_bytes = None
            self.audio_state_var.set(f"Theme Audio: Media read failed ({exc})")
        self.render_detail_preview()
        self.refresh_selected_audio()
        self.place_detail_panel()
        self.canvas.render()

    def reveal_selected_mod(self):
        if not self.selected:
            return
        folder = os.path.dirname(self.selected.path)
        if os.path.isdir(folder):
            try:
                os.startfile(folder)
            except Exception:
                messagebox.showinfo("Folder", folder)

    def save_selected_classification(self):
        if not self.selected:
            return
        state = self.load_state()
        genre_overrides = state.setdefault("genre_overrides", {})
        subgroup_overrides = state.setdefault("subgroup_overrides", {})
        genre_value = self.detail_genre_var.get().strip().lower() or self.selected.genre
        subgroup_value = self.detail_subgroup_var.get().strip()
        if genre_value in GENRES:
            genre_overrides[self.selected.filename] = genre_value
        subgroup_overrides[self.selected.filename] = subgroup_value
        self.save_state(state)
        self.rescan_and_render(status=f"Saved overrides for {self.selected.filename}.")

    def rescan_and_render(self, status: Optional[str] = None):
        sel_name = self.selected.filename if self.selected else None
        self.scan_library()
        found_selected = False
        if sel_name:
            for mod in self.library_mods:
                if mod.filename == sel_name:
                    self.selected = mod
                    self.select_mod_record(mod)
                    found_selected = True
                    break
        if sel_name and not found_selected:
            self.clear_selection()
        self.canvas.render()
        if status:
            self.set_status(status, "green")

    def scan_library(self):
        self.ledger.ensure_exists()
        self.detail_media_cache.clear()
        self.installer_target_cache.clear()
        self.installer_target_detail_cache.clear()
        files = []
        wanted = {self.profile["single_ext"].lower(), self.profile["package_ext"].lower(), INSTALLER_EXTENSION.lower()}
        if os.path.isdir(self.game_mod_dir):
            for name in sorted(os.listdir(self.game_mod_dir), key=str.lower):
                full = os.path.join(self.game_mod_dir, name)
                if not os.path.isfile(full):
                    continue
                ext = os.path.splitext(name)[1].lower()
                if ext in wanted:
                    files.append(full)

        self.library_mods = []
        for path in files:
            filename = os.path.basename(path)
            is_installer = is_installer_filename(filename)
            enabled = self.ledger.is_enabled(filename)
            installer_package_type = ""
            installer_asset_count = 0
            installer_payload_count = 0
            try:
                if is_installer:
                    package = AldnoahInstallerReader().read(
                        path,
                        include_blobs=False,
                        include_asset_blobs=False,
                        include_payload_blobs=False,
                    )
                    meta = package.metadata or {}
                    installer_package_type = str(meta.get("package_type") or "wizard")
                    installer_asset_count = len(package.assets)
                    installer_payload_count = len(package.payloads)
                    preview_count = sum(1 for asset in package.assets if asset.role in {"preview", "banner", "option_preview", "icon"})
                    has_audio = any(asset.role == "audio" for asset in package.assets)
                    display_name = str(meta.get("mod_name") or "").strip() or title_from_filename(filename)
                    author = str(meta.get("author") or "")
                    version = str(meta.get("version") or "")
                    description = str(meta.get("description") or "")
                    file_count = installer_payload_count
                    build_mode = f"Installer / {installer_package_type.title()}"
                    try:
                        format_version = int(meta.get("format_version") or 0)
                    except Exception:
                        format_version = 0
                    parse_error = ""
                    genre = self.genre_for_file(filename, normalize_genre_key(str(meta.get("genre") or "misc")))
                else:
                    parsed = ModParser(path).read(include_payloads=False, include_media=False)
                    meta = parsed.meta
                    display_name = meta.display_name or title_from_filename(filename)
                    author = meta.author or ""
                    version = meta.version or ""
                    description = meta.description or ""
                    file_count = meta.file_count
                    build_mode = meta.build_mode
                    format_version = meta.format_version
                    preview_count = meta.preview_count
                    has_audio = meta.has_audio
                    parse_error = ""
                    genre = self.genre_for_file(filename, meta.genre)
            except Exception as e:
                display_name = title_from_filename(filename)
                author = ""
                version = ""
                description = "Could not parse metadata for this installer file." if is_installer else "Could not parse metadata for this mod file."
                file_count = 0
                build_mode = "Unknown"
                format_version = 0
                preview_count = 0
                has_audio = False
                parse_error = str(e)
                genre = self.genre_for_file(filename, "misc")

            subgroup = self.subgroup_for_file(filename, genre)

            self.library_mods.append(LibraryMod(
                path=path,
                filename=filename,
                display_name=display_name,
                author=author,
                version=version,
                description=description,
                file_count=file_count,
                enabled=enabled,
                genre=genre,
                subgroup=subgroup,
                build_mode=build_mode,
                format_version=format_version,
                preview_count=preview_count,
                has_audio=has_audio,
                parse_error=parse_error,
                is_installer=is_installer,
                installer_package_type=installer_package_type,
                installer_asset_count=installer_asset_count,
                installer_payload_count=installer_payload_count,
            ))

        self.constellations = self.build_constellations(self.library_mods)
        self.refresh_orrery_links()

    def refresh_orrery_links(self):
        targets: Dict[str, Set[Tuple[int, int]]] = {}
        details: Dict[str, Dict[Tuple[int, int], Set[str]]] = {}
        for mod in self.library_mods:
            if mod.parse_error:
                targets[mod.filename] = set()
                details[mod.filename] = {}
                continue
            if mod.is_installer:
                state_targets = self.installer_targets_from_state(mod.filename) if mod.enabled else set()
                state_details = self.installer_target_details_from_state(mod.filename) if mod.enabled else {}
                if state_targets:
                    targets[mod.filename] = state_targets
                    details[mod.filename] = state_details
                elif mod.enabled:
                    package_details = self.installer_target_details_from_package(mod.path)
                    targets[mod.filename] = set(package_details.keys())
                    details[mod.filename] = package_details
                else:
                    targets[mod.filename] = set()
                    details[mod.filename] = {}
                continue
            try:
                parsed = ModParser(mod.path).read(include_media=False)
                targets[mod.filename] = {
                    (entry.tail.idx_marker, entry.tail.entry_off)
                    for entry in parsed.entries
                }
                details[mod.filename] = self.target_details_from_entries(parsed.entries)
            except Exception:
                targets[mod.filename] = set()
                details[mod.filename] = {}
        self.mod_targets = targets
        self.mod_target_details = details
        self.refresh_conflict_context()

    def refresh_conflict_context(self):
        enabled_names = {
            mod.filename
            for mod in self.library_mods
            if mod.enabled and not mod.parse_error
        }
        selected_filename = ""
        if self.selected and not self.selected.parse_error:
            selected_filename = self.selected.filename
        self.orrery_links, self.conflict_mod_names = build_contextual_conflict_links(
            self.mod_targets,
            enabled_names,
            selected_filename,
        )

    def genre_for_file(self, filename: str, embedded_genre: str) -> str:
        state = self.load_state()
        overrides = state.get("genre_overrides") or {}
        value = (overrides.get(filename) or "").strip().lower()
        if value in GENRES:
            return value
        if embedded_genre in GENRES:
            return embedded_genre
        return "misc"

    def subgroup_for_file(self, filename: str, genre: str) -> str:
        state = self.load_state()
        overrides = state.get("subgroup_overrides") or {}
        value = (overrides.get(filename) or "").strip()
        if value:
            return value
        base = GENRE_KEY_TO_LABEL.get(genre, genre.title())
        return f"{base} Constellation"

    def build_constellations(self, mods: List[LibraryMod]) -> List[Constellation]:
        constellations: List[Constellation] = []
        grouped_by_genre: Dict[str, Dict[str, List[LibraryMod]]] = {g: {} for g in GENRES}
        for mod in sorted(mods, key=lambda m: (m.genre, m.subgroup.lower(), m.display_name.lower(), m.filename.lower())):
            grouped_by_genre.setdefault(mod.genre, {})
            grouped_by_genre[mod.genre].setdefault(mod.subgroup, []).append(mod)

        for genre in GENRES:
            subgroups = grouped_by_genre.get(genre, {})
            raw_chunks: List[Tuple[str, List[LibraryMod]]] = []
            for subgroup, subgroup_mods in sorted(subgroups.items(), key=lambda kv: kv[0].lower()):
                if len(subgroup_mods) <= CONSTELLATION_LIMIT:
                    raw_chunks.append((subgroup, subgroup_mods))
                else:
                    for idx in range(0, len(subgroup_mods), CONSTELLATION_LIMIT):
                        chunk = subgroup_mods[idx: idx + CONSTELLATION_LIMIT]
                        suffix = f" {1 + (idx // CONSTELLATION_LIMIT)}"
                        raw_chunks.append((subgroup + suffix, chunk))

            if not raw_chunks:
                continue

            genre_cx, genre_cy = GENRE_CENTERS[genre]
            count = len(raw_chunks)
            orbit_radius = 250.0 if count <= 4 else 360.0
            for i, (label, chunk) in enumerate(raw_chunks):
                angle = (2 * math.pi * i / max(1, count)) - math.pi / 2
                if count == 1:
                    cx = genre_cx
                    cy = genre_cy
                else:
                    cx = genre_cx + (math.cos(angle) * orbit_radius)
                    cy = genre_cy + (math.sin(angle) * orbit_radius)
                const = Constellation(
                    genre=genre,
                    label=label,
                    cx=cx,
                    cy=cy,
                    mods=chunk,
                    id=f"{genre}:{label}",
                )
                self.layout_stars_for_constellation(const)
                constellations.append(const)
        return constellations

    def layout_stars_for_constellation(self, const: Constellation):
        mods = list(sorted(const.mods, key=lambda m: (m.display_name.lower(), m.filename.lower())))
        if not mods:
            return
        if len(mods) == 1:
            mods[0].x = const.cx
            mods[0].y = const.cy
            return

        base_radius = 70.0 + max(0, len(mods) - 4) * 8.0
        for idx, mod in enumerate(mods):
            h = stable_hash(mod.filename)
            angle = ((2 * math.pi) * idx / len(mods)) + ((h % 17) * 0.02)
            radius = base_radius + (h % 37) - 18
            if mod.enabled:
                radius *= 0.66
            else:
                radius *= 1.12
            mod.x = const.cx + (math.cos(angle) * radius)
            mod.y = const.cy + (math.sin(angle) * radius)

    def set_install_folder(self):
        base = filedialog.askdirectory(title=f"Select install folder for {self.profile['display_name']}")
        if not base:
            return
        try:
            self.set_install_folder_path(base, silent=False)
        except Exception:
            return
        self.set_status(f"Install folder set: {self.base_dir}", "blue")

    def add_mod_files(self):
        paths = filedialog.askopenfilenames(
            title=f"Add mod files for {self.profile['display_name']}",
            filetypes=[
                ("Supported Mods", f"*{self.profile['single_ext']} *{self.profile['package_ext']} *{INSTALLER_EXTENSION}"),
                ("Aldnoah Installers", f"*{INSTALLER_EXTENSION}"),
                ("All files", "*.*"),
            ],
        )
        if not paths:
            return
        copied = 0
        for src in paths:
            try:
                dst = os.path.join(self.game_mod_dir, os.path.basename(src))
                shutil.copy2(src, dst)
                copied += 1
            except Exception as e:
                messagebox.showerror("Add Mod Error", f"Failed copying {src}:\n{e}")
                return
        self.rescan_and_render(status=f"Added {copied} mod file(s) to the library.")

    def require_ready(self) -> bool:
        if not self.base_dir or not self.cfg or not self.layout:
            messagebox.showwarning("Not Ready", "Please click 'Set Install Folder' first.")
            return False
        if not self.containers or not self.idx_files:
            messagebox.showwarning("Schema Missing", "The selected game schema does not define any containers or IDX files.")
            return False
        return True

    def apply_selected_mod(self):
        if not self.selected:
            self.set_status("Select a star first.", "red")
            return
        self.apply_mod_file(self.selected.path)

    def launch_installer(self, path: str):
        try:
            package = AldnoahInstallerReader().read(
                path,
                include_blobs=False,
                include_asset_blobs=False,
                include_payload_blobs=False,
            )
            package_type = str((package.metadata or {}).get("package_type") or "wizard").strip().lower()
            if package_type == "standard":
                StandardInstallerWindow(self, path)
            else:
                InstallerWizardWindow(self, path)
        except Exception as exc:
            messagebox.showerror("Installer Error", str(exc))
            self.set_status(f"Installer launch failed: {exc}", "red")

    def launch_installer_wizard(self, path: str):
        self.launch_installer(path)

    def apply_mod_file(self, path: str):
        filename = os.path.basename(path)
        if is_installer_filename(filename):
            if not self.require_ready():
                return
            self.launch_installer(path)
            return

        if not self.require_ready():
            return
        if self.ledger.is_enabled(filename):
            self.set_status(f"'{filename}' is already enabled. Disable it first to reapply.", "blue")
            return

        try:
            parsed = ModParser(path).read(include_media=False)
            entries = parsed.entries
        except Exception as e:
            messagebox.showerror("Mod Parse Error", str(e))
            return

        targets = {(ent.tail.idx_marker, ent.tail.entry_off) for ent in entries}
        if not self.confirm_apply_collisions(filename, targets):
            return

        if not self.apply_entries(filename, entries):
            return

        self.rescan_and_render(status=f"Applied {filename}.")

    def apply_entries(self, filename: str, entries: List[ModFileEntry]) -> bool:
        by_bin: Dict[int, List[ModFileEntry]] = {}
        for ent in entries:
            by_bin.setdefault(ent.tail.idx_marker, []).append(ent)

        total_done = 0
        total = len(entries)
        write_name_next = True

        for idx_marker, grouped_entries in sorted(by_bin.items(), key=lambda kv: kv[0]):
            bin_path = self.prompt_for_container(idx_marker)
            if not bin_path:
                self.set_status("Apply cancelled.", "red")
                return False

            idx_path = self.resolve_idx_path(idx_marker)
            if not idx_path:
                self.set_status(f"Missing IDX for bin index {idx_marker}.", "red")
                return False

            for ent in grouped_entries:
                try:
                    new_off = self.append_payload(bin_path, ent.payload)
                    original_entry = self.read_idx_entry(idx_path, ent.tail.entry_off)
                    patched = self.layout.patch_entry_bytes(
                        original_entry,
                        new_data_off_bytes=new_off,
                        new_size=len(ent.payload),
                        force_uncompressed=True,
                    )
                    self.write_idx_entry(idx_path, ent.tail.entry_off, patched)
                    self.ledger.append_record(
                        filename,
                        idx_marker=idx_marker,
                        entry_off=ent.tail.entry_off,
                        original_entry=original_entry,
                        entry_size=self.layout.entry_size,
                        write_name=write_name_next,
                    )
                    write_name_next = False
                except Exception as e:
                    messagebox.showerror(
                        "Apply Error",
                        f"Failed applying '{ent.stored_name}' (IDX marker {idx_marker} at 0x{ent.tail.entry_off:X}):\n{e}",
                    )
                    self.set_status("Apply failed (partial changes may have been written).", "red")
                    return False
                total_done += 1
                self.set_status(f"Applying {total_done}/{total}", "blue")
                self.update_idletasks()

        return True

    def confirm_apply_collisions(self, filename: str, targets: Set[Tuple[int, int]]) -> bool:
        enabled_names = {
            mod.filename
            for mod in self.library_mods
            if mod.enabled and not mod.parse_error
        }
        collisions = find_target_collisions(filename, targets, self.mod_targets, enabled_names)
        if not collisions:
            return True

        shared_targets = set()
        lines = []
        for name in sorted(collisions, key=str.lower):
            shared = collisions[name]
            shared_targets.update(shared)
            lines.append(f"- {name}: {len(shared)} target(s)")

        ok = messagebox.askyesno(
            "Apply Collision Warning",
            "This mod touches target(s) already changed by enabled mods.\n\n"
            + "\n".join(lines[:12])
            + ("\n- ..." if len(lines) > 12 else "")
            + f"\n\nShared target count: {len(shared_targets)}\n\nContinue applying anyway?",
        )
        if not ok:
            self.set_status(f"Apply cancelled; {filename} collides with enabled mod targets.", "red")
            return False
        self.set_status(f"Continuing apply with {len(shared_targets)} known collision target(s).", "blue")
        return True

    def selected_conflict_rows(self, limit: int = 100) -> Tuple[List[dict], int]:
        if not self.selected:
            return [], 0
        selected_name = self.selected.filename
        selected_targets = set(self.mod_targets.get(selected_name, set()))
        if not selected_targets:
            return [], 0

        enabled_names = {
            mod.filename
            for mod in self.library_mods
            if mod.enabled and not mod.parse_error and mod.filename != selected_name
        }
        rows: List[dict] = []
        total = 0
        selected_details = self.mod_target_details.get(selected_name, {})

        for other_name in sorted(enabled_names, key=str.lower):
            shared_targets = selected_targets & set(self.mod_targets.get(other_name, set()))
            if not shared_targets:
                continue
            other_details = self.mod_target_details.get(other_name, {})
            for target in sorted(shared_targets):
                selected_files = sorted(selected_details.get(target) or {"unknown payload"})
                other_files = sorted(other_details.get(target) or {"unknown payload"})
                for selected_file in selected_files:
                    for other_file in other_files:
                        total += 1
                        if len(rows) < limit:
                            rows.append({
                                "target": target,
                                "selected_file": selected_file,
                                "other_mod": other_name,
                                "other_file": other_file,
                            })
        return rows, total

    def show_conflict_panel(self):
        if not self.selected:
            return
        rows, total = self.selected_conflict_rows(limit=100)
        if not rows:
            messagebox.showinfo("Conflict Inspector", "No enabled mod conflicts are currently visible for this selection.")
            return

        win = tk.Toplevel(self)
        win.title(f"Conflict Inspector, {self.selected.display_name}")
        win.geometry("920x560")
        win.configure(bg=ORRERY_BG)
        setup_lilac_styles_if_needed(win)
        win.transient(self)

        header = tk.Frame(win, bg=ORRERY_BG_2)
        header.pack(fill="x")
        tk.Label(
            header,
            text=f"Conflict Inspector: {self.selected.display_name}",
            bg=ORRERY_BG_2,
            fg=LENS_GOLD,
            font=("Segoe UI", 14, "bold"),
            anchor="w",
        ).pack(fill="x", padx=12, pady=(10, 2))
        tk.Label(
            header,
            text=f"Showing {len(rows)} of {total} conflicting file pair(s). Display limit: 100.",
            bg=ORRERY_BG_2,
            fg=TEXT_MUTED,
            font=("Segoe UI", 10),
            anchor="w",
        ).pack(fill="x", padx=12, pady=(0, 10))

        body = tk.Frame(win, bg=ORRERY_BG, padx=12, pady=12)
        body.pack(fill="both", expand=True)
        text = tk.Text(body, wrap=tk.NONE, bg="#0F0B16", fg=TEXT, insertbackground=TEXT, relief="flat", bd=0, font=("Consolas", 9))
        scroll_y = ttk.Scrollbar(body, orient="vertical", command=text.yview)
        scroll_x = ttk.Scrollbar(body, orient="horizontal", command=text.xview)
        text.configure(yscrollcommand=scroll_y.set, xscrollcommand=scroll_x.set)
        text.grid(row=0, column=0, sticky="nsew")
        scroll_y.grid(row=0, column=1, sticky="ns")
        scroll_x.grid(row=1, column=0, sticky="ew")
        body.grid_rowconfigure(0, weight=1)
        body.grid_columnconfigure(0, weight=1)

        for row in rows:
            idx_marker, entry_off = row["target"]
            text.insert(tk.END, f"BIN {idx_marker} | IDX 0x{entry_off:08X}\n")
            text.insert(tk.END, f"  {self.selected.filename}: {row['selected_file']}\n")
            text.insert(tk.END, f"  {row['other_mod']}: {row['other_file']}\n\n")
        if total > len(rows):
            text.insert(tk.END, f"... {total - len(rows)} more conflicting file pair(s) hidden by the 100 row cap.\n")
        text.config(state=tk.DISABLED)

    def destroy(self):
        self.audio_player.stop()
        super().destroy()

    def disable_selected(self):
        if not self.selected:
            self.set_status("Select a star first.", "red")
            return
        if not self.require_ready():
            return
        self.disable_mod(self.selected.filename)

    def disable_mod(self, mod_name: str):
        if not os.path.exists(self.ledger_path):
            self.set_status("No ledger found.", "red")
            return False

        target = mod_name.strip().lower()
        restored = 0
        total = 0

        for name, idx_marker, entry_off, entry_size, entry_bytes in self.ledger.iter_records():
            if not name:
                continue
            if name.strip().lower() != target:
                continue
            total += 1
            idx_path = self.resolve_idx_path(idx_marker)
            if not idx_path:
                self.set_status(f"Missing IDX for BIN {idx_marker}; cannot restore.", "red")
                return False
            try:
                with open(idx_path, "r+b") as f:
                    f.seek(entry_off)
                    f.write(entry_bytes[:entry_size])
                restored += 1
            except Exception as e:
                messagebox.showerror("Disable Error", f"Failed restoring an IDX entry:\n{e}")
                self.set_status("Disable failed (partial changes may remain).", "red")
                return False

        if total == 0:
            self.set_status(f"'{mod_name}' not found in ledger.", "red")
            return False

        try:
            kept = self.ledger.rewrite_without_mod(mod_name)
            self.ledger.write_raw(kept)
        except Exception as e:
            messagebox.showerror("Ledger Error", f"Failed rewriting ledger:\n{e}")
            return False

        if is_installer_filename(mod_name):
            self.clear_installer_selection_state(mod_name)
        self.rescan_and_render(status=f"Disabled '{mod_name}' (restored {restored}/{total} IDX entries).")
        return True

    def disable_all(self):
        if not self.require_ready():
            return
        if not os.path.exists(self.ledger_path) or os.path.getsize(self.ledger_path) == 0:
            self.save_installer_state({})
            self.set_status("No mods are enabled.", "blue")
            return

        ok = messagebox.askyesno(
            "Disable All",
            "This will restore all tracked IDX entries, truncate BINs back to original sizes, and clear the ledger. Continue?",
        )
        if not ok:
            return

        restored = 0
        total = 0
        for name, idx_marker, entry_off, entry_size, entry_bytes in self.ledger.iter_records():
            if not name:
                continue
            total += 1
            idx_path = self.resolve_idx_path(idx_marker)
            if not idx_path:
                self.set_status(f"Missing IDX for BIN {idx_marker}; cannot restore all.", "red")
                return
            try:
                with open(idx_path, "r+b") as f:
                    f.seek(entry_off)
                    f.write(entry_bytes[:entry_size])
                restored += 1
            except Exception as e:
                messagebox.showerror("Disable All Error", f"Failed restoring an IDX entry:\n{e}")
                self.set_status("Disable All failed (partial changes may remain).", "red")
                return

        self.truncate_bins_to_original()
        try:
            self.ledger.write_raw(b"")
        except Exception:
            pass
        self.save_installer_state({})
        self.rescan_and_render(status=f"Disabled all mods (restored {restored}/{total} IDX entries).")

    def prompt_for_container(self, idx_marker: int) -> Optional[str]:
        if idx_marker in self.container_paths and os.path.isfile(self.container_paths[idx_marker]):
            return self.container_paths[idx_marker]

        expected = None
        if 0 <= idx_marker < len(self.containers):
            expected = str(self.containers[idx_marker])

        initialdir = self.base_dir or os.getcwd()
        title = f"Select BIN {idx_marker}"
        if expected:
            title += f" (expected: {expected})"

        path = filedialog.askopenfilename(title=title, initialdir=initialdir, filetypes=[("All files", "*.*")])
        if not path:
            return None

        if expected and os.path.basename(path).lower() != os.path.basename(expected).lower():
            ok = messagebox.askyesno(
                "Confirm BIN Selection",
                f"You selected:\n  {os.path.basename(path)}\n\nBut the config expects:\n  {expected}\n\nUse this file anyway?",
            )
            if not ok:
                return self.prompt_for_container(idx_marker)

        self.container_paths[idx_marker] = path
        state = self.load_state()
        state["install_folder"] = self.base_dir or state.get("install_folder")
        state["container_paths"] = {str(k): v for k, v in self.container_paths.items()}
        state["idx_paths"] = {str(k): v for k, v in self.idx_paths.items()}
        self.save_state(state)
        return path

    def resolve_idx_path(self, idx_marker: int) -> Optional[str]:
        if len(self.idx_files) == 1 and len(self.containers) > 1:
            idx_marker = 0
        if idx_marker in self.idx_paths and os.path.isfile(self.idx_paths[idx_marker]):
            return self.idx_paths[idx_marker]

        expected = None
        if 0 <= idx_marker < len(self.idx_files):
            expected = str(self.idx_files[idx_marker])

        if self.base_dir and expected:
            p = os.path.join(self.base_dir, expected)
            if os.path.isfile(p):
                self.idx_paths[idx_marker] = p
                return p

        title = f"Select IDX file for BIN {idx_marker}"
        if expected:
            title += f" (expected: {expected})"
        path = filedialog.askopenfilename(title=title, initialdir=self.base_dir or os.getcwd(), filetypes=[("All files", "*.*")])
        if not path:
            return None

        self.idx_paths[idx_marker] = path
        state = self.load_state()
        state["install_folder"] = self.base_dir or state.get("install_folder")
        state["container_paths"] = {str(k): v for k, v in self.container_paths.items()}
        state["idx_paths"] = {str(k): v for k, v in self.idx_paths.items()}
        self.save_state(state)
        return path

    def append_payload(self, bin_path: str, payload: bytes) -> int:
        with open(bin_path, "r+b") as f:
            f.seek(0, os.SEEK_END)
            pos = f.tell()
            pad = pad_len(pos, ALIGN)
            if pad:
                f.write(b"\x00" * pad)
                pos += pad
            start_off = pos
            f.write(payload)
            end_pos = f.tell()
            pad2 = pad_len(end_pos, ALIGN)
            if pad2:
                f.write(b"\x00" * pad2)
        return start_off

    def read_idx_entry(self, idx_path: str, entry_off: int) -> bytes:
        assert self.layout is not None
        with open(idx_path, "rb") as f:
            f.seek(entry_off)
            chunk = f.read(self.layout.entry_size)
        if len(chunk) != self.layout.entry_size:
            raise ValueError(f"IDX entry read failed at offset 0x{entry_off:X}.")
        return chunk

    def write_idx_entry(self, idx_path: str, entry_off: int, entry_bytes: bytes):
        assert self.layout is not None
        if len(entry_bytes) < self.layout.entry_size:
            raise ValueError("entry_bytes shorter than entry_size")
        with open(idx_path, "r+b") as f:
            f.seek(entry_off)
            f.write(entry_bytes[:self.layout.entry_size])

    def capture_original_sizes_from_install(self):
        if not self.base_dir or not self.containers:
            return
        if os.path.isfile(self.orig_sizes_path):
            try:
                with open(self.orig_sizes_path, "r", encoding="utf-8") as f:
                    existing = json.load(f) or {}
                if existing:
                    return
            except Exception:
                pass

        data = {}
        for idx_marker, name in enumerate(self.containers):
            try:
                p = os.path.join(self.base_dir, str(name))
                if os.path.isfile(p):
                    data[str(idx_marker)] = {"container": str(name), "size": os.path.getsize(p)}
            except Exception:
                continue

        try:
            os.makedirs(os.path.dirname(self.orig_sizes_path), exist_ok=True)
            with open(self.orig_sizes_path, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2)
        except Exception:
            pass

    def truncate_bins_to_original(self):
        if not self.base_dir:
            self.set_status("Warning: install folder unknown; skipping truncation.", "red")
            return
        if not os.path.exists(self.orig_sizes_path):
            self.set_status("Warning: original container sizes not recorded; skipping truncation.", "red")
            return

        try:
            with open(self.orig_sizes_path, "r", encoding="utf-8") as f:
                data = json.load(f) or {}
        except Exception:
            self.set_status("Warning: failed reading original sizes JSON; skipping truncation.", "red")
            return

        truncated = 0
        for key, info in (data or {}).items():
            try:
                idx_marker = int(key)
                container_name = info.get("container")
                size = int(info.get("size", 0))
                if not container_name or size <= 0:
                    continue
                path = self.container_paths.get(idx_marker) or os.path.join(self.base_dir, str(container_name))
                if not os.path.isfile(path):
                    continue
                cur = os.path.getsize(path)
                if cur > size:
                    with open(path, "r+b") as fbin:
                        fbin.truncate(size)
                    truncated += 1
            except Exception:
                continue

        if truncated:
            self.set_status(f"Truncated {truncated} BIN file(s) back to original sizes.", "blue")


class StandardInstallerWindow(tk.Toplevel):
    def __init__(self, manager: ModManagerWindowV2, path: str):
        super().__init__(manager)
        self.manager = manager
        self.path = path
        self.filename = os.path.basename(path)
        self.package = AldnoahInstallerReader().read(
            path,
            include_blobs=False,
            include_asset_blobs=True,
            include_payload_blobs=True,
        )
        self.metadata = self.package.metadata or {}
        self.icon_blob = self.first_asset_blob("icon")
        self.banner_blob = self.first_asset_blob("banner")
        self.preview_blobs = [
            asset.data
            for asset in self.package.assets
            if asset.role in {"preview", "option_preview"}
            and asset.data
            and str(asset.mime_type).lower().startswith("image/")
        ]
        self.preview_index = 0
        self.preview_photo = None
        self.icon_photo = None
        self.banner_photo = None
        self.valid_payloads, self.entries, self.invalid = installer_payloads_to_entries(self.package.payloads)

        title = self.metadata.get("mod_name") or title_from_filename(self.filename)
        self.title(f"{title} Standard Package")
        self.geometry("980x680")
        self.minsize(860, 600)
        self.configure(bg=ORRERY_BG)
        setup_lilac_styles_if_needed(self)
        self.transient(manager)

        self.build_ui()
        self.refresh_preview()
        self.refresh_payload_list()
        self.refresh_plan()

    def first_asset_blob(self, role: str) -> Optional[bytes]:
        for asset in self.package.assets:
            if asset.role == role and asset.data:
                return asset.data
        return None

    def image_photo_from_blob(self, blob: bytes, size: Tuple[int, int]) -> Optional[ImageTk.PhotoImage]:
        try:
            with Image.open(BytesIO(blob)) as img:
                if img.mode not in ("RGB", "RGBA"):
                    img = img.convert("RGBA" if "A" in img.getbands() else "RGB")
                if img.mode == "RGBA":
                    composite = Image.new("RGBA", img.size, (18, 13, 24, 255))
                    composite.alpha_composite(img)
                    img = composite.convert("RGB")
                else:
                    img = img.convert("RGB")
                resampling = getattr(getattr(Image, "Resampling", Image), "LANCZOS")
                return ImageTk.PhotoImage(img.resize(size, resampling))
        except Exception:
            return None

    def build_ui(self):
        header = tk.Frame(self, bg=ORRERY_BG_2, height=96)
        header.pack(side=tk.TOP, fill=tk.X)
        header.pack_propagate(False)
        header.grid_columnconfigure(1, weight=1)

        icon_box = tk.Frame(header, bg=ORRERY_BG_2, width=64, height=64)
        icon_box.grid(row=0, column=0, sticky="nsw", padx=(14, 8), pady=14)
        icon_box.grid_propagate(False)
        if self.icon_blob:
            self.icon_photo = self.image_photo_from_blob(self.icon_blob, (52, 52))
        if self.icon_photo:
            tk.Label(icon_box, image=self.icon_photo, bg=ORRERY_BG_2).pack(expand=True)
        else:
            tk.Label(icon_box, text="AE", bg=ORRERY_BG_2, fg=LENS_GOLD, font=("Segoe UI", 14, "bold")).pack(fill="both", expand=True)

        title_area = tk.Frame(header, bg=ORRERY_BG_2)
        title_area.grid(row=0, column=1, sticky="nsew", pady=12)
        tk.Label(
            title_area,
            text=self.metadata.get("mod_name") or title_from_filename(self.filename),
            bg=ORRERY_BG_2,
            fg=LENS_GOLD,
            font=("Segoe UI", 18, "bold"),
            anchor="w",
        ).pack(fill="x")
        tk.Label(
            title_area,
            text=f"{self.metadata.get('author', 'Unknown')}  |  {self.metadata.get('version', 'Unknown')}  |  standard",
            bg=ORRERY_BG_2,
            fg=TEXT_MUTED,
            font=("Segoe UI", 10),
            anchor="w",
        ).pack(fill="x", pady=(2, 0))

        if self.banner_blob:
            self.banner_photo = self.image_photo_from_blob(self.banner_blob, (410, 72))
        if self.banner_photo:
            tk.Label(header, image=self.banner_photo, bg=ORRERY_BG_2).grid(row=0, column=2, sticky="e", padx=(12, 14), pady=12)

        body = tk.Frame(self, bg=ORRERY_BG)
        body.pack(fill="both", expand=True, padx=12, pady=12)
        body.grid_columnconfigure(0, weight=1)
        body.grid_columnconfigure(1, weight=1)
        body.grid_rowconfigure(0, weight=1)

        left = tk.Frame(body, bg=LENS_BG, highlightthickness=1, highlightbackground=LENS_EDGE)
        left.grid(row=0, column=0, sticky="nsew", padx=(0, 10))
        tk.Label(left, text="Standard Package", bg=LENS_PANEL, fg=TEXT, font=("Segoe UI", 10, "bold"), anchor="w", padx=10, pady=7).pack(fill="x")
        self.summary_text = tk.Text(left, height=8, wrap=tk.WORD, bg=LENS_PANEL, fg=TEXT, insertbackground=TEXT, relief="flat", bd=0)
        self.summary_text.pack(fill="x", padx=10, pady=(10, 8))
        self.summary_text.insert(
            "1.0",
            "\n".join(
                [
                    self.metadata.get("description") or "No description.",
                    "",
                    "Standard packages install every valid payload in the package table.",
                    "There are no option pages or selectable variants in this flow.",
                ]
            ),
        )
        self.summary_text.config(state=tk.DISABLED)

        tk.Label(left, text="Payload Table", bg=LENS_BG, fg=TEXT, font=("Segoe UI", 10, "bold"), anchor="w").pack(fill="x", padx=10)
        payload_wrap = tk.Frame(left, bg=LENS_BG)
        payload_wrap.pack(fill="both", expand=True, padx=10, pady=(4, 10))
        payload_wrap.grid_rowconfigure(0, weight=1)
        payload_wrap.grid_columnconfigure(0, weight=1)
        self.payload_text = tk.Text(payload_wrap, wrap=tk.NONE, bg="#0F0B16", fg=TEXT_MUTED, insertbackground=TEXT, relief="flat", bd=0)
        self.payload_text.grid(row=0, column=0, sticky="nsew")
        scroll = ttk.Scrollbar(payload_wrap, orient="vertical", command=self.payload_text.yview)
        scroll.grid(row=0, column=1, sticky="ns")
        self.payload_text.configure(yscrollcommand=scroll.set)

        right = tk.Frame(body, bg=LENS_BG, highlightthickness=1, highlightbackground=LENS_EDGE)
        right.grid(row=0, column=1, sticky="nsew")
        tk.Label(right, text="Live Preview", bg=LENS_PANEL, fg=TEXT, font=("Segoe UI", 10, "bold"), anchor="w", padx=10, pady=7).pack(fill="x")
        self.preview_canvas = tk.Canvas(right, width=360, height=200, bg=DETAIL_PREVIEW_BG, highlightthickness=0)
        self.preview_canvas.pack(fill="x", padx=10, pady=(10, 8))
        self.preview_canvas.bind("<Configure>", lambda _e: self.refresh_preview())
        nav = tk.Frame(right, bg=LENS_BG)
        nav.pack(fill="x", padx=10, pady=(0, 10))
        self.preview_counter = tk.StringVar(value="0 / 0")
        self.prev_btn = tk.Button(nav, text="Prev", width=8, command=lambda: self.cycle_preview(-1))
        self.prev_btn.pack(side=tk.LEFT)
        self.next_btn = tk.Button(nav, text="Next", width=8, command=lambda: self.cycle_preview(1))
        self.next_btn.pack(side=tk.LEFT, padx=(6, 0))
        tk.Label(nav, textvariable=self.preview_counter, bg=LENS_BG, fg=TEXT_MUTED, font=("Segoe UI", 9)).pack(side=tk.RIGHT)

        tk.Label(right, text="Generated Install Plan", bg=LENS_BG, fg=TEXT, font=("Segoe UI", 10, "bold"), anchor="w").pack(fill="x", padx=10)
        self.plan_text = tk.Text(right, height=11, wrap=tk.WORD, bg="#0F0B16", fg=TEXT_MUTED, insertbackground=TEXT, relief="flat", bd=0)
        self.plan_text.pack(fill="both", expand=True, padx=10, pady=(4, 10))
        self.plan_text.config(state=tk.DISABLED)

        footer = tk.Frame(self, bg=ORRERY_BG_2, height=52)
        footer.pack(side=tk.BOTTOM, fill=tk.X)
        footer.pack_propagate(False)
        tk.Button(footer, text="Install Package", command=self.run_install, width=20).pack(side=tk.RIGHT, padx=(8, 14), pady=10)
        tk.Button(footer, text="Cancel", command=self.destroy, width=12).pack(side=tk.RIGHT, padx=8, pady=10)

    def refresh_payload_list(self):
        rows = []
        entry_by_payload = {payload.payload_id: entry for payload, entry in zip(self.valid_payloads, self.entries)}
        for payload in self.package.payloads:
            entry = entry_by_payload.get(payload.payload_id)
            if entry:
                rows.append(f"{payload.stored_name}  ->  BIN {entry.tail.idx_marker} | IDX 0x{entry.tail.entry_off:08X}")
            else:
                rows.append(f"{payload.stored_name}  ->  invalid taildata")
        self.payload_text.config(state=tk.NORMAL)
        self.payload_text.delete("1.0", tk.END)
        self.payload_text.insert(tk.END, "\n".join(rows) if rows else "No payloads embedded.")
        self.payload_text.config(state=tk.DISABLED)

    def cycle_preview(self, delta: int):
        if not self.preview_blobs:
            return
        self.preview_index = (self.preview_index + delta) % len(self.preview_blobs)
        self.refresh_preview()

    def refresh_preview(self):
        canvas = self.preview_canvas
        canvas.delete("all")
        width = max(1, canvas.winfo_width() or int(canvas.cget("width")))
        height = max(1, canvas.winfo_height() or int(canvas.cget("height")))
        canvas.create_rectangle(0, 0, width, height, fill=DETAIL_PREVIEW_BG, outline="")

        total = len(self.preview_blobs)
        self.preview_counter.set(f"{self.preview_index + 1} / {total}" if total else "0 / 0")
        nav_state = tk.NORMAL if total > 1 else tk.DISABLED
        self.prev_btn.config(state=nav_state)
        self.next_btn.config(state=nav_state)
        if not total:
            canvas.create_text(width // 2, height // 2, text="No Preview Image", fill=TEXT_MUTED, font=("Segoe UI", 11, "bold"))
            return

        self.preview_index %= total
        try:
            with Image.open(BytesIO(self.preview_blobs[self.preview_index])) as img:
                if img.mode not in ("RGB", "RGBA"):
                    img = img.convert("RGBA" if "A" in img.getbands() else "RGB")
                if img.mode == "RGBA":
                    composite = Image.new("RGBA", img.size, (18, 13, 24, 255))
                    composite.alpha_composite(img)
                    img = composite.convert("RGB")
                else:
                    img = img.convert("RGB")
                img = trim_installer_preview_padding(img)
                resampling = getattr(getattr(Image, "Resampling", Image), "LANCZOS")
                frame = img.resize((width, height), resampling)
                self.preview_photo = ImageTk.PhotoImage(frame)
                canvas.create_image(0, 0, anchor="nw", image=self.preview_photo)
        except Exception as exc:
            canvas.create_text(width // 2, height // 2, text=f"Preview error:\n{exc}", fill="#FFD2DA", width=280)

    def refresh_plan(self):
        targets = {(entry.tail.idx_marker, entry.tail.entry_off) for entry in self.entries}
        enabled_names = {
            mod.filename
            for mod in self.manager.library_mods
            if mod.enabled and not mod.parse_error
        }
        collisions = find_target_collisions(self.filename, targets, self.manager.mod_targets, enabled_names)
        lines = [
            "Package mode: Standard",
            f"Payloads: {len(self.valid_payloads)} / {len(self.package.payloads)} valid",
            f"Target IDX entries: {len(targets)}",
        ]
        if self.manager.ledger.is_enabled(self.filename):
            lines.append("Mode: reinstall/update existing standard package")
        if self.invalid:
            lines.append(f"Invalid payloads: {len(self.invalid)}")
        if collisions:
            shared = set()
            lines.append("Enabled collisions:")
            for name in sorted(collisions, key=str.lower)[:8]:
                shared.update(collisions[name])
                lines.append(f"- {name}: {len(collisions[name])} target(s)")
            if len(collisions) > 8:
                lines.append("- ...")
            lines.append(f"Shared target count: {len(shared)}")
        for payload in self.valid_payloads[:8]:
            lines.append(f"- {payload.stored_name}")
        if len(self.valid_payloads) > 8:
            lines.append("- ...")
        self.plan_text.config(state=tk.NORMAL)
        self.plan_text.delete("1.0", tk.END)
        self.plan_text.insert(tk.END, "\n".join(lines))
        self.plan_text.config(state=tk.DISABLED)

    def run_install(self):
        if self.invalid:
            ok = messagebox.askyesno(
                "Invalid Payloads",
                "Some embedded payloads could not be parsed and will be skipped.\n\n"
                + "\n".join(self.invalid[:8])
                + ("\n..." if len(self.invalid) > 8 else "")
                + "\n\nContinue with valid payloads?",
            )
            if not ok:
                return
        if not self.entries:
            messagebox.showwarning("No Payloads", "No valid payloads are embedded in this standard package.")
            return

        targets = {(entry.tail.idx_marker, entry.tail.entry_off) for entry in self.entries}
        if not self.manager.confirm_apply_collisions(self.filename, targets):
            return

        if self.manager.ledger.is_enabled(self.filename):
            ok = messagebox.askyesno(
                "Reinstall Standard Package",
                "This standard package is already enabled.\n\nDisable the current payload records and install the package again?",
            )
            if not ok:
                return
            if not self.manager.disable_mod(self.filename):
                return

        if not self.manager.apply_entries(self.filename, self.entries):
            return

        self.manager.record_installer_selection(self.filename, [], self.valid_payloads, self.entries, package_type="standard")
        self.manager.rescan_and_render(status=f"Installed standard package {self.filename} with {len(self.entries)} payload(s).")
        messagebox.showinfo("Standard Package Complete", f"Installed {len(self.entries)} payload(s) from {self.filename}.")
        self.destroy()


class InstallerWizardWindow(tk.Toplevel):
    def __init__(self, manager: ModManagerWindowV2, path: str):
        super().__init__(manager)
        self.manager = manager
        self.path = path
        self.filename = os.path.basename(path)
        self.package = AldnoahInstallerReader().read(
            path,
            include_blobs=False,
            include_asset_blobs=True,
            include_payload_blobs=True,
        )
        self.metadata = self.package.metadata or {}
        self.asset_by_id = {asset.asset_id: asset for asset in self.package.assets}
        self.payload_by_id = {payload.payload_id: payload for payload in self.package.payloads}
        self.icon_blob = self.first_asset_blob("icon")
        self.banner_blob = self.first_asset_blob("banner")
        saved = manager.load_installer_state().get(self.filename, {})
        self.previous_option_ids = set(saved.get("selected_option_ids", [])) if isinstance(saved, dict) else set()
        self.group_controls = {}
        self.option_by_id = {}
        self.option_order: List[str] = []
        self.initial_option_id: Optional[str] = None
        self.preview_photo = None
        self.icon_photo = None
        self.banner_photo = None
        self.current_preview_blob = None

        title = self.metadata.get("mod_name") or title_from_filename(self.filename)
        self.title(f"{title} Installer")
        self.geometry("1080x760")
        self.minsize(940, 660)
        self.configure(bg=ORRERY_BG)
        setup_lilac_styles_if_needed(self)
        self.transient(manager)

        self.build_ui()
        self.build_wizard()
        self.refresh_plan()

    def first_asset_blob(self, role: str) -> Optional[bytes]:
        for asset in self.package.assets:
            if asset.role == role and asset.data:
                return asset.data
        return None

    def image_photo_from_blob(self, blob: bytes, size: Tuple[int, int]) -> Optional[ImageTk.PhotoImage]:
        try:
            with Image.open(BytesIO(blob)) as img:
                if img.mode not in ("RGB", "RGBA"):
                    img = img.convert("RGBA" if "A" in img.getbands() else "RGB")
                if img.mode == "RGBA":
                    composite = Image.new("RGBA", img.size, (18, 13, 24, 255))
                    composite.alpha_composite(img)
                    img = composite.convert("RGB")
                else:
                    img = img.convert("RGB")
                resampling = getattr(getattr(Image, "Resampling", Image), "LANCZOS")
                return ImageTk.PhotoImage(img.resize(size, resampling))
        except Exception:
            return None

    def build_ui(self):
        header = tk.Frame(self, bg=ORRERY_BG_2, height=96)
        header.pack(side=tk.TOP, fill=tk.X)
        header.pack_propagate(False)
        header.grid_columnconfigure(1, weight=1)

        icon_box = tk.Frame(header, bg=ORRERY_BG_2, width=64, height=64)
        icon_box.grid(row=0, column=0, sticky="nsw", padx=(14, 8), pady=14)
        icon_box.grid_propagate(False)
        if self.icon_blob:
            self.icon_photo = self.image_photo_from_blob(self.icon_blob, (52, 52))
        if self.icon_photo:
            tk.Label(icon_box, image=self.icon_photo, bg=ORRERY_BG_2).pack(expand=True)
        else:
            tk.Label(icon_box, text="AE", bg=LENS_BG, fg=LENS_GOLD, font=("Segoe UI", 14, "bold")).pack(fill="both", expand=True)

        title_area = tk.Frame(header, bg=ORRERY_BG_2)
        title_area.grid(row=0, column=1, sticky="nsew", pady=12)
        tk.Label(
            title_area,
            text=self.metadata.get("mod_name") or title_from_filename(self.filename),
            bg=ORRERY_BG_2,
            fg=LENS_GOLD,
            font=("Segoe UI", 18, "bold"),
            anchor="w",
        ).pack(fill="x")
        tk.Label(
            title_area,
            text=f"{self.metadata.get('author', 'Unknown')}  |  {self.metadata.get('version', 'Unknown')}  |  {self.metadata.get('package_type', 'wizard')}",
            bg=ORRERY_BG_2,
            fg=TEXT_MUTED,
            font=("Segoe UI", 10),
            anchor="w",
        ).pack(fill="x", pady=(2, 0))

        if self.banner_blob:
            self.banner_photo = self.image_photo_from_blob(self.banner_blob, (410, 72))
        if self.banner_photo:
            tk.Label(header, image=self.banner_photo, bg=ORRERY_BG_2).grid(row=0, column=2, sticky="e", padx=(12, 14), pady=12)

        body = tk.Frame(self, bg=ORRERY_BG)
        body.pack(fill="both", expand=True, padx=12, pady=12)
        body.grid_columnconfigure(0, minsize=170)
        body.grid_columnconfigure(1, weight=1)
        body.grid_columnconfigure(2, minsize=340)
        body.grid_rowconfigure(0, weight=1)

        left = tk.Frame(body, bg=LENS_BG, highlightthickness=1, highlightbackground=LENS_EDGE)
        left.grid(row=0, column=0, sticky="nsew", padx=(0, 10))
        tk.Label(left, text="Install Steps", bg=LENS_PANEL, fg=TEXT, font=("Segoe UI", 10, "bold"), anchor="w", padx=10, pady=7).pack(fill="x")
        self.step_list = tk.Listbox(left, bg=LENS_BG, fg=TEXT_MUTED, activestyle="none", relief="flat", bd=0, highlightthickness=0)
        self.step_list.pack(fill="both", expand=True, padx=8, pady=8)

        center = tk.Frame(body, bg=LENS_BG, highlightthickness=1, highlightbackground=LENS_EDGE)
        center.grid(row=0, column=1, sticky="nsew", padx=(0, 10))
        tk.Label(center, text="Option Constellation", bg=LENS_PANEL, fg=TEXT, font=("Segoe UI", 10, "bold"), anchor="w", padx=10, pady=7).pack(fill="x")
        self.option_canvas = tk.Canvas(center, bg=LENS_BG, highlightthickness=0)
        self.option_scroll = ttk.Scrollbar(center, orient="vertical", command=self.option_canvas.yview)
        self.option_frame = tk.Frame(self.option_canvas, bg=LENS_BG)
        self.option_canvas.create_window((0, 0), window=self.option_frame, anchor="nw")
        self.option_canvas.configure(yscrollcommand=self.option_scroll.set)
        self.option_scroll.pack(side="right", fill="y")
        self.option_canvas.pack(side="left", fill="both", expand=True)
        self.option_frame.bind("<Configure>", lambda _e: self.option_canvas.configure(scrollregion=self.option_canvas.bbox("all")))

        right = tk.Frame(body, bg=LENS_BG, highlightthickness=1, highlightbackground=LENS_EDGE)
        right.grid(row=0, column=2, sticky="nsew")
        tk.Label(right, text="Live Preview", bg=LENS_PANEL, fg=TEXT, font=("Segoe UI", 10, "bold"), anchor="w", padx=10, pady=7).pack(fill="x")
        self.preview_canvas = tk.Canvas(right, width=310, height=180, bg=DETAIL_PREVIEW_BG, highlightthickness=0)
        self.preview_canvas.pack(fill="x", padx=10, pady=(10, 8))
        self.preview_canvas.bind("<Configure>", lambda _e: self.redraw_preview())
        self.info_text = tk.Text(right, height=12, wrap=tk.WORD, bg=LENS_PANEL, fg=TEXT, insertbackground=TEXT, relief="flat", bd=0)
        self.info_text.pack(fill="both", expand=True, padx=10, pady=(0, 10))
        self.info_text.config(state=tk.DISABLED)
        tk.Label(right, text="Generated Install Plan", bg=LENS_BG, fg=TEXT, font=("Segoe UI", 10, "bold"), anchor="w").pack(fill="x", padx=10)
        self.plan_text = tk.Text(right, height=8, wrap=tk.WORD, bg="#0F0B16", fg=TEXT_MUTED, insertbackground=TEXT, relief="flat", bd=0)
        self.plan_text.pack(fill="x", padx=10, pady=(4, 10))
        self.plan_text.config(state=tk.DISABLED)

        footer = tk.Frame(self, bg=ORRERY_BG_2, height=52)
        footer.pack(side=tk.BOTTOM, fill=tk.X)
        footer.pack_propagate(False)
        tk.Button(footer, text="Install Selected Payloads", command=self.run_install, width=24).pack(side=tk.RIGHT, padx=(8, 14), pady=10)
        tk.Button(footer, text="Cancel", command=self.destroy, width=12).pack(side=tk.RIGHT, padx=8, pady=10)

    def build_wizard(self):
        pages = self.package.wizard.get("pages", []) if isinstance(self.package.wizard, dict) else []
        if not pages:
            tk.Label(self.option_frame, text="This installer has no wizard pages.", bg=LENS_BG, fg=TEXT_MUTED).pack(anchor="w", padx=12, pady=12)
            return

        for page in pages:
            page_name = page.get("name") or "Install"
            self.step_list.insert(tk.END, page_name)
            page_label = tk.Label(self.option_frame, text=page_name, bg=LENS_BG, fg=LENS_GOLD, font=("Segoe UI", 14, "bold"), anchor="w")
            page_label.pack(fill="x", padx=12, pady=(14, 4))

            for group in page.get("groups", []):
                self.build_group(group)

        if self.initial_option_id and self.initial_option_id in self.option_by_id:
            self.show_option(self.option_by_id[self.initial_option_id])
        elif self.option_order:
            self.show_option(self.option_by_id[self.option_order[0]])

    def build_group(self, group: dict):
        group_id = group.get("id") or f"group_{len(self.group_controls)}"
        mode = group.get("selection_mode") or "multi"
        required = bool(group.get("required", False))
        defaults = set(group.get("default_option_ids", []) or [])
        use_previous = bool(self.previous_option_ids)

        frame = tk.LabelFrame(
            self.option_frame,
            text=f" {group.get('name') or 'Options'} ",
            bg=LENS_BG,
            fg=TEXT,
            font=("Segoe UI", 10, "bold"),
            highlightthickness=1,
            highlightbackground=LENS_EDGE,
        )
        frame.pack(fill="x", padx=12, pady=8)

        options = list(group.get("options", []) or [])
        if mode == "single":
            var = tk.StringVar(value="")
            self.group_controls[group_id] = {"mode": "single", "required": required, "name": group.get("name") or "Options", "var": var, "options": []}
        else:
            self.group_controls[group_id] = {"mode": "multi", "required": required, "name": group.get("name") or "Options", "options": []}

        for idx, option in enumerate(options):
            option_id = option.get("id") or f"{group_id}_option_{idx}"
            option["id"] = option_id
            self.option_by_id[option_id] = option
            self.option_order.append(option_id)

            selected = option_id in self.previous_option_ids if use_previous else (option_id in defaults or bool(option.get("default_selected", False)))
            card = tk.Frame(frame, bg=LENS_PANEL, highlightthickness=1, highlightbackground="#4B3A66", padx=8, pady=6)
            card.pack(fill="x", padx=8, pady=5)
            card.bind("<Button-1>", lambda _e, opt=option: self.show_option(opt))

            if mode == "single":
                if selected or (required and not self.group_controls[group_id]["var"].get() and idx == 0 and not defaults and not use_previous):
                    self.group_controls[group_id]["var"].set(option_id)
                if self.group_controls[group_id]["var"].get() == option_id and not self.initial_option_id:
                    self.initial_option_id = option_id
                widget = tk.Radiobutton(
                    card,
                    text=option.get("name") or "Option",
                    variable=self.group_controls[group_id]["var"],
                    value=option_id,
                    bg=LENS_PANEL,
                    fg=TEXT,
                    activebackground=LENS_PANEL,
                    activeforeground=TEXT,
                    selectcolor=LENS_BG,
                    command=lambda opt=option: self.select_option(opt),
                )
            else:
                var = tk.BooleanVar(value=selected)
                option["_var"] = var
                if selected and not self.initial_option_id:
                    self.initial_option_id = option_id
                widget = tk.Checkbutton(
                    card,
                    text=option.get("name") or "Option",
                    variable=var,
                    bg=LENS_PANEL,
                    fg=TEXT,
                    activebackground=LENS_PANEL,
                    activeforeground=TEXT,
                    selectcolor=LENS_BG,
                    command=lambda opt=option: self.select_option(opt),
                )
            widget.pack(anchor="w")
            widget.bind("<Enter>", lambda _e, opt=option: self.show_option(opt))
            payload_count = len(option.get("payload_ids", []) or [])
            payload_label = tk.Label(card, text=f"{payload_count} payload reference(s)", bg=LENS_PANEL, fg=TEXT_MUTED, anchor="w")
            payload_label.pack(fill="x", padx=24)
            payload_label.bind("<Button-1>", lambda _e, opt=option: self.show_option(opt))
            self.group_controls[group_id]["options"].append(option)

    def select_option(self, option: dict):
        self.show_option(option)
        self.refresh_plan()

    def selected_option_ids(self) -> List[str]:
        selected: List[str] = []
        for control in self.group_controls.values():
            if control["mode"] == "single":
                value = control["var"].get()
                if value:
                    selected.append(value)
            else:
                for option in control["options"]:
                    var = option.get("_var")
                    if var is not None and bool(var.get()):
                        selected.append(option["id"])
        return selected

    @staticmethod
    def normalize_rule_token(value: str) -> str:
        token = str(value or "").strip()
        while token[:1] in {"-", "*"}:
            token = token[1:].strip()
        prefixes = (
            "option:",
            "selected:",
            "mod:",
            "enabled:",
            "dependency:",
            "depends:",
            "requires:",
            "require:",
            "conflict:",
            "file:",
            "installer:",
        )
        lowered = token.lower()
        for prefix in prefixes:
            if lowered.startswith(prefix):
                token = token[len(prefix) :].strip()
                break
        token = token.strip().strip("\"'`()[]{}")
        return " ".join(token.replace("\\", "/").lower().split())

    def parse_rule_line(self, raw: str) -> Tuple[str, bool]:
        text = str(raw or "").strip()
        negated = False
        lowered = text.lower()
        for prefix in ("!", "not:", "not ", "without:", "without ", "missing:", "disabled:", "absent:"):
            if lowered.startswith(prefix):
                negated = True
                text = text[len(prefix) :].strip()
                break
        token = self.normalize_rule_token(text)
        if token in {"", "none", "n/a", "na", "- none"}:
            return "", negated
        return token, negated

    def option_terms(self, option: dict) -> Set[str]:
        terms: Set[str] = set()
        for value in (option.get("id"), option.get("name")):
            token = self.normalize_rule_token(str(value or ""))
            if token:
                terms.add(token)
        return terms

    def enabled_mod_terms(self) -> Set[str]:
        terms: Set[str] = set()
        for mod in self.manager.library_mods:
            if not mod.enabled or mod.parse_error or mod.filename == self.filename:
                continue
            for value in (mod.filename, mod.display_name):
                token = self.normalize_rule_token(value)
                if token:
                    terms.add(token)
                if value:
                    stem = os.path.splitext(str(value))[0]
                    stem_token = self.normalize_rule_token(stem)
                    if stem_token:
                        terms.add(stem_token)
        return terms

    def selected_rule_terms(self, selected_ids: Optional[Set[str]] = None) -> Set[str]:
        selected_ids = selected_ids if selected_ids is not None else set(self.selected_option_ids())
        terms: Set[str] = set()
        for option_id in selected_ids:
            option = self.option_by_id.get(option_id)
            if option:
                terms.update(self.option_terms(option))
        return terms

    def active_rule_terms(self, selected_ids: Optional[Set[str]] = None) -> Set[str]:
        return self.selected_rule_terms(selected_ids) | self.enabled_mod_terms()

    def rule_is_satisfied(self, raw: str, active_terms: Set[str]) -> Optional[bool]:
        token, negated = self.parse_rule_line(raw)
        if not token:
            return None
        active = token in active_terms
        return not active if negated else active

    def conflict_is_active(self, raw: str, active_terms: Set[str]) -> Optional[bool]:
        token, negated = self.parse_rule_line(raw)
        if not token:
            return None
        active = token in active_terms
        return not active if negated else active

    def rule_issues_for_option(self, option: dict, active_terms: Set[str]) -> List[str]:
        label = option.get("name") or option.get("id") or "Option"
        issues: List[str] = []
        for raw in option.get("conditions", []) or []:
            result = self.rule_is_satisfied(raw, active_terms)
            if result is False:
                issues.append(f"{label}: condition not met, {raw}")
        for raw in option.get("dependencies", []) or []:
            result = self.rule_is_satisfied(raw, active_terms)
            if result is False:
                issues.append(f"{label}: missing dependency, {raw}")
        for raw in option.get("conflicts", []) or []:
            result = self.conflict_is_active(raw, active_terms)
            if result is True:
                issues.append(f"{label}: conflicts with {raw}")
        return issues

    def selected_rule_issues(self) -> List[str]:
        selected_ids = set(self.selected_option_ids())
        active_terms = self.active_rule_terms(selected_ids)
        issues: List[str] = []
        for option_id in self.option_order:
            if option_id not in selected_ids:
                continue
            option = self.option_by_id.get(option_id)
            if option:
                issues.extend(self.rule_issues_for_option(option, active_terms))
        return issues

    def rule_status_lines_for_option(self, option: dict) -> List[str]:
        has_rules = any(option.get(key) for key in ("conditions", "dependencies", "conflicts"))
        if not has_rules:
            return []
        active_terms = self.active_rule_terms()
        issues = self.rule_issues_for_option(option, active_terms)
        if not issues:
            return ["Rule Status:", "- Ready"]
        return ["Rule Status:", *[f"- {issue}" for issue in issues[:6]]]

    def option_preview_asset(self, option: dict):
        preview_id = option.get("preview_asset_id") or ""
        asset = self.asset_by_id.get(preview_id)
        if asset and asset.data:
            return asset

        preview_name = str(option.get("preview_display_name") or option.get("preview_name") or "").strip().lower()
        if preview_name:
            for candidate in self.package.assets:
                if (
                    candidate.role == "option_preview"
                    and candidate.data
                    and str(candidate.display_name or "").strip().lower() == preview_name
                ):
                    return candidate

        option_previews = [asset for asset in self.package.assets if asset.role == "option_preview" and asset.data]
        if len(option_previews) == 1:
            return option_previews[0]
        return None

    def required_gaps(self) -> List[str]:
        gaps = []
        selected = set(self.selected_option_ids())
        for control in self.group_controls.values():
            if not control.get("required"):
                continue
            option_ids = {option["id"] for option in control["options"]}
            if not (selected & option_ids):
                gaps.append(control.get("name") or "Options")
        return gaps

    def selected_payloads(self) -> List:
        selected = set(self.selected_option_ids())
        payloads = []
        seen = set()
        for option_id in self.option_order:
            if option_id not in selected:
                continue
            for payload_id in self.option_by_id[option_id].get("payload_ids", []) or []:
                payload = self.payload_by_id.get(payload_id)
                if payload and payload_id not in seen:
                    seen.add(payload_id)
                    payloads.append(payload)
        return payloads

    def payload_to_entry(self, payload) -> ModFileEntry:
        return installer_payload_to_entry(payload)

    def selected_entries(self) -> Tuple[List, List[ModFileEntry], List[str]]:
        return installer_payloads_to_entries(self.selected_payloads())

    def refresh_plan(self):
        payloads, entries, invalid = self.selected_entries()
        targets = {(entry.tail.idx_marker, entry.tail.entry_off) for entry in entries}
        rule_issues = self.selected_rule_issues()
        lines = [
            f"Selected options: {len(self.selected_option_ids())}",
            f"Payloads: {len(payloads)}",
            f"Target IDX entries: {len(targets)}",
        ]
        if self.manager.ledger.is_enabled(self.filename):
            lines.append("Mode: reinstall/update existing selection")
        if invalid:
            lines.append(f"Invalid payloads: {len(invalid)}")
        if rule_issues:
            lines.append(f"Rule blockers: {len(rule_issues)}")
            for issue in rule_issues[:6]:
                lines.append(f"- {issue}")
            if len(rule_issues) > 6:
                lines.append("- ...")
        for payload in payloads[:8]:
            lines.append(f"- {payload.stored_name}")
        if len(payloads) > 8:
            lines.append("- ...")
        self.plan_text.config(state=tk.NORMAL)
        self.plan_text.delete("1.0", tk.END)
        self.plan_text.insert(tk.END, "\n".join(lines))
        self.plan_text.config(state=tk.DISABLED)

    def show_option(self, option: dict):
        lines = [
            option.get("name") or "Option",
            "",
            option.get("description") or "No description.",
            "",
            f"Payloads: {len(option.get('payload_ids', []) or [])}",
        ]
        for label, key in [("Conditions", "conditions"), ("Dependencies", "dependencies"), ("Conflicts", "conflicts")]:
            values = option.get(key, []) or []
            if values:
                lines.append("")
                lines.append(f"{label}:")
                lines.extend(f"- {value}" for value in values)
        status_lines = self.rule_status_lines_for_option(option)
        if status_lines:
            lines.append("")
            lines.extend(status_lines)
        self.info_text.config(state=tk.NORMAL)
        self.info_text.delete("1.0", tk.END)
        self.info_text.insert(tk.END, "\n".join(lines))
        self.info_text.config(state=tk.DISABLED)
        self.current_preview_blob = None
        asset = self.option_preview_asset(option)
        if asset and asset.data:
            self.current_preview_blob = asset.data
        self.redraw_preview()

    def redraw_preview(self):
        canvas = self.preview_canvas
        canvas.delete("all")
        width = max(1, canvas.winfo_width() or int(canvas.cget("width")))
        height = max(1, canvas.winfo_height() or int(canvas.cget("height")))
        canvas.create_rectangle(0, 0, width, height, fill=DETAIL_PREVIEW_BG, outline="")
        blob = getattr(self, "current_preview_blob", None)
        if not blob:
            canvas.create_text(width // 2, height // 2, text="No Option Preview", fill=TEXT_MUTED, font=("Segoe UI", 11, "bold"))
            return
        try:
            with Image.open(BytesIO(blob)) as img:
                if img.mode not in ("RGB", "RGBA"):
                    img = img.convert("RGBA" if "A" in img.getbands() else "RGB")
                if img.mode == "RGBA":
                    composite = Image.new("RGBA", img.size, (18, 13, 24, 255))
                    composite.alpha_composite(img)
                    img = composite.convert("RGB")
                else:
                    img = img.convert("RGB")
                img = trim_installer_preview_padding(img)
                resampling = getattr(getattr(Image, "Resampling", Image), "LANCZOS")
                frame = img.resize((width, height), resampling)
                self.preview_photo = ImageTk.PhotoImage(frame)
                canvas.create_image(0, 0, anchor="nw", image=self.preview_photo)
        except Exception as exc:
            canvas.create_text(width // 2, height // 2, text=f"Preview error:\n{exc}", fill="#FFD2DA", width=280)

    def run_install(self):
        gaps = self.required_gaps()
        if gaps:
            messagebox.showwarning("Required Selection", "Choose an option for:\n\n" + "\n".join(f"- {name}" for name in gaps))
            return

        option_ids = self.selected_option_ids()
        rule_issues = self.selected_rule_issues()
        if rule_issues:
            messagebox.showwarning(
                "Installer Rules Blocked",
                "Resolve these installer rules before installing:\n\n"
                + "\n".join(f"- {issue}" for issue in rule_issues[:12])
                + ("\n- ..." if len(rule_issues) > 12 else ""),
            )
            self.refresh_plan()
            return
        payloads, entries, invalid = self.selected_entries()
        if invalid:
            ok = messagebox.askyesno(
                "Invalid Payloads",
                "Some selected payloads could not be parsed and will be skipped.\n\n"
                + "\n".join(invalid[:8])
                + ("\n..." if len(invalid) > 8 else "")
                + "\n\nContinue with valid payloads?",
            )
            if not ok:
                return
        if not entries:
            messagebox.showwarning("No Payloads", "No valid payloads are selected for installation.")
            return

        targets = {(entry.tail.idx_marker, entry.tail.entry_off) for entry in entries}
        if not self.manager.confirm_apply_collisions(self.filename, targets):
            return

        if self.manager.ledger.is_enabled(self.filename):
            ok = messagebox.askyesno(
                "Reinstall Installer",
                "This installer is already enabled.\n\nDisable the current selection and install the new choices?",
            )
            if not ok:
                return
            if not self.manager.disable_mod(self.filename):
                return

        if not self.manager.apply_entries(self.filename, entries):
            return

        self.manager.record_installer_selection(self.filename, option_ids, payloads, entries, package_type="wizard")
        self.manager.rescan_and_render(status=f"Installed {self.filename} with {len(entries)} installer payload(s).")
        messagebox.showinfo("Installer Complete", f"Installed {len(entries)} payload(s) from {self.filename}.")
        self.destroy()


SELECT_BG = "#0F0C18"
SELECT_BG_2 = "#171224"
SELECT_PANEL = "#1C1530"
SELECT_PANEL_2 = "#281D44"
SELECT_PANEL_3 = "#D7C2EC"
SELECT_TEXT = "#F6F1FF"
SELECT_SUBTEXT = "#CDBCE3"
SELECT_MUTED = "#9D89B8"
SELECT_LINE = "#8E7AE2"
SELECT_STAR = "#EFE8FF"
SELECT_GOLD = "#C9972D"
SELECT_BLUE = "#3F5CA8"
SELECT_GREEN = "#41A35A"
SELECT_ROSE = "#A6526C"
SELECT_NODE = "#6B57C8"
SELECT_NODE_SEL = "#F5D889"
SELECT_NODE_RING = "#A89AF0"

GAME_SELECT_SUMMARIES = {
    "DW7XL": "Four linked data skies.",
    "DW8XL": "Shared IDX plus four BIN skies.",
    "DW8E": "Single container layout.",
    "WO3": "Eight BIN constellation with a big orbit.",
    "WO4": "Single LINKDATA sky.",
    "BN": "Three BIN layout.",
    "WAS": "Single BIN layout.",
}


class GameSelectConstellationCanvas(tk.Canvas):
    def __init__(self, parent: tk.Misc, controller: "ModManagerGameSelect"):
        super().__init__(parent, bg=SELECT_BG, highlightthickness=0, bd=0, relief="flat")
        self.controller = controller
        self.item_to_game: Dict[int, str] = {}
        self.phase = 0.0
        rnd = random.Random(271)
        self.stars = [(rnd.uniform(0.04, 0.96), rnd.uniform(0.06, 0.94), rnd.randint(1, 3)) for _ in range(96)]
        self.bind("<Configure>", lambda _e: self.render())
        self.bind("<Button-1>", self.on_click)
        self.bind("<Double-Button-1>", lambda _e: self.controller.open_selected_game())
        self.after(120, self.tick)

    def tick(self):
        self.phase += 0.08
        if self.winfo_exists():
            self.render()
            self.after(120, self.tick)

    def coords(self, width: int, height: int) -> Dict[str, Tuple[float, float]]:
        return {
            "DW7XL": (width * 0.15, height * 0.29),
            "DW8XL": (width * 0.37, height * 0.20),
            "DW8E": (width * 0.69, height * 0.24),
            "WO3": (width * 0.23, height * 0.66),
            "WO4": (width * 0.52, height * 0.56),
            "BN": (width * 0.52, height * 0.82),
            "WAS": (width * 0.83, height * 0.62),
        }

    def on_click(self, event):
        hit = self.find_overlapping(event.x - 5, event.y - 5, event.x + 5, event.y + 5)
        for item_id in reversed(hit):
            game_id = self.item_to_game.get(item_id)
            if game_id:
                self.controller.select_game(game_id)
                return

    def render(self):
        self.delete("all")
        self.item_to_game.clear()
        width = max(1, self.winfo_width())
        height = max(1, self.winfo_height())
        coords = self.coords(width, height)

        self.create_rectangle(0, 0, width, height, fill=SELECT_BG, outline="")
        self.create_rectangle(0, 0, width, int(height * 0.24), fill=SELECT_BG_2, outline="")
        for idx in range(8):
            y = int(height * 0.16) + idx * 72
            sway = math.sin(self.phase * 0.7 + idx * 0.8) * 11
            self.create_line(0, y + sway, width, y - sway, fill="#211A34", width=1)

        ring_w = max(240, int(width * 0.34))
        ring_h = max(170, int(height * 0.30))
        self.create_arc(22, 24, 22 + ring_w, 24 + ring_h, start=65, extent=242, style=tk.ARC, outline=SELECT_LINE, width=2)
        self.create_arc(width - ring_w - 30, 18, width - 30, 18 + ring_h, start=248, extent=232, style=tk.ARC, outline="#53A0FF", width=2)

        for x, y, radius in self.stars:
            sx = int(x * width)
            sy = int(y * height)
            self.create_oval(sx - radius, sy - radius, sx + radius, sy + radius, fill=SELECT_STAR, outline="")

        links = [
            ("DW7XL", "DW8XL"),
            ("DW8XL", "DW8E"),
            ("DW7XL", "WO3"),
            ("WO3", "WO4"),
            ("WO4", "BN"),
            ("BN", "WAS"),
            ("DW8E", "WAS"),
            ("DW8XL", "WO4"),
            ("DW8XL", "BN"),
        ]
        for left, right in links:
            ax, ay = coords[left]
            bx, by = coords[right]
            self.create_line(ax, ay, bx, by, fill=SELECT_LINE, width=2)

        self.create_text(20, 18, anchor="nw", text="Manager Constellation Gateway", fill=SELECT_TEXT, font=("Segoe UI", 17, "bold"))
        self.create_text(22, 48, anchor="nw", text="Single click a game star to inspect its mod ledger orbit. Double click to open the manager.", fill=SELECT_SUBTEXT, font=("Segoe UI", 9))
        self.create_text(width - 18, 22, anchor="ne", text="Select the sky you want to manage", fill=SELECT_SUBTEXT, font=("Segoe UI", 10, "italic"))

        sorted_items = sorted(MOD_PROFILES.items(), key=lambda kv: kv[1]["display_name"])
        for game_id, profile in sorted_items:
            gx, gy = coords[game_id]
            selected = self.controller.selected_game_id == game_id
            active = self.controller.is_manager_open(game_id)
            pulse = 13 + math.sin(self.phase * 2.0 + gx * 0.01) * 3
            radius = 13 if selected else 10
            fill = SELECT_NODE_SEL if selected else (SELECT_GREEN if active else SELECT_NODE)
            outline = SELECT_GOLD if selected else (SELECT_GREEN if active else SELECT_NODE_RING)
            halo = self.create_oval(
                gx - pulse * 2,
                gy - pulse * 2,
                gx + pulse * 2,
                gy + pulse * 2,
                outline=outline,
                width=1,
                stipple="gray25",
            )
            orb = self.create_oval(gx - radius, gy - radius, gx + radius, gy + radius, fill=fill, outline=outline, width=2)
            short = self.create_text(gx, gy - 26, text=game_id, fill=SELECT_TEXT, font=("Segoe UI", 10, "bold"))
            label = self.create_text(
                gx,
                gy + 30,
                text=profile["display_name"].replace(" (PC)", ""),
                fill=SELECT_SUBTEXT,
                font=("Segoe UI", 9),
                width=180,
            )
            for item in (halo, orb, short, label):
                self.item_to_game[item] = game_id
            if active:
                badge = self.create_text(gx + 20, gy - 14, text="OPEN", fill="#D8FFEA", font=("Segoe UI", 8, "bold"))
                self.item_to_game[badge] = game_id


class ModManagerGameSelect(tk.Toplevel):
    def __init__(self, parent: tk.Misc):
        super().__init__(parent)
        self.child_windows: Dict[str, ModManagerWindowV2] = {}
        self.selected_game_id = "WO3" if "WO3" in MOD_PROFILES else sorted(MOD_PROFILES.keys())[0]
        self.status_var = tk.StringVar(value="Select a constellation to open its manager.")
        self.selected_title_var = tk.StringVar(value="")
        self.selected_meta_var = tk.StringVar(value="")
        self.selected_desc_var = tk.StringVar(value="")
        self.game_buttons: Dict[str, tk.Button] = {}

        self.title("Aldnoah Constellation Manager Gateway")
        self.configure(bg=SELECT_BG)
        self.geometry("1220x1000")
        self.minsize(1080, 900)

        setup_lilac_styles_if_needed(self)
        self.build_gui()
        self.select_game(self.selected_game_id, update_status=False)

    def build_gui(self):
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(1, weight=1)

        hero = tk.Canvas(self, height=168, bg=SELECT_BG, highlightthickness=0, bd=0, relief="flat")
        hero.grid(row=0, column=0, sticky="ew", padx=12, pady=(12, 10))
        hero.bind("<Configure>", lambda e: self.draw_hero(hero, e.width, e.height))

        content = tk.Frame(self, bg=SELECT_BG)
        content.grid(row=1, column=0, sticky="nsew", padx=12, pady=(0, 10))
        content.grid_columnconfigure(0, weight=3)
        content.grid_columnconfigure(1, weight=2)
        content.grid_rowconfigure(0, weight=1)

        left = self.build_panel(content, "Game Field of Stars", "Launch a manager from a live constellation map.", SELECT_BLUE)
        left["panel"].grid(row=0, column=0, sticky="nsew", padx=(0, 8))
        left["body"].grid_rowconfigure(0, weight=1)
        left["body"].grid_columnconfigure(0, weight=1)

        self.selector_canvas = GameSelectConstellationCanvas(left["body"], self)
        self.selector_canvas.grid(row=0, column=0, sticky="nsew", padx=14, pady=(14, 10))

        hint = tk.Label(
            left["body"],
            text="Tip: double click a star to jump straight into that manager.",
            bg=SELECT_PANEL_3,
            fg=SELECT_MUTED,
            anchor="w",
            font=("Segoe UI", 9, "italic"),
        )
        hint.grid(row=1, column=0, sticky="ew", padx=16, pady=(0, 14))

        right = self.build_panel(content, "Selected Orbit", "Review package extensions, ledger naming, and launch state.", SELECT_GOLD)
        right["panel"].grid(row=0, column=1, sticky="nsew", padx=(8, 0))
        right["body"].grid_columnconfigure(0, weight=1)

        title = tk.Label(right["body"], textvariable=self.selected_title_var, bg=SELECT_PANEL_3, fg="#180E2B", font=("Segoe UI", 18, "bold"), anchor="w", justify="left")
        title.grid(row=0, column=0, sticky="ew", padx=18, pady=(18, 6))

        meta = tk.Label(
            right["body"],
            textvariable=self.selected_meta_var,
            bg=SELECT_PANEL_3,
            fg="#3B2E57",
            font=("Consolas", 10),
            anchor="w",
            justify="left",
        )
        meta.grid(row=1, column=0, sticky="ew", padx=18)

        desc = tk.Label(
            right["body"],
            textvariable=self.selected_desc_var,
            bg=SELECT_PANEL_3,
            fg="#33254D",
            wraplength=360,
            justify="left",
            anchor="nw",
            font=("Segoe UI", 10),
            height=5,
        )
        desc.grid(row=2, column=0, sticky="ew", padx=18, pady=(14, 12))

        button_row = tk.Frame(right["body"], bg=SELECT_PANEL_3)
        button_row.grid(row=3, column=0, sticky="ew", padx=18)
        button_row.grid_columnconfigure(0, weight=1)
        button_row.grid_columnconfigure(1, weight=1)

        self.open_button = tk.Button(
            button_row,
            text="Open Selected Manager",
            command=self.open_selected_game,
            bg=SELECT_GREEN,
            fg=SELECT_TEXT,
            activebackground="#57B771",
            activeforeground=SELECT_TEXT,
            relief="flat",
            bd=0,
            padx=12,
            pady=10,
            font=("Segoe UI", 10, "bold"),
            cursor="hand2",
        )
        self.open_button.grid(row=0, column=0, sticky="ew", padx=(0, 6))

        close_button = tk.Button(
            button_row,
            text="Close Gateway",
            command=self.destroy,
            bg=SELECT_BLUE,
            fg=SELECT_TEXT,
            activebackground="#5075D0",
            activeforeground=SELECT_TEXT,
            relief="flat",
            bd=0,
            padx=12,
            pady=10,
            font=("Segoe UI", 10, "bold"),
            cursor="hand2",
        )
        close_button.grid(row=0, column=1, sticky="ew", padx=(6, 0))

        quick_wrap = tk.Frame(right["body"], bg=SELECT_PANEL_2, highlightthickness=1, highlightbackground=SELECT_LINE)
        quick_wrap.grid(row=4, column=0, sticky="nsew", padx=18, pady=(18, 18))
        quick_wrap.grid_columnconfigure(0, weight=1)
        quick_wrap.grid_columnconfigure(1, weight=1)

        quick_title = tk.Label(quick_wrap, text="Quick Launch Grid", bg=SELECT_PANEL_2, fg=SELECT_TEXT, font=("Segoe UI", 11, "bold"))
        quick_title.grid(row=0, column=0, columnspan=2, sticky="w", padx=12, pady=(12, 4))

        quick_sub = tk.Label(
            quick_wrap,
            text="Each node mirrors the star map. Active managers glow green.",
            bg=SELECT_PANEL_2,
            fg=SELECT_SUBTEXT,
            font=("Segoe UI", 9),
            anchor="w",
            justify="left",
        )
        quick_sub.grid(row=1, column=0, columnspan=2, sticky="ew", padx=12, pady=(0, 10))

        sorted_items = sorted(MOD_PROFILES.items(), key=lambda kv: kv[1]["display_name"])
        for idx, (game_id, profile) in enumerate(sorted_items):
            row = 2 + idx // 2
            col = idx % 2
            btn = tk.Button(
                quick_wrap,
                text=profile["display_name"],
                command=lambda gid=game_id: self.select_game(gid),
                relief="flat",
                bd=0,
                padx=10,
                pady=9,
                cursor="hand2",
                wraplength=170,
                justify="center",
                font=("Segoe UI", 9, "bold"),
            )
            btn.grid(row=row, column=col, sticky="ew", padx=12, pady=6)
            self.game_buttons[game_id] = btn

        footer = tk.Frame(self, bg=SELECT_PANEL_2, height=38)
        footer.grid(row=2, column=0, sticky="ew", padx=12, pady=(0, 12))
        footer.grid_propagate(False)
        footer.grid_columnconfigure(0, weight=1)
        status = tk.Label(footer, textvariable=self.status_var, bg=SELECT_PANEL_2, fg=SELECT_TEXT, anchor="w", font=("Segoe UI", 9))
        status.grid(row=0, column=0, sticky="ew", padx=14, pady=8)

    def build_panel(self, parent, title: str, subtitle: str, accent: str):
        panel = tk.Frame(parent, bg=SELECT_PANEL, highlightthickness=1, highlightbackground=SELECT_LINE)
        panel.grid_rowconfigure(1, weight=1)
        panel.grid_columnconfigure(0, weight=1)

        header = tk.Canvas(panel, height=96, bg=SELECT_PANEL, highlightthickness=0, bd=0, relief="flat")
        header.grid(row=0, column=0, sticky="ew")
        header.bind("<Configure>", lambda e, c=header, t=title, s=subtitle, a=accent: self.draw_panel_header(c, e.width, e.height, t, s, a))

        body = tk.Frame(panel, bg=SELECT_PANEL_3)
        body.grid(row=1, column=0, sticky="nsew")
        return {"panel": panel, "header": header, "body": body}

    def draw_hero(self, canvas: tk.Canvas, width: int, height: int):
        canvas.delete("all")
        canvas.create_rectangle(0, 0, width, height, fill=SELECT_BG, outline="")
        canvas.create_rectangle(0, 42, width, height, fill=SELECT_BG_2, outline="")
        for idx in range(38):
            x = ((idx * 91) + 48) % max(1, width)
            y = 22 + ((idx * 41) % max(1, height - 34))
            radius = 1 + (idx % 3)
            canvas.create_oval(x - radius, y - radius, x + radius, y + radius, fill=SELECT_STAR, outline="")

        points = [
            (width * 0.08, height * 0.30),
            (width * 0.19, height * 0.16),
            (width * 0.34, height * 0.38),
            (width * 0.52, height * 0.20),
            (width * 0.69, height * 0.33),
            (width * 0.84, height * 0.13),
            (width * 0.92, height * 0.33),
        ]
        for idx in range(len(points) - 1):
            ax, ay = points[idx]
            bx, by = points[idx + 1]
            canvas.create_line(ax, ay, bx, by, fill=SELECT_LINE, width=1)
        for x, y in points:
            canvas.create_oval(x - 3, y - 3, x + 3, y + 3, fill=SELECT_STAR, outline="")

        canvas.create_arc(36, 18, 196, 148, start=60, extent=250, style=tk.ARC, outline=SELECT_LINE, width=2)
        canvas.create_arc(width - 210, 12, width - 24, 154, start=250, extent=225, style=tk.ARC, outline="#53A0FF", width=2)
        canvas.create_text(34, 34, anchor="nw", text="Aldnoah Constellation Gateway", fill=SELECT_TEXT, font=("Segoe UI", 24, "bold"))
        canvas.create_text(
            36,
            76,
            anchor="nw",
            text="Choose the game sky whose mods you want to browse, enable, or disable.",
            fill=SELECT_SUBTEXT,
            font=("Segoe UI", 10),
        )
        canvas.create_text(width - 20, height - 24, anchor="se", text="Mod manager launch selector", fill=SELECT_SUBTEXT, font=("Segoe UI", 10, "italic"))

    def draw_panel_header(self, canvas: tk.Canvas, width: int, height: int, title: str, subtitle: str, accent: str):
        canvas.delete("all")
        canvas.create_rectangle(0, 0, width, height, fill=SELECT_PANEL, outline="")
        canvas.create_rectangle(0, 0, width, height, fill=SELECT_PANEL_2, outline="")
        for idx in range(18):
            x = ((idx * 63) + 26) % max(1, width)
            y = 14 + ((idx * 29) % max(1, height - 22))
            radius = 1 + (idx % 2)
            canvas.create_oval(x - radius, y - radius, x + radius, y + radius, fill=SELECT_STAR, outline="")
        canvas.create_line(18, height - 26, width - 18, height - 26, fill=accent, width=2)
        canvas.create_text(16, 16, anchor="nw", text=title, fill=SELECT_TEXT, font=("Segoe UI", 15, "bold"))
        canvas.create_text(16, 46, anchor="nw", text=subtitle, fill=SELECT_SUBTEXT, font=("Segoe UI", 9))

    def is_manager_open(self, game_id: str) -> bool:
        win = self.child_windows.get(game_id)
        return bool(win is not None and win.winfo_exists())

    def set_status(self, text: str):
        self.status_var.set(text)

    def update_game_buttons(self):
        for game_id, button in self.game_buttons.items():
            selected = self.selected_game_id == game_id
            active = self.is_manager_open(game_id)
            bg = SELECT_NODE_SEL if selected else (SELECT_GREEN if active else SELECT_PANEL)
            fg = "#180E2B" if selected else SELECT_TEXT
            active_bg = "#F7E6A9" if selected else ("#57B771" if active else SELECT_PANEL_2)
            button.config(
                bg=bg,
                fg=fg,
                activebackground=active_bg,
                activeforeground=fg,
                highlightthickness=1,
                highlightbackground=SELECT_GOLD if selected else (SELECT_GREEN if active else SELECT_LINE),
            )

    def select_game(self, game_id: str, *, update_status: bool = True):
        self.selected_game_id = game_id
        profile = MOD_PROFILES[game_id]
        schema = get_game_schema(game_id)
        manager_state = "Manager window already open." if self.is_manager_open(game_id) else "Manager window not open yet."
        self.selected_title_var.set(profile["display_name"])
        self.selected_meta_var.set(
            "\n".join(
                [
                    f"Game ID      : {game_id}",
                    f"Single Mod   : {profile['single_ext']}",
                    f"Package Mod  : {profile['package_ext']}",
                    f"Ledger File  : {profile['mods_file']}",
                    f"Containers   : {len(schema.containers)}",
                    f"IDX Layouts  : {len(schema.idx_files)}",
                ]
            )
        )
        self.selected_desc_var.set(f"{GAME_SELECT_SUMMARIES.get(game_id, 'Aldnoah game schema ready for constellation management.')}\n\n{manager_state}")
        self.update_game_buttons()
        try:
            self.selector_canvas.render()
        except Exception:
            pass
        if update_status:
            self.set_status(f"Selected {profile['display_name']}.")

    def open_selected_game(self):
        self.open_manager(self.selected_game_id)

    def open_manager(self, game_id: str):
        self.select_game(game_id, update_status=False)
        win = self.child_windows.get(game_id)
        if win is not None and win.winfo_exists():
            win.lift()
            win.focus_force()
            self.set_status(f"{MOD_PROFILES[game_id]['display_name']} is already open.")
            self.update_game_buttons()
            try:
                self.selector_canvas.render()
            except Exception:
                pass
            return
        profile = MOD_PROFILES[game_id]
        win = ModManagerWindowV2(self, game_id, profile)
        self.child_windows[game_id] = win
        self.set_status(f"Opened constellation manager for {profile['display_name']}.")
        self.update_game_buttons()
        try:
            self.selector_canvas.render()
        except Exception:
            pass

        def on_close():
            try:
                win.destroy()
            finally:
                self.child_windows[game_id] = None
                self.update_game_buttons()
                try:
                    self.selector_canvas.render()
                except Exception:
                    pass
                self.set_status(f"Closed constellation manager for {profile['display_name']}.")

        win.protocol("WM_DELETE_WINDOW", on_close)

if __name__ == "__main__":
    raise SystemExit("Run AE/main.pyw to launch Aldnoah Engine tools.")
