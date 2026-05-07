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
    SELECT_SUBTEXT,
    SELECT_TEXT,
    STATUS_BAD,
    STATUS_GOOD,
    STATUS_WARN,
    draw_constellation_backdrop,
    make_stars,
)
from .aldnoah_infos import BODYGUARD_NAMES, DW8XL_SUPPORT_SKILL_DESC, DW8XL_SUPPORT_SKILL_NAMES
from .aldnoah_reusables import (
    EditorBatchField,
    EditorBatchSelectionController,
    EditorActionSchema,
    EditorCenterSchema,
    EditorDropdownFieldSchema,
    EditorDropdownSectionSchema,
    EditorFieldSchema,
    EditorFieldSectionSchema,
    EditorHeroSchema,
    EditorListSchema,
    EditorPanelSchema,
    EditorRightSchema,
    EditorToggleSectionSchema,
    EditorWindowSchema,
    build_description_section,
    build_dropdown_section,
    build_editor_center_panel,
    build_editor_list_panel,
    build_editor_shell,
    build_field_section,
    build_scrollable_editor_panel,
    build_toggle_section,
    linear_field_offsets,
    write_batch_record_snapshots,
    write_batch_record_updates,
)


BODYGUARD_PATH = os.path.join(PROJECT_ROOT, "DW8XL_Unpacked", "Pack_00", "entry_00000", "003.xl")
BODYGUARD_EXPORT_PATH = os.path.join(PROJECT_ROOT, "DW8XL_Bodyguard_Edits", "Pack_00", "entry_00000", "003.xl")

BODYGUARD_COUNT = 903
BODYGUARD_OFFSET = 0x24
BODYGUARD_RECORD_SIZE = 20

BODYGUARD_FIELDS = [
    ("Support Skill 1", 1),
    ("Support Skill 2", 1),
    ("Unknown 1", 2),
    ("Faction", 1),
    ("Battle Skill", 1),
    ("Max Skill Level", 1),
    ("Cost", 1),
    ("Unknown 2", 2),
    ("Unknown 3", 1),
    ("Unknown 4", 1),
]

BODYGUARD_FIELD_INDEX = {field_name: idx for idx, (field_name, _byte_width) in enumerate(BODYGUARD_FIELDS)}
BODYGUARD_SUPPORT_SKILL_FIELD_INDICES = [
    BODYGUARD_FIELD_INDEX["Support Skill 1"],
    BODYGUARD_FIELD_INDEX["Support Skill 2"],
]
BODYGUARD_NON_DROPDOWN_FIELD_INDICES = [
    idx for idx in range(len(BODYGUARD_FIELDS)) if idx not in BODYGUARD_SUPPORT_SKILL_FIELD_INDICES
]
BODYGUARD_NON_DROPDOWN_SECTION_ROWS = {
    field_index: section_index // 2 for section_index, field_index in enumerate(BODYGUARD_NON_DROPDOWN_FIELD_INDICES)
}
BODYGUARD_FLAG_NAMES = [f"Flag {index:02d}" for index in range(1, 9)]
BODYGUARD_CORE_SIZE = sum(size for _field_name, size in BODYGUARD_FIELDS)
BODYGUARD_SUPPORT_SKILL_OPTION_LABELS = [
    f"{name}: {value}" for value, name in sorted(DW8XL_SUPPORT_SKILL_NAMES.items())
]
BODYGUARD_SUPPORT_SKILL_VALUE_TO_LABEL = {
    value: f"{name}: {value}" for value, name in sorted(DW8XL_SUPPORT_SKILL_NAMES.items())
}
BODYGUARD_SUPPORT_SKILL_LABEL_TO_VALUE = {
    label: value for value, label in BODYGUARD_SUPPORT_SKILL_VALUE_TO_LABEL.items()
}

BODYGUARD_WINDOW_SCHEMA = EditorWindowSchema(
    window_title="DW8XL Bodyguard Editor",
    hero=EditorHeroSchema(
        title="DW8XL Bodyguard Editor",
        subtitle="Mod the Bodyguards of DW8XL.",
        star_seed=905,
        star_count=48,
    ),
    left_panel=EditorPanelSchema(
        title="Bodyguard Lattice",
        subtitle="Select the DW8XL bodyguard slot you want to mod.",
        accent=SELECT_BLUE,
    ),
    center_panel=EditorPanelSchema(
        title="Bodyguard Constellation",
        subtitle="Navigate the 903 DW8XL bodyguard slots.",
        accent=SELECT_GOLD,
    ),
    right_panel=EditorPanelSchema(
        title="Bodyguard Field Editor",
        subtitle="Mod 003.xl bodyguard data and flag toggles.",
        accent=SELECT_GREEN,
    ),
)

BODYGUARD_LIST_SCHEMA = EditorListSchema(
    prev_label="Prev Guard",
    next_label="Next Guard",
)

BODYGUARD_CENTER_SCHEMA = EditorCenterSchema(
    prev_label="Prev Guard",
    next_label="Next Guard",
    apply_label="Apply Guard",
    hint_text="Changed bodyguard slots glow green after they are applied to memory. Drag inside the constellation to pan, use the mouse wheel to zoom, and zoom further in if you want bodyguard slot ids to appear above each node. Save File exports a full copy of 003.xl under the project root.",
)


@dataclass(frozen=True)
class BodyguardInfo:
    index: int
    name: str

    @property
    def label(self) -> str:
        slot_number = self.index + 1
        fallback = f"Bodyguard Slot {slot_number:03d}"
        return self.name if self.name == fallback else f"{self.name} | {slot_number:03d}"


BODYGUARDS = [
    BodyguardInfo(index, BODYGUARD_NAMES.get(index, f"Bodyguard Slot {index + 1:03d}"))
    for index in range(BODYGUARD_COUNT)
]


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


def support_skill_label(skill_id: int) -> str:
    return DW8XL_SUPPORT_SKILL_NAMES.get(skill_id, f"Skill ID {skill_id}")


def support_skill_description(skill_id: int) -> str:
    return DW8XL_SUPPORT_SKILL_DESC.get(skill_id, "No known support skill description for this id yet.")


def format_support_skill_option(value: int) -> str:
    return BODYGUARD_SUPPORT_SKILL_VALUE_TO_LABEL.get(value, f"Skill ID {value}: {value}")


def parse_support_skill_option(text: str) -> int:
    raw = (text or "").strip()
    if raw in BODYGUARD_SUPPORT_SKILL_LABEL_TO_VALUE:
        return BODYGUARD_SUPPORT_SKILL_LABEL_TO_VALUE[raw]
    if ":" in raw:
        suffix = raw.rsplit(":", 1)[1].strip()
        if suffix.isdigit():
            return int(suffix, 10)
    raise ValueError("Select a support skill from the dropdown list.")


def format_field_value(field_name: str, byte_width: int, value: int) -> str:
    if field_name.startswith("Unknown"):
        return f"0x{value:0{byte_width * 2}X}"
    signed_value = unsigned_to_signed(value, byte_width * 8)
    return str(signed_value if signed_value < 0 else value)


def helper_text_for_field(field_name: str, byte_width: int, value: int) -> str:
    return helper_text_for_sized_value(value, byte_width)


class BodyguardConstellationCanvas(tk.Canvas):
    def __init__(self, parent: tk.Misc, controller: "DW8XLBodyguardEditorWindow"):
        super().__init__(parent, bg=SELECT_BG, highlightthickness=0, bd=0, relief="flat")
        self.controller = controller
        self.item_to_bodyguard: Dict[int, int] = {}
        self.phase = 0.0
        self.stars = make_stars(959, 90)
        self.zoom = 1.0
        self.min_zoom = 0.42
        self.max_zoom = 4.0
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
        self.select_bodyguard_at(event.x, event.y)

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

    def bodyguard_positions(self, width: int, height: int) -> List[Tuple[int, float, float]]:
        arms = 21
        per_arm = math.ceil(BODYGUARD_COUNT / arms)
        scale_factor = math.sqrt(BODYGUARD_COUNT / 100)
        outer = max(180.0, min(width, height) * 0.44 * scale_factor)
        step_spacing = 1.22
        positions: List[Tuple[int, float, float]] = []
        for arm in range(arms):
            angle = (-math.pi / 2.0) + (arm * ((math.pi * 2.0) / arms))
            for step in range(per_arm):
                bodyguard_index = arm * per_arm + step
                if bodyguard_index >= BODYGUARD_COUNT:
                    break
                t = step / max(1, per_arm - 1)
                radius = 36.0 + (t * outer * step_spacing)
                bend = math.sin((step * 0.38) + (arm * 0.55)) * 0.16
                px = math.cos(angle + bend) * radius
                py = math.sin(angle + bend) * radius * 0.80
                positions.append((bodyguard_index, px, py))
        return positions

    def project_point(self, width: int, height: int, world_x: float, world_y: float) -> Tuple[float, float]:
        center_x = (width * 0.50) + self.pan_x
        center_y = (height * 0.54) + self.pan_y
        return center_x + (world_x * self.zoom), center_y + (world_y * self.zoom)

    def select_bodyguard_at(self, x: float, y: float):
        hit = self.find_overlapping(x - 8, y - 8, x + 8, y + 8)
        for item_id in reversed(hit):
            bodyguard_index = self.item_to_bodyguard.get(item_id)
            if bodyguard_index is not None:
                self.controller.select_bodyguard(bodyguard_index)
                return

    def focus_on_bodyguard(self, bodyguard_index: int):
        width = max(1, self.winfo_width())
        height = max(1, self.winfo_height())
        for idx, wx, wy in self.bodyguard_positions(width, height):
            if idx == bodyguard_index:
                self.pan_x = (width * 0.50) - ((width * 0.50) + (wx * self.zoom))
                self.pan_y = (height * 0.54) - ((height * 0.54) + (wy * self.zoom))
                self.render()
                return

    def render(self):
        self.delete("all")
        self.item_to_bodyguard.clear()
        width = max(1, self.winfo_width())
        height = max(1, self.winfo_height())
        draw_constellation_backdrop(self, width, height, self.stars, self.phase)
        self.create_text(18, 16, anchor="nw", text="Bodyguard Constellation", fill=SELECT_TEXT, font=("Segoe UI", 15, "bold"))
        self.create_text(
            20,
            44,
            anchor="nw",
            text="Gold is selected, green is modded, and violet is loaded. Drag to pan, wheel to zoom, and zoom further in to reveal bodyguard slot ids.",
            fill=SELECT_SUBTEXT,
            font=("Segoe UI", 9),
            width=max(200, width - 40),
        )
        positions = [(bodyguard_index, *self.project_point(width, height, wx, wy)) for bodyguard_index, wx, wy in self.bodyguard_positions(width, height)]
        if self.controller.current_main_bytes is None:
            self.create_text(width * 0.5, height * 0.56, text="Load 003.xl to light the bodyguard lattice.", fill=SELECT_SUBTEXT, font=("Segoe UI", 11))
            return

        arms = 21
        per_arm = math.ceil(BODYGUARD_COUNT / arms)
        zoom_scale = max(0.7, min(2.2, self.zoom))
        show_labels = self.zoom >= 2.35
        line_width = 1 if self.zoom < 1.6 else 2
        for arm in range(arms):
            start = arm * per_arm
            end = min(start + per_arm, len(positions))
            arm_positions = positions[start:end]
            for idx in range(len(arm_positions) - 1):
                _, ax, ay = arm_positions[idx]
                _, bx, by = arm_positions[idx + 1]
                self.create_line(ax, ay, bx, by, fill=SELECT_LINE, width=line_width)

        for bodyguard_index, px, py in positions:
            selected = self.controller.current_bodyguard_index == bodyguard_index
            changed = self.controller.bodyguard_is_changed(bodyguard_index)
            if selected:
                fill = SELECT_NODE_SEL
                outline = SELECT_GOLD
                radius = max(7, min(15, int(9 * zoom_scale)))
                pulse = max(13, min(25, (16 + math.sin(self.phase * 2.0 + (bodyguard_index * 0.12)) * 2) * zoom_scale))
                halo = self.create_oval(px - pulse, py - pulse, px + pulse, py + pulse, outline=outline, width=1, stipple="gray25")
                self.item_to_bodyguard[halo] = bodyguard_index
            elif changed:
                fill = SELECT_GREEN
                outline = "#A8E3B9"
                radius = max(5, min(12, int(7 * zoom_scale)))
            else:
                fill = SELECT_NODE
                outline = SELECT_NODE_RING
                radius = max(4, min(10, int(6 * zoom_scale)))
            orb = self.create_oval(px - radius, py - radius, px + radius, py + radius, fill=fill, outline=outline, width=2 if selected else 1)
            self.item_to_bodyguard[orb] = bodyguard_index
            if show_labels:
                label_fill = SELECT_TEXT if selected else SELECT_SUBTEXT
                label_size = max(7, min(10, int(7 * zoom_scale)))
                label = self.create_text(px, py - max(12, int(12 * zoom_scale)), text=str(bodyguard_index + 1), fill=label_fill, font=("Segoe UI", label_size, "bold"))
                self.item_to_bodyguard[label] = bodyguard_index


class DW8XLBodyguardEditorWindow(tk.Toplevel):
    def __init__(self, parent: tk.Misc):
        super().__init__(parent)
        self.bodyguards = list(BODYGUARDS)
        self.filtered_bodyguards = list(self.bodyguards)
        self.current_main_bytes: Optional[bytearray] = None
        self.original_main_bytes = b""
        self.current_bodyguard_index = 0
        self.files_dirty = False
        self.bodyguard_dirty = False
        self._loading_fields = False
        self._suppress_list_event = False

        self.status_var = tk.StringVar(value="Ready to edit the DW8XL bodyguard data.")
        self.dirty_var = tk.StringVar(value="Disk state: clean")
        self.bodyguard_search_var = tk.StringVar(value="")
        self.bodyguard_jump_var = tk.StringVar(value="1")
        self.bodyguard_title_var = tk.StringVar(value="No bodyguard loaded")
        self.bodyguard_meta_var = tk.StringVar(value="Load DW8XL bodyguard data to begin.")
        self.bodyguard_desc_var = tk.StringVar(value="")

        self.core_field_vars: List[Optional[tk.StringVar]] = []
        self.core_field_entries: List[Optional[tk.Entry]] = []
        self.core_field_helpers: List[Optional[tk.Label]] = []
        self.flag_vars: List[tk.IntVar] = []

        self.build_gui()
        self.bodyguard_search_var.trace_add("write", lambda *_: self.refresh_bodyguard_list())
        self.load_files()
        self.refresh_bodyguard_list()
        self.protocol("WM_DELETE_WINDOW", self.on_close_request)

    def build_gui(self):
        shell = build_editor_shell(self, BODYGUARD_WINDOW_SCHEMA, self.status_var)
        self.status_label = shell.status_label

        list_handles = build_editor_list_panel(
            shell.left_body,
            title_var=self.bodyguard_title_var,
            meta_var=self.bodyguard_meta_var,
            search_var=self.bodyguard_search_var,
            on_select=self.on_bodyguard_list_select,
            on_clear=lambda: self.bodyguard_search_var.set(""),
            on_prev=lambda: self.change_bodyguard(-1),
            on_next=lambda: self.change_bodyguard(1),
            schema=BODYGUARD_LIST_SCHEMA,
        )
        self.bodyguard_listbox = list_handles.listbox
        self.batch_controller = EditorBatchSelectionController(
            self,
            listbox=self.bodyguard_listbox,
            get_visible_ids=lambda: [bodyguard.index for bodyguard in self.filtered_bodyguards],
            get_current_id=lambda: self.current_bodyguard_index if self.current_main_bytes is not None else None,
            select_id=self.select_bodyguard,
            fields=self.batch_fields(),
            read_values=self.batch_read_values,
            apply_updates=self.apply_batch_updates,
            restore_values=self.restore_batch_snapshot,
            format_value=self.format_batch_value,
            parse_value=self.parse_batch_value,
            set_status=self.set_status,
            title="Bodyguard Multi-Slot Editor",
            noun="guards",
        )

        self.bodyguard_canvas = BodyguardConstellationCanvas(shell.center_body, self)
        build_editor_center_panel(
            shell.center_body,
            canvas=self.bodyguard_canvas,
            jump_var=self.bodyguard_jump_var,
            jump_command=self.jump_to_bodyguard,
            on_prev=lambda: self.change_bodyguard(-1),
            on_next=lambda: self.change_bodyguard(1),
            on_apply=self.apply_current_bodyguard,
            schema=BODYGUARD_CENTER_SCHEMA,
        )

        right_schema = EditorRightSchema(
            intro_text="Mod the bodyguard fields, scroll to reach the lower sections.",
            actions=[
                EditorActionSchema("Save File", self.save_current_files, SELECT_GREEN),
                EditorActionSchema("Reload File", self.reload_files, SELECT_GOLD, fg="#180E2B"),
                EditorActionSchema("Close Editor", self.on_close_request, SELECT_BLUE),
            ],
        )
        scroll_handles = build_scrollable_editor_panel(shell.right_body, dirty_var=self.dirty_var, schema=right_schema)

        field_schema = EditorFieldSectionSchema(
            title="003.xl Core Data",
            subtitle="Mapped bodyguard fields.",
            fields=[EditorFieldSchema(BODYGUARD_FIELDS[idx][0], BODYGUARD_FIELDS[idx][1]) for idx in BODYGUARD_NON_DROPDOWN_FIELD_INDICES],
            columns=2,
        )
        field_handles = build_field_section(
            scroll_handles.fields_wrap,
            schema=field_schema,
            on_change=lambda section_index: self.on_core_field_changed(BODYGUARD_NON_DROPDOWN_FIELD_INDICES[section_index]),
            helper_text_factory=lambda byte_width: helper_text_for_sized_value(0, byte_width),
        )
        self.core_field_vars = [None] * len(BODYGUARD_FIELDS)
        self.core_field_entries = [None] * len(BODYGUARD_FIELDS)
        self.core_field_helpers = [None] * len(BODYGUARD_FIELDS)
        for actual_index, var, entry, helper in zip(BODYGUARD_NON_DROPDOWN_FIELD_INDICES, field_handles.vars, field_handles.entries, field_handles.helpers):
            self.core_field_vars[actual_index] = var
            self.core_field_entries[actual_index] = entry
            self.core_field_helpers[actual_index] = helper

        dropdown_schema = EditorDropdownSectionSchema(
            title="Bodyguard Support Skills",
            subtitle="Support Skill 1 and Support Skill 2 use readonly dropdowns so only known safe support skill ids are selected.",
            fields=[
                EditorDropdownFieldSchema(
                    label=BODYGUARD_FIELDS[idx][0],
                    options=BODYGUARD_SUPPORT_SKILL_OPTION_LABELS,
                    default_text=BODYGUARD_SUPPORT_SKILL_OPTION_LABELS[0],
                )
                for idx in BODYGUARD_SUPPORT_SKILL_FIELD_INDICES
            ],
            columns=2,
        )
        dropdown_handles = build_dropdown_section(
            scroll_handles.fields_wrap,
            schema=dropdown_schema,
            on_change=lambda section_index: self.on_core_field_changed(BODYGUARD_SUPPORT_SKILL_FIELD_INDICES[section_index]),
        )
        for actual_index, var in zip(BODYGUARD_SUPPORT_SKILL_FIELD_INDICES, dropdown_handles.vars):
            self.core_field_vars[actual_index] = var

        self.flag_vars = build_toggle_section(
            scroll_handles.fields_wrap,
            schema=EditorToggleSectionSchema(
                title="003.xl Flags 1-8",
                subtitle="Untoggled writes 00 and toggled writes 01.",
                toggle_names=BODYGUARD_FLAG_NAMES,
                columns=4,
            ),
            on_toggle=self.on_flag_changed,
        )

        build_description_section(
            scroll_handles.fields_wrap,
            title="Support Skill Descriptions",
            textvariable=self.bodyguard_desc_var,
            wraplength=500,
        )

    def set_status(self, text: str, color: str = STATUS_GOOD):
        self.status_var.set(text)
        self.status_label.config(fg=color)

    def get_bodyguard_display_name(self, bodyguard_index: int) -> str:
        return BODYGUARD_NAMES.get(bodyguard_index, f"Bodyguard Slot {bodyguard_index + 1:03d}")

    def get_bodyguard_slot_label(self, bodyguard_index: int) -> str:
        name = self.get_bodyguard_display_name(bodyguard_index)
        fallback = f"Bodyguard Slot {bodyguard_index + 1:03d}"
        return name if name == fallback else f"{name} | {bodyguard_index + 1:03d}"

    def bodyguard_main_offset(self, bodyguard_index: int) -> int:
        return BODYGUARD_OFFSET + (bodyguard_index * BODYGUARD_RECORD_SIZE)

    def read_main_record(self, bodyguard_index: int, blob: Optional[bytes] = None) -> bytes:
        source = blob if blob is not None else self.current_main_bytes
        if source is None:
            return b""
        start = self.bodyguard_main_offset(bodyguard_index)
        return bytes(source[start : start + BODYGUARD_RECORD_SIZE])

    def read_core_values(self, bodyguard_index: int, blob: Optional[bytes] = None) -> List[int]:
        record = self.read_main_record(bodyguard_index, blob)
        if len(record) < BODYGUARD_RECORD_SIZE:
            return [0] * len(BODYGUARD_FIELDS)
        values: List[int] = []
        cursor = 0
        for _field_name, byte_width in BODYGUARD_FIELDS:
            values.append(int.from_bytes(record[cursor : cursor + byte_width], "little", signed=False))
            cursor += byte_width
        return values

    def read_flag_values(self, bodyguard_index: int, blob: Optional[bytes] = None) -> List[int]:
        record = self.read_main_record(bodyguard_index, blob)
        if len(record) < BODYGUARD_RECORD_SIZE:
            return [0] * len(BODYGUARD_FLAG_NAMES)
        start = BODYGUARD_CORE_SIZE
        end = start + len(BODYGUARD_FLAG_NAMES)
        return list(record[start:end])

    def batch_fields(self) -> List[EditorBatchField]:
        return [EditorBatchField(label, byte_width) for label, byte_width in BODYGUARD_FIELDS] + [
            EditorBatchField(name, 1) for name in BODYGUARD_FLAG_NAMES
        ]

    def batch_field_offsets(self) -> List[Tuple[int, int]]:
        return linear_field_offsets(BODYGUARD_FIELDS, extra_flags=BODYGUARD_FLAG_NAMES)

    def batch_read_values(self, bodyguard_index: int) -> List[int]:
        return self.read_core_values(bodyguard_index) + self.read_flag_values(bodyguard_index)

    def format_batch_value(self, field_index: int, value: int) -> str:
        if field_index >= len(BODYGUARD_FIELDS):
            return "1" if value else "0"
        field_name, byte_width = BODYGUARD_FIELDS[field_index]
        if field_index in BODYGUARD_SUPPORT_SKILL_FIELD_INDICES:
            return format_support_skill_option(value)
        return format_field_value(field_name, byte_width, value)

    def parse_batch_value(self, field_index: int, raw: str) -> int:
        if field_index >= len(BODYGUARD_FIELDS):
            return 1 if parse_sized_int(raw, 1) else 0
        _field_name, byte_width = BODYGUARD_FIELDS[field_index]
        if field_index in BODYGUARD_SUPPORT_SKILL_FIELD_INDICES:
            try:
                return parse_support_skill_option(raw)
            except ValueError:
                return parse_sized_int(raw, byte_width)
        return parse_sized_int(raw, byte_width)

    def apply_batch_updates(self, bodyguard_indices: Sequence[int], updates: Sequence[Tuple[int, int]]) -> bool:
        if self.current_main_bytes is None:
            return False
        write_batch_record_updates(
            self.current_main_bytes,
            record_offset=self.bodyguard_main_offset,
            record_size=BODYGUARD_RECORD_SIZE,
            field_offsets=self.batch_field_offsets(),
            slots=bodyguard_indices,
            updates=updates,
        )
        self.files_dirty = bytes(self.current_main_bytes) != self.original_main_bytes
        self.bodyguard_dirty = False
        self.load_bodyguard_into_fields(self.current_bodyguard_index)
        self.sync_bodyguard_selection()
        return True

    def restore_batch_snapshot(self, snapshot: Dict[int, List[int]]) -> bool:
        if self.current_main_bytes is None:
            return False
        write_batch_record_snapshots(
            self.current_main_bytes,
            record_offset=self.bodyguard_main_offset,
            record_size=BODYGUARD_RECORD_SIZE,
            field_offsets=self.batch_field_offsets(),
            snapshots=snapshot,
        )
        self.files_dirty = bytes(self.current_main_bytes) != self.original_main_bytes
        self.bodyguard_dirty = False
        self.load_bodyguard_into_fields(self.current_bodyguard_index)
        self.sync_bodyguard_selection()
        return True

    def bodyguard_is_changed(self, bodyguard_index: int) -> bool:
        if self.current_main_bytes is None or not self.original_main_bytes:
            return False
        return self.read_main_record(bodyguard_index) != self.read_main_record(bodyguard_index, self.original_main_bytes)

    def dirty_bodyguard_count(self) -> int:
        return sum(1 for bodyguard_index in range(BODYGUARD_COUNT) if self.bodyguard_is_changed(bodyguard_index))

    def build_support_skill_descriptions(self, core_values: Optional[List[int]] = None) -> str:
        if self.current_main_bytes is None:
            return ""
        if core_values is None:
            core_values = self.read_core_values(self.current_bodyguard_index)
        skill_1 = core_values[0]
        skill_2 = core_values[1]
        return "\n".join(
            [
                f"Support Skill 1 : {support_skill_label(skill_1)} ({skill_1})",
                support_skill_description(skill_1),
                "",
                f"Support Skill 2 : {support_skill_label(skill_2)} ({skill_2})",
                support_skill_description(skill_2),
            ]
        )

    def preview_core_values(self) -> Optional[List[int]]:
        if self.current_main_bytes is None:
            return None
        preview = self.read_core_values(self.current_bodyguard_index)
        for idx, (_field_name, byte_width) in enumerate(BODYGUARD_FIELDS):
            var = self.core_field_vars[idx]
            if var is None:
                continue
            try:
                if idx in BODYGUARD_SUPPORT_SKILL_FIELD_INDICES:
                    preview[idx] = parse_support_skill_option(var.get())
                else:
                    preview[idx] = parse_sized_int(var.get(), byte_width)
            except ValueError:
                pass
        return preview

    def update_dirty_banner(self):
        if self.bodyguard_dirty and self.files_dirty:
            self.dirty_var.set("Disk state: unapplied bodyguard edits + unsaved file changes")
        elif self.bodyguard_dirty:
            self.dirty_var.set("Disk state: unapplied bodyguard edits")
        elif self.files_dirty:
            self.dirty_var.set("Disk state: unsaved file changes in memory")
        else:
            self.dirty_var.set("Disk state: clean")

    def update_meta(self):
        if self.current_main_bytes is None:
            self.bodyguard_title_var.set("No bodyguard loaded")
            self.bodyguard_meta_var.set("Load DW8XL bodyguard data to begin.")
            self.bodyguard_desc_var.set("")
            return

        bodyguard_name = self.get_bodyguard_display_name(self.current_bodyguard_index)
        slot_number = self.current_bodyguard_index + 1
        self.bodyguard_title_var.set(self.get_bodyguard_slot_label(self.current_bodyguard_index))
        self.bodyguard_meta_var.set(
            "\n".join(
                [
                    f"Bodyguard Slot : {bodyguard_name} | {slot_number:03d}",
                    f"Main Path      : {os.path.relpath(BODYGUARD_PATH, PROJECT_ROOT)}",
                    f"Export Path    : {os.path.relpath(BODYGUARD_EXPORT_PATH, PROJECT_ROOT)}",
                    f"Guard Slots    : {BODYGUARD_COUNT}",
                    f"Dirty Guards   : {self.dirty_bodyguard_count()}",
                ]
            )
        )
        self.bodyguard_desc_var.set(self.build_support_skill_descriptions())

    def update_core_field_helper(self, field_index: int):
        if field_index in BODYGUARD_SUPPORT_SKILL_FIELD_INDICES:
            return
        var = self.core_field_vars[field_index]
        entry = self.core_field_entries[field_index]
        helper = self.core_field_helpers[field_index]
        if var is None or entry is None or helper is None:
            return
        raw = var.get()
        field_name, byte_width = BODYGUARD_FIELDS[field_index]
        try:
            value = parse_sized_int(raw, byte_width)
        except ValueError:
            entry.config(bg=FIELD_INVALID)
            helper.config(text="Invalid value. Use decimal, -1, or 0x-prefixed hex.", fg=STATUS_BAD)
            return
        row = BODYGUARD_NON_DROPDOWN_SECTION_ROWS.get(field_index, 0)
        entry.config(bg=FIELD_BG if row % 2 == 0 else FIELD_ALT_BG)
        helper.config(text=helper_text_for_field(field_name, byte_width, value), fg=SELECT_MUTED)

    def load_bodyguard_into_fields(self, bodyguard_index: int):
        if self.current_main_bytes is None:
            return
        core_values = self.read_core_values(bodyguard_index)
        flag_values = self.read_flag_values(bodyguard_index)
        self._loading_fields = True
        for idx, value in enumerate(core_values):
            var = self.core_field_vars[idx]
            if var is None:
                continue
            field_name, byte_width = BODYGUARD_FIELDS[idx]
            if idx in BODYGUARD_SUPPORT_SKILL_FIELD_INDICES:
                var.set(format_support_skill_option(value))
            else:
                var.set(format_field_value(field_name, byte_width, value))
        for idx, value in enumerate(flag_values):
            self.flag_vars[idx].set(1 if value else 0)
        self._loading_fields = False
        for idx in range(len(BODYGUARD_FIELDS)):
            self.update_core_field_helper(idx)
        self.bodyguard_dirty = False
        self.update_dirty_banner()
        self.bodyguard_jump_var.set(str(bodyguard_index + 1))
        self.bodyguard_canvas.render()
        self.update_meta()

    def parse_core_field_values(self) -> Optional[List[int]]:
        values: List[int] = []
        for idx, (field_name, byte_width) in enumerate(BODYGUARD_FIELDS):
            var = self.core_field_vars[idx]
            if var is None:
                values.append(0)
                continue
            try:
                if idx in BODYGUARD_SUPPORT_SKILL_FIELD_INDICES:
                    values.append(parse_support_skill_option(var.get()))
                else:
                    values.append(parse_sized_int(var.get(), byte_width))
            except ValueError as exc:
                entry = self.core_field_entries[idx]
                if entry is not None:
                    entry.focus_set()
                    try:
                        entry.selection_range(0, "end")
                    except Exception:
                        pass
                messagebox.showerror("Invalid Field Value", f"{field_name}: {exc}")
                self.set_status(f"{field_name} could not be applied. Fix the field and try again.", STATUS_BAD)
                return None
        return values

    def apply_current_bodyguard(self, *, show_status: bool = True) -> bool:
        if self.current_main_bytes is None:
            return False
        core_values = self.parse_core_field_values()
        if core_values is None:
            return False

        main_record = bytearray(self.read_main_record(self.current_bodyguard_index))
        cursor = 0
        for value, (_field_name, byte_width) in zip(core_values, BODYGUARD_FIELDS):
            main_record[cursor : cursor + byte_width] = value.to_bytes(byte_width, "little", signed=False)
            cursor += byte_width
        flag_start = BODYGUARD_CORE_SIZE
        for idx, flag_var in enumerate(self.flag_vars):
            main_record[flag_start + idx] = 1 if flag_var.get() else 0

        main_start = self.bodyguard_main_offset(self.current_bodyguard_index)
        main_end = main_start + BODYGUARD_RECORD_SIZE
        main_changed = bytes(self.current_main_bytes[main_start:main_end]) != bytes(main_record)
        if main_changed:
            self.current_main_bytes[main_start:main_end] = main_record
        self.files_dirty = bytes(self.current_main_bytes) != self.original_main_bytes
        self.bodyguard_dirty = False
        self.update_meta()
        self.update_dirty_banner()
        self.bodyguard_canvas.render()
        if show_status:
            color = STATUS_GOOD if main_changed else STATUS_WARN
            self.set_status(f"Applied {self.bodyguards[self.current_bodyguard_index].label} to memory. Save File when you're ready.", color)
        return True

    def save_current_files(self) -> bool:
        if self.current_main_bytes is None:
            return False
        if self.bodyguard_dirty and not self.apply_current_bodyguard(show_status=False):
            return False
        had_unsaved_changes = self.files_dirty
        try:
            os.makedirs(os.path.dirname(BODYGUARD_EXPORT_PATH), exist_ok=True)
            with open(BODYGUARD_EXPORT_PATH, "wb") as handle:
                handle.write(self.current_main_bytes)
        except OSError as exc:
            messagebox.showerror("Save Failed", f"Could not export bodyguard file:\n{exc}")
            self.set_status("Could not export the bodyguard file.", STATUS_BAD)
            return False
        self.original_main_bytes = bytes(self.current_main_bytes)
        self.files_dirty = False
        self.bodyguard_dirty = False
        self.update_meta()
        self.update_dirty_banner()
        self.bodyguard_canvas.render()
        suffix = " (clean copy)" if not had_unsaved_changes else ""
        self.set_status(f"Exported {os.path.relpath(BODYGUARD_EXPORT_PATH, PROJECT_ROOT)}{suffix}.", STATUS_GOOD)
        return True

    def load_files(self) -> bool:
        if not os.path.isfile(BODYGUARD_PATH):
            messagebox.showerror("Missing Bodyguard File", f"Could not find:\n{BODYGUARD_PATH}")
            self.set_status("Missing DW8XL bodyguard file.", STATUS_BAD)
            return False
        try:
            with open(BODYGUARD_PATH, "rb") as handle:
                main_blob = handle.read()
        except OSError as exc:
            messagebox.showerror("Read Failed", f"Could not read the bodyguard file:\n{exc}")
            self.set_status("Could not read the DW8XL bodyguard file.", STATUS_BAD)
            return False

        required_main = BODYGUARD_OFFSET + (BODYGUARD_COUNT * BODYGUARD_RECORD_SIZE)
        if len(main_blob) < required_main:
            messagebox.showerror("Bodyguard File Too Small", "003.xl does not contain the full reversed bodyguard block.")
            self.set_status("DW8XL bodyguard file is too small for the reversed block.", STATUS_BAD)
            return False

        self.current_main_bytes = bytearray(main_blob)
        self.original_main_bytes = bytes(main_blob)
        self.current_bodyguard_index = 0
        self.files_dirty = False
        self.bodyguard_dirty = False
        self.update_meta()
        self.load_bodyguard_into_fields(0)
        self.sync_bodyguard_selection()
        self.set_status("Loaded 003.xl", STATUS_GOOD)
        return True

    def confirm_file_transition(self, reason: str) -> bool:
        if self.current_main_bytes is None:
            return True
        if self.bodyguard_dirty and not self.apply_current_bodyguard(show_status=False):
            return False
        if not self.files_dirty:
            return True
        choice = messagebox.askyesnocancel("Unsaved Bodyguard Changes", f"Export changes from 003.xl before {reason}?")
        if choice is None:
            return False
        return self.save_current_files() if choice else True

    def reload_files(self):
        if self.current_main_bytes is None:
            return
        if self.bodyguard_dirty or self.files_dirty:
            if not messagebox.askyesno("Reload Bodyguard File", "Reloading 003.xl will discard unapplied and unsaved changes. Continue?"):
                return
        self.load_files()

    def refresh_bodyguard_list(self):
        query = self.bodyguard_search_var.get().strip().lower()
        self.filtered_bodyguards = [
            bodyguard
            for bodyguard in self.bodyguards
            if not query
            or query in bodyguard.label.lower()
            or query in bodyguard.name.lower()
            or query in f"{bodyguard.index + 1}"
            or query in f"{bodyguard.index + 1:03d}"
        ]
        self._suppress_list_event = True
        try:
            self.bodyguard_listbox.delete(0, tk.END)
            for bodyguard in self.filtered_bodyguards:
                self.bodyguard_listbox.insert(tk.END, bodyguard.label)
        finally:
            self._suppress_list_event = False
        self.sync_bodyguard_selection()

    def sync_bodyguard_selection(self):
        self._suppress_list_event = True
        try:
            if hasattr(self, "batch_controller"):
                self.batch_controller.sync_from_editor()
                return
            self.bodyguard_listbox.selection_clear(0, tk.END)
            visible_index = next(
                (idx for idx, bodyguard in enumerate(self.filtered_bodyguards) if bodyguard.index == self.current_bodyguard_index),
                None,
            )
            if visible_index is not None:
                self.bodyguard_listbox.selection_set(visible_index)
                self.bodyguard_listbox.activate(visible_index)
                self.bodyguard_listbox.see(visible_index)
        finally:
            self._suppress_list_event = False

    def on_bodyguard_list_select(self, _event):
        if self._suppress_list_event:
            return
        selection = self.bodyguard_listbox.curselection()
        if not selection:
            return
        target = self.filtered_bodyguards[selection[0]]
        self.select_bodyguard(target.index)

    def select_bodyguard(self, bodyguard_index: int):
        if self.current_main_bytes is None or bodyguard_index < 0 or bodyguard_index >= BODYGUARD_COUNT:
            return
        if bodyguard_index == self.current_bodyguard_index:
            self.sync_bodyguard_selection()
            return
        if self.bodyguard_dirty and not self.apply_current_bodyguard(show_status=False):
            self.sync_bodyguard_selection()
            return
        self.current_bodyguard_index = bodyguard_index
        self.load_bodyguard_into_fields(bodyguard_index)
        self.sync_bodyguard_selection()
        self.bodyguard_canvas.focus_on_bodyguard(bodyguard_index)
        self.set_status(f"Selected {self.bodyguards[bodyguard_index].label}.", STATUS_GOOD)

    def change_bodyguard(self, delta: int):
        if self.current_main_bytes is None:
            return
        self.select_bodyguard(max(0, min(BODYGUARD_COUNT - 1, self.current_bodyguard_index + delta)))

    def jump_to_bodyguard(self):
        if self.current_main_bytes is None:
            return
        try:
            bodyguard_number = int(self.bodyguard_jump_var.get().strip(), 10)
        except ValueError:
            messagebox.showerror("Invalid Bodyguard Slot", "Enter a number from 1 to 903.")
            self.set_status("Bodyguard jump failed. Use a decimal number from 1 to 903.", STATUS_BAD)
            return
        if bodyguard_number < 1 or bodyguard_number > BODYGUARD_COUNT:
            messagebox.showerror("Invalid Bodyguard Slot", "Bodyguard slot number must be between 1 and 903.")
            self.set_status("Bodyguard jump failed. Bodyguard slot number must be between 1 and 903.", STATUS_BAD)
            return
        self.select_bodyguard(bodyguard_number - 1)

    def on_core_field_changed(self, field_index: int):
        self.update_core_field_helper(field_index)
        if self._loading_fields:
            return
        preview = self.preview_core_values()
        if preview is not None:
            self.bodyguard_desc_var.set(self.build_support_skill_descriptions(preview))
        self.bodyguard_dirty = True
        self.update_dirty_banner()

    def on_flag_changed(self):
        if self._loading_fields:
            return
        self.bodyguard_dirty = True
        self.update_dirty_banner()

    def on_close_request(self):
        if not self.confirm_file_transition("closing the bodyguard editor"):
            return
        self.destroy()


if __name__ == "__main__":
    raise SystemExit("Run AE/main.pyw to launch Aldnoah Engine tools.")
