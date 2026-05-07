from __future__ import annotations

import binascii, hashlib, json, os, random, uuid
import datetime as _dt
from dataclasses import dataclass, field
from io import BytesIO
from tkinter import filedialog, messagebox, ttk
from typing import Dict, Iterable, List, Optional, Tuple

import tkinter as tk
from PIL import Image, ImageOps, ImageTk

from .aldnoah_energy import LILAC, apply_lilac_to_root, setup_lilac_styles


"""
This file handles the new .Aldnoah format, a custom binary mod installer

Container layout, v1:
    u8   signature_len
    bytes signature                 -> b"ALDNOAHINSTALL"
    u8   format_version             -> 1
    u16  header_flags               -> reserved, currently 0
    u32  section_count

    repeat section_count:
        bytes[4] section_tag         -> META, DATA, PAYL, WIZD
        u64      section_size
        u32      crc32
        bytes    section_data

Sections:
    META: u32 json_len/UTF-8 JSON metadata
    DATA: u32 asset_count/typed binary assets
    PAYL: u32 payload_count/payload file table and file blobs
    WIZD: u32 json_len/UTF-8 JSON wizard tree

The JSON portions are intentionally small and versioned, heavy resources remain
binary blobs with hashes and section CRCs
"""


INSTALLER_SIGNATURE = b"ALDNOAHINSTALL"
INSTALLER_FORMAT_VERSION = 1
INSTALLER_EXTENSION = ".Aldnoah"
SECTION_ORDER = ("META", "DATA", "PAYL", "WIZD")
MAX_GLOBAL_PREVIEWS = 7
MIN_EXPECTED_PAYLOAD_SIZE = 6
AUDIO_WARN_BYTES = 32 * 1024 * 1024

ASSET_ROLES = {
    "preview": 1,
    "option_preview": 2,
    "audio": 3,
    "icon": 4,
    "banner": 5,
}
REV_ASSET_ROLES = {v: k for k, v in ASSET_ROLES.items()}

GENRE_CHOICES = ["All", "Texture", "Model", "Text", "Overhaul", "Misc"]

BG = "#100C19"
PANEL = "#1E1730"
PANEL_2 = "#2B2145"
PANEL_3 = "#DCC6F0"
PANEL_4 = "#E7D9F5"
TEXT = "#F7F1FF"
TEXT_DARK = "#1D1429"
TEXT_MUTED = "#665374"
LINE = "#8E7AE2"
BLUE = "#3F5CA8"
GREEN = "#42A55D"
GOLD = "#B3842F"
RED = "#A04A63"
CANVAS_BG = "#0F0C18"
PREVIEW_SIZE = (420, 236)


def format_bytes(size: int) -> str:
    units = ["B", "KB", "MB", "GB"]
    amount = float(max(0, size))
    for unit in units:
        if amount < 1024.0 or unit == units[-1]:
            if unit == "B":
                return f"{int(amount)} {unit}"
            return f"{amount:.1f} {unit}"
        amount /= 1024.0
    return f"{size} B"


def sanitize_filename(text: str) -> str:
    base = (text or "").strip() or "Unnamed"
    safe = "".join(ch if ch not in '<>:"/\\|?*' else "_" for ch in base)
    return safe.strip(" .") or "Unnamed"


def is_wav_bytes(raw: bytes) -> bool:
    return len(raw) >= 12 and raw[:4] == b"RIFF" and raw[8:12] == b"WAVE"


def make_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:12]}"


def split_lines(text: str) -> List[str]:
    out: List[str] = []
    for line in (text or "").replace(",", "\n").splitlines():
        item = line.strip()
        if item:
            out.append(item)
    return out


def asset_lookup_key(role: str, path: str) -> Tuple[str, str]:
    return role, os.path.normcase(os.path.abspath(path))


def write_u8(handle, value: int):
    handle.write(int(value).to_bytes(1, "little", signed=False))


def write_u16(handle, value: int):
    handle.write(int(value).to_bytes(2, "little", signed=False))


def write_u32(handle, value: int):
    handle.write(int(value).to_bytes(4, "little", signed=False))


def write_u64(handle, value: int):
    handle.write(int(value).to_bytes(8, "little", signed=False))


def read_exact(handle, size: int, label: str) -> bytes:
    data = handle.read(size)
    if len(data) != size:
        raise ValueError(f"Unexpected EOF while reading {label}.")
    return data


def skip_bytes(handle, size: int, label: str = "bytes"):
    if size <= 0:
        return
    skipper = getattr(handle, "skip", None)
    if callable(skipper):
        skipper(size, label)
        return
    handle.seek(size, os.SEEK_CUR)


class CRCSectionReader:
    def __init__(self, handle, size: int, label: str):
        self.handle = handle
        self.remaining = int(size)
        self.label = label
        self.crc = 0

    def read(self, size: int) -> bytes:
        size = int(size)
        if size < 0:
            size = self.remaining
        size = min(size, self.remaining)
        data = self.handle.read(size)
        self.remaining -= len(data)
        self.crc = binascii.crc32(data, self.crc) & 0xFFFFFFFF
        return data

    def skip(self, size: int, label: str = "bytes"):
        size = int(size)
        if size > self.remaining:
            raise ValueError(f"Unexpected EOF while skipping {label}.")
        chunk_size = 1024 * 1024
        left = size
        while left > 0:
            chunk = self.read(min(chunk_size, left))
            if not chunk:
                raise ValueError(f"Unexpected EOF while skipping {label}.")
            left -= len(chunk)

    def read_remaining(self) -> bytes:
        return read_exact(self, self.remaining, f"{self.label} section data")

    def finish(self, expected_crc: int):
        if self.remaining:
            self.skip(self.remaining, f"{self.label} section padding")
        if self.crc != expected_crc:
            raise ValueError(f"{self.label} section failed CRC validation.")


def read_u8(handle, label: str) -> int:
    return int.from_bytes(read_exact(handle, 1, label), "little")


def read_u16(handle, label: str) -> int:
    return int.from_bytes(read_exact(handle, 2, label), "little")


def read_u32(handle, label: str) -> int:
    return int.from_bytes(read_exact(handle, 4, label), "little")


def read_u64(handle, label: str) -> int:
    return int.from_bytes(read_exact(handle, 8, label), "little")


def write_sized_string(handle, text: str, size_bytes: int = 2):
    raw = (text or "").encode("utf-8", errors="replace")
    limit = (1 << (size_bytes * 8)) - 1
    if len(raw) > limit:
        raise ValueError(f"String is too long for a {size_bytes}-byte field.")
    handle.write(len(raw).to_bytes(size_bytes, "little"))
    handle.write(raw)


def read_sized_string(handle, size_bytes: int = 2, label: str = "string") -> str:
    if size_bytes == 1:
        size = read_u8(handle, f"{label} length")
    elif size_bytes == 2:
        size = read_u16(handle, f"{label} length")
    else:
        raise ValueError("Unsupported string size field.")
    return read_exact(handle, size, label).decode("utf-8", errors="replace")


def json_blob(data: dict) -> bytes:
    raw = json.dumps(data, ensure_ascii=True, separators=(",", ":"), sort_keys=True).encode("utf-8")
    buf = BytesIO()
    write_u32(buf, len(raw))
    buf.write(raw)
    return buf.getvalue()


def read_json_blob(data: bytes, label: str) -> dict:
    handle = BytesIO(data)
    size = read_u32(handle, f"{label} json length")
    raw = read_exact(handle, size, f"{label} json")
    return json.loads(raw.decode("utf-8"))


def mime_from_path(path: str, fallback: str = "application/octet-stream") -> str:
    ext = os.path.splitext(path)[1].lower()
    if ext in (".jpg", ".jpeg"):
        return "image/jpeg"
    if ext == ".png":
        return "image/png"
    if ext == ".bmp":
        return "image/bmp"
    if ext == ".webp":
        return "image/webp"
    if ext == ".wav":
        return "audio/wav"
    return fallback


def image_bounds_for_role(role: str) -> Tuple[int, int]:
    if role == "banner":
        return (1200, 420)
    if role == "icon":
        return (512, 512)
    if role == "option_preview":
        return (720, 480)
    return (960, 540)


def process_image_asset(path: str, role: str) -> Tuple[bytes, str]:
    bounds = image_bounds_for_role(role)
    with Image.open(path) as img:
        if img.mode not in ("RGB", "RGBA"):
            img = img.convert("RGBA" if "A" in img.getbands() else "RGB")
        if img.mode == "RGBA":
            bg = Image.new("RGBA", img.size, (16, 12, 25, 255))
            bg.alpha_composite(img)
            img = bg.convert("RGB")
        else:
            img = img.convert("RGB")

        resampling = getattr(getattr(Image, "Resampling", Image), "LANCZOS")
        if role in {"preview", "option_preview"}:
            out = img.resize(bounds, resampling)
        else:
            img = ImageOps.contain(img, bounds, method=resampling)
            out = Image.new("RGB", bounds, (16, 12, 25))
            out.paste(img, ((bounds[0] - img.width) // 2, (bounds[1] - img.height) // 2))
        buf = BytesIO()
        out.save(buf, format="JPEG", quality=90, optimize=True)
        return buf.getvalue(), "image/jpeg"


def read_asset_file(path: str, role: str) -> Tuple[bytes, str]:
    if role in {"preview", "option_preview", "icon", "banner"}:
        return process_image_asset(path, role)

    with open(path, "rb") as handle:
        raw = handle.read()
    if role == "audio":
        if not is_wav_bytes(raw):
            raise ValueError(f"{os.path.basename(path)} is not a RIFF/WAVE .wav file.")
        return raw, "audio/wav"
    return raw, mime_from_path(path)


@dataclass
class InstallerAsset:
    asset_id: str
    role: str
    display_name: str
    mime_type: str
    data: bytes
    source_path: str = ""

    @property
    def size(self) -> int:
        return len(self.data)


@dataclass
class InstallerPayload:
    payload_id: str
    stored_name: str
    source_name: str
    sha256: str
    data: bytes
    source_path: str = ""

    @property
    def size(self) -> int:
        return len(self.data)


@dataclass
class AldnoahInstallerPackage:
    metadata: dict
    assets: List[InstallerAsset] = field(default_factory=list)
    payloads: List[InstallerPayload] = field(default_factory=list)
    wizard: dict = field(default_factory=dict)


class AldnoahInstallerWriter:
    def __init__(self, signature: bytes = INSTALLER_SIGNATURE, version: int = INSTALLER_FORMAT_VERSION):
        self.signature = signature
        self.version = version

    def write_installer(self, save_path: str, package: AldnoahInstallerPackage):
        sections = {
            "META": json_blob(package.metadata),
            "DATA": self.build_assets_section(package.assets),
            "PAYL": self.build_payload_section(package.payloads),
            "WIZD": json_blob(package.wizard),
        }

        with open(save_path, "wb") as handle:
            write_u8(handle, len(self.signature))
            handle.write(self.signature)
            write_u8(handle, self.version)
            write_u16(handle, 0)
            write_u32(handle, len(SECTION_ORDER))

            for tag in SECTION_ORDER:
                raw = sections[tag]
                handle.write(tag.encode("ascii"))
                write_u64(handle, len(raw))
                write_u32(handle, binascii.crc32(raw) & 0xFFFFFFFF)
                handle.write(raw)

    @staticmethod
    def build_assets_section(assets: Iterable[InstallerAsset]) -> bytes:
        buf = BytesIO()
        asset_list = list(assets)
        write_u32(buf, len(asset_list))
        for asset in asset_list:
            if asset.role not in ASSET_ROLES:
                raise ValueError(f"Unknown asset role: {asset.role}")
            write_sized_string(buf, asset.asset_id, 2)
            write_u8(buf, ASSET_ROLES[asset.role])
            write_sized_string(buf, asset.display_name, 2)
            write_sized_string(buf, asset.mime_type, 2)
            write_u64(buf, len(asset.data))
            buf.write(asset.data)
        return buf.getvalue()

    @staticmethod
    def build_payload_section(payloads: Iterable[InstallerPayload]) -> bytes:
        buf = BytesIO()
        payload_list = list(payloads)
        write_u32(buf, len(payload_list))
        for payload in payload_list:
            if len(payload.data) < MIN_EXPECTED_PAYLOAD_SIZE:
                raise ValueError(f"{payload.source_name} is too small to contain Aldnoah taildata.")
            digest = bytes.fromhex(payload.sha256)
            if len(digest) != 32:
                raise ValueError(f"{payload.source_name} has an invalid SHA-256 digest.")
            write_sized_string(buf, payload.payload_id, 2)
            write_sized_string(buf, payload.stored_name, 2)
            write_sized_string(buf, payload.source_name, 2)
            buf.write(digest)
            write_u64(buf, len(payload.data))
            buf.write(payload.data)
        return buf.getvalue()


class AldnoahInstallerReader:
    def read(
        self,
        path: str,
        *,
        include_blobs: bool = True,
        include_asset_blobs: Optional[bool] = None,
        include_payload_blobs: Optional[bool] = None,
    ) -> AldnoahInstallerPackage:
        if include_asset_blobs is None:
            include_asset_blobs = include_blobs
        if include_payload_blobs is None:
            include_payload_blobs = include_blobs

        metadata = None
        wizard = None
        assets: List[InstallerAsset] = []
        payloads: List[InstallerPayload] = []
        seen_sections = set()

        with open(path, "rb") as handle:
            sig_len = read_u8(handle, "signature length")
            sig = read_exact(handle, sig_len, "signature")
            if sig != INSTALLER_SIGNATURE:
                raise ValueError("Unsupported installer signature.")

            version = read_u8(handle, "format version")
            if version != INSTALLER_FORMAT_VERSION:
                raise ValueError(f"Unsupported .Aldnoah installer format version: {version}")

            read_u16(handle, "header flags")
            section_count = read_u32(handle, "section count")

            for _ in range(section_count):
                tag = read_exact(handle, 4, "section tag").decode("ascii", errors="replace")
                size = read_u64(handle, f"{tag} section size")
                expected_crc = read_u32(handle, f"{tag} crc32")
                section = CRCSectionReader(handle, size, tag)
                if tag == "META":
                    metadata = read_json_blob(section.read_remaining(), "metadata")
                elif tag == "WIZD":
                    wizard = read_json_blob(section.read_remaining(), "wizard")
                elif tag == "DATA":
                    assets = self.read_assets_section(section, include_blobs=bool(include_asset_blobs))
                elif tag == "PAYL":
                    payloads = self.read_payload_section(section, include_blobs=bool(include_payload_blobs))
                else:
                    section.skip(size, f"{tag} section data")
                section.finish(expected_crc)
                seen_sections.add(tag)

        missing = [tag for tag in SECTION_ORDER if tag not in seen_sections]
        if missing:
            raise ValueError(f"Installer is missing section(s): {', '.join(missing)}")
        return AldnoahInstallerPackage(metadata=metadata or {}, assets=assets, payloads=payloads, wizard=wizard or {})

    @staticmethod
    def read_assets_section(data, *, include_blobs: bool = True) -> List[InstallerAsset]:
        handle = BytesIO(data) if isinstance(data, (bytes, bytearray)) else data
        count = read_u32(handle, "asset count")
        assets: List[InstallerAsset] = []
        for idx in range(count):
            asset_id = read_sized_string(handle, 2, f"asset {idx + 1} id")
            role_byte = read_u8(handle, f"asset {idx + 1} role")
            role = REV_ASSET_ROLES.get(role_byte, "unknown")
            display_name = read_sized_string(handle, 2, f"asset {idx + 1} display name")
            mime_type = read_sized_string(handle, 2, f"asset {idx + 1} mime")
            size = read_u64(handle, f"asset {idx + 1} size")
            blob = read_exact(handle, size, f"asset {idx + 1} data") if include_blobs else b""
            if not include_blobs:
                skip_bytes(handle, size, f"asset {idx + 1} data")
            assets.append(InstallerAsset(asset_id, role, display_name, mime_type, blob))
        return assets

    @staticmethod
    def read_payload_section(data, *, include_blobs: bool = True) -> List[InstallerPayload]:
        handle = BytesIO(data) if isinstance(data, (bytes, bytearray)) else data
        count = read_u32(handle, "payload count")
        payloads: List[InstallerPayload] = []
        for idx in range(count):
            payload_id = read_sized_string(handle, 2, f"payload {idx + 1} id")
            stored_name = read_sized_string(handle, 2, f"payload {idx + 1} stored name")
            source_name = read_sized_string(handle, 2, f"payload {idx + 1} source name")
            sha256 = read_exact(handle, 32, f"payload {idx + 1} sha256").hex()
            size = read_u64(handle, f"payload {idx + 1} size")
            blob = read_exact(handle, size, f"payload {idx + 1} data") if include_blobs else b""
            if not include_blobs:
                skip_bytes(handle, size, f"payload {idx + 1} data")
            payloads.append(InstallerPayload(payload_id, stored_name, source_name, sha256, blob))
        return payloads


class InstallerCreatorWindow(tk.Toplevel):
    def __init__(
        self,
        parent: tk.Misc,
        *,
        game_id: str,
        profile: dict,
        game_dir: str,
        starter_metadata: Optional[dict] = None,
    ):
        super().__init__(parent)
        self.parent = parent
        self.game_id = game_id
        self.profile = profile
        self.game_dir = game_dir
        self.writer = AldnoahInstallerWriter()

        starter_metadata = starter_metadata or {}

        self.title(f"{profile['display_name']} .Aldnoah Installer Architect")
        self.configure(bg=BG)
        self.geometry("1500x930")
        self.minsize(1320, 820)
        setup_lilac_styles(self)
        apply_lilac_to_root(self)

        self.modname = tk.StringVar(value=starter_metadata.get("display_name", ""))
        self.author = tk.StringVar(value=starter_metadata.get("author", ""))
        self.version = tk.StringVar(value=starter_metadata.get("version", ""))
        self.genre = tk.StringVar(value=starter_metadata.get("genre", "Texture") if starter_metadata.get("genre", "Texture") in GENRE_CHOICES else "Texture")
        self.build_mode = tk.StringVar(value=starter_metadata.get("build_mode", "Debug"))
        self.package_type = tk.StringVar(value="wizard")
        self.status_var = tk.StringVar(value="Ready to design a .Aldnoah installer.")
        self.audio_summary_var = tk.StringVar(value="No installer theme WAV selected")
        self.global_summary_var = tk.StringVar(value="No preview, banner, or icon assets selected")
        self._metadata_refresh_pending = False

        self.global_preview_paths: List[str] = list(starter_metadata.get("preview_paths", []) or [])[:MAX_GLOBAL_PREVIEWS]
        self.audio_path: Optional[str] = starter_metadata.get("audio_path") or None
        self.banner_path: Optional[str] = None
        self.icon_path: Optional[str] = None
        self.preview_photo = None
        self.option_preview_photo = None
        self._star_points = self.build_star_points(90, seed=311)

        self.arch_data: Dict[str, dict] = {}
        self.current_item: Optional[str] = None

        self.build_gui()
        self.watch_metadata_fields()
        starter_description = starter_metadata.get("description", "")
        if starter_description:
            self.description.insert("1.0", starter_description)
        self.seed_wizard()
        self.refresh_all()

    def build_gui(self):
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(1, weight=1)

        self.hero = tk.Canvas(self, height=118, bg=BG, highlightthickness=0)
        self.hero.grid(row=0, column=0, sticky="ew", padx=12, pady=(12, 8))
        self.hero.bind("<Configure>", self.draw_hero)

        body = tk.Frame(self, bg=BG)
        body.grid(row=1, column=0, sticky="nsew", padx=12, pady=4)
        body.grid_columnconfigure(0, weight=0, minsize=300)
        body.grid_columnconfigure(1, weight=1, minsize=480)
        body.grid_columnconfigure(2, weight=1, minsize=460)
        body.grid_rowconfigure(0, weight=1)

        left = self.build_panel(body, "Install Steps", "Pages, groups, and options", width=300)
        left.grid(row=0, column=0, sticky="nsew", padx=(0, 8))
        center = self.build_panel(body, "Architect Core", "Metadata and selected node editor", width=480)
        center.grid(row=0, column=1, sticky="nsew", padx=8)
        right = self.build_panel(body, "Live Plan", "Preview, details, and generated install plan", width=460)
        right.grid(row=0, column=2, sticky="nsew", padx=(8, 0))

        self.build_left(left.body)
        self.build_center(center.body)
        self.build_right(right.body)

        footer = tk.Frame(self, bg=BG, height=62)
        footer.grid(row=2, column=0, sticky="ew", padx=12, pady=(8, 12))
        footer.grid_columnconfigure(0, weight=1)
        self.status_label = tk.Label(footer, textvariable=self.status_var, bg=BG, fg="#CDBCE3", font=("Segoe UI", 10, "bold"))
        self.status_label.grid(row=0, column=0, sticky="w")
        self.action_button(footer, f"Create Installer ({INSTALLER_EXTENSION})", self.create_installer, GREEN).grid(row=0, column=1, sticky="e", padx=(8, 0))

    def build_panel(self, parent: tk.Misc, title: str, subtitle: str, width: int = 300):
        outer = tk.Frame(parent, bg=LINE, highlightthickness=0, width=width)
        outer.grid_propagate(False)
        outer.grid_rowconfigure(1, weight=1)
        outer.grid_columnconfigure(0, weight=1)
        header = tk.Canvas(outer, height=74, bg=PANEL, highlightthickness=0)
        header.grid(row=0, column=0, sticky="ew")
        header.bind("<Configure>", lambda event, c=header, t=title, s=subtitle: self.draw_panel_header(c, t, s))
        body = tk.Frame(outer, bg=PANEL_3, padx=12, pady=12)
        body.grid(row=1, column=0, sticky="nsew")
        outer.body = body  # type: ignore[attr-defined]
        return outer

    def build_left(self, parent: tk.Frame):
        parent.grid_rowconfigure(1, weight=1)
        parent.grid_columnconfigure(0, weight=1)

        tools = tk.Frame(parent, bg=PANEL_3)
        tools.grid(row=0, column=0, sticky="ew")
        self.mini_button(tools, "+ Page", self.add_page, BLUE).pack(side="left", padx=(0, 5), pady=(0, 8))
        self.mini_button(tools, "+ Group", self.add_group, BLUE).pack(side="left", padx=5, pady=(0, 8))
        self.mini_button(tools, "+ Option", self.add_option, BLUE).pack(side="left", padx=5, pady=(0, 8))

        self.tree = ttk.Treeview(parent, selectmode="browse", show="tree")
        self.tree.grid(row=1, column=0, sticky="nsew", pady=(0, 8))
        self.tree.bind("<<TreeviewSelect>>", self.on_tree_select)

        bottom_tools = tk.Frame(parent, bg=PANEL_3)
        bottom_tools.grid(row=2, column=0, sticky="ew")
        self.mini_button(bottom_tools, "Delete", self.delete_selected, RED).pack(side="left", padx=(0, 6), pady=(0, 10))
        self.mini_button(bottom_tools, "Expand", lambda: self.set_tree_open(True), GOLD).pack(side="left", padx=6, pady=(0, 10))
        self.mini_button(bottom_tools, "Collapse", lambda: self.set_tree_open(False), GOLD).pack(side="left", padx=6, pady=(0, 10))

        assets = tk.Frame(parent, bg=PANEL_4, padx=10, pady=10)
        assets.grid(row=3, column=0, sticky="ew")
        tk.Label(assets, text="Mod Data Assets", bg=PANEL_4, fg=TEXT_DARK, font=("Segoe UI", 10, "bold")).pack(anchor="w")
        tk.Label(assets, textvariable=self.global_summary_var, bg=PANEL_4, fg=TEXT_MUTED, wraplength=260, justify="left", font=("Segoe UI", 9)).pack(anchor="w", pady=(4, 6))
        self.global_preview_list = tk.Listbox(assets, height=4, bg=CANVAS_BG, fg="#E9DEF5", activestyle="none", font=("Consolas", 9), relief="flat", bd=0)
        self.global_preview_list.pack(fill="x", pady=(0, 6))
        self.global_preview_list.bind("<<ListboxSelect>>", self.on_global_preview_select)

        row1 = tk.Frame(assets, bg=PANEL_4)
        row1.pack(fill="x")
        self.mini_button(row1, "+ Preview", self.add_global_preview, BLUE).pack(side="left", padx=(0, 4), pady=3)
        self.mini_button(row1, "- Preview", self.remove_global_preview, RED).pack(side="left", padx=4, pady=3)

        row2 = tk.Frame(assets, bg=PANEL_4)
        row2.pack(fill="x")
        self.mini_button(row2, "Set Banner", self.set_banner, GOLD).pack(side="left", padx=(0, 4), pady=3)
        self.mini_button(row2, "Clear Banner", self.clear_banner, RED).pack(side="left", padx=4, pady=3)

        row2b = tk.Frame(assets, bg=PANEL_4)
        row2b.pack(fill="x")
        self.mini_button(row2b, "Set Icon", self.set_icon, GOLD).pack(side="left", padx=(0, 4), pady=3)
        self.mini_button(row2b, "Clear Icon", self.clear_icon, RED).pack(side="left", padx=4, pady=3)

        row3 = tk.Frame(assets, bg=PANEL_4)
        row3.pack(fill="x")
        self.mini_button(row3, "Theme WAV", self.set_audio, GREEN).pack(side="left", padx=(0, 4), pady=3)
        self.mini_button(row3, "Clear WAV", self.clear_audio, RED).pack(side="left", padx=4, pady=3)
        tk.Label(assets, textvariable=self.audio_summary_var, bg=PANEL_4, fg=TEXT_MUTED, wraplength=260, justify="left", font=("Segoe UI", 9)).pack(anchor="w", pady=(6, 0))

    def build_center(self, parent: tk.Frame):
        parent.grid_columnconfigure(0, weight=1)
        parent.grid_rowconfigure(1, weight=1)

        meta = tk.Frame(parent, bg=PANEL_4, padx=12, pady=12)
        meta.grid(row=0, column=0, sticky="ew", pady=(0, 10))
        for col in range(4):
            meta.grid_columnconfigure(col, weight=1)

        self.field_label(meta, "Installer Name").grid(row=0, column=0, sticky="w")
        tk.Entry(meta, textvariable=self.modname, font=("Segoe UI", 10), relief="flat").grid(row=1, column=0, sticky="ew", padx=(0, 8), ipady=5)
        self.field_label(meta, "Author").grid(row=0, column=1, sticky="w")
        tk.Entry(meta, textvariable=self.author, font=("Segoe UI", 10), relief="flat").grid(row=1, column=1, sticky="ew", padx=8, ipady=5)
        self.field_label(meta, "Version").grid(row=0, column=2, sticky="w")
        tk.Entry(meta, textvariable=self.version, font=("Segoe UI", 10), relief="flat").grid(row=1, column=2, sticky="ew", padx=8, ipady=5)
        self.field_label(meta, "Sky Type").grid(row=0, column=3, sticky="w")
        ttk.Combobox(meta, textvariable=self.genre, values=GENRE_CHOICES, state="readonly").grid(row=1, column=3, sticky="ew", padx=(8, 0), ipady=3)

        self.field_label(meta, "Package Type").grid(row=2, column=0, sticky="w", pady=(10, 0))
        ttk.Combobox(meta, textvariable=self.package_type, values=("wizard", "standard"), state="readonly").grid(row=3, column=0, sticky="ew", padx=(0, 8), ipady=3)
        self.field_label(meta, "Build Mode").grid(row=2, column=1, sticky="w", pady=(10, 0))
        mode_row = tk.Frame(meta, bg=PANEL_4)
        mode_row.grid(row=3, column=1, sticky="ew", padx=8)
        for label in ("Debug", "Release"):
            tk.Radiobutton(mode_row, text=label, value=label, variable=self.build_mode, bg=PANEL_4, activebackground=PANEL_4).pack(side="left", padx=(0, 8))

        self.field_label(meta, "Description").grid(row=2, column=2, sticky="w", pady=(10, 0))
        self.description = tk.Text(meta, height=4, wrap=tk.WORD, relief="flat", padx=8, pady=6, font=("Segoe UI", 9))
        self.description.grid(row=3, column=2, columnspan=2, sticky="ew", padx=(8, 0))

        editor = tk.Frame(parent, bg=PANEL_4, padx=12, pady=12)
        editor.grid(row=1, column=0, sticky="nsew")
        editor.grid_columnconfigure(0, weight=1)
        editor.grid_rowconfigure(0, weight=1)

        self.blank_frame = tk.Frame(editor, bg=PANEL_4)
        self.blank_frame.grid(row=0, column=0, sticky="nsew")
        tk.Label(self.blank_frame, text="Select a page, group, or option to edit.", bg=PANEL_4, fg=TEXT_MUTED, font=("Segoe UI", 13, "bold")).pack(expand=True)

        self.page_frame = tk.Frame(editor, bg=PANEL_4)
        self.group_frame = tk.Frame(editor, bg=PANEL_4)
        self.option_frame = tk.Frame(editor, bg=PANEL_4)
        self.build_page_editor(self.page_frame)
        self.build_group_editor(self.group_frame)
        self.build_option_editor(self.option_frame)

    def build_page_editor(self, parent: tk.Frame):
        parent.grid_columnconfigure(0, weight=1)
        tk.Label(parent, text="Page", bg=PANEL_4, fg=TEXT_DARK, font=("Segoe UI", 15, "bold")).grid(row=0, column=0, sticky="w")
        self.field_label(parent, "Page Name").grid(row=1, column=0, sticky="w", pady=(14, 0))
        self.page_name_entry = tk.Entry(parent, font=("Segoe UI", 12), relief="flat")
        self.page_name_entry.grid(row=2, column=0, sticky="ew", ipady=7)
        self.page_name_entry.bind("<KeyRelease>", self.update_current_name)

    def build_group_editor(self, parent: tk.Frame):
        parent.grid_columnconfigure(0, weight=1)
        tk.Label(parent, text="Group", bg=PANEL_4, fg=TEXT_DARK, font=("Segoe UI", 15, "bold")).grid(row=0, column=0, sticky="w")
        self.field_label(parent, "Group Name").grid(row=1, column=0, sticky="w", pady=(14, 0))
        self.group_name_entry = tk.Entry(parent, font=("Segoe UI", 12), relief="flat")
        self.group_name_entry.grid(row=2, column=0, sticky="ew", ipady=7)
        self.group_name_entry.bind("<KeyRelease>", self.update_current_name)

        row = tk.Frame(parent, bg=PANEL_4)
        row.grid(row=3, column=0, sticky="ew", pady=(14, 0))
        row.grid_columnconfigure(0, weight=1)
        row.grid_columnconfigure(1, weight=1)
        left = tk.Frame(row, bg=PANEL_4)
        left.grid(row=0, column=0, sticky="ew", padx=(0, 10))
        right = tk.Frame(row, bg=PANEL_4)
        right.grid(row=0, column=1, sticky="ew")

        self.field_label(left, "Selection Mode").pack(anchor="w")
        self.group_mode_var = tk.StringVar(value="Single Select")
        mode = ttk.Combobox(left, textvariable=self.group_mode_var, values=("Single Select", "Multi Select"), state="readonly")
        mode.pack(fill="x", ipady=4)
        mode.bind("<<ComboboxSelected>>", lambda _e: self.update_current_group())

        self.group_required_var = tk.BooleanVar(value=True)
        tk.Checkbutton(right, text="Required group", variable=self.group_required_var, command=self.update_current_group, bg=PANEL_4, activebackground=PANEL_4, font=("Segoe UI", 10, "bold")).pack(anchor="w", pady=(22, 0))

        note = (
            "Single select maps to radio choices. Multi select maps to checkboxes. "
            "Required groups must resolve to at least one option during installation."
        )
        tk.Label(parent, text=note, bg=PANEL_4, fg=TEXT_MUTED, wraplength=560, justify="left").grid(row=4, column=0, sticky="w", pady=(16, 0))

    def build_option_editor(self, parent: tk.Frame):
        parent.grid_columnconfigure(0, weight=1)
        parent.grid_columnconfigure(1, weight=0)
        parent.grid_rowconfigure(4, weight=1)

        tk.Label(parent, text="Option", bg=PANEL_4, fg=TEXT_DARK, font=("Segoe UI", 15, "bold")).grid(row=0, column=0, sticky="w")
        self.option_default_var = tk.BooleanVar(value=False)
        tk.Checkbutton(parent, text="Default option", variable=self.option_default_var, command=self.update_current_option, bg=PANEL_4, activebackground=PANEL_4, font=("Segoe UI", 10, "bold")).grid(row=0, column=1, sticky="e")

        self.field_label(parent, "Option Name").grid(row=1, column=0, sticky="w", pady=(12, 0))
        self.option_name_entry = tk.Entry(parent, font=("Segoe UI", 12), relief="flat")
        self.option_name_entry.grid(row=2, column=0, columnspan=2, sticky="ew", ipady=7)
        self.option_name_entry.bind("<KeyRelease>", self.update_current_name)

        self.field_label(parent, "Description").grid(row=3, column=0, sticky="w", pady=(12, 0))
        self.option_desc = tk.Text(parent, height=5, wrap=tk.WORD, relief="flat", padx=8, pady=6, font=("Segoe UI", 9))
        self.option_desc.grid(row=4, column=0, columnspan=2, sticky="nsew")
        self.option_desc.bind("<KeyRelease>", lambda _e: self.update_current_option())

        payload_box = tk.Frame(parent, bg=PANEL_3, padx=10, pady=10)
        payload_box.grid(row=5, column=0, columnspan=2, sticky="ew", pady=(12, 0))
        payload_box.grid_columnconfigure(0, weight=1)
        tk.Label(payload_box, text="Payload References", bg=PANEL_3, fg=TEXT_DARK, font=("Segoe UI", 10, "bold")).grid(row=0, column=0, sticky="w")
        self.option_payload_list = tk.Listbox(payload_box, height=5, bg=CANVAS_BG, fg="#A8FFB2", activestyle="none", font=("Consolas", 9), relief="flat", bd=0)
        self.option_payload_list.grid(row=1, column=0, sticky="ew", pady=(6, 6))
        payload_btns = tk.Frame(payload_box, bg=PANEL_3)
        payload_btns.grid(row=2, column=0, sticky="ew")
        self.mini_button(payload_btns, "+ Payloads", self.add_option_payloads, BLUE).pack(side="left", padx=(0, 5))
        self.mini_button(payload_btns, "- Selected", self.remove_option_payload, RED).pack(side="left", padx=5)
        self.mini_button(payload_btns, "Clear", self.clear_option_payloads, RED).pack(side="left", padx=5)

        adv = tk.Frame(parent, bg=PANEL_4)
        adv.grid(row=6, column=0, columnspan=2, sticky="ew", pady=(12, 0))
        adv.grid_columnconfigure(0, weight=1)
        adv.grid_columnconfigure(1, weight=1)
        adv.grid_columnconfigure(2, weight=1)
        self.conditions_text = self.small_text_box(adv, "Conditions", 0)
        self.dependencies_text = self.small_text_box(adv, "Dependencies", 1)
        self.conflicts_text = self.small_text_box(adv, "Conflicts", 2)

        img_tools = tk.Frame(parent, bg=PANEL_4)
        img_tools.grid(row=7, column=0, columnspan=2, sticky="ew", pady=(12, 0))
        self.mini_button(img_tools, "Set Option Preview", self.set_option_preview, GOLD).pack(side="left", padx=(0, 6))
        self.mini_button(img_tools, "Clear Option Preview", self.clear_option_preview, RED).pack(side="left", padx=6)

    def small_text_box(self, parent: tk.Frame, label: str, column: int) -> tk.Text:
        wrap = tk.Frame(parent, bg=PANEL_4)
        wrap.grid(row=0, column=column, sticky="ew", padx=(0 if column == 0 else 6, 0 if column == 2 else 6))
        self.field_label(wrap, label).pack(anchor="w")
        text = tk.Text(wrap, height=3, wrap=tk.WORD, relief="flat", padx=6, pady=4, font=("Segoe UI", 9))
        text.pack(fill="x")
        text.bind("<KeyRelease>", lambda _e: self.update_current_option())
        return text

    def build_right(self, parent: tk.Frame):
        parent.grid_rowconfigure(2, weight=1)
        parent.grid_columnconfigure(0, weight=1)

        self.preview_canvas = tk.Canvas(parent, width=PREVIEW_SIZE[0], height=PREVIEW_SIZE[1], bg=CANVAS_BG, highlightthickness=1, highlightbackground=LINE)
        self.preview_canvas.grid(row=0, column=0, sticky="ew")
        self.preview_canvas.bind("<Configure>", lambda _event: self.refresh_preview())

        self.info_text = tk.Text(parent, height=8, wrap=tk.WORD, relief="flat", padx=8, pady=8, bg=PANEL_4, fg=TEXT_DARK, font=("Segoe UI", 9))
        self.info_text.grid(row=1, column=0, sticky="ew", pady=(10, 10))
        self.info_text.config(state=tk.DISABLED)

        tk.Label(parent, text="Generated Install Plan", bg=PANEL_3, fg=TEXT_DARK, font=("Segoe UI", 11, "bold"), anchor="w").grid(row=2, column=0, sticky="sw")
        self.plan_text = tk.Text(parent, height=18, wrap=tk.WORD, relief="flat", padx=8, pady=8, bg=CANVAS_BG, fg="#E8DFF7", font=("Consolas", 9))
        self.plan_text.grid(row=3, column=0, sticky="nsew", pady=(6, 0))
        self.plan_text.config(state=tk.DISABLED)

    def field_label(self, parent: tk.Misc, text: str):
        return tk.Label(parent, text=text, bg=parent.cget("bg"), fg=TEXT_DARK, font=("Segoe UI", 9, "bold"), anchor="w")

    def action_button(self, parent: tk.Misc, text: str, command, color: str):
        return tk.Button(parent, text=text, command=command, bg=color, fg="white", activebackground=color, activeforeground="white", relief="flat", bd=0, padx=18, pady=10, font=("Segoe UI", 10, "bold"), cursor="hand2")

    def mini_button(self, parent: tk.Misc, text: str, command, color: str):
        return tk.Button(parent, text=text, command=command, bg=color, fg="white", activebackground=color, activeforeground="white", relief="flat", bd=0, padx=10, pady=6, font=("Segoe UI", 8, "bold"), cursor="hand2")

    def draw_hero(self, _event=None):
        canvas = self.hero
        canvas.delete("all")
        width = max(1, canvas.winfo_width())
        height = max(1, canvas.winfo_height())
        canvas.create_rectangle(0, 0, width, height, fill=BG, outline="")
        canvas.create_rectangle(0, 40, width, height, fill=PANEL, outline="")
        for x, y, radius in self._star_points:
            sx = int(x * width)
            sy = int(y * height)
            canvas.create_oval(sx - radius, sy - radius, sx + radius, sy + radius, fill="#EFE8FF", outline="")
        canvas.create_arc(26, 14, 218, 148, start=52, extent=248, style=tk.ARC, outline=LINE, width=2)
        canvas.create_arc(width - 240, 10, width - 26, 154, start=238, extent=230, style=tk.ARC, outline="#53A0FF", width=2)
        canvas.create_text(30, 26, anchor="nw", text=".Aldnoah Installer Architect", fill=TEXT, font=("Segoe UI", 22, "bold"))
        canvas.create_text(32, 68, anchor="nw", text=f"{self.profile['display_name']} | Binary wizard format v{INSTALLER_FORMAT_VERSION}", fill="#CDBCE3", font=("Segoe UI", 10))

    def draw_panel_header(self, canvas: tk.Canvas, title: str, subtitle: str):
        canvas.delete("all")
        width = max(1, canvas.winfo_width())
        height = max(1, canvas.winfo_height())
        canvas.create_rectangle(0, 0, width, height, fill=PANEL, outline="")
        canvas.create_rectangle(0, 0, width, 12, fill=LINE, outline="")
        canvas.create_text(14, 22, anchor="nw", text=title, fill=TEXT, font=("Segoe UI", 12, "bold"))
        canvas.create_text(14, 46, anchor="nw", text=subtitle, fill="#CDBCE3", font=("Segoe UI", 9))

    @staticmethod
    def build_star_points(count: int, seed: int) -> List[Tuple[float, float, int]]:
        rng = random.Random(seed)
        return [(rng.uniform(0.04, 0.96), rng.uniform(0.10, 0.92), rng.randint(1, 2)) for _ in range(count)]

    def set_status(self, text: str, color: str = "#CDBCE3"):
        self.status_var.set(text)
        self.status_label.config(fg=color)

    def watch_metadata_fields(self):
        for var in (self.modname, self.author, self.version, self.genre, self.build_mode, self.package_type):
            var.trace_add("write", lambda *_args: self.schedule_metadata_refresh())
        self.description.bind("<KeyRelease>", lambda _event: self.schedule_metadata_refresh())

    def schedule_metadata_refresh(self):
        if self._metadata_refresh_pending:
            return
        self._metadata_refresh_pending = True
        self.after_idle(self.run_metadata_refresh)

    def run_metadata_refresh(self):
        self._metadata_refresh_pending = False
        if hasattr(self, "plan_text"):
            self.refresh_all()

    def seed_wizard(self):
        page = self.create_node("", "page", "Install")
        group = self.create_node(page, "group", "Core Choices")
        option = self.create_node(group, "option", "Default Install")
        self.arch_data[group]["required"] = True
        self.arch_data[option]["default"] = True
        self.tree.item(page, open=True)
        self.tree.item(group, open=True)
        self.tree.selection_set(option)

    def create_node(self, parent: str, node_type: str, name: str) -> str:
        item_id = self.tree.insert(parent, "end", text=name, open=True)
        data = {"type": node_type, "id": make_id(node_type), "name": name}
        if node_type == "group":
            data.update({"selection_type": "Single Select", "required": True})
        elif node_type == "option":
            data.update({
                "description": "",
                "default": False,
                "preview_path": None,
                "payload_paths": [],
                "conditions": "",
                "dependencies": "",
                "conflicts": "",
            })
        self.arch_data[item_id] = data
        return item_id

    def add_page(self):
        count = len([iid for iid, data in self.arch_data.items() if data["type"] == "page"]) + 1
        item_id = self.create_node("", "page", f"Install Page {count}")
        self.tree.selection_set(item_id)
        self.refresh_all()

    def add_group(self):
        parent = self.selected_page_item()
        if not parent:
            parent = self.create_node("", "page", "Install")
        count = len(self.tree.get_children(parent)) + 1
        item_id = self.create_node(parent, "group", f"Choice Group {count}")
        self.tree.item(parent, open=True)
        self.tree.selection_set(item_id)
        self.refresh_all()

    def add_option(self):
        parent = self.selected_group_item()
        if not parent:
            page = self.selected_page_item() or self.create_node("", "page", "Install")
            parent = self.create_node(page, "group", "Core Choices")
            self.tree.item(page, open=True)
        count = len(self.tree.get_children(parent)) + 1
        item_id = self.create_node(parent, "option", f"Option {count}")
        self.tree.item(parent, open=True)
        self.tree.selection_set(item_id)
        self.refresh_all()

    def selected_item(self) -> Optional[str]:
        sel = self.tree.selection()
        return sel[0] if sel else None

    def selected_page_item(self) -> Optional[str]:
        item = self.selected_item()
        while item:
            data = self.arch_data.get(item)
            if data and data["type"] == "page":
                return item
            item = self.tree.parent(item)
        return None

    def selected_group_item(self) -> Optional[str]:
        item = self.selected_item()
        while item:
            data = self.arch_data.get(item)
            if data and data["type"] == "group":
                return item
            item = self.tree.parent(item)
        return None

    def delete_selected(self):
        item = self.selected_item()
        if not item:
            return
        for child in self.walk_tree(item):
            self.arch_data.pop(child, None)
        self.tree.delete(item)
        self.current_item = None
        self.show_editor(None)
        self.refresh_all()

    def walk_tree(self, item: str) -> List[str]:
        out = [item]
        for child in self.tree.get_children(item):
            out.extend(self.walk_tree(child))
        return out

    def set_tree_open(self, open_value: bool):
        for item in self.tree.get_children(""):
            self.set_tree_open_recursive(item, open_value)

    def set_tree_open_recursive(self, item: str, open_value: bool):
        self.tree.item(item, open=open_value)
        for child in self.tree.get_children(item):
            self.set_tree_open_recursive(child, open_value)

    def on_tree_select(self, _event=None):
        item = self.selected_item()
        self.current_item = item
        self.show_editor(item)
        self.refresh_preview()
        self.refresh_info()

    def show_editor(self, item: Optional[str]):
        for frame in (self.blank_frame, self.page_frame, self.group_frame, self.option_frame):
            frame.grid_forget()

        if not item or item not in self.arch_data:
            self.blank_frame.grid(row=0, column=0, sticky="nsew")
            return

        data = self.arch_data[item]
        if data["type"] == "page":
            self.page_frame.grid(row=0, column=0, sticky="nsew")
            self.page_name_entry.delete(0, tk.END)
            self.page_name_entry.insert(0, data["name"])
        elif data["type"] == "group":
            self.group_frame.grid(row=0, column=0, sticky="nsew")
            self.group_name_entry.delete(0, tk.END)
            self.group_name_entry.insert(0, data["name"])
            self.group_mode_var.set(data.get("selection_type", "Single Select"))
            self.group_required_var.set(bool(data.get("required", True)))
        else:
            self.option_frame.grid(row=0, column=0, sticky="nsew")
            self.option_name_entry.delete(0, tk.END)
            self.option_name_entry.insert(0, data["name"])
            self.option_default_var.set(bool(data.get("default", False)))
            self.option_desc.delete("1.0", tk.END)
            self.option_desc.insert("1.0", data.get("description", ""))
            self.conditions_text.delete("1.0", tk.END)
            self.conditions_text.insert("1.0", data.get("conditions", ""))
            self.dependencies_text.delete("1.0", tk.END)
            self.dependencies_text.insert("1.0", data.get("dependencies", ""))
            self.conflicts_text.delete("1.0", tk.END)
            self.conflicts_text.insert("1.0", data.get("conflicts", ""))
            self.option_payload_list.delete(0, tk.END)
            for path in data.get("payload_paths", []):
                self.option_payload_list.insert(tk.END, os.path.basename(path))

    def update_current_name(self, _event=None):
        item = self.current_item
        if not item or item not in self.arch_data:
            return
        data = self.arch_data[item]
        if data["type"] == "page":
            name = self.page_name_entry.get().strip() or "Install Page"
        elif data["type"] == "group":
            name = self.group_name_entry.get().strip() or "Choice Group"
        else:
            name = self.option_name_entry.get().strip() or "Option"
        data["name"] = name
        self.tree.item(item, text=name)
        self.refresh_all()

    def update_current_group(self):
        item = self.current_item
        if not item or self.arch_data.get(item, {}).get("type") != "group":
            return
        self.arch_data[item]["selection_type"] = self.group_mode_var.get()
        self.arch_data[item]["required"] = bool(self.group_required_var.get())
        self.refresh_all()

    def update_current_option(self):
        item = self.current_item
        if not item or self.arch_data.get(item, {}).get("type") != "option":
            return
        data = self.arch_data[item]
        data["default"] = bool(self.option_default_var.get())
        data["description"] = self.option_desc.get("1.0", tk.END).strip()
        data["conditions"] = self.conditions_text.get("1.0", tk.END).strip()
        data["dependencies"] = self.dependencies_text.get("1.0", tk.END).strip()
        data["conflicts"] = self.conflicts_text.get("1.0", tk.END).strip()
        self.refresh_all()

    def add_option_payloads(self):
        item = self.current_item
        if not item or self.arch_data.get(item, {}).get("type") != "option":
            return
        paths = filedialog.askopenfilenames(parent=self, title="Select payload files for this option", filetypes=[("All files", "*.*")])
        if not paths:
            return
        data = self.arch_data[item]
        existing = list(data.get("payload_paths", []))
        added = 0
        for path in paths:
            if path in existing:
                continue
            ok, reason = self.validate_payload_path(path)
            if not ok:
                messagebox.showwarning("Invalid Payload File", f"{os.path.basename(path)}\n\n{reason}")
                continue
            existing.append(path)
            added += 1
        data["payload_paths"] = existing
        self.show_editor(item)
        self.set_status(f"Added {added} payload file(s) to option.", "#9FE7AC" if added else RED)
        self.refresh_all()

    def remove_option_payload(self):
        item = self.current_item
        if not item or self.arch_data.get(item, {}).get("type") != "option":
            return
        sel = list(self.option_payload_list.curselection())
        if not sel:
            self.set_status("Select a payload entry to remove.", RED)
            return
        paths = list(self.arch_data[item].get("payload_paths", []))
        for idx in reversed(sel):
            if 0 <= idx < len(paths):
                del paths[idx]
        self.arch_data[item]["payload_paths"] = paths
        self.show_editor(item)
        self.refresh_all()

    def clear_option_payloads(self):
        item = self.current_item
        if not item or self.arch_data.get(item, {}).get("type") != "option":
            return
        self.arch_data[item]["payload_paths"] = []
        self.show_editor(item)
        self.refresh_all()

    def set_option_preview(self):
        item = self.current_item
        if not item or self.arch_data.get(item, {}).get("type") != "option":
            return
        path = filedialog.askopenfilename(parent=self, title="Select option preview image", filetypes=[("Images", "*.png;*.jpg;*.jpeg;*.bmp;*.webp")])
        if not path:
            return
        self.arch_data[item]["preview_path"] = path
        self.refresh_all()

    def clear_option_preview(self):
        item = self.current_item
        if not item or self.arch_data.get(item, {}).get("type") != "option":
            return
        self.arch_data[item]["preview_path"] = None
        self.refresh_all()

    def on_global_preview_select(self, _event=None):
        self.set_status("Showing selected global preview asset.", BLUE)
        self.refresh_preview()

    def add_global_preview(self):
        if len(self.global_preview_paths) >= MAX_GLOBAL_PREVIEWS:
            messagebox.showwarning("Preview Limit", f"Only {MAX_GLOBAL_PREVIEWS} global preview images can be embedded.")
            return
        paths = filedialog.askopenfilenames(parent=self, title="Select global preview image(s)", filetypes=[("Images", "*.png;*.jpg;*.jpeg;*.bmp;*.webp")])
        if not paths:
            return
        for path in paths:
            if len(self.global_preview_paths) >= MAX_GLOBAL_PREVIEWS:
                break
            if path not in self.global_preview_paths:
                self.global_preview_paths.append(path)
        self.refresh_all()

    def remove_global_preview(self):
        sel = list(self.global_preview_list.curselection())
        if not sel:
            self.set_status("Select a preview image to remove.", RED)
            return
        for idx in reversed(sel):
            if 0 <= idx < len(self.global_preview_paths):
                del self.global_preview_paths[idx]
        self.refresh_all()

    def set_banner(self):
        path = filedialog.askopenfilename(parent=self, title="Select banner art", filetypes=[("Images", "*.png;*.jpg;*.jpeg;*.bmp;*.webp")])
        if path:
            self.banner_path = path
            self.refresh_all()

    def clear_banner(self):
        self.banner_path = None
        self.set_status("Cleared banner art.", BLUE)
        self.refresh_all()

    def set_icon(self):
        path = filedialog.askopenfilename(parent=self, title="Select installer icon", filetypes=[("Images", "*.png;*.jpg;*.jpeg;*.bmp;*.webp")])
        if path:
            self.icon_path = path
            self.refresh_all()

    def clear_icon(self):
        self.icon_path = None
        self.set_status("Cleared installer icon.", BLUE)
        self.refresh_all()

    def set_audio(self):
        path = filedialog.askopenfilename(parent=self, title="Select installer theme WAV", filetypes=[("WAV Audio", "*.wav")])
        if not path:
            return
        try:
            with open(path, "rb") as handle:
                raw = handle.read()
            if not is_wav_bytes(raw):
                raise ValueError("Embedded installer audio must be a RIFF/WAVE .wav file.")
        except Exception as exc:
            messagebox.showerror("Invalid WAV", str(exc))
            return
        if len(raw) > AUDIO_WARN_BYTES:
            messagebox.showwarning("Large WAV", f"{os.path.basename(path)} is {format_bytes(len(raw))}. It is valid, but it will make the installer heavier.")
        self.audio_path = path
        self.refresh_all()

    def clear_audio(self):
        self.audio_path = None
        self.refresh_all()

    def validate_payload_path(self, path: str) -> Tuple[bool, str]:
        if not os.path.isfile(path):
            return False, "Not a file."
        size = os.path.getsize(path)
        if size < MIN_EXPECTED_PAYLOAD_SIZE:
            return False, f"File is too small to contain expected Aldnoah taildata ({size} bytes)."
        return True, ""

    def refresh_all(self):
        self.refresh_assets_list()
        self.refresh_info()
        self.refresh_preview()
        self.refresh_plan()
        self.hero.after_idle(self.draw_hero)

    def refresh_assets_list(self):
        if hasattr(self, "global_preview_list"):
            self.global_preview_list.delete(0, tk.END)
            for path in self.global_preview_paths:
                self.global_preview_list.insert(tk.END, os.path.basename(path))
        bits = []
        if self.global_preview_paths:
            bits.append(f"{len(self.global_preview_paths)} preview(s)")
        if self.banner_path:
            bits.append("banner")
        if self.icon_path:
            bits.append("icon")
        self.global_summary_var.set(", ".join(bits) if bits else "No preview, banner, or icon assets selected")
        if self.audio_path:
            try:
                self.audio_summary_var.set(f"{os.path.basename(self.audio_path)} | {format_bytes(os.path.getsize(self.audio_path))}")
            except OSError:
                self.audio_summary_var.set(os.path.basename(self.audio_path))
        else:
            self.audio_summary_var.set("No installer theme WAV selected")

    def refresh_info(self):
        text = ""
        item = self.current_item
        if item and item in self.arch_data:
            data = self.arch_data[item]
            if data["type"] == "page":
                groups = len(self.tree.get_children(item))
                text = f"Page: {data['name']}\nGroups: {groups}\n\nPages appear as major steps in the left-side installer rail."
            elif data["type"] == "group":
                options = len(self.tree.get_children(item))
                text = (
                    f"Group: {data['name']}\n"
                    f"Mode: {data.get('selection_type', 'Single Select')}\n"
                    f"Required: {'Yes' if data.get('required', True) else 'No'}\n"
                    f"Options: {options}"
                )
            else:
                payloads = data.get("payload_paths", [])
                preview = data.get("preview_path")
                text = (
                    f"Option: {data['name']}\n"
                    f"Default: {'Yes' if data.get('default') else 'No'}\n"
                    f"Payloads: {len(payloads)}\n"
                    f"Preview: {os.path.basename(preview) if preview else 'None'}\n\n"
                    f"{data.get('description', '')}"
                )
        else:
            text = "Select a wizard node to inspect it."
        self.info_text.config(state=tk.NORMAL)
        self.info_text.delete("1.0", tk.END)
        self.info_text.insert("1.0", text)
        self.info_text.config(state=tk.DISABLED)

    def refresh_preview(self):
        canvas = self.preview_canvas
        canvas.delete("all")
        width = max(1, canvas.winfo_width())
        if width <= 1:
            width = max(1, int(canvas.cget("width")))
        height = max(1, canvas.winfo_height())
        if height <= 1:
            height = max(1, int(canvas.cget("height")))
        canvas.create_rectangle(0, 0, width, height, fill=CANVAS_BG, outline="")

        path = None
        sel = self.global_preview_list.curselection() if hasattr(self, "global_preview_list") else ()
        if sel and self.global_preview_paths:
            idx = sel[0]
            if 0 <= idx < len(self.global_preview_paths):
                path = self.global_preview_paths[idx]

        item = self.current_item
        if not path and item and item in self.arch_data and self.arch_data[item]["type"] == "option":
            path = self.arch_data[item].get("preview_path")
        if not path and self.banner_path:
            path = self.banner_path
        if not path and self.global_preview_paths:
            path = self.global_preview_paths[0]

        if path and os.path.isfile(path):
            try:
                with Image.open(path) as img:
                    if img.mode not in ("RGB", "RGBA"):
                        img = img.convert("RGBA" if "A" in img.getbands() else "RGB")
                    if img.mode == "RGBA":
                        bg = Image.new("RGBA", img.size, (15, 12, 24, 255))
                        bg.alpha_composite(img)
                        img = bg.convert("RGB")
                    else:
                        img = img.convert("RGB")
                    resampling = getattr(getattr(Image, "Resampling", Image), "LANCZOS")
                    frame = img.resize((width, height), resampling)
                    self.preview_photo = ImageTk.PhotoImage(frame)
                    canvas.create_image(0, 0, anchor="nw", image=self.preview_photo)
                    canvas.create_rectangle(0, 0, width, height, outline="#B9A7D8")
                    canvas.create_text(10, height - 12, anchor="sw", text=os.path.basename(path), fill="#F4EDFF", font=("Segoe UI", 9, "bold"))
                    return
            except Exception as exc:
                canvas.create_text(width // 2, height // 2, text=f"Preview error:\n{exc}", fill="#FFB9C4", font=("Segoe UI", 10), width=320)
                return

        for x, y, radius in self.build_star_points(28, seed=91):
            sx = int(x * width)
            sy = int(y * height)
            canvas.create_oval(sx - radius, sy - radius, sx + radius, sy + radius, fill="#F4EDFF", outline="")
        canvas.create_arc(28, 30, 186, 190, start=28, extent=270, style=tk.ARC, outline=LINE, width=2)
        canvas.create_text(width // 2, height // 2 - 10, text="No Preview Asset", fill="#F4EDFF", font=("Segoe UI", 15, "bold"))
        canvas.create_text(width // 2, height // 2 + 20, text="Set a banner, global preview, or option preview.", fill="#CFC4E7", font=("Segoe UI", 9), width=380)

    def refresh_plan(self):
        lines, warnings = self.build_plan_lines()
        self.plan_text.config(state=tk.NORMAL)
        self.plan_text.delete("1.0", tk.END)
        self.plan_text.insert("1.0", "\n".join(lines))
        if warnings:
            self.plan_text.insert(tk.END, "\n\nWarnings:\n")
            for warning in warnings:
                self.plan_text.insert(tk.END, f"- {warning}\n")
        self.plan_text.config(state=tk.DISABLED)

    def build_plan_lines(self) -> Tuple[List[str], List[str]]:
        package_type = (self.package_type.get().strip() or "wizard").lower()
        is_standard = package_type == "standard"
        page_count = len(self.tree.get_children(""))
        group_count = 0
        option_count = 0
        payload_paths = set()
        default_lines = []
        warnings = []

        for page_id in self.tree.get_children(""):
            page_data = self.arch_data.get(page_id, {})
            if not is_standard:
                default_lines.append(f"[Page] {page_data.get('name', 'Install')}")
            page_groups = self.tree.get_children(page_id)
            if not page_groups:
                warnings.append(f"Page '{page_data.get('name', 'Install')}' has no groups.")
            for group_id in page_groups:
                group_count += 1
                group = self.arch_data.get(group_id, {})
                options = list(self.tree.get_children(group_id))
                if not options:
                    warnings.append(f"Group '{group.get('name', 'Group')}' has no options.")
                    continue
                mode = "single" if group.get("selection_type") == "Single Select" else "multi"
                required = bool(group.get("required", True))
                default_options = [opt for opt in options if self.arch_data.get(opt, {}).get("default")]
                if mode == "single" and not default_options and required:
                    default_options = options[:1]
                if not is_standard and required and not default_options:
                    warnings.append(f"Required group '{group.get('name', 'Group')}' has no default selection.")
                default_names = [self.arch_data[o]["name"] for o in default_options if o in self.arch_data]
                if not is_standard:
                    default_lines.append(f"  [Group] {group.get('name', 'Group')} ({mode}, {'required' if required else 'optional'})")
                    if default_names:
                        default_lines.append(f"    default: {', '.join(default_names)}")
                for option_id in options:
                    option_count += 1
                    option = self.arch_data.get(option_id, {})
                    payloads = option.get("payload_paths", [])
                    if not payloads:
                        warnings.append(f"Option '{option.get('name', 'Option')}' has no payload files.")
                    for path in payloads:
                        payload_paths.add(path)

        lines = [
            f"Installer: {self.modname.get().strip() or 'Untitled'}",
            f"Game: {self.profile['display_name']} ({self.game_id})",
            f"Genre: {self.genre.get()} | Type: {self.package_type.get()} | Build: {self.build_mode.get()}",
            f"Pages: {page_count} | Groups: {group_count} | Options: {option_count}",
            f"Unique payload blobs: {len(payload_paths)}",
            f"Assets: previews={len(self.global_preview_paths)}, banner={'yes' if self.banner_path else 'no'}, icon={'yes' if self.icon_path else 'no'}, audio={'yes' if self.audio_path else 'no'}",
            "",
        ]
        if is_standard:
            lines.append("Standard install path:")
            lines.append("  Installs every unique payload blob in this package.")
            for path in sorted(payload_paths, key=lambda p: os.path.basename(p).lower())[:12]:
                lines.append(f"  - {os.path.basename(path)}")
            if len(payload_paths) > 12:
                lines.append("  - ...")
            if not payload_paths:
                lines.append("  No payload blobs yet.")
        else:
            lines.append("Default install path:")
            lines.extend(default_lines or ["  No wizard steps yet."])
        return lines, warnings

    def validate_metadata(self) -> dict:
        name = self.modname.get().strip()
        author = self.author.get().strip()
        version = self.version.get().strip()
        description = self.description.get("1.0", tk.END).strip()
        genre = self.genre.get().strip()
        package_type = self.package_type.get().strip() or "wizard"
        if not name:
            raise ValueError("Installer Name is required.")
        if not author:
            raise ValueError("Author is required.")
        if genre not in GENRE_CHOICES:
            raise ValueError("Choose a valid Sky Type.")
        return {
            "format_version": INSTALLER_FORMAT_VERSION,
            "mod_name": name,
            "author": author,
            "version": version,
            "game_profile": self.game_id,
            "game_display_name": self.profile["display_name"],
            "genre": genre,
            "description": description,
            "package_type": package_type,
            "build_mode": self.build_mode.get(),
            "created_utc": _dt.datetime.utcnow().replace(microsecond=0).isoformat() + "Z",
            "builder": "Aldnoah Engine",
            "features": {
                "conflict_preview": True,
                "install_summary": True,
                "save_previous_selections": True,
                "reinstall_with_prior_choices": True,
                "option_previews": True,
                "theme_audio": bool(self.audio_path),
            },
        }

    def build_package(self) -> AldnoahInstallerPackage:
        metadata = self.validate_metadata()
        assets, asset_ids = self.collect_assets()
        payloads, payload_ids = self.collect_payloads()
        if str(metadata.get("package_type", "")).lower() == "standard":
            wizard = {
                "wizard_version": 1,
                "ui": {"layout": "standard"},
                "behavior": {"install_all_payloads": True},
                "pages": [],
            }
        else:
            wizard = self.collect_wizard(asset_ids, payload_ids)
        if not payloads:
            raise ValueError("Add at least one payload file to at least one option.")
        return AldnoahInstallerPackage(metadata=metadata, assets=assets, payloads=payloads, wizard=wizard)

    def collect_assets(self) -> Tuple[List[InstallerAsset], Dict[Tuple[str, str], str]]:
        assets: List[InstallerAsset] = []
        asset_ids: Dict[Tuple[str, str], str] = {}

        def add_asset(path: Optional[str], role: str) -> str:
            if not path:
                return ""
            key = asset_lookup_key(role, path)
            if key in asset_ids:
                return asset_ids[key]
            data, mime = read_asset_file(path, role)
            asset_id = make_id("asset")
            assets.append(InstallerAsset(asset_id, role, os.path.basename(path), mime, data, path))
            asset_ids[key] = asset_id
            return asset_id

        for path in self.global_preview_paths:
            add_asset(path, "preview")
        add_asset(self.banner_path, "banner")
        add_asset(self.icon_path, "icon")
        add_asset(self.audio_path, "audio")
        for item_id, data in self.arch_data.items():
            if data.get("type") == "option":
                add_asset(data.get("preview_path"), "option_preview")
        return assets, asset_ids

    def collect_payloads(self) -> Tuple[List[InstallerPayload], Dict[str, str]]:
        payloads: List[InstallerPayload] = []
        payload_ids: Dict[str, str] = {}
        used_names: Dict[str, int] = {}

        for data in self.arch_data.values():
            if data.get("type") != "option":
                continue
            for path in data.get("payload_paths", []):
                abs_path = os.path.abspath(path)
                if abs_path in payload_ids:
                    continue
                ok, reason = self.validate_payload_path(path)
                if not ok:
                    raise ValueError(f"{os.path.basename(path)}: {reason}")
                with open(path, "rb") as handle:
                    raw = handle.read()
                base = os.path.basename(path)
                count = used_names.get(base, 0)
                used_names[base] = count + 1
                root, ext = os.path.splitext(base)
                stored_name = base if count == 0 else f"{root}_{count + 1}{ext}"
                payload_id = make_id("payload")
                payloads.append(InstallerPayload(payload_id, stored_name, base, hashlib.sha256(raw).hexdigest(), raw, path))
                payload_ids[abs_path] = payload_id
        return payloads, payload_ids

    def collect_wizard(self, asset_ids: Dict[Tuple[str, str], str], payload_ids: Dict[str, str]) -> dict:
        pages = []
        for page_id in self.tree.get_children(""):
            page_data = self.arch_data[page_id]
            page = {"id": page_data["id"], "name": page_data["name"], "groups": []}
            for group_id in self.tree.get_children(page_id):
                group_data = self.arch_data[group_id]
                mode = "single" if group_data.get("selection_type") == "Single Select" else "multi"
                required = bool(group_data.get("required", True))
                group = {
                    "id": group_data["id"],
                    "name": group_data["name"],
                    "selection_mode": mode,
                    "required": required,
                    "min_select": 1 if required else 0,
                    "max_select": 1 if mode == "single" else 0,
                    "default_option_ids": [],
                    "options": [],
                }
                option_ids = list(self.tree.get_children(group_id))
                for option_id in option_ids:
                    option_data = self.arch_data[option_id]
                    preview_path = option_data.get("preview_path")
                    preview_asset_id = ""
                    preview_display_name = ""
                    if preview_path:
                        preview_asset_id = asset_ids.get(asset_lookup_key("option_preview", preview_path), "")
                        preview_display_name = os.path.basename(preview_path)
                    option_payload_ids = [
                        payload_ids[os.path.abspath(path)]
                        for path in option_data.get("payload_paths", [])
                        if os.path.abspath(path) in payload_ids
                    ]
                    option = {
                        "id": option_data["id"],
                        "name": option_data["name"],
                        "description": option_data.get("description", ""),
                        "default_selected": bool(option_data.get("default", False)),
                        "preview_asset_id": preview_asset_id,
                        "preview_display_name": preview_display_name,
                        "payload_ids": option_payload_ids,
                        "conditions": split_lines(option_data.get("conditions", "")),
                        "dependencies": split_lines(option_data.get("dependencies", "")),
                        "conflicts": split_lines(option_data.get("conflicts", "")),
                    }
                    if option["default_selected"]:
                        group["default_option_ids"].append(option["id"])
                    group["options"].append(option)
                if mode == "single" and required and not group["default_option_ids"] and group["options"]:
                    group["default_option_ids"].append(group["options"][0]["id"])
                page["groups"].append(group)
            pages.append(page)

        return {
            "wizard_version": 1,
            "ui": {
                "layout": "constellation",
                "steps_region": "left",
                "options_region": "center",
                "preview_region": "right",
                "plan_region": "bottom",
            },
            "behavior": {
                "conflict_preview": True,
                "install_summary_page": True,
                "save_previous_selections": True,
                "update_with_prior_choices": True,
            },
            "pages": pages,
        }

    def create_installer(self):
        try:
            package = self.build_package()
        except Exception as exc:
            messagebox.showerror("Installer Incomplete", str(exc))
            self.set_status(str(exc), RED)
            return

        default_name = sanitize_filename(package.metadata["mod_name"]) + INSTALLER_EXTENSION
        save_path = filedialog.asksaveasfilename(
            parent=self,
            title=f"Save Aldnoah Installer ({INSTALLER_EXTENSION})",
            defaultextension=INSTALLER_EXTENSION,
            initialdir=self.game_dir,
            initialfile=default_name,
            filetypes=[("Aldnoah Installer", f"*{INSTALLER_EXTENSION}"), ("All files", "*.*")],
        )
        if not save_path:
            self.set_status("Save cancelled.", RED)
            return

        try:
            self.writer.write_installer(save_path, package)
            roundtrip = AldnoahInstallerReader().read(save_path, include_blobs=False)
            package_type = str(package.metadata.get("package_type") or "wizard").lower()
            if package_type == "standard":
                status = (
                    f"Created standard package {os.path.basename(save_path)} with "
                    f"{len(package.payloads)} payload blob(s) and {len(package.assets)} asset(s)."
                )
            else:
                status = (
                    f"Created {os.path.basename(save_path)} with {len(roundtrip.wizard.get('pages', []))} page(s), "
                    f"{len(package.payloads)} payload blob(s), and {len(package.assets)} asset(s)."
                )
            self.set_status(
                status,
                "#9FE7AC",
            )
            messagebox.showinfo("Installer Created", f"Created {os.path.basename(save_path)}")
        except Exception as exc:
            messagebox.showerror("Installer Creation Failed", str(exc))
            self.set_status(f"Creation failed: {exc}", RED)


def open_installer_creator(
    parent: tk.Misc,
    *,
    game_id: str,
    profile: dict,
    game_dir: str,
    starter_metadata: Optional[dict] = None,
) -> InstallerCreatorWindow:
    return InstallerCreatorWindow(
        parent,
        game_id=game_id,
        profile=profile,
        game_dir=game_dir,
        starter_metadata=starter_metadata,
    )


if __name__ == "__main__":
    raise SystemExit("Run AE/main.pyw to launch Aldnoah Engine tools.")
