from __future__ import annotations

import math, os, random
import tkinter as tk
from dataclasses import dataclass
from io import BytesIO
from tkinter import filedialog, messagebox, ttk
from typing import Dict, List, Optional, Tuple

from PIL import Image, ImageOps, ImageTk

from .aldnoah_energy import LILAC, apply_lilac_to_root, setup_lilac_styles


PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir))
BASE_MODS_DIR = os.path.join(PROJECT_ROOT, "Mods_Folder")

MOD_PROFILES = {
    "DW7XL": {
        "display_name": "Dynasty Warriors 7 XL (PC)",
        "single_ext": ".DW7XLM",
        "package_ext": ".DW7XLP",
        "mods_file": "DW7XL.MODS",
    },
    "DW8XL": {
        "display_name": "Dynasty Warriors 8 XL (PC)",
        "single_ext": ".DW8XLM",
        "package_ext": ".DW8XLP",
        "mods_file": "DW8XL.MODS",
    },
    "DW8E": {
        "display_name": "Dynasty Warriors 8 Empires (PC)",
        "single_ext": ".DW8EM",
        "package_ext": ".DW8EP",
        "mods_file": "DW8E.MODS",
    },
    "WO3": {
        "display_name": "Warriors Orochi 3 (PC)",
        "single_ext": ".WO3M",
        "package_ext": ".WO3P",
        "mods_file": "WO3.MODS",
    },
    "TK": {
        "display_name": "Toukiden Kiwami (PC)",
        "single_ext": ".TKS",
        "package_ext": ".TKP",
        "mods_file": "TK.MODS",
    },
    "BN": {
        "display_name": "Bladestorm Nightmare (PC)",
        "single_ext": ".BNM",
        "package_ext": ".BNP",
        "mods_file": "BSN.MODS",
    },
    "WAS": {
        "display_name": "Warriors All Stars (PC)",
        "single_ext": ".WASM",
        "package_ext": ".WASP",
        "mods_file": "WAS.MODS",
    },
}

# Aldnoah Mod Package
#   u8  signature_len
#   sig bytes                       -> b"ALDNOAHMOD"
#   u8  format_version              -> 3
#   u8  build_mode                  -> 0=debug, 1=release
#   u8  genre_id
#   u8  display_name_len + name
#   u8  author_len + author
#   u8  version_len + version
#   u16 description_len + description
#   u8  preview_count
#   repeat preview_count: u32 size + jpeg bytes
#   u8  has_audio
#   if has_audio: u32 size + wav bytes
#   u32 payload_count
#   repeat payload_count: u16 stored_name_len + stored_name + u32 payload_size + payload

ALDNOAH_SIGNATURE = b"ALDNOAHMOD"
ALDNOAH_FORMAT_VERSION = 3
MIN_EXPECTED_PAYLOAD_SIZE = 6
MAX_PREVIEW_IMAGES = 5
AUDIO_WARN_BYTES = 32 * 1024 * 1024
PREVIEW_CANVAS_SIZE = (340, 196)
PREVIEW_BG_RGB = (200, 162, 200)

GENRE_CHOICES = ["All", "Texture", "Model", "Text", "Overhaul", "Misc"]
GENRE_MAP = {
    "All": 0,
    "Texture": 1,
    "Model": 2,
    "Text": 3,
    "Overhaul": 4,
    "Misc": 5,
}

CARD_BG = "#DCC1ED"
CARD_ALT_BG = "#E8D8F6"
CARD_OUTLINE = "#8464A4"
HERO_BG = "#120B24"
HERO_MID = "#2C1D4F"
HERO_ACCENT = "#6B5ACD"
TEXT_MAIN = "#20152D"
TEXT_MUTED = "#5B496B"
BUTTON_GREEN = "#42A55D"
BUTTON_GOLD = "#B3842F"
BUTTON_BLUE = "#3F5CA8"
BUTTON_RED = "#A04A63"
CANVAS_BG = "#0F0C18"


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
    base = (text or "").strip()
    if not base:
        return "Unnamed"
    safe = "".join(ch if ch not in '<>:"/\\|?*' else "_" for ch in base)
    return safe.strip(" .") or "Unnamed"


def is_wav_bytes(raw: bytes) -> bool:
    return len(raw) >= 12 and raw[:4] == b"RIFF" and raw[8:12] == b"WAVE"


@dataclass
class PayloadEntry:
    source_path: str
    stored_name: str
    size: int


class AldnoahPackageWriter:
    def __init__(self, signature: bytes = ALDNOAH_SIGNATURE, version: int = ALDNOAH_FORMAT_VERSION):
        self.signature = signature
        self.version = version

    @staticmethod
    def write_the_string(handle, text: str, size_bytes: int = 1):
        raw = (text or "").encode("utf-8", errors="replace")
        max_len = (1 << (size_bytes * 8)) - 1
        if len(raw) > max_len:
            raise ValueError(f"String too long for a {size_bytes}-byte field: {len(raw)} > {max_len}")
        handle.write(len(raw).to_bytes(size_bytes, "little"))
        handle.write(raw)

    @staticmethod
    def process_preview_image(image_path: str) -> bytes:
        try:
            with Image.open(image_path) as img:
                if img.mode not in ("RGB", "RGBA"):
                    img = img.convert("RGBA" if "A" in img.getbands() else "RGB")
                if img.mode == "RGBA":
                    composite = Image.new("RGBA", img.size, PREVIEW_BG_RGB + (255,))
                    composite.alpha_composite(img)
                    img = composite.convert("RGB")
                else:
                    img = img.convert("RGB")
                buf = BytesIO()
                img.save(buf, format="JPEG", quality=88)
                return buf.getvalue()
        except Exception as exc:
            raise ValueError(f"Could not process preview image '{os.path.basename(image_path)}': {exc}") from exc

    @staticmethod
    def read_audio_bytes(audio_path: str) -> bytes:
        with open(audio_path, "rb") as handle:
            raw = handle.read()
        if not is_wav_bytes(raw):
            raise ValueError("Embedded audio must be a RIFF/WAVE .wav file.")
        return raw

    def write_package(
        self,
        save_path: str,
        *,
        display_name: str,
        author: str,
        version_text: str,
        description: str,
        build_release: bool,
        genre_name: str,
        preview_paths: List[str],
        audio_path: Optional[str],
        payload_entries: List[PayloadEntry],
    ) -> None:
        if not payload_entries:
            raise ValueError("No payload entries were provided.")
        if genre_name not in GENRE_MAP:
            raise ValueError(f"Unsupported genre: {genre_name}")

        preview_blobs = [self.process_preview_image(path) for path in preview_paths[:MAX_PREVIEW_IMAGES]]
        audio_blob = self.read_audio_bytes(audio_path) if audio_path else None

        with open(save_path, "wb") as handle:
            handle.write(len(self.signature).to_bytes(1, "little"))
            handle.write(self.signature)
            handle.write(int(self.version).to_bytes(1, "little"))
            handle.write((1 if build_release else 0).to_bytes(1, "little"))
            handle.write(GENRE_MAP[genre_name].to_bytes(1, "little"))
            self.write_the_string(handle, display_name, 1)
            self.write_the_string(handle, author, 1)
            self.write_the_string(handle, version_text, 1)
            self.write_the_string(handle, description, 2)

            handle.write(len(preview_blobs).to_bytes(1, "little"))
            for blob in preview_blobs:
                handle.write(len(blob).to_bytes(4, "little"))
                handle.write(blob)

            if audio_blob:
                handle.write((1).to_bytes(1, "little"))
                handle.write(len(audio_blob).to_bytes(4, "little"))
                handle.write(audio_blob)
            else:
                handle.write((0).to_bytes(1, "little"))

            handle.write(len(payload_entries).to_bytes(4, "little"))
            for entry in payload_entries:
                self.write_the_string(handle, entry.stored_name, 2)
                handle.write(entry.size.to_bytes(4, "little"))
                with open(entry.source_path, "rb") as src:
                    handle.write(src.read())


class ModCreatorWindow(tk.Toplevel):
    def __init__(self, parent, game_id: str, profile: dict):
        super().__init__(parent)
        self.game_id = game_id
        self.profile = profile
        self.single_ext = profile["single_ext"]
        self.package_ext = profile["package_ext"]
        self.mods_file = profile["mods_file"]
        self.writer = AldnoahPackageWriter()

        self.configure(bg=LILAC)
        self.title(f"{profile['display_name']} Constellation Forge")
        self.geometry("1390x980")
        self.minsize(1280, 860)
        self.resizable(True, True)
        setup_lilac_styles(self)
        apply_lilac_to_root(self)

        self.modname = tk.StringVar()
        self.authorname = tk.StringVar()
        self.version = tk.StringVar()
        self.genre = tk.StringVar(value="Texture")
        self.build_mode = tk.StringVar(value="Debug")
        self.status_var = tk.StringVar(value="Ready to forge a new Aldnoah mod package.")

        self.files_to_pack: List[str] = []
        self.images_to_pack: List[str] = []
        self.audio_to_pack: Optional[str] = None
        self.preview_index = 0
        self.preview_photo: Optional[ImageTk.PhotoImage] = None
        self._star_points = self.build_star_points(52, seed=11)

        self.payload_summary_var = tk.StringVar()
        self.media_summary_var = tk.StringVar()
        self.hero_summary_var = tk.StringVar()
        self.audio_summary_var = tk.StringVar(value="No embedded WAV selected")
        self.selection_hint_var = tk.StringVar()

        self.ensure_metadata_dir()
        self.build_gui()
        self.refresh_all_summaries()
        self.render_preview()

    def ensure_metadata_dir(self):
        game_dir = os.path.join(BASE_MODS_DIR, self.game_id)
        os.makedirs(game_dir, exist_ok=True)
        self.game_dir = game_dir
        self.mods_path = os.path.join(game_dir, self.mods_file)
        if not os.path.isfile(self.mods_path):
            with open(self.mods_path, "ab"):
                pass

    def build_gui(self):
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(1, weight=1)

        self.hero = tk.Canvas(self, bg=HERO_BG, highlightthickness=0, height=168)
        self.hero.grid(row=0, column=0, sticky="nsew", padx=12, pady=(12, 8))
        self.hero.bind("<Configure>", self.draw_hero)

        body = tk.Frame(self, bg=LILAC)
        body.grid(row=1, column=0, sticky="nsew", padx=12, pady=4)
        body.grid_columnconfigure(0, weight=3, uniform="forge")
        body.grid_columnconfigure(1, weight=3, uniform="forge")
        body.grid_columnconfigure(2, weight=4, uniform="forge")
        body.grid_rowconfigure(0, weight=1)

        meta_card, meta_body = self.create_card(body, "Metadata Core", "Name the mod, set its sky type, and describe the package.")
        meta_card.grid(row=0, column=0, sticky="nsew", padx=(0, 8))
        media_card, media_body = self.create_card(body, "Preview Observatory", "Embed gallery art and one Windows-ready WAV theme.")
        media_card.grid(row=0, column=1, sticky="nsew", padx=8)
        payload_card, payload_body = self.create_card(body, "Payload Constellation", "Stage unpacked payload files that already carry Aldnoah taildata.")
        payload_card.grid(row=0, column=2, sticky="nsew", padx=(8, 0))

        self.build_metadata_panel(meta_body)
        self.build_media_panel(media_body)
        self.build_payload_panel(payload_body)

        footer = tk.Frame(self, bg=LILAC, height=72)
        footer.grid(row=2, column=0, sticky="nsew", padx=12, pady=(8, 12))
        footer.grid_columnconfigure(0, weight=1)
        footer.grid_columnconfigure(1, weight=0)

        left = tk.Frame(footer, bg=LILAC)
        left.grid(row=0, column=0, sticky="w")
        self.status_label = tk.Label(left, textvariable=self.status_var, bg=LILAC, fg="#1F6B32", font=("Segoe UI", 10, "bold"))
        self.status_label.pack(anchor="w")
        
        actions = tk.Frame(footer, bg=LILAC)
        actions.grid(row=0, column=1, sticky="e")
        self.action_button(actions, f"Create Single Mod ({self.single_ext})", self.create_single_mod, BUTTON_GOLD).pack(side="left", padx=6)
        self.action_button(actions, f"Create Package Mod ({self.package_ext})", self.create_package_mod, BUTTON_GREEN).pack(side="left", padx=6)
        self.action_button(actions, "Open Game Mods Folder", self.open_game_mods_folder, BUTTON_BLUE).pack(side="left", padx=6)

    def create_card(self, parent: tk.Misc, title: str, subtitle: str) -> Tuple[tk.Frame, tk.Frame]:
        outer = tk.Frame(parent, bg=CARD_OUTLINE, bd=0, highlightthickness=0)
        outer.grid_rowconfigure(1, weight=1)
        outer.grid_columnconfigure(0, weight=1)

        top = tk.Canvas(outer, height=96, bg=HERO_BG, highlightthickness=0)
        top.grid(row=0, column=0, sticky="ew")
        top.bind("<Configure>", lambda event, canvas=top, header=title, note=subtitle: self.draw_card_header(canvas, header, note))

        body = tk.Frame(outer, bg=CARD_BG, padx=14, pady=14)
        body.grid(row=1, column=0, sticky="nsew")
        return outer, body

    def build_metadata_panel(self, parent: tk.Frame):
        self.field_label(parent, "Mod Name")
        tk.Entry(parent, textvariable=self.modname, font=("Segoe UI", 11), relief="flat", bd=0).pack(fill="x", ipady=7, pady=(0, 10))

        self.field_label(parent, "Author")
        tk.Entry(parent, textvariable=self.authorname, font=("Segoe UI", 11), relief="flat", bd=0).pack(fill="x", ipady=7, pady=(0, 10))

        row = tk.Frame(parent, bg=CARD_BG)
        row.pack(fill="x", pady=(0, 10))
        row.grid_columnconfigure(0, weight=1)
        row.grid_columnconfigure(1, weight=1)

        left = tk.Frame(row, bg=CARD_BG)
        left.grid(row=0, column=0, sticky="ew", padx=(0, 6))
        self.field_label(left, "Version")
        tk.Entry(left, textvariable=self.version, font=("Segoe UI", 11), relief="flat", bd=0).pack(fill="x", ipady=7)

        right = tk.Frame(row, bg=CARD_BG)
        right.grid(row=0, column=1, sticky="ew", padx=(6, 0))
        self.field_label(right, "Build Mode")
        build_row = tk.Frame(right, bg=CARD_BG)
        build_row.pack(fill="x", pady=(0, 2))
        for label in ("Debug", "Release"):
            tk.Radiobutton(
                build_row,
                text=label,
                value=label,
                variable=self.build_mode,
                bg=CARD_BG,
                activebackground=CARD_BG,
                font=("Segoe UI", 10, "bold"),
                command=self.refresh_all_summaries,
            ).pack(side="left", padx=(0, 10))

        self.field_label(parent, "Sky Type")
        self.genre_combo = ttk.Combobox(parent, state="readonly", values=GENRE_CHOICES, textvariable=self.genre, width=18)
        self.genre_combo.pack(anchor="w", pady=(0, 6))
        self.genre_combo.bind("<<ComboboxSelected>>", lambda _e: self.refresh_all_summaries())

        self.field_label(parent, "Description")
        self.description = tk.Text(parent, height=13, wrap=tk.WORD, relief="flat", bd=0, font=("Segoe UI", 10), padx=8, pady=8)
        self.description.pack(fill="both", expand=True, pady=(0, 10))

    def build_media_panel(self, parent: tk.Frame):
        preview_box = tk.Frame(parent, bg=CARD_ALT_BG, padx=12, pady=12)
        preview_box.pack(fill="x")

        top_row = tk.Frame(preview_box, bg=CARD_ALT_BG)
        top_row.pack(fill="x", pady=(0, 8))
        tk.Label(top_row, text="Fixed Preview Canvas", bg=CARD_ALT_BG, fg=TEXT_MAIN, font=("Segoe UI", 11, "bold")).pack(side="left")
        tk.Label(top_row, textvariable=self.media_summary_var, bg=CARD_ALT_BG, fg=TEXT_MUTED, font=("Segoe UI", 9)).pack(side="right")

        self.preview_canvas = tk.Canvas(
            preview_box,
            width=PREVIEW_CANVAS_SIZE[0],
            height=PREVIEW_CANVAS_SIZE[1],
            bg=CANVAS_BG,
            highlightthickness=1,
            highlightbackground=CARD_OUTLINE,
        )
        self.preview_canvas.pack(anchor="center")

        preview_nav = tk.Frame(preview_box, bg=CARD_ALT_BG)
        preview_nav.pack(fill="x", pady=(10, 0))
        self.mini_button(preview_nav, "Prev", lambda: self.cycle_preview(-1), BUTTON_BLUE).pack(side="left")
        self.mini_button(preview_nav, "Next", lambda: self.cycle_preview(1), BUTTON_BLUE).pack(side="left", padx=(6, 0))
        tk.Label(preview_nav, textvariable=self.selection_hint_var, bg=CARD_ALT_BG, fg=TEXT_MUTED, font=("Segoe UI", 9)).pack(side="right")

        audio_box = tk.Frame(parent, bg=CARD_ALT_BG, padx=12, pady=12)
        audio_box.pack(fill="x", pady=(14, 0))
        tk.Label(audio_box, text="Embedded Theme Audio", bg=CARD_ALT_BG, fg=TEXT_MAIN, font=("Segoe UI", 11, "bold")).pack(anchor="w")
        tk.Label(audio_box, textvariable=self.audio_summary_var, bg=CARD_ALT_BG, fg=TEXT_MUTED, wraplength=330, justify="left", font=("Segoe UI", 9)).pack(anchor="w", pady=(6, 8))
        btn_row = tk.Frame(audio_box, bg=CARD_ALT_BG)
        btn_row.pack(fill="x")
        self.mini_button(btn_row, "Select WAV", self.set_audio, BUTTON_GREEN).pack(side="left")
        self.mini_button(btn_row, "Clear WAV", self.clear_audio, BUTTON_RED).pack(side="left", padx=6)

        list_row = tk.Frame(parent, bg=CARD_BG)
        list_row.pack(fill="both", expand=True, pady=(14, 0))
        self.field_label(list_row, "Embedded Preview Images")
        self.image_list = tk.Listbox(
            list_row,
            height=5,
            selectmode=tk.SINGLE,
            bg="#120E1B",
            fg="#E9DEF5",
            activestyle="none",
            font=("Consolas", 9),
            relief="flat",
            bd=0,
        )
        self.image_list.pack(fill="both", expand=True, pady=(0, 8))
        self.image_list.bind("<<ListboxSelect>>", self.on_select_preview_image)

        img_btns = tk.Frame(list_row, bg=CARD_BG)
        img_btns.pack(fill="x", pady=(0, 4))
        self.mini_button(img_btns, "Add Images", self.add_images, BUTTON_BLUE).pack(side="left")
        self.mini_button(img_btns, "Remove Selected", self.remove_image, BUTTON_RED).pack(side="left", padx=6)

    def build_payload_panel(self, parent: tk.Frame):
        stats = tk.Frame(parent, bg=CARD_ALT_BG, padx=12, pady=12)
        stats.pack(fill="x")
        tk.Label(stats, text="Manifest Status", bg=CARD_ALT_BG, fg=TEXT_MAIN, font=("Segoe UI", 11, "bold")).pack(anchor="w")
        tk.Label(stats, textvariable=self.payload_summary_var, bg=CARD_ALT_BG, fg=TEXT_MUTED, wraplength=420, justify="left", font=("Segoe UI", 9)).pack(anchor="w", pady=(6, 8))

        self.payload_canvas = tk.Canvas(stats, height=104, bg=CANVAS_BG, highlightthickness=1, highlightbackground=CARD_OUTLINE)
        self.payload_canvas.pack(fill="x")
        self.payload_canvas.bind("<Configure>", self.draw_payload_sky)

        list_box = tk.Frame(parent, bg=CARD_BG)
        list_box.pack(fill="both", expand=True, pady=(14, 0))
        self.field_label(list_box, "Payload Files")
        self.file_list = tk.Listbox(
            list_box,
            selectmode=tk.EXTENDED,
            bg="#120E1B",
            fg="#A8FFB2",
            activestyle="none",
            font=("Consolas", 10),
            relief="flat",
            bd=0,
        )
        self.file_list.pack(fill="both", expand=True, pady=(0, 8))

        payload_btns = tk.Frame(list_box, bg=CARD_BG)
        payload_btns.pack(fill="x")
        self.mini_button(payload_btns, "Add Files", self.add_files, BUTTON_BLUE).pack(side="left")
        self.mini_button(payload_btns, "Add Folder", self.add_folder, BUTTON_BLUE).pack(side="left", padx=6)
        self.mini_button(payload_btns, "Remove Selected", self.remove_selected, BUTTON_RED).pack(side="left", padx=6)
        self.mini_button(payload_btns, "Clear All", self.clear_all_files, BUTTON_RED).pack(side="left")

    def field_label(self, parent: tk.Misc, text: str):
        tk.Label(parent, text=text, bg=parent.cget("bg"), fg=TEXT_MAIN, font=("Segoe UI", 10, "bold"), anchor="w").pack(fill="x", pady=(0, 4))

    def action_button(self, parent: tk.Misc, text: str, command, color: str) -> tk.Button:
        return tk.Button(
            parent,
            text=text,
            command=command,
            bg=color,
            fg="white",
            activebackground=color,
            activeforeground="white",
            font=("Segoe UI", 10, "bold"),
            relief="flat",
            bd=0,
            padx=18,
            pady=10,
            cursor="hand2",
        )

    def mini_button(self, parent: tk.Misc, text: str, command, color: str) -> tk.Button:
        return tk.Button(
            parent,
            text=text,
            command=command,
            bg=color,
            fg="white",
            activebackground=color,
            activeforeground="white",
            font=("Segoe UI", 9, "bold"),
            relief="flat",
            bd=0,
            padx=12,
            pady=7,
            cursor="hand2",
        )

    def draw_hero(self, _event=None):
        canvas = self.hero
        canvas.delete("all")
        width = max(1, canvas.winfo_width())
        height = max(1, canvas.winfo_height())

        band_colors = [HERO_BG, "#1B1234", HERO_MID, "#46306D"]
        band_height = max(1, height // len(band_colors))
        for idx, color in enumerate(band_colors):
            y0 = idx * band_height
            canvas.create_rectangle(0, y0, width, y0 + band_height + 2, fill=color, outline="")

        for x, y, radius in self._star_points:
            sx = int(x * width)
            sy = int(y * height)
            canvas.create_oval(sx - radius, sy - radius, sx + radius, sy + radius, fill="#F4EDFF", outline="")

        canvas.create_arc(36, 22, 236, 222, start=28, extent=288, style=tk.ARC, outline="#9A87F4", width=2)
        canvas.create_arc(width - 260, -20, width - 24, 216, start=210, extent=262, style=tk.ARC, outline="#6FB4FF", width=2)

        links = [(0, 3), (3, 7), (7, 11), (11, 14), (17, 21), (21, 24), (24, 28)]
        for a, b in links:
            ax, ay, _ = self._star_points[a]
            bx, by, _ = self._star_points[b]
            canvas.create_line(int(ax * width), int(ay * height), int(bx * width), int(by * height), fill="#8977D8", width=1)

        canvas.create_text(34, 34, anchor="nw", text="Aldnoah Constellation Forge", fill="white", font=("Segoe UI", 22, "bold"))
        canvas.create_text(
            36,
            72,
            anchor="nw",
            text=f"{self.profile['display_name']}  |  {self.single_ext} and {self.package_ext}  |  Windows-only rich package builder",
            fill="#D8D0F4",
            font=("Segoe UI", 10),
        )
        canvas.create_text(36, 102, anchor="nw", text=self.hero_summary_var.get(), fill="#F2E9FF", font=("Consolas", 10, "bold"))
        canvas.create_text(width - 28, height - 24, anchor="se", text="Embedded metadata, previews, one WAV, then payloads", fill="#D8D0F4", font=("Segoe UI", 10, "italic"))

    def draw_card_header(self, canvas: tk.Canvas, title: str, subtitle: str):
        canvas.delete("all")
        width = max(1, canvas.winfo_width())
        height = max(1, canvas.winfo_height())
        canvas.create_rectangle(0, 0, width, height, fill=HERO_MID, outline="")
        canvas.create_rectangle(0, 0, width, 18, fill=HERO_ACCENT, outline="")
        local_points = self.build_star_points(16, seed=len(title) * 9 + 3)
        for x, y, radius in local_points:
            sx = int(x * width)
            sy = int((y * 0.8 + 0.12) * height)
            canvas.create_oval(sx - radius, sy - radius, sx + radius, sy + radius, fill="#F2E9FF", outline="")
        for a, b in ((0, 4), (4, 7), (7, 10), (2, 6), (6, 12)):
            ax, ay, _ = local_points[a]
            bx, by, _ = local_points[b]
            canvas.create_line(int(ax * width), int((ay * 0.8 + 0.12) * height), int(bx * width), int((by * 0.8 + 0.12) * height), fill="#8E7AE2")
        canvas.create_text(14, 28, anchor="nw", text=title, fill="white", font=("Segoe UI", 13, "bold"))
        canvas.create_text(14, 54, anchor="nw", text=subtitle, fill="#D7CEF7", font=("Segoe UI", 9), width=max(120, width - 28))

    def draw_payload_sky(self, _event=None):
        canvas = self.payload_canvas
        canvas.delete("all")
        width = max(1, canvas.winfo_width())
        height = max(1, canvas.winfo_height())
        canvas.create_rectangle(0, 0, width, height, fill=CANVAS_BG, outline="")

        labels = [
            ("Meta", 0.12, 0.58, "#D2B6FF"),
            ("Preview", 0.36, 0.34 if self.images_to_pack else 0.58, "#80C6FF"),
            ("Audio", 0.58, 0.34 if self.audio_to_pack else 0.62, "#FFD166"),
            ("Payload", 0.82, 0.52, "#7AE582"),
        ]
        last_xy = None
        for text, x, y, color in labels:
            sx = int(width * x)
            sy = int(height * y)
            if last_xy is not None:
                canvas.create_line(last_xy[0], last_xy[1], sx, sy, fill="#6858A8", width=2)
            canvas.create_oval(sx - 7, sy - 7, sx + 7, sy + 7, fill=color, outline="")
            canvas.create_text(sx, sy - 16, text=text, fill="#E8DFF7", font=("Segoe UI", 9, "bold"))
            last_xy = (sx, sy)

        count_note = f"{len(self.files_to_pack)} files"
        size_note = format_bytes(sum(os.path.getsize(path) for path in self.files_to_pack if os.path.isfile(path)))
        canvas.create_text(width - 12, height - 12, anchor="se", text=f"{count_note}  |  {size_note}", fill="#C9BEEB", font=("Consolas", 9))

    @staticmethod
    def build_star_points(count: int, seed: int) -> List[Tuple[float, float, int]]:
        rng = random.Random(seed)
        return [(rng.uniform(0.04, 0.96), rng.uniform(0.12, 0.9), rng.randint(1, 3)) for _ in range(count)]

    def set_status(self, text: str, color: str = "#1F6B32"):
        self.status_var.set(text)
        self.status_label.config(fg=color)

    def open_game_mods_folder(self):
        try:
            os.startfile(self.game_dir)
        except Exception:
            messagebox.showinfo("Mods Folder", self.game_dir)

    def validate_payload_path(self, file_path: str) -> Tuple[bool, str]:
        if not os.path.isfile(file_path):
            return False, "Not a file."
        size = os.path.getsize(file_path)
        if size < MIN_EXPECTED_PAYLOAD_SIZE:
            return False, f"File is too small to contain expected taildata ({size} bytes)."
        return True, ""

    def append_unique_files(self, new_paths: List[str]):
        added = 0
        for file_path in new_paths:
            if file_path in self.files_to_pack:
                continue
            ok, reason = self.validate_payload_path(file_path)
            if not ok:
                messagebox.showwarning("Invalid Payload File", f"{os.path.basename(file_path)}\n\n{reason}")
                continue
            self.files_to_pack.append(file_path)
            self.file_list.insert(tk.END, os.path.basename(file_path))
            added += 1
        if added:
            self.set_status(f"Added {added} payload file(s).")
        else:
            self.set_status("No new payload files were added.", BUTTON_RED)
        self.refresh_all_summaries()

    def add_files(self):
        files = filedialog.askopenfilenames(parent=self, title="Select unpacker output files to package", filetypes=[("All files", "*.*")])
        if files:
            self.append_unique_files(list(files))

    def add_folder(self):
        folder = filedialog.askdirectory(parent=self, title="Select a folder of payload files")
        if not folder:
            return
        paths = [os.path.join(folder, name) for name in sorted(os.listdir(folder), key=str.lower) if os.path.isfile(os.path.join(folder, name))]
        if not paths:
            self.set_status("The selected folder does not contain files.", BUTTON_RED)
            return
        self.append_unique_files(paths)

    def remove_selected(self):
        selected = list(self.file_list.curselection())
        if not selected:
            self.set_status("Select payload entries to remove first.", BUTTON_RED)
            return
        for idx in reversed(selected):
            self.file_list.delete(idx)
            del self.files_to_pack[idx]
        self.set_status("Removed selected payload entries.", BUTTON_BLUE)
        self.refresh_all_summaries()

    def clear_all_files(self):
        self.files_to_pack.clear()
        self.file_list.delete(0, tk.END)
        self.set_status("Cleared the payload manifest.", BUTTON_BLUE)
        self.refresh_all_summaries()

    def add_images(self):
        if len(self.images_to_pack) >= MAX_PREVIEW_IMAGES:
            messagebox.showwarning("Preview Limit", f"Only {MAX_PREVIEW_IMAGES} preview images can be embedded.")
            return
        images = filedialog.askopenfilenames(parent=self, title="Select Preview Images", filetypes=[("Images", "*.png;*.jpg;*.jpeg;*.bmp;*.webp")])
        if not images:
            return
        added = 0
        for image_path in images:
            if len(self.images_to_pack) >= MAX_PREVIEW_IMAGES:
                break
            if image_path not in self.images_to_pack:
                self.images_to_pack.append(image_path)
                self.image_list.insert(tk.END, os.path.basename(image_path))
                added += 1
        if self.images_to_pack:
            self.preview_index = len(self.images_to_pack) - 1
            self.image_list.selection_clear(0, tk.END)
            self.image_list.selection_set(self.preview_index)
            self.image_list.activate(self.preview_index)
        if added:
            self.set_status(f"Added {added} preview image(s).")
        self.refresh_all_summaries()
        self.render_preview()

    def remove_image(self):
        selection = self.image_list.curselection()
        if not selection:
            self.set_status("Select a preview image to remove first.", BUTTON_RED)
            return
        idx = selection[0]
        self.image_list.delete(idx)
        del self.images_to_pack[idx]
        if self.images_to_pack:
            self.preview_index = max(0, min(self.preview_index, len(self.images_to_pack) - 1))
            self.image_list.selection_set(self.preview_index)
        else:
            self.preview_index = 0
        self.set_status("Removed the selected preview image.", BUTTON_BLUE)
        self.refresh_all_summaries()
        self.render_preview()

    def on_select_preview_image(self, _event=None):
        selection = self.image_list.curselection()
        if not selection:
            return
        self.preview_index = selection[0]
        self.render_preview()

    def cycle_preview(self, delta: int):
        if not self.images_to_pack:
            self.set_status("No preview images are staged yet.", BUTTON_RED)
            return
        self.preview_index = (self.preview_index + delta) % len(self.images_to_pack)
        self.image_list.selection_clear(0, tk.END)
        self.image_list.selection_set(self.preview_index)
        self.image_list.activate(self.preview_index)
        self.render_preview()

    def render_preview(self):
        canvas = self.preview_canvas
        canvas.delete("all")
        width, height = PREVIEW_CANVAS_SIZE
        canvas.create_rectangle(0, 0, width, height, fill=CANVAS_BG, outline="")
        for x, y, radius in self.build_star_points(20, seed=77):
            sx = int(x * width)
            sy = int(y * height)
            canvas.create_oval(sx - radius, sy - radius, sx + radius, sy + radius, fill="#F4EDFF", outline="")
        canvas.create_arc(24, 28, 170, 174, start=22, extent=280, style=tk.ARC, outline="#5F73CF", width=2)
        canvas.create_arc(width - 180, 36, width - 24, 190, start=182, extent=248, style=tk.ARC, outline="#8E77E1", width=2)

        if not self.images_to_pack:
            canvas.create_text(width // 2, height // 2 - 10, text="No Preview Image", fill="#F4EDFF", font=("Segoe UI", 16, "bold"))
            canvas.create_text(width // 2, height // 2 + 20, text="Add up to five images. The canvas stays fixed so the layout never shifts.", fill="#CFC4E7", font=("Segoe UI", 9), width=300)
            self.selection_hint_var.set("0 / 0")
            return

        image_path = self.images_to_pack[self.preview_index]
        try:
            with Image.open(image_path) as img:
                if img.mode not in ("RGB", "RGBA"):
                    img = img.convert("RGBA" if "A" in img.getbands() else "RGB")
                if img.mode == "RGBA":
                    composite = Image.new("RGBA", img.size, (15, 12, 24, 255))
                    composite.alpha_composite(img)
                    img = composite.convert("RGB")
                else:
                    img = img.convert("RGB")
                img = ImageOps.contain(img, PREVIEW_CANVAS_SIZE)
                frame = Image.new("RGB", PREVIEW_CANVAS_SIZE, CANVAS_BG)
                offset = ((PREVIEW_CANVAS_SIZE[0] - img.width) // 2, (PREVIEW_CANVAS_SIZE[1] - img.height) // 2)
                frame.paste(img, offset)
                self.preview_photo = ImageTk.PhotoImage(frame)
                canvas.create_image(0, 0, anchor="nw", image=self.preview_photo)
                canvas.create_rectangle(0, 0, width, height, outline="#C4B4ED")
                canvas.create_text(10, height - 12, anchor="sw", text=os.path.basename(image_path), fill="#F4EDFF", font=("Segoe UI", 9, "bold"))
        except Exception as exc:
            canvas.create_text(width // 2, height // 2, text=f"Preview error:\n{exc}", fill="#FFB9C4", font=("Segoe UI", 10), width=300)

        self.selection_hint_var.set(f"{self.preview_index + 1} / {len(self.images_to_pack)}")

    def set_audio(self):
        wav = filedialog.askopenfilename(parent=self, title="Select Theme WAV", filetypes=[("WAV Audio", "*.wav")])
        if not wav:
            return
        try:
            audio_bytes = self.writer.read_audio_bytes(wav)
        except Exception as exc:
            messagebox.showerror("Invalid WAV", str(exc))
            self.set_status(str(exc), BUTTON_RED)
            return
        if len(audio_bytes) > AUDIO_WARN_BYTES:
            messagebox.showwarning(
                "Large WAV",
                f"{os.path.basename(wav)} is {format_bytes(len(audio_bytes))}.\n\nLarge embedded WAVs are allowed, but they will increase mod package size and may take longer to load in the manager.",
            )
        self.audio_to_pack = wav
        self.audio_summary_var.set(f"{os.path.basename(wav)}  |  {format_bytes(len(audio_bytes))}  |  RIFF/WAVE ready for WinMM playback")
        self.set_status("Embedded WAV selected.")
        self.refresh_all_summaries()

    def clear_audio(self):
        self.audio_to_pack = None
        self.audio_summary_var.set("No embedded WAV selected")
        self.set_status("Cleared embedded audio.", BUTTON_BLUE)
        self.refresh_all_summaries()

    def build_payload_entries(self, single_mode: bool) -> List[PayloadEntry]:
        if not self.files_to_pack:
            raise ValueError("Add at least one payload file first.")
        if single_mode and len(self.files_to_pack) != 1:
            raise ValueError("Single mod creation requires exactly one payload file.")

        used_names: Dict[str, int] = {}
        entries: List[PayloadEntry] = []
        for file_path in self.files_to_pack:
            stem_name = os.path.basename(file_path)
            count = used_names.get(stem_name, 0)
            used_names[stem_name] = count + 1
            root, ext = os.path.splitext(stem_name)
            stored_name = stem_name if count == 0 else f"{root}_{count + 1}{ext}"
            entries.append(PayloadEntry(source_path=file_path, stored_name=stored_name, size=os.path.getsize(file_path)))
        return entries

    def validate_metadata(self) -> Tuple[str, str, str, str, bool, str]:
        display_name = self.modname.get().strip()
        author = self.authorname.get().strip()
        version_text = self.version.get().strip()
        description = self.description.get("1.0", tk.END).strip()
        build_release = self.build_mode.get() == "Release"
        genre_name = self.genre.get().strip()

        if not display_name:
            raise ValueError("Mod Name is required.")
        if not author:
            raise ValueError("Author is required.")
        if genre_name not in GENRE_MAP:
            raise ValueError("Choose a valid Sky Type.")
        return display_name, author, version_text, description, build_release, genre_name

    def default_save_path(self, extension: str, display_name: str) -> str:
        return os.path.join(self.game_dir, sanitize_filename(display_name) + extension)

    def create_mod(self, single_mode: bool):
        try:
            display_name, author, version_text, description, build_release, genre_name = self.validate_metadata()
            payload_entries = self.build_payload_entries(single_mode=single_mode)
        except Exception as exc:
            self.set_status(str(exc), BUTTON_RED)
            return

        extension = self.single_ext if single_mode else self.package_ext
        type_label = "single mod" if single_mode else "package mod"
        save_path = filedialog.asksaveasfilename(
            parent=self,
            title=f"Save {type_label} ({extension})",
            defaultextension=extension,
            initialfile=os.path.basename(self.default_save_path(extension, display_name)),
            initialdir=self.game_dir,
            filetypes=[(f"{type_label.title()} File", f"*{extension}"), ("All files", "*.*")],
        )
        if not save_path:
            self.set_status("Save cancelled.", BUTTON_RED)
            return

        try:
            self.writer.write_package(
                save_path,
                display_name=display_name,
                author=author,
                version_text=version_text,
                description=description,
                build_release=build_release,
                genre_name=genre_name,
                preview_paths=self.images_to_pack,
                audio_path=self.audio_to_pack,
                payload_entries=payload_entries,
            )
            self.set_status(
                f"Created {os.path.basename(save_path)} with {len(payload_entries)} payload file(s), {len(self.images_to_pack)} preview image(s), and {'a WAV' if self.audio_to_pack else 'no WAV'}.",
                "#1F6B32",
            )
        except Exception as exc:
            messagebox.showerror("Package Creation Failed", str(exc))
            self.set_status(f"Creation failed: {exc}", BUTTON_RED)

    def create_single_mod(self):
        self.create_mod(single_mode=True)

    def create_package_mod(self):
        self.create_mod(single_mode=False)

    def refresh_all_summaries(self):
        payload_count = len(self.files_to_pack)
        payload_size = sum(os.path.getsize(path) for path in self.files_to_pack if os.path.isfile(path))
        image_count = len(self.images_to_pack)
        audio_note = "WAV embedded" if self.audio_to_pack else "no WAV"
        self.payload_summary_var.set(f"{payload_count} payload file(s) staged, totaling {format_bytes(payload_size)}.")
        self.media_summary_var.set(f"{image_count}/{MAX_PREVIEW_IMAGES} previews, {audio_note}")
        self.hero_summary_var.set(f"Sky={self.genre.get()}  |  Mode={self.build_mode.get()}  |  Payloads={payload_count}  |  Previews={image_count}  |  Audio={'Yes' if self.audio_to_pack else 'No'}")
        if not self.audio_to_pack:
            self.audio_summary_var.set("No embedded WAV selected")
        self.hero.after_idle(self.draw_hero)
        if hasattr(self, "payload_canvas"):
            self.payload_canvas.after_idle(self.draw_payload_sky)


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
SELECT_NODE = "#6B57C8"
SELECT_NODE_SEL = "#F5D889"
SELECT_NODE_RING = "#A89AF0"

GAME_FORGE_SUMMARIES = {
    "DW7XL": "Build Creator packages for the four sky Dynasty Warriors 7 XL layout.",
    "DW8XL": "Forge Aldnoah packages for the shared IDX Dynasty Warriors 8 XL orbit.",
    "DW8E": "Create packages for a single sky layout.",
    "WO3": "Forge for the eight sky Warriors Orochi 3 layout.",
    "TK": "Forge for the four sky Toukiden Kiwami layout.",
    "BN": "Build nightmare sky packages across a three container layout.",
    "WAS": "Create packages for a single container layout.",
}


class CreatorSelectConstellationCanvas(tk.Canvas):
    def __init__(self, parent: tk.Misc, controller: "ModCreatorGameSelect"):
        super().__init__(parent, bg=SELECT_BG, highlightthickness=0, bd=0, relief="flat")
        self.controller = controller
        self.item_to_game: Dict[int, str] = {}
        self.phase = 0.0
        rnd = random.Random(181)
        self.stars = [(rnd.uniform(0.04, 0.96), rnd.uniform(0.06, 0.94), rnd.randint(1, 3)) for _ in range(96)]
        self.bind("<Configure>", lambda _e: self.render())
        self.bind("<Button-1>", self.on_click)
        self.bind("<Double-Button-1>", lambda _e: self.controller.open_selected_game())
        self.after(120, self._tick)

    def _tick(self):
        self.phase += 0.08
        if self.winfo_exists():
            self.render()
            self.after(120, self._tick)

    def coords(self, width: int, height: int) -> Dict[str, Tuple[float, float]]:
        return {
            "DW7XL": (width * 0.15, height * 0.29),
            "DW8XL": (width * 0.37, height * 0.20),
            "DW8E": (width * 0.69, height * 0.24),
            "WO3": (width * 0.23, height * 0.66),
            "TK": (width * 0.52, height * 0.56),
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
            ("WO3", "TK"),
            ("TK", "BN"),
            ("BN", "WAS"),
            ("DW8E", "WAS"),
            ("DW8XL", "TK"),
            ("DW8XL", "BN"),
        ]
        for left, right in links:
            ax, ay = coords[left]
            bx, by = coords[right]
            self.create_line(ax, ay, bx, by, fill=SELECT_LINE, width=2)

        self.create_text(20, 18, anchor="nw", text="Forge Constellation Gateway", fill=SELECT_TEXT, font=("Segoe UI", 17, "bold"))
        self.create_text(22, 48, anchor="nw", text="Single click a game star to inspect its forge profile. Double click to open the creator.", fill=SELECT_SUBTEXT, font=("Segoe UI", 9))
        self.create_text(width - 18, 22, anchor="ne", text="Select the sky you want to forge for", fill=SELECT_SUBTEXT, font=("Segoe UI", 10, "italic"))

        sorted_items = sorted(MOD_PROFILES.items(), key=lambda kv: kv[1]["display_name"])
        for game_id, profile in sorted_items:
            gx, gy = coords[game_id]
            selected = self.controller.selected_game_id == game_id
            active = self.controller.is_creator_open(game_id)
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
                badge = self.create_text(gx + 18, gy - 14, text="OPEN", fill="#D8FFEA", font=("Segoe UI", 8, "bold"))
                self.item_to_game[badge] = game_id


class ModCreatorGameSelect(tk.Toplevel):
    def __init__(self, parent):
        super().__init__(parent)
        self.child_windows: Dict[str, Optional[ModCreatorWindow]] = {}
        self.selected_game_id = "WO3" if "WO3" in MOD_PROFILES else sorted(MOD_PROFILES.keys())[0]
        self.status_var = tk.StringVar(value="Select a constellation to open its forge.")
        self.selected_title_var = tk.StringVar(value="")
        self.selected_meta_var = tk.StringVar(value="")
        self.selected_desc_var = tk.StringVar(value="")
        self.game_buttons: Dict[str, tk.Button] = {}

        self.title("Aldnoah Constellation Forge Gateway")
        self.configure(bg=SELECT_BG)
        self.geometry("1220x1000")
        self.minsize(1080, 900)

        setup_lilac_styles(self)
        apply_lilac_to_root(self)

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

        left = self.build_panel(content, "Game Field of Stars", "Launch a creator from a live constellation map.", SELECT_BLUE)
        left["panel"].grid(row=0, column=0, sticky="nsew", padx=(0, 8))
        left["body"].grid_rowconfigure(0, weight=1)
        left["body"].grid_columnconfigure(0, weight=1)

        self.selector_canvas = CreatorSelectConstellationCanvas(left["body"], self)
        self.selector_canvas.grid(row=0, column=0, sticky="nsew", padx=14, pady=(14, 10))

        hint = tk.Label(
            left["body"],
            text="Tip: double click a star to jump straight into that forge.",
            bg=SELECT_PANEL_3,
            fg=SELECT_MUTED,
            anchor="w",
            font=("Segoe UI", 9, "italic"),
        )
        hint.grid(row=1, column=0, sticky="ew", padx=16, pady=(0, 14))

        right = self.build_panel(content, "Selected Forge Profile", "Review package extensions, creator limits, and launch state.", SELECT_GOLD)
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
            height=6,
        )
        desc.grid(row=2, column=0, sticky="ew", padx=18, pady=(14, 12))

        button_row = tk.Frame(right["body"], bg=SELECT_PANEL_3)
        button_row.grid(row=3, column=0, sticky="ew", padx=18)
        button_row.grid_columnconfigure(0, weight=1)
        button_row.grid_columnconfigure(1, weight=1)

        self.open_button = tk.Button(
            button_row,
            text="Open Selected Forge",
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
            text="Each node mirrors the star map. Active forges glow green.",
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
        canvas.create_text(34, 34, anchor="nw", text="Aldnoah Constellation Forge Gateway", fill=SELECT_TEXT, font=("Segoe UI", 24, "bold"))
        canvas.create_text(
            36,
            76,
            anchor="nw",
            text="Choose the game sky whose package format you want to forge with metadata, previews, WAV audio, and payloads.",
            fill=SELECT_SUBTEXT,
            font=("Segoe UI", 10),
        )
        canvas.create_text(width - 20, height - 24, anchor="se", text="Mod creator launch selector", fill=SELECT_SUBTEXT, font=("Segoe UI", 10, "italic"))

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

    def is_creator_open(self, game_id: str) -> bool:
        win = self.child_windows.get(game_id)
        return bool(win is not None and win.winfo_exists())

    def set_status(self, text: str):
        self.status_var.set(text)

    def update_game_buttons(self):
        for game_id, button in self.game_buttons.items():
            selected = self.selected_game_id == game_id
            active = self.is_creator_open(game_id)
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
        creator_state = "Forge window already open." if self.is_creator_open(game_id) else "Forge window not open yet."
        self.selected_title_var.set(profile["display_name"])
        self.selected_meta_var.set(
            "\n".join(
                [
                    f"Game ID      : {game_id}",
                    f"Single Mod   : {profile['single_ext']}",
                    f"Package Mod  : {profile['package_ext']}",
                    f"Ledger File  : {profile['mods_file']}",
                    f"Format       : ALDNOAH v{ALDNOAH_FORMAT_VERSION}",
                    f"Preview Cap  : {MAX_PREVIEW_IMAGES} images + 1 WAV",
                ]
            )
        )
        self.selected_desc_var.set(f"{GAME_FORGE_SUMMARIES.get(game_id, 'Aldnoah forge profile ready.')}\n\n{creator_state}")
        self.update_game_buttons()
        try:
            self.selector_canvas.render()
        except Exception:
            pass
        if update_status:
            self.set_status(f"Selected {profile['display_name']}.")

    def open_selected_game(self):
        self.open_creator(self.selected_game_id)

    def open_creator(self, game_id: str):
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
        win = ModCreatorWindow(self, game_id, profile)
        self.child_windows[game_id] = win
        self.set_status(f"Opened constellation forge for {profile['display_name']}.")
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
                self.set_status(f"Closed constellation forge for {profile['display_name']}.")

        win.protocol("WM_DELETE_WINDOW", on_close)
if __name__ == "__main__":
    raise SystemExit("Run AE/main.pyw to launch Aldnoah Engine tools.")
