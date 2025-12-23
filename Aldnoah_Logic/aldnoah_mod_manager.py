
"""
Aldnoah Mod Manager

General mod manager for Koei Tecmo PC container + IDX games using taildata guides

Taildata format (NOT written into BIN when applying):
  6 bytes appended to the end of each extracted file by aldnoah_unpack.py which are
  1 byte idx_marker, 4 byte idx_entry_offset, 1 byte comp_marker

This mod manager:
  reads .<GAME>M (single) and .<GAME>P (package) mod files produced by aldnoah_mod_creator.py
  splits each mod payload from its trailing 6 byte taildata
  appends payload bytes to the selected BIN (16 byte alignment only)
  patches the target IDX entry at idx_entry_offset (resolved from .ref config)
  tracks enabled mods in a ledger and can restore IDX entries on disable
  can Disable All which also truncates BINs back to original sizes

Designed to live alongside:
  aldnoah_config.py (for loading Configs/<GAME>.ref)
  aldnoah_mod_creator.py (extensions/profiles)
"""

from __future__ import annotations

import os
import json
import tkinter as tk
from dataclasses import dataclass
from tkinter import ttk, filedialog, messagebox

from .aldnoah_energy import LILAC, setup_lilac_styles, apply_lilac_to_root
from typing import Dict, List, Optional, Tuple


# Imports with package or script fallback
try:
    # If inside a package (Aldnoah_Logic)
    from .aldnoah_config import load_ref_config
except Exception:
    # If run as a standalone script in the same directory
    from aldnoah_config import load_ref_config


# Theme/constants
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir))
BASE_MODS_DIR = os.path.join(PROJECT_ROOT, "Mods_Folder")

# Keep the same per game profiles as aldnoah_mod_creator.py
MOD_PROFILES = {
    "DW7XL": {"display_name": "Dynasty Warriors 7 XL (PC)",      "single_ext": ".DW7XLM", "package_ext": ".DW7XLP", "mods_file": "DW7XL.MODS"},
    "DW8XL": {"display_name": "Dynasty Warriors 8 XL (PC)",      "single_ext": ".DW8XLM", "package_ext": ".DW8XLP", "mods_file": "DW8XL.MODS"},
    "DW8E":  {"display_name": "Dynasty Warriors 8 Empires (PC)", "single_ext": ".DW8EM",  "package_ext": ".DW8EP",  "mods_file": "DW8E.MODS"},
    "WO3":   {"display_name": "Warriors Orochi 3 (PC)",          "single_ext": ".WO3M",   "package_ext": ".WO3P",   "mods_file": "WO3.MODS"},
    "BN":    {"display_name": "Bladestorm Nightmare (PC)",       "single_ext": ".BNM",    "package_ext": ".BNP",    "mods_file": "BSN.MODS"},
    "WAS":   {"display_name": "Warriors All Stars (PC)",         "single_ext": ".WASM",   "package_ext": ".WASP",   "mods_file": "WAS.MODS"},
}

TAILDATA_LEN = 6
ALIGN = 16


def setup_lilac_styles_if_needed(root: tk.Misc):
    """Ensure lilac ttk style exists for this Tk interpreter (delegates to aldnoah_energy)"""
    setup_lilac_styles(root)
    apply_lilac_to_root(root)

def _normalize_endian(v: str) -> str:
    v = (v or "little").strip().lower()
    if v in ("le", "little", "l"):
        return "little"
    if v in ("be", "big", "b"):
        return "big"
    return "little"


def _ensure_dir(p: str) -> str:
    os.makedirs(p, exist_ok=True)
    return p


def _read_u8(b: bytes, off: int) -> int:
    return b[off]


def _pad_len(pos: int, boundary: int) -> int:
    return (-pos) % boundary


@dataclass
class TailData:
    idx_marker: int
    entry_off: int
    comp_marker: int  # informational only (0/1), not required for apply

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
    payload: bytes
    tail: TailData


@dataclass
class ModMeta:
    display_name: str
    author: str
    version: str
    description: str
    file_count: int


class RefLayout:
    """
    Minimal layout info needed to patch one IDX entry:
    
      entry_size
      field_size/raw_vars + heuristics to write offset/size/flag
      endian
      shift_bits + vars_to_shift (to convert stored offsets <-> byte offsets)
    """

    def __init__(self, cfg: dict):
        self.cfg = cfg
        self.endian = _normalize_endian(str(cfg.get("Endian", "little")))

        self.raw_vars = cfg.get("Raw_Variables", []) or []
        if isinstance(self.raw_vars, str):
            # allow A, B, C style even if someone hand edits .ref
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

        # shift support (PC usually 0)
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

        # Heuristic field picks
        lower = [v.lower() for v in self.raw_vars]
        self.offset_field = self._pick_field(["offset"], prefer=["Offset"])
        self.orig_size_field = self._pick_field(["size"], prefer=["Original_Size", "Full_Size", "Size"], reject=["compressed"])
        self.comp_size_field = self._pick_field(["compressed", "csize"], prefer=["Compressed_Size"], allow_none=True)
        self.comp_flag_field = self._pick_field(["compression", "flag", "marker"], prefer=["Compression_Marker"], allow_none=True)

    def _pick_field(self, contains_any: List[str], prefer: List[str], reject: Optional[List[str]] = None, allow_none: bool = False) -> Optional[str]:
        reject = reject or []
        # exact prefer first
        for p in prefer:
            if p in self.raw_vars:
                return p
        # then heuristic
        for name in self.raw_vars:
            l = name.lower()
            if any(k in l for k in contains_any) and not any(r in l for r in reject):
                return name
        return None if allow_none else (prefer[0] if prefer else None)

    def _field_span(self, field_name: str) -> Tuple[int, int]:
        if field_name not in self.raw_vars or self.field_size <= 0:
            raise KeyError(f"Field '{field_name}' missing in Raw_Variables")
        idx = self.raw_vars.index(field_name)
        start = idx * self.field_size
        end = start + self.field_size
        return start, end

    def patch_entry_bytes(self, entry_bytes: bytes, *, new_data_off_bytes: int, new_size: int, force_uncompressed: bool = True) -> bytes:
        """
        Return a patched copy of the entry bytes
        This is intentionally conservative: if a field is missing, skip it
        """
        if len(entry_bytes) < self.entry_size:
            raise ValueError("IDX entry bytes shorter than entry_size")
        b = bytearray(entry_bytes[:self.entry_size])

        def write_int(field: Optional[str], value: int):
            if not field:
                return
            try:
                s, e = self._field_span(field)
            except Exception:
                return
            width = e - s
            b[s:e] = int(value).to_bytes(width, self.endian, signed=False)

        # offset storage may be shifted (stored in blocks)
        stored_off = int(new_data_off_bytes)
        if self.shift_bits and self.offset_field:
            # If vars_to_shift is empty assume offset fields are shifted
            should_shift = (not self.vars_to_shift) or (self.offset_field in self.vars_to_shift)
            if should_shift:
                stored_off = stored_off >> self.shift_bits

        write_int(self.offset_field, stored_off)

        # sizes
        write_int(self.orig_size_field, int(new_size))
        if self.comp_size_field:
            write_int(self.comp_size_field, int(new_size))

        # compression flag: safest default is uncompressed (0) when applying user edited data
        if self.comp_flag_field and force_uncompressed:
            write_int(self.comp_flag_field, 0)

        return bytes(b)


class ModLedger:
    """
    Binary ledger stored per game
    Records store original IDX entry bytes for restoration

    Record format (repeat until EOF):
      u8  name_len
      u8 name_bytes (if name_len>0 else inherit last)
      u8  idx_marker
      u32 entry_off
      u16 entry_size
      u8 original_entry_bytes[entry_size]
    """

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
        """
        Return bytes for a ledger file with all records for mod_name removed
        """
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
    """
    Parse mod files made by aldnoah_mod_creator.py:
      header: u8 name_len, name bytes, u32 file_count, u8 author_len, author, u8 version_len, version, u16 desc_len, desc
      payload: repeat file_count: u32 size, size bytes
    """
    def __init__(self, path: str):
        self.path = path

    def read(self) -> Tuple[ModMeta, List[ModFileEntry]]:
        with open(self.path, "rb") as f:
            name_len_b = f.read(1)
            if not name_len_b:
                raise ValueError("Empty mod file")
            name_len = int.from_bytes(name_len_b, "little")
            name = f.read(name_len).decode("utf-8", errors="replace")
            file_count = int.from_bytes(f.read(4), "little")

            author_len = int.from_bytes(f.read(1), "little")
            author = f.read(author_len).decode("utf-8", errors="replace")

            version_len = int.from_bytes(f.read(1), "little")
            version = f.read(version_len).decode("utf-8", errors="replace")

            desc_len = int.from_bytes(f.read(2), "little")
            description = f.read(desc_len).decode("utf-8", errors="replace")

            meta = ModMeta(
                display_name=name,
                author=author,
                version=version,
                description=description,
                file_count=file_count,
            )

            entries: List[ModFileEntry] = []
            for _ in range(file_count):
                sz_b = f.read(4)
                if len(sz_b) != 4:
                    raise ValueError("Unexpected EOF while reading file size")
                sz = int.from_bytes(sz_b, "little", signed=False)
                blob = f.read(sz)
                if len(blob) != sz:
                    raise ValueError("Unexpected EOF while reading file blob")
                if sz < TAILDATA_LEN:
                    raise ValueError("A mod blob is smaller than 6-byte taildata; did you select a file not produced by the Aldnoah unpacker?")
                payload = blob[:-TAILDATA_LEN]
                tail_raw = blob[-TAILDATA_LEN:]
                tail = TailData.parse(tail_raw, endian="little")
                entries.append(ModFileEntry(payload=payload, tail=tail))

            return meta, entries


class ModManagerWindow(tk.Toplevel):
    def __init__(self, parent: tk.Misc, game_id: str, profile: dict):
        super().__init__(parent)
        self.game_id = game_id
        self.profile = profile

        self.configure(bg=LILAC)
        self.title(f"{profile['display_name']} Mod Manager")
        self.geometry("1120x760")
        self.resizable(False, False)

        setup_lilac_styles_if_needed(self)

        # paths / config
        self.base_dir: Optional[str] = None
        self.cfg: Optional[dict] = None
        self.layout: Optional[RefLayout] = None
        self.containers: List[str] = []
        self.idx_files: List[str] = []
        self.container_paths: Dict[int, str] = {}  # idx_marker -> chosen path (cached)
        self.idx_paths: Dict[int, str] = {}        # idx_marker -> resolved idx path

        # ledger + orig sizes
        self.game_mod_dir = _ensure_dir(os.path.join(BASE_MODS_DIR, self.game_id))
        self.ledger_path = os.path.join(self.game_mod_dir, profile["mods_file"])
        self.ledger = ModLedger(self.ledger_path)

        
        self.orig_sizes_path = os.path.join(self.game_mod_dir, "orig_container_sizes.json")
        self.state_path = os.path.join(self.game_mod_dir, "manager_state.json")
        self._load_state_and_autoset_install()

        # currently loaded mod (not yet applied)
        self.loaded_mod_path: Optional[str] = None
        self.loaded_mod_name: Optional[str] = None  # display as filename
        self.loaded_meta: Optional[ModMeta] = None
        self.loaded_entries: List[ModFileEntry] = []

        # GUI vars
        self.v_mod_file = tk.StringVar(value="No mod selected.")
        self.v_author = tk.StringVar(value="")
        self.v_version = tk.StringVar(value="")
        self.v_bins_needed = tk.StringVar(value="")
        self.v_status = tk.StringVar(value="")

        self.force_uncompressed = tk.BooleanVar(value=True)

        self._build_gui()
        self._refresh_mods_list()

    # GUI

    def _lilac_label(self, parent, **kw):
        base = dict(bg=LILAC, bd=0, relief="flat", highlightthickness=0, takefocus=0)
        base.update(kw)
        return tk.Label(parent, **base)

    def _build_gui(self):
        # Left: mod info
        self._lilac_label(self, text="Mod File:").place(x=10, y=10)
        self._lilac_label(self, textvariable=self.v_mod_file).place(x=90, y=10)

        self._lilac_label(self, text="Author:").place(x=10, y=45)
        self._lilac_label(self, textvariable=self.v_author).place(x=90, y=45)

        self._lilac_label(self, text="Version:").place(x=10, y=80)
        self._lilac_label(self, textvariable=self.v_version).place(x=90, y=80)

        self._lilac_label(self, text="Bin Needed:").place(x=10, y=115)
        self._lilac_label(self, textvariable=self.v_bins_needed).place(x=100, y=115)

        self._lilac_label(self, text="Description:").place(x=10, y=150)
        self.desc = tk.Text(self, wrap=tk.WORD, height=16, width=58)
        self.desc.place(x=10, y=175)
        self.desc.config(state=tk.DISABLED)

        # Right: enabled mods list
        self._lilac_label(self, text="Enabled Mods:").place(x=640, y=10)
        self.mods_list = tk.Listbox(self, height=22, width=52)
        self.mods_list.place(x=640, y=35)

        # Buttons
        tk.Button(self, text="Set Install Folder", width=18, height=2, command=self.set_install_folder).place(x=460, y=10)
        tk.Button(self, text="Select Mod", width=18, height=2, command=self.select_mod).place(x=460, y=65)
        self.btn_apply = tk.Button(self, text="Apply Mod", width=18, height=2, command=self.apply_loaded_mod)
        self.btn_apply.place(x=460, y=120)

        tk.Button(self, text="Disable Selected", width=18, height=2, command=self.disable_selected).place(x=460, y=200)
        tk.Button(self, text="Disable All (restore + truncate)", width=28, height=2, command=self.disable_all).place(x=430, y=255)

        # Options
        cb = tk.Checkbutton(
            self,
            text="Force uncompressed IDX flag when applying (recommended)",
            variable=self.force_uncompressed,
            bg=LILAC,
            activebackground=LILAC
        )
        cb.place(x=10, y=520)

        # Status
        self.status_label = self._lilac_label(self, textvariable=self.v_status, fg="green")
        self.status_label.place(x=10, y=700)

        # Help text
        help_text = (
            "Workflow:\n"
            "1) Set Install Folder\n"
            "2) Select a mod (.M or .P)\n"
            "3) Apply Mod → you will be prompted to choose the required BIN(s)\n\n"
            "Disable Selected restores IDX entries (does not shrink BIN).\n"
            "Disable All restores IDX and truncates BIN(s) back to original sizes."
        )
        self._lilac_label(self, text=help_text, fg="black").place(x=10, y=560)

    # Install folder + config


    def _load_state(self) -> dict:
        try:
            if os.path.isfile(self.state_path):
                with open(self.state_path, "r", encoding="utf-8") as f:
                    return json.load(f) or {}
        except Exception:
            pass
        return {}

    def _save_state(self, data: dict):
        try:
            os.makedirs(os.path.dirname(self.state_path), exist_ok=True)
            with open(self.state_path, "w", encoding="utf-8") as f:
                json.dump(data or {}, f, indent=2)
        except Exception:
            pass

    def _load_state_and_autoset_install(self):
        """Load saved install folder and container/idx selections for convenience"""
        state = self._load_state()
        install = state.get("install_folder")
        if isinstance(install, str) and install and os.path.isdir(install):
            # Silent auto restore: no popups unless something fails
            try:
                self._set_install_folder_path(install, silent=True)
                self._set_status(f"Restored install folder: {install}", "blue")
            except Exception:
                # If config can't load or paths invalid, user can re-set manually
                pass

        # Restore per bin chosen paths
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

    def _set_install_folder_path(self, base: str, *, silent: bool = False):
        """Core setter used by both the dialog and the auto restore path"""
        if not base or not os.path.isdir(base):
            raise ValueError("Invalid install folder")

        try:
            cfg = load_ref_config(self.game_id)
        except Exception as e:
            if not silent:
                messagebox.showerror("Config Error", f"Failed to load {self.game_id}.ref:\n{e}")
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

        # Pre-resolve idx paths if possible
        self.idx_paths.clear()
        for i, idx_name in enumerate(self.idx_files):
            p = os.path.join(self.base_dir, str(idx_name))
            if os.path.isfile(p):
                self.idx_paths[i] = p

        # Capture original container sizes deterministically from config names (if not already captured)
        self._capture_original_sizes_from_install()

        # Persist state (install folder + any cached selections)
        state = self._load_state()
        state["install_folder"] = self.base_dir
        state.setdefault("container_paths", {})
        state.setdefault("idx_paths", {})
        self._save_state(state)


    def set_install_folder(self):
        base = filedialog.askdirectory(title=f"Select install folder for {self.profile['display_name']}")
        if not base:
            return
        try:
            self._set_install_folder_path(base, silent=False)
        except Exception:
            return

        # Warnings for patching fields (after layout exists)
        if self.layout and self.layout.offset_field not in (self.layout.raw_vars or []):
            messagebox.showwarning(
                "Config Warning",
                "Could not find an Offset-like field in Raw_Variables.\n"
                "Applying mods may not work unless your .ref defines Raw_Variables including an offset field."
            )
        if self.layout and self.layout.orig_size_field and self.layout.orig_size_field not in (self.layout.raw_vars or []):
            messagebox.showwarning(
                "Config Warning",
                "Could not find an Original_Size-like field in Raw_Variables.\n"
                "Applying mods may not work unless your .ref defines the size field."
            )

        self._set_status(f"Install folder set: {self.base_dir}", "blue")

        # Update state with any cached selections
        state = self._load_state()
        state["install_folder"] = self.base_dir
        state["container_paths"] = {str(k): v for k, v in self.container_paths.items()}
        state["idx_paths"] = {str(k): v for k, v in self.idx_paths.items()}
        self._save_state(state)

    def _require_ready(self) -> bool:
        if not self.base_dir or not self.cfg or not self.layout:
            messagebox.showwarning("Not Ready", "Please click 'Set Install Folder' first.")
            return False
        if not self.containers or not self.idx_files:
            messagebox.showwarning("Config Missing", "Your .ref config has no Containers or IDX_Files.")
            return False
        return True

    # Mod selection/display

    def select_mod(self):
        ext1 = self.profile["single_ext"]
        ext2 = self.profile["package_ext"]
        path = filedialog.askopenfilename(
            title=f"Select a mod ({ext1} or {ext2})",
            filetypes=[("Single Mod", f"*{ext1}"), ("Package Mod", f"*{ext2}"), ("All files", "*.*")]
        )
        if not path:
            return

        filename = os.path.basename(path)
        self.loaded_mod_path = path
        self.loaded_mod_name = filename

        # Prevent accidental re-apply
        if self.ledger.is_enabled(filename):
            self._set_status(f"'{filename}' is already enabled. Disable it first to reapply.", "blue")
            self.btn_apply.config(state=tk.DISABLED)
        else:
            self.btn_apply.config(state=tk.NORMAL)

        try:
            meta, entries = ModParser(path).read()
        except Exception as e:
            messagebox.showerror("Mod Parse Error", str(e))
            return

        self.loaded_meta = meta
        self.loaded_entries = entries

        self.v_mod_file.set(filename)
        self.v_author.set(meta.author)
        self.v_version.set(meta.version)

        self.desc.config(state=tk.NORMAL)
        self.desc.delete("1.0", tk.END)
        self.desc.insert(tk.END, meta.description or "")
        self.desc.config(state=tk.DISABLED)

        bins = sorted({e.tail.idx_marker for e in entries})
        self.v_bins_needed.set(", ".join(str(b) for b in bins) if bins else "")

        self._set_status(f"Loaded mod: {filename} ({len(entries)} file(s))", "green")

    # Apply

    def apply_loaded_mod(self):
        if not self._require_ready():
            return
        if not self.loaded_mod_path or not self.loaded_mod_name or not self.loaded_entries:
            self._set_status("No mod loaded.", "red")
            return
        if self.ledger.is_enabled(self.loaded_mod_name):
            self._set_status(f"'{self.loaded_mod_name}' is already enabled. Disable it first to reapply.", "blue")
            return

        # Group entries by required bin index (idx_marker)
        by_bin: Dict[int, List[ModFileEntry]] = {}
        for ent in self.loaded_entries:
            by_bin.setdefault(ent.tail.idx_marker, []).append(ent)

        # Apply per bin group
        total_done = 0
        total = len(self.loaded_entries)
        write_name_next = True  # first record writes name, subsequent use 0 len continuation

        for idx_marker, entries in sorted(by_bin.items(), key=lambda kv: kv[0]):
            bin_path = self._prompt_for_container(idx_marker)
            if not bin_path:
                self._set_status("Apply cancelled.", "red")
                return

            idx_path = self._resolve_idx_path(idx_marker)
            if not idx_path:
                self._set_status(f"Missing IDX for bin index {idx_marker}.", "red")
                return

            # Apply each entry
            for ent in entries:
                try:
                    # append to BIN (16 byte aligned)
                    new_off = self._append_payload(bin_path, ent.payload)

                    # patch IDX entry
                    original_entry = self._read_idx_entry(idx_path, ent.tail.entry_off)
                    patched = self.layout.patch_entry_bytes(
                        original_entry,
                        new_data_off_bytes=new_off,
                        new_size=len(ent.payload),
                        force_uncompressed=bool(self.force_uncompressed.get()),
                    )
                    self._write_idx_entry(idx_path, ent.tail.entry_off, patched)

                    # ledger record (store original bytes so disable can restore)
                    self.ledger.append_record(
                        self.loaded_mod_name,
                        idx_marker=idx_marker,
                        entry_off=ent.tail.entry_off,
                        original_entry=original_entry,
                        entry_size=self.layout.entry_size,
                        write_name=write_name_next,
                    )
                    write_name_next = False

                except Exception as e:
                    messagebox.showerror("Apply Error", f"Failed applying an entry:\n{e}")
                    self._set_status("Apply failed (partial changes may have been written).", "red")
                    return

                total_done += 1
                self._set_status(f"Applying {total_done}/{total}", "blue")
                self.update_idletasks()

        self._refresh_mods_list()
        self.btn_apply.config(state=tk.DISABLED)
        self._set_status("Mod applied successfully.", "green")

        # Clear loaded mod state
        self.loaded_entries = []

    def _prompt_for_container(self, idx_marker: int) -> Optional[str]:
        """
        Prompt the user to pick the required BIN for idx_marker, caching the choice for the session
        The dialog title shows the required bin number
        """
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

        # Validation: if we know expected filename, warn on mismatch
        if expected and os.path.basename(path).lower() != os.path.basename(expected).lower():
            ok = messagebox.askyesno(
                "Confirm BIN Selection",
                f"You selected:\n  {os.path.basename(path)}\n\nBut the config expects:\n  {expected}\n\nUse this file anyway?"
            )
            if not ok:
                return self._prompt_for_container(idx_marker)

        self.container_paths[idx_marker] = path
        # persist selection
        state = self._load_state()
        state["install_folder"] = self.base_dir or state.get("install_folder")
        state["container_paths"] = {str(k): v for k, v in self.container_paths.items()}
        state["idx_paths"] = {str(k): v for k, v in self.idx_paths.items()}
        self._save_state(state)
        return path

    def _resolve_idx_path(self, idx_marker: int) -> Optional[str]:
        """
        Prefer base_dir + config IDX_Files, if missing prompt user

        Special case: if the config uses ONE IDX for MANY containers,
        the IDX file does not depend on idx_marker
        """

        # Single IDX/multi-container mode: always use IDX_Files[0]
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

        # Prompt
        title = f"Select IDX file for BIN {idx_marker}"
        if expected:
            title += f" (expected: {expected})"
        path = filedialog.askopenfilename(title=title, initialdir=self.base_dir or os.getcwd(), filetypes=[("All files", "*.*")])
        if not path:
            return None

        self.idx_paths[idx_marker] = path
        # persist selection
        state = self._load_state()
        state["install_folder"] = self.base_dir or state.get("install_folder")
        state["container_paths"] = {str(k): v for k, v in self.container_paths.items()}
        state["idx_paths"] = {str(k): v for k, v in self.idx_paths.items()}
        self._save_state(state)
        return path

    def _append_payload(self, bin_path: str, payload: bytes) -> int:
        """
        Append payload to BIN with 16 byte alignment
        Returns the byte offset where payload starts
        """
        with open(bin_path, "r+b") as f:
            f.seek(0, os.SEEK_END)
            pos = f.tell()
            pad = _pad_len(pos, ALIGN)
            if pad:
                f.write(b"\x00" * pad)
                pos += pad
            start_off = pos
            f.write(payload)
            # pad EOF for the next append
            end_pos = f.tell()
            pad2 = _pad_len(end_pos, ALIGN)
            if pad2:
                f.write(b"\x00" * pad2)
        return start_off

    def _read_idx_entry(self, idx_path: str, entry_off: int) -> bytes:
        assert self.layout is not None
        with open(idx_path, "rb") as f:
            f.seek(entry_off)
            chunk = f.read(self.layout.entry_size)
        if len(chunk) != self.layout.entry_size:
            raise ValueError(f"IDX entry read failed at offset 0x{entry_off:X} (wanted {self.layout.entry_size} bytes, got {len(chunk)}).")
        return chunk

    def _write_idx_entry(self, idx_path: str, entry_off: int, entry_bytes: bytes):
        assert self.layout is not None
        if len(entry_bytes) < self.layout.entry_size:
            raise ValueError("entry_bytes shorter than entry_size")
        with open(idx_path, "r+b") as f:
            f.seek(entry_off)
            f.write(entry_bytes[:self.layout.entry_size])



    def _capture_original_sizes_from_install(self):
        """
        Record original BIN sizes using config container filenames + current install folder
        This makes truncation stable across sessions (no absolute BIN paths stored)
        """
        if not self.base_dir or not self.containers:
            return

        # If already exists and non-empty keep it
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

    def disable_selected(self):
        if not self._require_ready():
            return
        sel = self.mods_list.curselection()
        if not sel:
            self._set_status("Select a mod in the list first.", "red")
            return
        mod_name = self.mods_list.get(sel[0]).strip()
        if not mod_name:
            return
        self._disable_mod(mod_name)

    def _disable_mod(self, mod_name: str):
        """
        Restore IDX entries for mod_name and remove from ledger
        """
        if not os.path.exists(self.ledger_path):
            self._set_status("No ledger found.", "red")
            return

        target = mod_name.strip().lower()
        restored = 0
        total = 0

        # Restore
        for name, idx_marker, entry_off, entry_size, entry_bytes in self.ledger.iter_records():
            if not name:
                continue
            if name.strip().lower() != target:
                continue
            total += 1
            idx_path = self._resolve_idx_path(idx_marker)
            if not idx_path:
                self._set_status(f"Missing IDX for BIN {idx_marker}; cannot restore.", "red")
                return
            try:
                with open(idx_path, "r+b") as f:
                    f.seek(entry_off)
                    f.write(entry_bytes[:entry_size])
                restored += 1
            except Exception as e:
                messagebox.showerror("Disable Error", f"Failed restoring an IDX entry:\n{e}")
                self._set_status("Disable failed (partial changes may remain).", "red")
                return

        if total == 0:
            self._set_status(f"'{mod_name}' not found in ledger.", "red")
            return

        # Rewrite ledger without those records
        try:
            kept = self.ledger.rewrite_without_mod(mod_name)
            self.ledger.write_raw(kept)
        except Exception as e:
            messagebox.showerror("Ledger Error", f"Failed rewriting ledger:\n{e}")

        self._refresh_mods_list()
        self._set_status(f"Disabled '{mod_name}' (restored {restored}/{total} IDX entries).", "blue")

    def disable_all(self):
        if not self._require_ready():
            return
        if not os.path.exists(self.ledger_path) or os.path.getsize(self.ledger_path) == 0:
            self._set_status("No mods are enabled.", "blue")
            return

        ok = messagebox.askyesno(
            "Disable All",
            "This will:\n"
            "- Restore ALL tracked IDX entries\n"
            "- Truncate BINs back to original sizes (if recorded)\n"
            "- Clear the enabled-mod ledger\n\n"
            "Continue?"
        )
        if not ok:
            return

        # Restore all entries
        restored = 0
        total = 0
        for name, idx_marker, entry_off, entry_size, entry_bytes in self.ledger.iter_records():
            if not name:
                continue
            total += 1
            idx_path = self._resolve_idx_path(idx_marker)
            if not idx_path:
                self._set_status(f"Missing IDX for BIN {idx_marker}; cannot restore all.", "red")
                return
            try:
                with open(idx_path, "r+b") as f:
                    f.seek(entry_off)
                    f.write(entry_bytes[:entry_size])
                restored += 1
            except Exception as e:
                messagebox.showerror("Disable All Error", f"Failed restoring an IDX entry:\n{e}")
                self._set_status("Disable All failed (partial changes may remain).", "red")
                return

        # Truncate bins
        self._truncate_bins_to_original()

        # Clear ledger
        try:
            self.ledger.write_raw(b"")
        except Exception:
            pass

        self._refresh_mods_list()
        self._set_status(f"Disabled all mods (restored {restored}/{total} IDX entries).", "blue")


    def _truncate_bins_to_original(self):
        """
        Truncate BIN containers back to sizes recorded in orig_container_sizes.json
        Uses the current install folder + container filename from config
        """
        if not self.base_dir:
            self._set_status("Warning: install folder unknown; skipping truncation.", "red")
            return
        if not os.path.exists(self.orig_sizes_path):
            self._set_status("Warning: original container sizes not recorded; skipping truncation.", "red")
            return

        try:
            with open(self.orig_sizes_path, "r", encoding="utf-8") as f:
                data = json.load(f) or {}
        except Exception:
            self._set_status("Warning: failed reading original sizes JSON; skipping truncation.", "red")
            return

        truncated = 0
        for key, info in (data or {}).items():
            try:
                idx_marker = int(key)
                container_name = info.get("container")
                size = int(info.get("size", 0))
                if not container_name or size <= 0:
                    continue

                # Prefer a user-picked path if present in this session, else use install folder + config name.
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
            self._set_status(f"Truncated {truncated} BIN file(s) back to original sizes.", "blue")


    # UI helpers

    def _refresh_mods_list(self):
        self.ledger.ensure_exists()
        self.mods_list.delete(0, tk.END)
        for name in self.ledger.list_unique_mods():
            self.mods_list.insert(tk.END, name)

    def _set_status(self, text: str, color: str = "green"):
        self.v_status.set(text)
        try:
            self.status_label.config(fg=color)
        except Exception:
            pass


class ModManagerGameSelect(tk.Toplevel):
    """
    Entry window: choose which game to open
    """
    def __init__(self, parent: tk.Misc):
        super().__init__(parent)
        self.child_windows: Dict[str, ModManagerWindow] = {}

        self.title("Aldnoah Mod Manager, Select Game")
        self.configure(bg=LILAC)
        self.resizable(False, False)
        self.geometry("520x420")

        setup_lilac_styles_if_needed(self)

        tk.Label(self, text="Select a game to open its Mod Manager:", bg=LILAC).place(x=20, y=20)

        row_h = 40
        left_x = 20
        right_x = 260
        top_y = 70
        max_cols = 2

        sorted_items = sorted(MOD_PROFILES.items(), key=lambda kv: kv[1]["display_name"])

        for idx, (game_id, profile) in enumerate(sorted_items):
            row = idx // max_cols
            col = idx % max_cols
            x = left_x if col == 0 else right_x
            y = top_y + row * row_h

            tk.Button(
                self,
                text=profile["display_name"],
                width=30,
                command=lambda gid=game_id: self.open_manager(gid),
            ).place(x=x, y=y)

    def open_manager(self, game_id: str):
        win = self.child_windows.get(game_id)
        if win is not None and win.winfo_exists():
            win.lift()
            win.focus_force()
            return
        profile = MOD_PROFILES[game_id]
        win = ModManagerWindow(self, game_id, profile)
        self.child_windows[game_id] = win

        def on_close():
            try:
                win.destroy()
            finally:
                self.child_windows[game_id] = None

        win.protocol("WM_DELETE_WINDOW", on_close)



def runner():
    root = tk.Tk()
    root.withdraw()
    win = ModManagerGameSelect(root)
    win.protocol("WM_DELETE_WINDOW", root.destroy)
    root.mainloop()

if __name__ == "__main__":
    runner()
