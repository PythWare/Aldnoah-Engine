from __future__ import annotations
import math, os
import tkinter as tk
from dataclasses import dataclass
from tkinter import messagebox
from typing import Dict, List, Optional, Sequence, Tuple

from .aldnoah_editors import (
    FIELD_ALT_BG,
    FIELD_BG,
    FIELD_INVALID,
    FIELD_OUTLINE,
    FIELD_TEXT,
    PROJECT_ROOT,
    SELECT_BG,
    SELECT_BLUE,
    SELECT_GOLD,
    SELECT_GREEN,
    SELECT_LINE,
    SELECT_MUTED,
    SELECT_NODE,
    SELECT_NODE_RING,
    SELECT_NODE_SEL,
    SELECT_PANEL_2,
    SELECT_PANEL_3,
    SELECT_STAR,
    SELECT_SUBTEXT,
    SELECT_TEXT,
    STATUS_BAD,
    STATUS_GOOD,
    STATUS_WARN,
    action_button,
    build_panel,
    draw_constellation_backdrop,
    make_stars,
)
from .aldnoah_energy import apply_lilac_to_root, setup_lilac_styles
from .aldnoah_infos import DW8XL_OFF_SKILL_NAMES, DW8XL_OFF_SKILL_DESC
from .aldnoah_reusables import (
    EditorBatchField,
    EditorBatchSelectionController,
    build_description_section,
    install_constellation_virtualization,
    linear_field_offsets,
    write_batch_record_snapshots,
    write_batch_record_updates,
)


OFF_SKILL_PATH = os.path.join(
    PROJECT_ROOT,
    "DW8XL_Unpacked",
    "Pack_00",
    "entry_00000",
    "013.xl"
)

OFF_SKILL_EXPORT_PATH = os.path.join(
    PROJECT_ROOT,
    "DW8XL_Officer_Skill_Edits",
    "Pack_00",
    "entry_00000",
    "013.xl"
)

OFF_SKILL_COUNT = 104
OFF_SKILL_OFFSET = 0x20
OFF_SKILL_RECORD_SIZE = 17

OFF_SKILL_FIELDS = [
    ("Unknown 1", 2),
    ("Unknown 2", 2),
    ("Unknown 3", 2),
    ("Unknown 4", 2),
    ("Unknown 5", 1),
]

OFF_SKILL_FLAG_NAMES = [f"Flag {i:02d}" for i in range(1, 9)]

OFF_SKILL_CORE_SIZE = sum(size for _, size in OFF_SKILL_FIELDS)

@dataclass(frozen=True)
class OFFSKILLInfo:
    index: int
    name: str

    @property
    def label(self):
        slot_number = self.index + 1
        fallback = f"Skill {slot_number:03d}"
        return self.name if self.name == fallback else f"{self.name} | {slot_number:03d}"


OFF_SKILLS = [
    OFFSKILLInfo(index, DW8XL_OFF_SKILL_NAMES.get(index, f"Skill {index + 1:03d}"))
    for index in range(OFF_SKILL_COUNT)
]

def off_skill_offset(index: int) -> int:
    return OFF_SKILL_OFFSET + (index * OFF_SKILL_RECORD_SIZE)


def read_unit(blob: bytes, index: int) -> bytes:
    start = off_skill_offset(index)
    return blob[start:start + OFF_SKILL_RECORD_SIZE]


def write_unit(blob: bytearray, index: int, data: bytes):
    start = off_skill_offset(index)
    blob[start:start + OFF_SKILL_RECORD_SIZE] = data


def unsigned_to_signed(value: int, bits: int) -> int:
    sign_bit = 1 << (bits - 1)
    full_range = 1 << bits
    return value - full_range if value & sign_bit else value


def parse_sized_int(text: str, byte_width: int) -> int:
    raw = (text or "").strip().replace("_", "")
    if not raw:
        raise ValueError("Value cannot be empty.")
    bits = byte_width * 8
    base = 16 if raw.lower().startswith(("0x", "-0x", "+0x")) else 10
    try:
        value = int(raw, base)
    except ValueError as exc:
        raise ValueError("Use decimal, -1, or 0x-prefixed hex.") from exc
    min_signed = -(1 << (bits - 1))
    max_unsigned = (1 << bits) - 1
    if value < min_signed or value > max_unsigned:
        raise ValueError(f"Value must stay within signed {bits}-bit or unsigned {bits}-bit range.")
    return value & max_unsigned


def helper_text_for_sized_value(value: int, byte_width: int) -> str:
    bits = byte_width * 8
    return f"u{bits} {value} | i{bits} {unsigned_to_signed(value, bits)} | 0x{value:0{byte_width * 2}X}"


def format_core_value(field_name: str, byte_width: int, value: int) -> str:
    if field_name.startswith("Unknown"):
        return f"0x{value:0{byte_width * 2}X}"
    signed_value = unsigned_to_signed(value, byte_width * 8)
    return str(signed_value if signed_value < 0 else value)

class OffSkillConstellationCanvas(tk.Canvas):
    def __init__(self, parent: tk.Misc, controller: "DW8XLOFFSKILLEditorWindow"):
        super().__init__(parent, bg=SELECT_BG, highlightthickness=0, bd=0, relief="flat")
        self.controller = controller
        self.item_to_officer: Dict[int, int] = {}
        self.phase = 0.0
        self.stars = make_stars(941, 82)
        self.zoom = 1.0
        self.min_zoom = 0.55
        self.max_zoom = 3.25
        self.pan_x = 0.0
        self.pan_y = 0.0
        self._press_xy = (0, 0)
        self._press_pan = (0.0, 0.0)
        self._dragging = False
        self.bind("<Configure>", lambda _e: self.render())
        self.bind("<ButtonPress-1>", self.on_press)
        self.bind("<B1-Motion>", self.on_drag)
        self.bind("<ButtonRelease-1>", self.on_release)
        self.bind("<MouseWheel>", self.on_mousewheel)
        self.bind("<Button-4>", lambda e: self.zoom_at(e.x, e.y, 1.12))
        self.bind("<Button-5>", lambda e: self.zoom_at(e.x, e.y, 1 / 1.12))
        self.after(120, self.tick)

    def tick(self):
        self.phase += 0.08
        if self.winfo_exists():
            self.render()
            self.after(120, self.tick)

    def on_press(self, event):
        self._press_xy = (event.x, event.y)
        self._press_pan = (self.pan_x, self.pan_y)
        self._dragging = False

    def on_drag(self, event):
        dx = event.x - self._press_xy[0]
        dy = event.y - self._press_xy[1]
        if not self._dragging and ((dx * dx) + (dy * dy)) >= 25:
            self._dragging = True
        if not self._dragging:
            return
        self.pan_x = self._press_pan[0] + dx
        self.pan_y = self._press_pan[1] + dy
        self.render()

    def on_release(self, event):
        if self._dragging:
            return
        self.select_officer_at(event.x, event.y)

    def on_mousewheel(self, event):
        self.zoom_at(event.x, event.y, 1.12 if event.delta > 0 else (1 / 1.12))

    def zoom_at(self, screen_x: float, screen_y: float, factor: float):
        width = max(1, self.winfo_width())
        height = max(1, self.winfo_height())
        new_zoom = max(self.min_zoom, min(self.max_zoom, self.zoom * factor))
        if abs(new_zoom - self.zoom) < 1e-6:
            return
        center_x = (width * 0.50) + self.pan_x
        center_y = (height * 0.54) + self.pan_y
        world_x = (screen_x - center_x) / self.zoom
        world_y = (screen_y - center_y) / self.zoom
        self.zoom = new_zoom
        self.pan_x = screen_x - ((width * 0.50) + (world_x * self.zoom))
        self.pan_y = screen_y - ((height * 0.54) + (world_y * self.zoom))
        self.render()

    def officer_positions(self, width: int, height: int) -> List[Tuple[int, float, float]]:
        arms = 20
        per_arm = math.ceil(OFF_SKILL_COUNT / arms)

        scale_factor = math.sqrt(OFF_SKILL_COUNT / 100)
        outer = max(160.0, min(width, height) * 0.42 * scale_factor)

        step_spacing = 1.25

        positions: List[Tuple[int, float, float]] = []

        for arm in range(arms):
            angle = (-math.pi / 2.0) + (arm * ((math.pi * 2.0) / arms))

            for step in range(per_arm):
                officer_index = arm * per_arm + step

                if officer_index >= OFF_SKILL_COUNT:
                    break

                t = step / max(1, per_arm - 1)

                radius = 40.0 + (t * outer * step_spacing)

                bend = math.sin((step * 0.45) + (arm * 0.6)) * 0.18

                px = math.cos(angle + bend) * radius
                py = math.sin(angle + bend) * radius * 0.78

                positions.append((officer_index, px, py))

        return positions

    def project_point(self, width: int, height: int, world_x: float, world_y: float) -> Tuple[float, float]:
        center_x = (width * 0.50) + self.pan_x
        center_y = (height * 0.54) + self.pan_y
        return center_x + (world_x * self.zoom), center_y + (world_y * self.zoom)

    def select_officer_at(self, x: float, y: float):
        hit = self.find_overlapping(x - 8, y - 8, x + 8, y + 8)
        for item_id in reversed(hit):
            officer_index = self.item_to_officer.get(item_id)
            if officer_index is not None:
                self.controller.select_officer(officer_index)
                return

    def focus_on_officer(self, officer_index: int):
        width = max(1, self.winfo_width())
        height = max(1, self.winfo_height())

        positions = self.officer_positions(width, height)

        for idx, wx, wy in positions:
            if idx == officer_index:
                target_x = (width * 0.50)
                target_y = (height * 0.54)

                self.pan_x = target_x - (wx * self.zoom + width * 0.50)
                self.pan_y = target_y - (wy * self.zoom + height * 0.54)

                self.render()
                return

    def render(self):
        self.delete("all")
        self.item_to_officer.clear()
        width = max(1, self.winfo_width())
        height = max(1, self.winfo_height())
        draw_constellation_backdrop(self, width, height, self.stars, self.phase)
        self.create_text(18, 16, anchor="nw", text="Officer Skill Constellation", fill=SELECT_TEXT, font=("Segoe UI", 15, "bold"))
        self.create_text(
            20,
            44,
            anchor="nw",
            text="Gold is selected, green is modded, and violet is loaded. Drag to pan, wheel to zoom, and zoom further in to reveal officer skill ids.",
            fill=SELECT_SUBTEXT,
            font=("Segoe UI", 9),
            width=max(200, width - 40),
        )
        positions = [(officer_index, *self.project_point(width, height, wx, wy)) for officer_index, wx, wy in self.officer_positions(width, height)]
        if self.controller.current_main_bytes is None:
            self.create_text(width * 0.5, height * 0.56, text="Load 013.xl to light the officer skill lattice.", fill=SELECT_SUBTEXT, font=("Segoe UI", 11))
            return

        arms = 20
        per_arm = math.ceil(OFF_SKILL_COUNT / arms)
        zoom_scale = max(0.8, min(2.0, self.zoom))
        show_labels = self.zoom >= 1.6
        line_width = 1 if self.zoom < 1.5 else 2
        for arm in range(arms):
            start = arm * per_arm
            end = min(start + per_arm, len(positions))

            arm_positions = positions[start:end]

            for i in range(len(arm_positions) - 1):
                _, ax, ay = arm_positions[i]
                _, bx, by = arm_positions[i + 1]

                self.create_line(ax, ay, bx, by, fill=SELECT_LINE, width=line_width)

        for officer_index, px, py in positions:
            selected = self.controller.current_officer_index == officer_index
            changed = self.controller.officer_is_changed(officer_index)
            if selected:
                fill = SELECT_NODE_SEL
                outline = SELECT_GOLD
                radius = max(8, min(18, int(10 * zoom_scale)))
                pulse = max(14, min(28, (17 + math.sin(self.phase * 2.0 + (officer_index * 0.3)) * 2) * zoom_scale))
                halo = self.create_oval(px - pulse, py - pulse, px + pulse, py + pulse, outline=outline, width=1, stipple="gray25")
                self.item_to_officer[halo] = officer_index
            elif changed:
                fill = SELECT_GREEN
                outline = "#A8E3B9"
                radius = max(6, min(14, int(8 * zoom_scale)))
            else:
                fill = SELECT_NODE
                outline = SELECT_NODE_RING
                radius = max(5, min(12, int(7 * zoom_scale)))
            orb = self.create_oval(px - radius, py - radius, px + radius, py + radius, fill=fill, outline=outline, width=2 if selected else 1)
            self.item_to_officer[orb] = officer_index
            if show_labels:
                label_fill = SELECT_TEXT if selected else SELECT_SUBTEXT
                label_size = max(8, min(11, int(8 * zoom_scale)))
                label = self.create_text(px, py - max(14, int(14 * zoom_scale)), text=str(officer_index + 1), fill=label_fill, font=("Segoe UI", label_size, "bold"))
                self.item_to_officer[label] = officer_index


class DW8XLOFFSKILLEditorWindow(tk.Toplevel):
    def __init__(self, parent: tk.Misc):
        super().__init__(parent)
        self.officers = list(OFF_SKILLS)
        self.filtered_officers = list(self.officers)
        self.current_main_bytes: Optional[bytearray] = None
        self.original_main_bytes = b""
        self.current_officer_index = 0
        self.files_dirty = False
        self.officer_dirty = False
        self._loading_fields = False
        self._suppress_list_event = False
        self.officer_desc_var = tk.StringVar(value="")
        self.officer_search_var = tk.StringVar(value="")
        self.officer_title_var = tk.StringVar(value="No officer skill loaded")
        self.officer_meta_var = tk.StringVar(value="Load DW8XL officer skill data to begin.")
        self.status_var = tk.StringVar(value="Ready to edit the DW8XL officer skill data.")
        self.dirty_var = tk.StringVar(value="Disk state: clean")
        self.officer_jump_var = tk.StringVar(value="1")

        self.core_field_vars: List[tk.StringVar] = []
        self.core_field_entries: List[tk.Entry] = []
        self.core_field_helpers: List[tk.Label] = []
        self.flag_vars: List[tk.IntVar] = []

        self.title("DW8XL Officer Skill Editor")
        self.configure(bg=SELECT_BG)
        self.geometry("1780x1120")
        self.minsize(1500, 960)

        setup_lilac_styles(self)
        apply_lilac_to_root(self)

        self.build_gui()
        self.officer_search_var.trace_add("write", lambda *_: self.refresh_officer_list())
        self.load_files()
        self.refresh_officer_list()
        self.protocol("WM_DELETE_WINDOW", self.on_close_request)

    def build_gui(self):
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(1, weight=1)

        hero = tk.Canvas(self, height=172, bg=SELECT_BG, highlightthickness=0, bd=0, relief="flat")
        hero.grid(row=0, column=0, sticky="ew", padx=12, pady=(12, 10))
        hero.bind("<Configure>", lambda e: self.draw_hero(hero, e.width, e.height))

        content = tk.Frame(self, bg=SELECT_BG)
        content.grid(row=1, column=0, sticky="nsew", padx=12, pady=(0, 10))
        content.grid_columnconfigure(0, weight=2, uniform="officer")
        content.grid_columnconfigure(1, weight=3, uniform="officer")
        content.grid_columnconfigure(2, weight=5, uniform="officer")
        content.grid_rowconfigure(0, weight=1)

        left = build_panel(content, "Officer Skill Lattice", "Select the DW8XL Officer Skill to mod.", SELECT_BLUE)
        left["panel"].grid(row=0, column=0, sticky="nsew", padx=(0, 8))
        left["body"].grid_columnconfigure(0, weight=1)
        left["body"].grid_rowconfigure(3, weight=1)

        center = build_panel(content, "Officer Skill Constellation", "Navigate the Officer Skills.", SELECT_GOLD)
        center["panel"].grid(row=0, column=1, sticky="nsew", padx=8)
        center["body"].grid_columnconfigure(0, weight=1)
        center["body"].grid_rowconfigure(0, weight=1)

        right = build_panel(content, "Officer Skill Field Editor", "Edit 013.xl officer skill data and flag toggles.", SELECT_GREEN)
        right["panel"].grid(row=0, column=2, sticky="nsew", padx=(8, 0))
        right["body"].grid_columnconfigure(0, weight=1)
        right["body"].grid_rowconfigure(2, weight=1)

        self.build_left_panel(left["body"])
        self.build_center_panel(center["body"])
        self.build_right_panel(right["body"])

        footer = tk.Frame(self, bg=SELECT_PANEL_2, height=42)
        footer.grid(row=2, column=0, sticky="ew", padx=12, pady=(0, 12))
        footer.grid_propagate(False)
        footer.grid_columnconfigure(0, weight=1)
        self.status_label = tk.Label(footer, textvariable=self.status_var, bg=SELECT_PANEL_2, fg=STATUS_GOOD, anchor="w", font=("Segoe UI", 9, "bold"))
        self.status_label.grid(row=0, column=0, sticky="ew", padx=14, pady=10)

    def build_left_panel(self, parent: tk.Frame):
        tk.Label(parent, textvariable=self.officer_title_var, bg=SELECT_PANEL_3, fg="#180E2B", font=("Segoe UI", 17, "bold"), anchor="w", justify="left").grid(row=0, column=0, sticky="ew", padx=18, pady=(18, 6))
        tk.Label(parent, textvariable=self.officer_meta_var, bg=SELECT_PANEL_3, fg="#3B2E57", font=("Consolas", 10), anchor="w", justify="left").grid(row=1, column=0, sticky="ew", padx=18)

        search_wrap = tk.Frame(parent, bg=SELECT_PANEL_3)
        search_wrap.grid(row=2, column=0, sticky="ew", padx=18, pady=(16, 10))
        search_wrap.grid_columnconfigure(0, weight=1)
        search_entry = tk.Entry(search_wrap, textvariable=self.officer_search_var, bg=FIELD_BG, fg=FIELD_TEXT, insertbackground=FIELD_TEXT, relief="flat", bd=0, font=("Segoe UI", 10))
        search_entry.grid(row=0, column=0, sticky="ew", ipady=7)
        action_button(search_wrap, "Clear", lambda: self.officer_search_var.set(""), SELECT_BLUE).grid(row=0, column=1, padx=(8, 0))

        list_wrap = tk.Frame(parent, bg=SELECT_PANEL_3)
        list_wrap.grid(row=3, column=0, sticky="nsew", padx=18)
        list_wrap.grid_columnconfigure(0, weight=1)
        list_wrap.grid_rowconfigure(0, weight=1)
        self.officer_listbox = tk.Listbox(list_wrap, selectmode=tk.SINGLE, bg="#120E1B", fg="#E9DEF5", activestyle="none", font=("Consolas", 9), relief="flat", bd=0, highlightthickness=1, highlightbackground=SELECT_LINE, selectbackground=SELECT_NODE, selectforeground=SELECT_TEXT)
        self.officer_listbox.grid(row=0, column=0, sticky="nsew")
        self.officer_listbox.bind("<<ListboxSelect>>", self.on_officer_list_select)
        self.batch_controller = EditorBatchSelectionController(
            self,
            listbox=self.officer_listbox,
            get_visible_ids=lambda: [officer.index for officer in self.filtered_officers],
            get_current_id=lambda: self.current_officer_index if self.current_main_bytes is not None else None,
            select_id=self.select_officer,
            fields=self.batch_fields(),
            read_values=self.batch_read_values,
            apply_updates=self.apply_batch_updates,
            restore_values=self.restore_batch_snapshot,
            set_status=self.set_status,
            title="Officer Skill Multi-Slot Editor",
            noun="skills",
        )
        officer_scroll = tk.Scrollbar(list_wrap, orient="vertical", command=self.officer_listbox.yview)
        officer_scroll.grid(row=0, column=1, sticky="ns")
        self.officer_listbox.config(yscrollcommand=officer_scroll.set)

        nav = tk.Frame(parent, bg=SELECT_PANEL_3)
        nav.grid(row=4, column=0, sticky="ew", padx=18, pady=(12, 8))
        nav.grid_columnconfigure(0, weight=1)
        nav.grid_columnconfigure(1, weight=1)
        action_button(nav, "Prev", lambda: self.change_officer(-1), SELECT_BLUE).grid(row=0, column=0, sticky="ew", padx=(0, 6))
        action_button(nav, "Next", lambda: self.change_officer(1), SELECT_BLUE).grid(row=0, column=1, sticky="ew", padx=(6, 0))
        tk.Label(parent, text="Entries accept decimal, -1, or 0x-prefixed hex.", bg=SELECT_PANEL_3, fg=SELECT_MUTED, wraplength=320, justify="left", anchor="w", font=("Segoe UI", 9, "italic")).grid(row=5, column=0, sticky="ew", padx=18, pady=(0, 18))

    def build_center_panel(self, parent: tk.Frame):
        self.officer_canvas = OffSkillConstellationCanvas(parent, self)
        install_constellation_virtualization(self.officer_canvas, node_limit=100)
        self.officer_canvas.grid(row=0, column=0, sticky="nsew", padx=14, pady=(18, 10))

        nav = tk.Frame(parent, bg=SELECT_PANEL_3)
        nav.grid(row=1, column=0, sticky="ew", padx=18, pady=(0, 8))
        nav.grid_columnconfigure(1, weight=1)
        action_button(nav, "Prev", lambda: self.change_officer(-1), SELECT_BLUE).grid(row=0, column=0, padx=(0, 8))
        jump_entry = tk.Entry(nav, textvariable=self.officer_jump_var, bg=FIELD_BG, fg=FIELD_TEXT, insertbackground=FIELD_TEXT, relief="flat", bd=0, font=("Consolas", 10), width=8, justify="center")
        jump_entry.grid(row=0, column=1, sticky="ew", ipady=7)
        jump_entry.bind("<Return>", lambda _e: self.jump_to_officer())
        action_button(nav, "Go", self.jump_to_officer, SELECT_GOLD, fg="#180E2B").grid(row=0, column=2, padx=8)
        action_button(nav, "Next", lambda: self.change_officer(1), SELECT_BLUE).grid(row=0, column=3, padx=(0, 8))
        action_button(nav, "Apply", self.apply_current_officer, SELECT_GREEN).grid(row=0, column=4)
        tk.Label(parent, text="Changed skills glow green after they are applied to memory. Drag inside the constellation to pan, use the mouse wheel to zoom, and zoom further in if you want skill ids to appear above each node. Save File exports a full copy of 013.xl under the project root.", bg=SELECT_PANEL_3, fg=SELECT_MUTED, wraplength=460, justify="left", anchor="w", font=("Segoe UI", 9, "italic")).grid(row=2, column=0, sticky="ew", padx=18, pady=(0, 18))

    def build_right_panel(self, parent: tk.Frame):
        tk.Label(parent, textvariable=self.dirty_var, bg=SELECT_PANEL_3, fg="#3B2E57", font=("Segoe UI", 10, "bold"), anchor="w", justify="left").grid(row=0, column=0, sticky="ew", padx=18, pady=(18, 6))
        tk.Label(parent, text="Mod the core fields and flag toggles. Scroll to reach the lower sections.", bg=SELECT_PANEL_3, fg=SELECT_MUTED, wraplength=620, justify="left", anchor="w", font=("Segoe UI", 9)).grid(row=1, column=0, sticky="ew", padx=18, pady=(0, 10))

        scroll_shell = tk.Frame(parent, bg=SELECT_PANEL_3)
        scroll_shell.grid(row=2, column=0, sticky="nsew", padx=18)
        scroll_shell.grid_rowconfigure(0, weight=1)
        scroll_shell.grid_columnconfigure(0, weight=1)

        self.fields_canvas = tk.Canvas(scroll_shell, bg=SELECT_PANEL_3, highlightthickness=0, bd=0, relief="flat")
        self.fields_canvas.grid(row=0, column=0, sticky="nsew")

        field_scrollbar = tk.Scrollbar(scroll_shell, orient="vertical", command=self.fields_canvas.yview)
        field_scrollbar.grid(row=0, column=1, sticky="ns")
        self.fields_canvas.configure(yscrollcommand=field_scrollbar.set)

        fields_wrap = tk.Frame(self.fields_canvas, bg=SELECT_PANEL_3)
        self.fields_canvas_window = self.fields_canvas.create_window((0, 0), window=fields_wrap, anchor="nw")
        fields_wrap.bind("<Configure>", lambda _e: self.fields_canvas.configure(scrollregion=self.fields_canvas.bbox("all")))
        self.fields_canvas.bind("<Configure>", lambda e: self.fields_canvas.itemconfigure(self.fields_canvas_window, width=e.width))

        self.build_core_section(fields_wrap)
        self.build_flag_section(fields_wrap)
        self.desc_label = build_description_section(
            fields_wrap,
            title="Skill Description",
            textvariable=self.officer_desc_var,
            panel_bg=SELECT_PANEL_2,
            line_color=SELECT_LINE,
            title_fg=SELECT_TEXT,
            body_fg=SELECT_SUBTEXT,
            wraplength=500,
        )

        actions = tk.Frame(parent, bg=SELECT_PANEL_3)
        actions.grid(row=3, column=0, sticky="ew", padx=18, pady=(14, 18))
        actions.grid_columnconfigure(0, weight=1)
        actions.grid_columnconfigure(1, weight=1)
        actions.grid_columnconfigure(2, weight=1)
        action_button(actions, "Save File", self.save_current_files, SELECT_GREEN).grid(row=0, column=0, sticky="ew", padx=(0, 6))
        action_button(actions, "Reload File", self.reload_files, SELECT_GOLD, fg="#180E2B").grid(row=0, column=1, sticky="ew", padx=6)
        action_button(actions, "Close Editor", self.on_close_request, SELECT_BLUE).grid(row=0, column=2, sticky="ew", padx=(6, 0))

    def build_core_section(self, parent: tk.Frame):
        core_section = tk.Frame(parent, bg=SELECT_PANEL_2, highlightthickness=1, highlightbackground=SELECT_LINE)
        core_section.pack(fill="x", pady=(0, 12))
        core_section.grid_columnconfigure(0, weight=1)
        core_section.grid_columnconfigure(1, weight=1)
        tk.Label(core_section, text="013.xl Core Data", bg=SELECT_PANEL_2, fg=SELECT_TEXT, font=("Segoe UI", 11, "bold")).grid(row=0, column=0, columnspan=2, sticky="w", padx=12, pady=(12, 4))
        tk.Label(core_section, text="Mapped fields.", bg=SELECT_PANEL_2, fg=SELECT_SUBTEXT, font=("Segoe UI", 9), anchor="w", justify="left", wraplength=620).grid(row=1, column=0, columnspan=2, sticky="ew", padx=12, pady=(0, 10))

        columns = []
        for col in range(2):
            frame = tk.Frame(core_section, bg=SELECT_PANEL_2)
            frame.grid(row=2, column=col, sticky="nsew", padx=(12 if col == 0 else 6, 6 if col == 0 else 12), pady=(0, 12))
            columns.append(frame)

        for idx, (field_name, byte_width) in enumerate(OFF_SKILL_FIELDS):
            row = idx // 2
            bg = FIELD_BG if row % 2 == 0 else FIELD_ALT_BG
            block = tk.Frame(columns[idx % 2], bg=bg, highlightthickness=1, highlightbackground=FIELD_OUTLINE, padx=8, pady=8)
            block.pack(fill="x", pady=4)
            tk.Label(block, text=field_name, bg=bg, fg="#24183C", font=("Segoe UI", 10, "bold"), anchor="w").pack(fill="x")
            var = tk.StringVar(value="0")
            entry = tk.Entry(block, textvariable=var, bg=bg, fg=FIELD_TEXT, insertbackground=FIELD_TEXT, relief="flat", bd=0, font=("Consolas", 10))
            entry.pack(fill="x", ipady=6, pady=(4, 3))
            helper = tk.Label(block, text=helper_text_for_sized_value(0, byte_width), bg=bg, fg=SELECT_MUTED, font=("Segoe UI", 8), anchor="w", justify="left")
            helper.pack(fill="x")
            var.trace_add("write", lambda *_args, i=idx: self.on_core_field_changed(i))
            self.core_field_vars.append(var)
            self.core_field_entries.append(entry)
            self.core_field_helpers.append(helper)

    def build_flag_section(self, parent: tk.Frame):
        flag_section = tk.Frame(parent, bg=SELECT_PANEL_2, highlightthickness=1, highlightbackground=SELECT_LINE)
        flag_section.pack(fill="x", pady=(0, 12))
        tk.Label(flag_section, text="013.xl Flags 1-8", bg=SELECT_PANEL_2, fg=SELECT_TEXT, font=("Segoe UI", 11, "bold")).grid(row=0, column=0, sticky="w", padx=12, pady=(12, 4))
        tk.Label(flag_section, text="Untoggled writes 00 and toggled writes 01. These flags aren't fully known yet.", bg=SELECT_PANEL_2, fg=SELECT_SUBTEXT, font=("Segoe UI", 9), anchor="w", justify="left", wraplength=620).grid(row=1, column=0, sticky="ew", padx=12, pady=(0, 10))

        flag_grid = tk.Frame(flag_section, bg=SELECT_PANEL_2)
        flag_grid.grid(row=2, column=0, sticky="ew", padx=12, pady=(0, 12))
        for col in range(5):
            flag_grid.grid_columnconfigure(col, weight=1)

        for idx, flag_name in enumerate(OFF_SKILL_FLAG_NAMES):
            col = idx % 5
            row = idx // 5
            var = tk.IntVar(value=0)
            toggle = tk.Checkbutton(flag_grid, text=flag_name, variable=var, command=self.on_flag_changed, indicatoron=False, relief="flat", bd=0, bg=FIELD_BG if row % 2 == 0 else FIELD_ALT_BG, fg="#24183C", activebackground=FIELD_ALT_BG, activeforeground="#24183C", selectcolor=SELECT_GREEN, font=("Segoe UI", 8, "bold"), padx=6, pady=6, cursor="hand2")
            toggle.grid(row=row, column=col, sticky="ew", padx=4, pady=4)
            self.flag_vars.append(var)

    def draw_hero(self, canvas: tk.Canvas, width: int, height: int):
        canvas.delete("all")
        draw_constellation_backdrop(canvas, width, height, make_stars(887, 46), 0.0)
        points = [(width * 0.05, height * 0.41), (width * 0.16, height * 0.16), (width * 0.28, height * 0.36), (width * 0.41, height * 0.15), (width * 0.56, height * 0.35), (width * 0.71, height * 0.18), (width * 0.84, height * 0.40), (width * 0.93, height * 0.21)]
        for idx in range(len(points) - 1):
            canvas.create_line(*points[idx], *points[idx + 1], fill=SELECT_LINE, width=1)
        for x, y in points:
            canvas.create_oval(x - 3, y - 3, x + 3, y + 3, fill=SELECT_STAR, outline="")
        canvas.create_text(34, 34, anchor="nw", text="DW8XL Officer Skill Editor", fill=SELECT_TEXT, font=("Segoe UI", 26, "bold"))
        canvas.create_text(36, 78, anchor="nw", text="Mod the Officer Skills", fill=SELECT_SUBTEXT, font=("Segoe UI", 10), width=max(380, width - 120))

    def set_status(self, text: str, color: str = STATUS_GOOD):
        self.status_var.set(text)
        self.status_label.config(fg=color)

    def get_off_skill_display_name(self, off_skill_index: int) -> str:
        if 0 <= off_skill_index < len(DW8XL_OFF_SKILL_NAMES):
            return DW8XL_OFF_SKILL_NAMES[off_skill_index]
        
        return f"Skill {off_skill_index + 1:03d}"

    def officer_main_offset(self, officer_index: int) -> int:
        return OFF_SKILL_OFFSET + (officer_index * OFF_SKILL_RECORD_SIZE)

    def read_main_record(self, officer_index: int, blob: Optional[bytes] = None) -> bytes:
        source = blob if blob is not None else self.current_main_bytes
        if source is None:
            return b""
        start = self.officer_main_offset(officer_index)
        return bytes(source[start : start + OFF_SKILL_RECORD_SIZE])

    def read_core_values(self, officer_index: int, blob: Optional[bytes] = None) -> List[int]:
        record = self.read_main_record(officer_index, blob)
        if len(record) < OFF_SKILL_RECORD_SIZE:
            return [0] * len(OFF_SKILL_FIELDS)
        values: List[int] = []
        cursor = 0
        for _field_name, byte_width in OFF_SKILL_FIELDS:
            values.append(int.from_bytes(record[cursor : cursor + byte_width], "little", signed=False))
            cursor += byte_width
        return values

    def read_flag_values(self, officer_index: int, blob: Optional[bytes] = None) -> List[int]:
        record = self.read_main_record(officer_index, blob)
        if len(record) < OFF_SKILL_RECORD_SIZE:
            return [0] * len(OFF_SKILL_FLAG_NAMES)
        start = OFF_SKILL_CORE_SIZE
        end = start + len(OFF_SKILL_FLAG_NAMES)
        return list(record[start:end])

    def batch_fields(self) -> List[EditorBatchField]:
        return [EditorBatchField(label, byte_width) for label, byte_width in OFF_SKILL_FIELDS] + [
            EditorBatchField(name, 1) for name in OFF_SKILL_FLAG_NAMES
        ]

    def batch_field_offsets(self) -> List[Tuple[int, int]]:
        return linear_field_offsets(OFF_SKILL_FIELDS, extra_flags=OFF_SKILL_FLAG_NAMES)

    def batch_read_values(self, officer_index: int) -> List[int]:
        return self.read_core_values(officer_index) + self.read_flag_values(officer_index)

    def apply_batch_updates(self, officer_indices: Sequence[int], updates: Sequence[Tuple[int, int]]) -> bool:
        if self.current_main_bytes is None:
            return False
        write_batch_record_updates(
            self.current_main_bytes,
            record_offset=self.officer_main_offset,
            record_size=OFF_SKILL_RECORD_SIZE,
            field_offsets=self.batch_field_offsets(),
            slots=officer_indices,
            updates=updates,
        )
        self.files_dirty = bytes(self.current_main_bytes) != self.original_main_bytes
        self.officer_dirty = False
        self.load_officer_into_fields(self.current_officer_index)
        self.sync_officer_selection()
        return True

    def restore_batch_snapshot(self, snapshot: Dict[int, List[int]]) -> bool:
        if self.current_main_bytes is None:
            return False
        write_batch_record_snapshots(
            self.current_main_bytes,
            record_offset=self.officer_main_offset,
            record_size=OFF_SKILL_RECORD_SIZE,
            field_offsets=self.batch_field_offsets(),
            snapshots=snapshot,
        )
        self.files_dirty = bytes(self.current_main_bytes) != self.original_main_bytes
        self.officer_dirty = False
        self.load_officer_into_fields(self.current_officer_index)
        self.sync_officer_selection()
        return True

    def officer_is_changed(self, off_skill_index: int) -> bool:
        if self.current_main_bytes is None or not self.original_main_bytes:
            return False

        return self.read_main_record(off_skill_index) != self.read_main_record(off_skill_index, self.original_main_bytes)
    
    def dirty_OFF_SKILL_COUNT(self) -> int:
        return sum(1 for officer_index in range(OFF_SKILL_COUNT) if self.officer_is_changed(officer_index))

    def update_dirty_banner(self):
        if self.officer_dirty and self.files_dirty:
            self.dirty_var.set("Disk state: unapplied officer skill edits + unsaved file changes")
        elif self.officer_dirty:
            self.dirty_var.set("Disk state: unapplied officer skill edits")
        elif self.files_dirty:
            self.dirty_var.set("Disk state: unsaved file changes in memory")
        else:
            self.dirty_var.set("Disk state: clean")

    def update_meta(self):
        if self.current_main_bytes is None:
            self.officer_title_var.set("No officer skill loaded")
            self.officer_meta_var.set("Load DW8XL officer skill data to begin.")
            self.officer_desc_var.set("")
            return

        if 0 <= self.current_officer_index < len(DW8XL_OFF_SKILL_NAMES):
            name = DW8XL_OFF_SKILL_NAMES[self.current_officer_index]
        else:
            name = f"Skill {self.current_officer_index + 1:03d}"

        slot_number = self.current_officer_index + 1
        self.officer_title_var.set(f"{name} | {slot_number:03d}")

        self.officer_meta_var.set(
            "\n".join(
                [
                    f"Officer Skill  : {name} | {slot_number:03d}",
                    f"Main Path      : {os.path.relpath(OFF_SKILL_PATH, PROJECT_ROOT)}",
                    f"Export Path    : {os.path.relpath(OFF_SKILL_EXPORT_PATH, PROJECT_ROOT)}",
                    f"Skill Slots    : {OFF_SKILL_COUNT}",
                    f"Dirty Skills   : {self.dirty_OFF_SKILL_COUNT()}",
                ]
            )
        )
        desc = DW8XL_OFF_SKILL_DESC.get(self.current_officer_index, "No description available.")
        self.officer_desc_var.set(desc)

    def update_core_field_helper(self, field_index: int):
        raw = self.core_field_vars[field_index].get()
        entry = self.core_field_entries[field_index]
        helper = self.core_field_helpers[field_index]
        field_name, byte_width = OFF_SKILL_FIELDS[field_index]
        try:
            value = parse_sized_int(raw, byte_width)
        except ValueError:
            entry.config(bg=FIELD_INVALID)
            helper.config(text="Invalid value. Use decimal, -1, or 0x-prefixed hex.", fg=STATUS_BAD)
            return
        row = field_index // 2
        entry.config(bg=FIELD_BG if row % 2 == 0 else FIELD_ALT_BG)
        helper.config(text=helper_text_for_sized_value(value, byte_width), fg=SELECT_MUTED)

    def load_officer_into_fields(self, officer_index: int):
        if self.current_main_bytes is None:
            return
        core_values = self.read_core_values(officer_index)
        flag_values = self.read_flag_values(officer_index)
        self._loading_fields = True
        for idx, value in enumerate(core_values):
            field_name, byte_width = OFF_SKILL_FIELDS[idx]
            self.core_field_vars[idx].set(format_core_value(field_name, byte_width, value))
        for idx, value in enumerate(flag_values):
            self.flag_vars[idx].set(1 if value else 0)
        self._loading_fields = False
        for idx in range(len(OFF_SKILL_FIELDS)):
            self.update_core_field_helper(idx)
        self.officer_dirty = False
        self.update_dirty_banner()
        self.officer_jump_var.set(str(officer_index + 1))
        self.officer_canvas.render()
        self.update_meta()

    def parse_core_field_values(self) -> Optional[List[int]]:
        values: List[int] = []
        for idx, (field_name, byte_width) in enumerate(OFF_SKILL_FIELDS):
            try:
                values.append(parse_sized_int(self.core_field_vars[idx].get(), byte_width))
            except ValueError as exc:
                self.core_field_entries[idx].focus_set()
                try:
                    self.core_field_entries[idx].selection_range(0, "end")
                except Exception:
                    pass
                messagebox.showerror("Invalid Field Value", f"{field_name}: {exc}")
                self.set_status(f"{field_name} could not be applied. Fix the field and try again.", STATUS_BAD)
                return None
        return values

    def apply_current_officer(self, *, show_status: bool = True) -> bool:
        if self.current_main_bytes is None:
            return False
        core_values = self.parse_core_field_values()
        if core_values is None:
            return False

        main_record = bytearray(self.read_main_record(self.current_officer_index))
        cursor = 0
        for value, (_field_name, byte_width) in zip(core_values, OFF_SKILL_FIELDS):
            main_record[cursor : cursor + byte_width] = value.to_bytes(byte_width, "little", signed=False)
            cursor += byte_width
        flag_start = OFF_SKILL_CORE_SIZE
        for idx, flag_var in enumerate(self.flag_vars):
            main_record[flag_start + idx] = 1 if flag_var.get() else 0
        cursor = 0

        main_start = self.officer_main_offset(self.current_officer_index)
        main_end = main_start + OFF_SKILL_RECORD_SIZE
        main_changed = bytes(self.current_main_bytes[main_start:main_end]) != bytes(main_record)
        if main_changed:
            self.current_main_bytes[main_start:main_end] = main_record
        self.files_dirty = bytes(self.current_main_bytes) != self.original_main_bytes
        self.officer_dirty = False
        self.update_meta()
        self.update_dirty_banner()
        self.officer_canvas.render()
        if show_status:
            color = STATUS_GOOD if (main_changed) else STATUS_WARN
            self.set_status(f"Applied {self.officers[self.current_officer_index].label} to memory. Save Officer Skill File when you're ready.", color)
        return True

    def save_current_files(self) -> bool:
        if self.current_main_bytes is None:
            return False
        if self.officer_dirty and not self.apply_current_officer(show_status=False):
            return False
        had_unsaved_changes = self.files_dirty
        export_main = OFF_SKILL_EXPORT_PATH
        try:
            os.makedirs(os.path.dirname(OFF_SKILL_EXPORT_PATH), exist_ok=True)
            with open(OFF_SKILL_EXPORT_PATH, "wb") as handle:
                handle.write(self.current_main_bytes)
        except OSError as exc:
            messagebox.showerror("Save Failed", f"Could not export officer skill file:\n{exc}")
            self.set_status("Could not export the officer skill file.", STATUS_BAD)
            return False
        self.original_main_bytes = bytes(self.current_main_bytes)
        self.files_dirty = False
        self.officer_dirty = False
        self.update_meta()
        self.update_dirty_banner()
        self.officer_canvas.render()
        suffix = " (clean copies)" if not had_unsaved_changes else ""
        self.set_status(f"Exported {os.path.relpath(export_main, PROJECT_ROOT)}{suffix}.", STATUS_GOOD)
        return True

    def load_files(self) -> bool:
        missing_paths = [OFF_SKILL_PATH] if not os.path.isfile(OFF_SKILL_PATH) else []
        if missing_paths:
            messagebox.showerror("Missing Officer Skill File", "Could not find:\n" + "\n".join(missing_paths))
            self.set_status("Missing DW8XL officer skill file.", STATUS_BAD)
            return False
        try:
            with open(OFF_SKILL_PATH, "rb") as handle:
                main_blob = handle.read()
        except OSError as exc:
            messagebox.showerror("Read Failed", f"Could not read the officer skill file:\n{exc}")
            self.set_status("Could not read the DW8XL officer skill file.", STATUS_BAD)
            return False

        required_main = OFF_SKILL_OFFSET + (OFF_SKILL_COUNT * OFF_SKILL_RECORD_SIZE)
        if len(main_blob) < required_main:
            messagebox.showerror("Officer Skill File Too Small", "013.xl does not contain the full reversed block.")
            self.set_status("DW8XL officer skill file is too small for the reversed blocks.", STATUS_BAD)
            return False

        self.current_main_bytes = bytearray(main_blob)
        self.original_main_bytes = bytes(main_blob)
        self.current_officer_index = 0
        self.files_dirty = False
        self.officer_dirty = False
        self.update_meta()
        self.load_officer_into_fields(0)
        self.sync_officer_selection()
        self.set_status("Loaded 013.xl", STATUS_GOOD)
        return True

    def confirm_file_transition(self, reason: str) -> bool:
        if self.current_main_bytes is None:
            return True
        if self.officer_dirty and not self.apply_current_officer(show_status=False):
            return False
        if not self.files_dirty:
            return True
        choice = messagebox.askyesnocancel("Unsaved Officer Skill Changes", f"Export changes from 013.xl before {reason}?")
        if choice is None:
            return False
        return self.save_current_files() if choice else True

    def reload_files(self):
        if self.current_main_bytes is None:
            return
        if self.officer_dirty or self.files_dirty:
            if not messagebox.askyesno("Reload Officer Skill File", "Reloading 013.xl will discard unapplied and unsaved changes. Continue?"):
                return
        self.load_files()

    def refresh_officer_list(self):
        query = self.officer_search_var.get().strip().lower()
        self.filtered_officers = [
            officer
            for officer in self.officers
            if not query
            or query in officer.label.lower()
            or query in officer.name.lower()
            or query in f"{officer.index + 1}"
            or query in f"{officer.index + 1:03d}"
        ]
        self._suppress_list_event = True
        try:
            self.officer_listbox.delete(0, tk.END)
            for officer in self.filtered_officers:
                self.officer_listbox.insert(tk.END, officer.label)
        finally:
            self._suppress_list_event = False
        self.sync_officer_selection()

    def sync_officer_selection(self):
        self._suppress_list_event = True
        try:
            if hasattr(self, "batch_controller"):
                self.batch_controller.sync_from_editor()
                return
            self.officer_listbox.selection_clear(0, tk.END)
            target_ordinal = self.current_officer_index + 1
            visible_index = next(
                (idx for idx, officer in enumerate(self.filtered_officers)
                 if officer.index == self.current_officer_index),
                None
            )
            if visible_index is not None:
                self.officer_listbox.selection_set(visible_index)
                self.officer_listbox.activate(visible_index)
                self.officer_listbox.see(visible_index)
        finally:
            self._suppress_list_event = False

    def on_officer_list_select(self, _event):
        if self._suppress_list_event:
            return
        selection = self.officer_listbox.curselection()
        if not selection:
            return
        target = self.filtered_officers[selection[0]]
        self.select_officer(target.index)

    def select_officer(self, officer_index: int):
        if self.current_main_bytes is None or officer_index < 0 or officer_index >= OFF_SKILL_COUNT:
            return
        if officer_index == self.current_officer_index:
            self.sync_officer_selection()
            return
        if self.officer_dirty and not self.apply_current_officer(show_status=False):
            self.sync_officer_selection()
            return
        self.current_officer_index = officer_index
        self.load_officer_into_fields(officer_index)
        self.sync_officer_selection()
        self.officer_canvas.focus_on_officer(officer_index)
        self.set_status(f"Selected {self.officers[officer_index].label}.", STATUS_GOOD)

    def change_officer(self, delta: int):
        if self.current_main_bytes is None:
            return
        self.select_officer(max(0, min(OFF_SKILL_COUNT - 1, self.current_officer_index + delta)))

    def jump_to_officer(self):
        if self.current_main_bytes is None:
            return
        try:
            officer_number = int(self.officer_jump_var.get().strip(), 10)
        except ValueError:
            messagebox.showerror("Invalid Officer Skill", "Enter a number from 1 to 104.")
            self.set_status("Officer Skill jump failed. Use a decimal number from 1 to 104.", STATUS_BAD)
            return
        if officer_number < 1 or officer_number > OFF_SKILL_COUNT:
            messagebox.showerror("Invalid Officer Skill", "Officer Skill number must be between 1 and 104.")
            self.set_status("Officer Skill jump failed. Officer Skill number must be between 1 and 104.", STATUS_BAD)
            return
        self.select_officer(officer_number - 1)

    def on_core_field_changed(self, field_index: int):
        self.update_core_field_helper(field_index)
        if self._loading_fields:
            return
        self.officer_dirty = True
        self.update_dirty_banner()

    def on_flag_changed(self):
        if self._loading_fields:
            return
        self.officer_dirty = True
        self.update_dirty_banner()

    def on_close_request(self):
        if not self.confirm_file_transition("closing the officer skill editor"):
            return
        self.destroy()


if __name__ == "__main__":
    raise SystemExit("Run AE/main.pyw to launch Aldnoah Engine tools.")
