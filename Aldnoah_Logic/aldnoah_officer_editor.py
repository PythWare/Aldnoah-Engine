from __future__ import annotations

import math, os
import tkinter as tk
from dataclasses import dataclass
from math import ceil
from tkinter import messagebox
from typing import Dict, List, Optional, Sequence, Tuple

from .aldnoah_editors import (
    FIELD_ALT_BG,
    FIELD_BG,
    FIELD_INVALID,
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
from .aldnoah_energy import (
    PROJECT_ROOT,
    BinaryRecordSectionSchema,
    OfficerEditorSchema,
    get_officer_editor_schema,
)
from .aldnoah_reusables import (
    EditorBatchField,
    EditorBatchSelectionController,
    EditorActionSchema,
    EditorCenterSchema,
    EditorFieldSchema,
    EditorFieldSectionSchema,
    EditorHeroSchema,
    EditorListSchema,
    EditorPanelSchema,
    EditorRightSchema,
    EditorToggleSectionSchema,
    EditorWindowSchema,
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


OFFICER_LIST_SCHEMA = EditorListSchema(
    prev_label="Prev Officer",
    next_label="Next Officer",
)


@dataclass(frozen=True)
class OfficerInfo:
    index: int
    name: str
    placeholder_prefix: str

    @property
    def ordinal(self) -> int:
        return self.index + 1

    @property
    def title(self) -> str:
        return self.name or f"{self.placeholder_prefix} {self.ordinal:03d}"

    @property
    def label(self) -> str:
        fallback = f"{self.placeholder_prefix} {self.ordinal:03d}"
        return self.title if self.title == fallback else f"{self.title} | {self.ordinal:03d}"


def load_indexed_lines(path: str) -> Tuple[str, ...]:
    if not path or not os.path.isfile(path):
        return ()
    with open(path, "r", encoding="utf-8", errors="replace") as handle:
        return tuple(line.rstrip("\r\n") for line in handle)


def officer_name_source(schema: OfficerEditorSchema) -> Tuple[str, ...]:
    if schema.officer_names:
        return schema.officer_names
    if schema.name_list_path:
        return load_indexed_lines(schema.name_list_path)[: schema.officer_count]
    return ()


def build_officer_infos(schema: OfficerEditorSchema) -> List[OfficerInfo]:
    source_names = officer_name_source(schema)
    officers: List[OfficerInfo] = []
    for index in range(schema.officer_count):
        if index < len(source_names) and source_names[index].strip():
            name = source_names[index].strip()
        else:
            name = f"{schema.placeholder_prefix} {index + 1:03d}"
        officers.append(OfficerInfo(index=index, name=name, placeholder_prefix=schema.placeholder_prefix))
    return officers


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


def field_uses_hex(section: BinaryRecordSectionSchema, field_name: str) -> bool:
    return any(field_name.startswith(prefix) for prefix in section.hex_field_prefixes)


def format_field_value(section: BinaryRecordSectionSchema, field_name: str, byte_width: int, value: int) -> str:
    if field_uses_hex(section, field_name):
        return f"0x{value:0{byte_width * 2}X}"
    signed_value = unsigned_to_signed(value, byte_width * 8)
    return str(signed_value if signed_value < 0 else value)


def build_window_schema(schema: OfficerEditorSchema) -> EditorWindowSchema:
    return EditorWindowSchema(
        window_title=f"{schema.game_id} Officer Editor",
        hero=EditorHeroSchema(
            title=f"{schema.game_id} Officer Editor",
            subtitle=f"Mod the playable officers for {schema.display_name}, then export safe file copies under the project root.",
            star_seed=schema.hero_star_seed,
            star_count=schema.hero_star_count,
        ),
        left_panel=EditorPanelSchema(
            title="Officer Lattice",
            subtitle=f"Select the {schema.game_id} playable officer you want to edit.",
            accent=SELECT_BLUE,
        ),
        center_panel=EditorPanelSchema(
            title="Officer Constellation",
            subtitle=f"Navigate the {schema.officer_count} playable officers for {schema.game_id}.",
            accent=SELECT_GOLD,
        ),
        right_panel=EditorPanelSchema(
            title="Officer Field Editor",
            subtitle=f"Edit the schema-driven officer data for {schema.game_id}.",
            accent=SELECT_GREEN,
        ),
        column_weights=(2, 3, 6),
    )


def build_center_schema(schema: OfficerEditorSchema) -> EditorCenterSchema:
    file_labels = [schema.primary_section.file_label]
    if schema.secondary_section is not None:
        file_labels.append(schema.secondary_section.file_label)
    loaded_text = " and ".join(file_labels)
    return EditorCenterSchema(
        prev_label="Prev Officer",
        next_label="Next Officer",
        apply_label="Apply Officer",
        hint_text=f"Changed officers glow green after they are applied to memory. Drag inside the constellation to pan, use the mouse wheel to zoom, and zoom further in if you want officer ids to appear above each node. Save Officer File{'s' if len(file_labels) > 1 else ''} exports full copies of {loaded_text} under the project root.",
    )


class OfficerConstellationCanvas(tk.Canvas):
    def __init__(self, parent: tk.Misc, controller: "OfficerEditorWindow"):
        super().__init__(parent, bg=SELECT_BG, highlightthickness=0, bd=0, relief="flat")
        self.controller = controller
        self.item_to_officer: Dict[int, int] = {}
        self.phase = 0.0
        self.stars = make_stars(controller.schema.constellation_star_seed, controller.schema.constellation_star_count)
        self.zoom = 1.0
        self.min_zoom = 0.55
        self.max_zoom = 3.35
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
        arms = self.controller.schema.constellation_arms
        per_arm = ceil(self.controller.schema.officer_count / arms)
        outer = max(120.0, min(width, height) * 0.42)
        positions: List[Tuple[int, float, float]] = []
        for arm in range(arms):
            angle = (-math.pi / 2.0) + (arm * ((math.pi * 2.0) / arms))
            for step in range(per_arm):
                officer_index = arm * per_arm + step
                if officer_index >= self.controller.schema.officer_count:
                    break
                t = step / max(1, per_arm - 1)
                radius = 28.0 + (t * outer)
                bend = math.sin((step * 0.58) + (arm * 0.75)) * 0.20
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
        for idx, world_x, world_y in self.officer_positions(width, height):
            if idx == officer_index:
                self.pan_x = (width * 0.50) - ((width * 0.50) + (world_x * self.zoom))
                self.pan_y = (height * 0.54) - ((height * 0.54) + (world_y * self.zoom))
                self.render()
                return

    def render(self):
        self.delete("all")
        self.item_to_officer.clear()
        width = max(1, self.winfo_width())
        height = max(1, self.winfo_height())
        draw_constellation_backdrop(self, width, height, self.stars, self.phase)
        self.create_text(18, 16, anchor="nw", text="Officer Constellation", fill=SELECT_TEXT, font=("Segoe UI", 15, "bold"))
        self.create_text(
            20,
            44,
            anchor="nw",
            text="Gold is selected, green is modded, and violet is loaded. Drag to pan, wheel to zoom, and zoom further in to reveal officer ids.",
            fill=SELECT_SUBTEXT,
            font=("Segoe UI", 9),
            width=max(200, width - 40),
        )
        positions = [(officer_index, *self.project_point(width, height, wx, wy)) for officer_index, wx, wy in self.officer_positions(width, height)]
        if self.controller.current_primary_bytes is None or (self.controller.schema.secondary_section is not None and self.controller.current_secondary_bytes is None):
            file_labels = [self.controller.schema.primary_section.file_label]
            if self.controller.schema.secondary_section is not None:
                file_labels.append(self.controller.schema.secondary_section.file_label)
            self.create_text(width * 0.5, height * 0.56, text=f"Load {' and '.join(file_labels)} to light the officer lattice.", fill=SELECT_SUBTEXT, font=("Segoe UI", 11))
            return

        arms = self.controller.schema.constellation_arms
        per_arm = ceil(self.controller.schema.officer_count / arms)
        zoom_scale = max(0.8, min(2.0, self.zoom))
        show_labels = self.zoom >= 1.6
        line_width = 1 if self.zoom < 1.5 else 2
        for arm in range(arms):
            arm_positions = positions[arm * per_arm : (arm + 1) * per_arm]
            for idx in range(len(arm_positions) - 1):
                _, ax, ay = arm_positions[idx]
                _, bx, by = arm_positions[idx + 1]
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


class OfficerEditorWindow(tk.Toplevel):
    def __init__(self, parent: tk.Misc, game_id: str):
        super().__init__(parent)
        self.game_id = game_id
        self.schema = get_officer_editor_schema(game_id)
        self.officers = build_officer_infos(self.schema)
        self.filtered_officers = list(self.officers)
        self.current_primary_bytes: Optional[bytearray] = None
        self.current_secondary_bytes: Optional[bytearray] = None
        self.original_primary_bytes = b""
        self.original_secondary_bytes = b""
        self.current_officer_index = 0
        self.files_dirty = False
        self.officer_dirty = False
        self._loading_fields = False
        self._suppress_list_event = False

        self.officer_search_var = tk.StringVar(value="")
        self.officer_title_var = tk.StringVar(value="No officer loaded")
        self.officer_meta_var = tk.StringVar(value=f"Load {self.schema.display_name} officer data to begin.")
        self.status_var = tk.StringVar(value=f"Ready to edit the {self.schema.display_name} playable officer data.")
        self.dirty_var = tk.StringVar(value="Disk state: clean")
        self.officer_jump_var = tk.StringVar(value="1")

        self.primary_field_vars: List[tk.StringVar] = []
        self.primary_field_entries: List[tk.Entry] = []
        self.primary_field_helpers: List[tk.Label] = []
        self.secondary_field_vars: List[tk.StringVar] = []
        self.secondary_field_entries: List[tk.Entry] = []
        self.secondary_field_helpers: List[tk.Label] = []
        self.flag_vars: List[tk.IntVar] = []

        self.build_gui()
        self.officer_search_var.trace_add("write", lambda *_: self.refresh_officer_list())
        self.refresh_officer_list()
        self.load_files()
        self.protocol("WM_DELETE_WINDOW", self.on_close_request)

    def build_gui(self):
        shell = build_editor_shell(self, build_window_schema(self.schema), self.status_var)
        self.status_label = shell.status_label

        list_handles = build_editor_list_panel(
            shell.left_body,
            title_var=self.officer_title_var,
            meta_var=self.officer_meta_var,
            search_var=self.officer_search_var,
            on_select=self.on_officer_list_select,
            on_clear=lambda: self.officer_search_var.set(""),
            on_prev=lambda: self.change_officer(-1),
            on_next=lambda: self.change_officer(1),
            schema=OFFICER_LIST_SCHEMA,
        )
        self.officer_listbox = list_handles.listbox
        self.batch_controller = EditorBatchSelectionController(
            self,
            listbox=self.officer_listbox,
            get_visible_ids=lambda: [officer.index for officer in self.filtered_officers],
            get_current_id=lambda: self.current_officer_index if self.current_primary_bytes is not None else None,
            select_id=self.select_officer,
            fields=self.batch_fields(),
            read_values=self.batch_read_values,
            apply_updates=self.apply_batch_updates,
            restore_values=self.restore_batch_snapshot,
            format_value=self.format_batch_value,
            parse_value=self.parse_batch_value,
            set_status=self.set_status,
            title="Officer Multi-Slot Editor",
            noun="officers",
        )

        self.officer_canvas = OfficerConstellationCanvas(shell.center_body, self)
        build_editor_center_panel(
            shell.center_body,
            canvas=self.officer_canvas,
            jump_var=self.officer_jump_var,
            jump_command=self.jump_to_officer,
            on_prev=lambda: self.change_officer(-1),
            on_next=lambda: self.change_officer(1),
            on_apply=self.apply_current_officer,
            schema=build_center_schema(self.schema),
        )

        file_word = "Files" if self.schema.secondary_section is not None else "File"
        intro_bits = [f"Edit the {self.schema.primary_section.file_label} officer fields"]
        if self.schema.primary_section.toggle_names:
            intro_bits.append(f"flip the {len(self.schema.primary_section.toggle_names)} flags")
        if self.schema.secondary_section is not None:
            intro_bits.append(f"adjust the {self.schema.secondary_section.file_label} section")
        intro_text = ", ".join(intro_bits[:-1]) + (", and " if len(intro_bits) > 2 else " and " if len(intro_bits) == 2 else "") + intro_bits[-1]
        right_schema = EditorRightSchema(
            intro_text=f"{intro_text}. Scroll to reach the lower sections.",
            actions=[
                EditorActionSchema(f"Save Officer {file_word}", self.save_current_files, SELECT_GREEN),
                EditorActionSchema(f"Reload Officer {file_word}", self.reload_files, SELECT_GOLD, fg="#180E2B"),
                EditorActionSchema("Close Editor", self.on_close_request, SELECT_BLUE),
            ],
        )
        scroll_handles = build_scrollable_editor_panel(shell.right_body, dirty_var=self.dirty_var, schema=right_schema)

        primary_handles = build_field_section(
            scroll_handles.fields_wrap,
            schema=EditorFieldSectionSchema(
                title=self.schema.primary_section.section_title,
                subtitle=self.schema.primary_section.section_subtitle,
                fields=[EditorFieldSchema(label, byte_width) for label, byte_width in self.schema.primary_section.fields],
                columns=self.schema.primary_section.columns,
            ),
            on_change=self.on_primary_field_changed,
            helper_text_factory=lambda byte_width: helper_text_for_sized_value(0, byte_width),
        )
        self.primary_field_vars = primary_handles.vars
        self.primary_field_entries = primary_handles.entries
        self.primary_field_helpers = primary_handles.helpers

        if self.schema.secondary_section is not None:
            secondary_handles = build_field_section(
                scroll_handles.fields_wrap,
                schema=EditorFieldSectionSchema(
                    title=self.schema.secondary_section.section_title,
                    subtitle=self.schema.secondary_section.section_subtitle,
                    fields=[EditorFieldSchema(label, byte_width) for label, byte_width in self.schema.secondary_section.fields],
                    columns=self.schema.secondary_section.columns,
                ),
                on_change=self.on_secondary_field_changed,
                helper_text_factory=lambda byte_width: helper_text_for_sized_value(0, byte_width),
            )
            self.secondary_field_vars = secondary_handles.vars
            self.secondary_field_entries = secondary_handles.entries
            self.secondary_field_helpers = secondary_handles.helpers

        if self.schema.primary_section.toggle_names:
            self.flag_vars = build_toggle_section(
                scroll_handles.fields_wrap,
                schema=EditorToggleSectionSchema(
                    title=self.schema.primary_section.toggle_title,
                    subtitle=self.schema.primary_section.toggle_subtitle,
                    toggle_names=self.schema.primary_section.toggle_names,
                    columns=self.schema.primary_section.toggle_columns,
                ),
                on_toggle=self.on_flag_changed,
            )

    def set_status(self, text: str, color: str = STATUS_GOOD):
        self.status_var.set(text)
        self.status_label.config(fg=color)

    def file_labels(self) -> List[str]:
        labels = [self.schema.primary_section.file_label]
        if self.schema.secondary_section is not None:
            labels.append(self.schema.secondary_section.file_label)
        return labels

    def officer_primary_offset(self, officer_index: int) -> int:
        return self.schema.primary_section.offset + (officer_index * self.schema.primary_section.record_size)

    def officer_secondary_offset(self, officer_index: int) -> int:
        secondary = self.schema.secondary_section
        if secondary is None:
            return 0
        return secondary.offset + (officer_index * secondary.record_size)

    def read_primary_record(self, officer_index: int, blob: Optional[bytes] = None) -> bytes:
        source = blob if blob is not None else self.current_primary_bytes
        if source is None:
            return b""
        start = self.officer_primary_offset(officer_index)
        return bytes(source[start : start + self.schema.primary_section.record_size])

    def read_secondary_record(self, officer_index: int, blob: Optional[bytes] = None) -> bytes:
        secondary = self.schema.secondary_section
        source = blob if blob is not None else self.current_secondary_bytes
        if secondary is None or source is None:
            return b""
        start = self.officer_secondary_offset(officer_index)
        return bytes(source[start : start + secondary.record_size])

    def read_section_values(self, officer_index: int, section: BinaryRecordSectionSchema, record: bytes) -> List[int]:
        if len(record) < section.record_size:
            return [0] * len(section.fields)
        values: List[int] = []
        cursor = 0
        for _field_name, byte_width in section.fields:
            values.append(int.from_bytes(record[cursor : cursor + byte_width], "little", signed=False))
            cursor += byte_width
        return values

    def read_primary_values(self, officer_index: int, blob: Optional[bytes] = None) -> List[int]:
        return self.read_section_values(officer_index, self.schema.primary_section, self.read_primary_record(officer_index, blob))

    def read_secondary_values(self, officer_index: int, blob: Optional[bytes] = None) -> List[int]:
        secondary = self.schema.secondary_section
        if secondary is None:
            return []
        return self.read_section_values(officer_index, secondary, self.read_secondary_record(officer_index, blob))

    def read_flag_values(self, officer_index: int, blob: Optional[bytes] = None) -> List[int]:
        if not self.schema.primary_section.toggle_names:
            return []
        record = self.read_primary_record(officer_index, blob)
        if len(record) < self.schema.primary_section.record_size:
            return [0] * len(self.schema.primary_section.toggle_names)
        start = sum(byte_width for _label, byte_width in self.schema.primary_section.fields)
        end = start + len(self.schema.primary_section.toggle_names)
        return list(record[start:end])

    def batch_fields(self) -> List[EditorBatchField]:
        fields = [EditorBatchField(f"Primary | {label}", byte_width) for label, byte_width in self.schema.primary_section.fields]
        fields.extend(EditorBatchField(f"Flag | {name}", 1) for name in self.schema.primary_section.toggle_names)
        if self.schema.secondary_section is not None:
            fields.extend(EditorBatchField(f"Secondary | {label}", byte_width) for label, byte_width in self.schema.secondary_section.fields)
        return fields

    def batch_read_values(self, officer_index: int) -> List[int]:
        return self.read_primary_values(officer_index) + self.read_flag_values(officer_index) + self.read_secondary_values(officer_index)

    def format_batch_value(self, field_index: int, value: int) -> str:
        primary_count = len(self.schema.primary_section.fields)
        flag_count = len(self.schema.primary_section.toggle_names)
        if field_index < primary_count:
            field_name, byte_width = self.schema.primary_section.fields[field_index]
            return format_field_value(self.schema.primary_section, field_name, byte_width, value)
        if field_index < primary_count + flag_count:
            return "1" if value else "0"
        secondary = self.schema.secondary_section
        if secondary is None:
            return str(value)
        secondary_index = field_index - primary_count - flag_count
        field_name, byte_width = secondary.fields[secondary_index]
        return format_field_value(secondary, field_name, byte_width, value)

    def parse_batch_value(self, field_index: int, raw: str) -> int:
        primary_count = len(self.schema.primary_section.fields)
        flag_count = len(self.schema.primary_section.toggle_names)
        if field_index < primary_count:
            _field_name, byte_width = self.schema.primary_section.fields[field_index]
            return parse_sized_int(raw, byte_width)
        if field_index < primary_count + flag_count:
            return 1 if parse_sized_int(raw, 1) else 0
        secondary = self.schema.secondary_section
        if secondary is None:
            return 0
        secondary_index = field_index - primary_count - flag_count
        _field_name, byte_width = secondary.fields[secondary_index]
        return parse_sized_int(raw, byte_width)

    def apply_batch_updates(self, officer_indices: Sequence[int], updates: Sequence[Tuple[int, int]]) -> bool:
        if self.current_primary_bytes is None or (self.schema.secondary_section is not None and self.current_secondary_bytes is None):
            return False
        primary_count = len(self.schema.primary_section.fields)
        flag_count = len(self.schema.primary_section.toggle_names)
        primary_updates = [(idx, value) for idx, value in updates if idx < primary_count + flag_count]
        secondary_updates = [(idx - primary_count - flag_count, value) for idx, value in updates if idx >= primary_count + flag_count]
        if primary_updates:
            write_batch_record_updates(
                self.current_primary_bytes,
                record_offset=self.officer_primary_offset,
                record_size=self.schema.primary_section.record_size,
                field_offsets=linear_field_offsets(self.schema.primary_section.fields, extra_flags=self.schema.primary_section.toggle_names),
                slots=officer_indices,
                updates=primary_updates,
            )
        if secondary_updates and self.schema.secondary_section is not None and self.current_secondary_bytes is not None:
            write_batch_record_updates(
                self.current_secondary_bytes,
                record_offset=self.officer_secondary_offset,
                record_size=self.schema.secondary_section.record_size,
                field_offsets=linear_field_offsets(self.schema.secondary_section.fields),
                slots=officer_indices,
                updates=secondary_updates,
            )
        self.files_dirty = bytes(self.current_primary_bytes) != self.original_primary_bytes or (
            self.current_secondary_bytes is not None and bytes(self.current_secondary_bytes) != self.original_secondary_bytes
        )
        self.officer_dirty = False
        self.load_officer_into_fields(self.current_officer_index)
        self.sync_officer_selection()
        return True

    def restore_batch_snapshot(self, snapshot: Dict[int, List[int]]) -> bool:
        if self.current_primary_bytes is None or (self.schema.secondary_section is not None and self.current_secondary_bytes is None):
            return False
        primary_count = len(self.schema.primary_section.fields)
        flag_count = len(self.schema.primary_section.toggle_names)
        primary_values = {slot: values[: primary_count + flag_count] for slot, values in snapshot.items()}
        write_batch_record_snapshots(
            self.current_primary_bytes,
            record_offset=self.officer_primary_offset,
            record_size=self.schema.primary_section.record_size,
            field_offsets=linear_field_offsets(self.schema.primary_section.fields, extra_flags=self.schema.primary_section.toggle_names),
            snapshots=primary_values,
        )
        if self.schema.secondary_section is not None and self.current_secondary_bytes is not None:
            secondary_values = {
                slot: values[primary_count + flag_count :]
                for slot, values in snapshot.items()
            }
            write_batch_record_snapshots(
                self.current_secondary_bytes,
                record_offset=self.officer_secondary_offset,
                record_size=self.schema.secondary_section.record_size,
                field_offsets=linear_field_offsets(self.schema.secondary_section.fields),
                snapshots=secondary_values,
            )
        self.files_dirty = bytes(self.current_primary_bytes) != self.original_primary_bytes or (
            self.current_secondary_bytes is not None and bytes(self.current_secondary_bytes) != self.original_secondary_bytes
        )
        self.officer_dirty = False
        self.load_officer_into_fields(self.current_officer_index)
        self.sync_officer_selection()
        return True

    def officer_is_changed(self, officer_index: int) -> bool:
        if self.current_primary_bytes is None or not self.original_primary_bytes:
            return False
        primary_changed = self.read_primary_record(officer_index) != self.read_primary_record(officer_index, self.original_primary_bytes)
        if self.schema.secondary_section is None:
            return primary_changed
        if self.current_secondary_bytes is None or not self.original_secondary_bytes:
            return primary_changed
        secondary_changed = self.read_secondary_record(officer_index) != self.read_secondary_record(officer_index, self.original_secondary_bytes)
        return primary_changed or secondary_changed

    def dirty_officer_count(self) -> int:
        return sum(1 for officer_index in range(self.schema.officer_count) if self.officer_is_changed(officer_index))

    def update_dirty_banner(self):
        if self.officer_dirty and self.files_dirty:
            self.dirty_var.set("Disk state: unapplied officer edits + unsaved file changes")
        elif self.officer_dirty:
            self.dirty_var.set("Disk state: unapplied officer edits")
        elif self.files_dirty:
            self.dirty_var.set("Disk state: unsaved file changes in memory")
        else:
            self.dirty_var.set("Disk state: clean")

    def update_meta(self):
        if self.current_primary_bytes is None or (self.schema.secondary_section is not None and self.current_secondary_bytes is None):
            self.officer_title_var.set("No officer loaded")
            self.officer_meta_var.set(f"Load {self.schema.display_name} officer data to begin.")
            return
        current_officer = self.officers[self.current_officer_index]
        lines = [
            f"Officer        : {current_officer.label}",
            f"{self.schema.primary_section.file_label} Path   : {os.path.relpath(self.schema.primary_section.file_path, PROJECT_ROOT)}",
            f"Export {self.schema.primary_section.file_label} : {os.path.relpath(self.schema.primary_section.export_path, PROJECT_ROOT)}",
        ]
        if self.schema.secondary_section is not None:
            lines.extend(
                [
                    f"{self.schema.secondary_section.file_label} Path   : {os.path.relpath(self.schema.secondary_section.file_path, PROJECT_ROOT)}",
                    f"Export {self.schema.secondary_section.file_label} : {os.path.relpath(self.schema.secondary_section.export_path, PROJECT_ROOT)}",
                ]
            )
        lines.extend(
            [
                f"Officer Count  : {self.schema.officer_count}",
                f"Dirty Officers : {self.dirty_officer_count()}",
            ]
        )
        self.officer_title_var.set(current_officer.title)
        self.officer_meta_var.set("\n".join(lines))

    def update_section_field_helper(
        self,
        field_index: int,
        section: BinaryRecordSectionSchema,
        vars_: List[tk.StringVar],
        entries: List[tk.Entry],
        helpers: List[tk.Label],
    ):
        raw = vars_[field_index].get()
        entry = entries[field_index]
        helper = helpers[field_index]
        field_name, byte_width = section.fields[field_index]
        try:
            value = parse_sized_int(raw, byte_width)
        except ValueError:
            entry.config(bg=FIELD_INVALID)
            helper.config(text="Invalid value. Use decimal, -1, or 0x-prefixed hex.", fg=STATUS_BAD)
            return
        row = field_index // section.columns
        entry.config(bg=FIELD_BG if row % 2 == 0 else FIELD_ALT_BG)
        helper.config(text=helper_text_for_sized_value(value, byte_width), fg=SELECT_MUTED)

    def load_officer_into_fields(self, officer_index: int):
        if self.current_primary_bytes is None or (self.schema.secondary_section is not None and self.current_secondary_bytes is None):
            return
        primary_values = self.read_primary_values(officer_index)
        flag_values = self.read_flag_values(officer_index)
        secondary_values = self.read_secondary_values(officer_index)
        self._loading_fields = True
        for idx, value in enumerate(primary_values):
            field_name, byte_width = self.schema.primary_section.fields[idx]
            self.primary_field_vars[idx].set(format_field_value(self.schema.primary_section, field_name, byte_width, value))
        for idx, value in enumerate(flag_values):
            self.flag_vars[idx].set(1 if value else 0)
        if self.schema.secondary_section is not None:
            for idx, value in enumerate(secondary_values):
                field_name, byte_width = self.schema.secondary_section.fields[idx]
                self.secondary_field_vars[idx].set(format_field_value(self.schema.secondary_section, field_name, byte_width, value))
        self._loading_fields = False
        for idx in range(len(self.schema.primary_section.fields)):
            self.update_section_field_helper(idx, self.schema.primary_section, self.primary_field_vars, self.primary_field_entries, self.primary_field_helpers)
        if self.schema.secondary_section is not None:
            for idx in range(len(self.schema.secondary_section.fields)):
                self.update_section_field_helper(idx, self.schema.secondary_section, self.secondary_field_vars, self.secondary_field_entries, self.secondary_field_helpers)
        self.officer_dirty = False
        self.update_dirty_banner()
        self.officer_jump_var.set(str(officer_index + 1))
        self.officer_canvas.render()
        self.update_meta()

    def parse_section_field_values(
        self,
        section: BinaryRecordSectionSchema,
        vars_: List[tk.StringVar],
        entries: List[tk.Entry],
        dialog_title: str,
    ) -> Optional[List[int]]:
        values: List[int] = []
        for idx, (field_name, byte_width) in enumerate(section.fields):
            try:
                values.append(parse_sized_int(vars_[idx].get(), byte_width))
            except ValueError as exc:
                entries[idx].focus_set()
                try:
                    entries[idx].selection_range(0, "end")
                except Exception:
                    pass
                messagebox.showerror(dialog_title, f"{field_name}: {exc}")
                self.set_status(f"{field_name} could not be applied. Fix the field and try again.", STATUS_BAD)
                return None
        return values

    def apply_current_officer(self, *, show_status: bool = True) -> bool:
        if self.current_primary_bytes is None or (self.schema.secondary_section is not None and self.current_secondary_bytes is None):
            return False
        primary_values = self.parse_section_field_values(self.schema.primary_section, self.primary_field_vars, self.primary_field_entries, "Invalid Field Value")
        if primary_values is None:
            return False
        secondary_values: List[int] = []
        if self.schema.secondary_section is not None:
            secondary_values = self.parse_section_field_values(self.schema.secondary_section, self.secondary_field_vars, self.secondary_field_entries, "Invalid Secondary Field Value")
            if secondary_values is None:
                return False

        primary_record = bytearray(self.schema.primary_section.record_size)
        cursor = 0
        for value, (_field_name, byte_width) in zip(primary_values, self.schema.primary_section.fields):
            primary_record[cursor : cursor + byte_width] = value.to_bytes(byte_width, "little", signed=False)
            cursor += byte_width
        for idx, flag_var in enumerate(self.flag_vars):
            primary_record[cursor + idx] = 1 if flag_var.get() else 0

        primary_start = self.officer_primary_offset(self.current_officer_index)
        primary_end = primary_start + self.schema.primary_section.record_size
        primary_changed = bytes(self.current_primary_bytes[primary_start:primary_end]) != bytes(primary_record)
        if primary_changed:
            self.current_primary_bytes[primary_start:primary_end] = primary_record

        secondary_changed = False
        if self.schema.secondary_section is not None and self.current_secondary_bytes is not None:
            secondary_record = bytearray(self.schema.secondary_section.record_size)
            cursor = 0
            for value, (_field_name, byte_width) in zip(secondary_values, self.schema.secondary_section.fields):
                secondary_record[cursor : cursor + byte_width] = value.to_bytes(byte_width, "little", signed=False)
                cursor += byte_width
            secondary_start = self.officer_secondary_offset(self.current_officer_index)
            secondary_end = secondary_start + self.schema.secondary_section.record_size
            secondary_changed = bytes(self.current_secondary_bytes[secondary_start:secondary_end]) != bytes(secondary_record)
            if secondary_changed:
                self.current_secondary_bytes[secondary_start:secondary_end] = secondary_record

        self.files_dirty = bytes(self.current_primary_bytes) != self.original_primary_bytes or (
            self.schema.secondary_section is not None and self.current_secondary_bytes is not None and bytes(self.current_secondary_bytes) != self.original_secondary_bytes
        )
        self.officer_dirty = False
        self.update_meta()
        self.update_dirty_banner()
        self.officer_canvas.render()
        if show_status:
            color = STATUS_GOOD if (primary_changed or secondary_changed) else STATUS_WARN
            self.set_status(f"Applied {self.officers[self.current_officer_index].title} to memory. Save Officer File{'s' if self.schema.secondary_section is not None else ''} when you're ready.", color)
        return True

    def save_current_files(self) -> bool:
        if self.current_primary_bytes is None or (self.schema.secondary_section is not None and self.current_secondary_bytes is None):
            return False
        if self.officer_dirty and not self.apply_current_officer(show_status=False):
            return False
        had_unsaved_changes = self.files_dirty
        try:
            os.makedirs(self.schema.primary_section.export_dir, exist_ok=True)
            with open(self.schema.primary_section.export_path, "wb") as handle:
                handle.write(self.current_primary_bytes)
            if self.schema.secondary_section is not None and self.current_secondary_bytes is not None:
                os.makedirs(self.schema.secondary_section.export_dir, exist_ok=True)
                with open(self.schema.secondary_section.export_path, "wb") as handle:
                    handle.write(self.current_secondary_bytes)
        except OSError as exc:
            messagebox.showerror("Save Failed", f"Could not export officer file data:\n{exc}")
            self.set_status("Could not export the officer files.", STATUS_BAD)
            return False
        self.original_primary_bytes = bytes(self.current_primary_bytes)
        if self.current_secondary_bytes is not None:
            self.original_secondary_bytes = bytes(self.current_secondary_bytes)
        self.files_dirty = False
        self.officer_dirty = False
        self.update_meta()
        self.update_dirty_banner()
        self.officer_canvas.render()
        exported = [os.path.relpath(self.schema.primary_section.export_path, PROJECT_ROOT)]
        if self.schema.secondary_section is not None:
            exported.append(os.path.relpath(self.schema.secondary_section.export_path, PROJECT_ROOT))
        suffix = " (clean copies)" if not had_unsaved_changes else ""
        self.set_status(f"Exported {' and '.join(exported)}{suffix}.", STATUS_GOOD)
        return True

    def load_files(self) -> bool:
        paths = [self.schema.primary_section.file_path]
        if self.schema.secondary_section is not None:
            paths.append(self.schema.secondary_section.file_path)
        missing_paths = [path for path in paths if not os.path.isfile(path)]
        if missing_paths:
            messagebox.showerror("Missing Officer Files", "Could not find:\n" + "\n".join(missing_paths))
            self.set_status(f"Missing {self.schema.game_id} officer files.", STATUS_BAD)
            return False
        try:
            with open(self.schema.primary_section.file_path, "rb") as handle:
                primary_blob = handle.read()
            secondary_blob = b""
            if self.schema.secondary_section is not None:
                with open(self.schema.secondary_section.file_path, "rb") as handle:
                    secondary_blob = handle.read()
        except OSError as exc:
            messagebox.showerror("Read Failed", f"Could not read the officer files:\n{exc}")
            self.set_status(f"Could not read the {self.schema.game_id} officer files.", STATUS_BAD)
            return False

        required_primary = self.schema.primary_section.offset + (self.schema.officer_count * self.schema.primary_section.record_size)
        if len(primary_blob) < required_primary:
            messagebox.showerror("Officer File Too Small", f"{self.schema.primary_section.file_label} does not contain the full reversed officer block.")
            self.set_status(f"{self.schema.game_id} officer primary file is too small for the reversed block.", STATUS_BAD)
            return False
        if self.schema.secondary_section is not None:
            required_secondary = self.schema.secondary_section.offset + (self.schema.officer_count * self.schema.secondary_section.record_size)
            if len(secondary_blob) < required_secondary:
                messagebox.showerror("Officer File Too Small", f"{self.schema.secondary_section.file_label} does not contain the full reversed officer block.")
                self.set_status(f"{self.schema.game_id} officer secondary file is too small for the reversed block.", STATUS_BAD)
                return False

        self.current_primary_bytes = bytearray(primary_blob)
        self.original_primary_bytes = bytes(primary_blob)
        if self.schema.secondary_section is not None:
            self.current_secondary_bytes = bytearray(secondary_blob)
            self.original_secondary_bytes = bytes(secondary_blob)
        else:
            self.current_secondary_bytes = None
            self.original_secondary_bytes = b""
        self.current_officer_index = 0
        self.files_dirty = False
        self.officer_dirty = False
        self.update_meta()
        self.load_officer_into_fields(0)
        self.sync_officer_selection()
        self.set_status(f"Loaded {' and '.join(self.file_labels())}.", STATUS_GOOD)
        return True

    def confirm_file_transition(self, reason: str) -> bool:
        if self.current_primary_bytes is None or (self.schema.secondary_section is not None and self.current_secondary_bytes is None):
            return True
        if self.officer_dirty and not self.apply_current_officer(show_status=False):
            return False
        if not self.files_dirty:
            return True
        choice = messagebox.askyesnocancel("Unsaved Officer Changes", f"Export changes from {' and '.join(self.file_labels())} before {reason}?")
        if choice is None:
            return False
        return self.save_current_files() if choice else True

    def reload_files(self):
        if self.current_primary_bytes is None or (self.schema.secondary_section is not None and self.current_secondary_bytes is None):
            return
        if self.officer_dirty or self.files_dirty:
            if not messagebox.askyesno("Reload Officer Files", f"Reloading {' and '.join(self.file_labels())} will discard unapplied and unsaved changes. Continue?"):
                return
        self.load_files()

    def refresh_officer_list(self):
        query = self.officer_search_var.get().strip().lower()
        self.filtered_officers = [
            officer
            for officer in self.officers
            if not query
            or query in officer.label.lower()
            or query in officer.title.lower()
            or query in f"{officer.ordinal}"
            or query in f"{officer.ordinal:03d}"
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
            visible_index = next((idx for idx, officer in enumerate(self.filtered_officers) if officer.index == self.current_officer_index), None)
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
        if self.current_primary_bytes is None or officer_index < 0 or officer_index >= self.schema.officer_count:
            return
        if self.schema.secondary_section is not None and self.current_secondary_bytes is None:
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
        if self.current_primary_bytes is None:
            return
        self.select_officer(max(0, min(self.schema.officer_count - 1, self.current_officer_index + delta)))

    def jump_to_officer(self):
        if self.current_primary_bytes is None:
            return
        raw = self.officer_jump_var.get().strip()
        if not raw.isdigit():
            self.set_status(f"Officer jump failed. Enter a slot number between 1 and {self.schema.officer_count}.", STATUS_BAD)
            return
        officer_number = int(raw)
        if not (1 <= officer_number <= self.schema.officer_count):
            self.set_status(f"Officer jump failed. Officer slot number must be between 1 and {self.schema.officer_count}.", STATUS_BAD)
            return
        self.select_officer(officer_number - 1)

    def on_primary_field_changed(self, field_index: int):
        self.update_section_field_helper(field_index, self.schema.primary_section, self.primary_field_vars, self.primary_field_entries, self.primary_field_helpers)
        if self._loading_fields:
            return
        self.officer_dirty = True
        self.update_dirty_banner()

    def on_secondary_field_changed(self, field_index: int):
        secondary = self.schema.secondary_section
        if secondary is None:
            return
        self.update_section_field_helper(field_index, secondary, self.secondary_field_vars, self.secondary_field_entries, self.secondary_field_helpers)
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
        if not self.confirm_file_transition("closing the officer editor"):
            return
        self.destroy()


class DW8XLOfficerEditorWindow(OfficerEditorWindow):
    def __init__(self, parent: tk.Misc):
        super().__init__(parent, "DW8XL")


class WO3OfficerEditorWindow(OfficerEditorWindow):
    def __init__(self, parent: tk.Misc):
        super().__init__(parent, "WO3")
