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
from .aldnoah_energy import PROJECT_ROOT, BinaryRecordSectionSchema, WeaponEditorSchema, get_weapon_editor_schema
from .aldnoah_infos import DW8XL_ELEMENT_DESC, DW8XL_ELEMENT_NAMES
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

__all__ = ["WeaponEditorWindow", "DW8XLWeaponEditorWindow", "WO3WeaponEditorWindow"]

WEAPON_LIST_SCHEMA = EditorListSchema(prev_label="Prev Weapon", next_label="Next Weapon")


@dataclass(frozen=True)
class WeaponInfo:
    index: int
    name: str
    placeholder_prefix: str

    @property
    def ordinal(self) -> int:
        return self.index + 1

    @property
    def title(self) -> str:
        return self.name or f"{self.placeholder_prefix} {self.ordinal:04d}"

    @property
    def label(self) -> str:
        fallback = f"{self.placeholder_prefix} {self.ordinal:04d}"
        return self.title if self.title == fallback else f"{self.title} | {self.ordinal:04d}"


def build_weapon_infos(schema: WeaponEditorSchema) -> List[WeaponInfo]:
    weapons: List[WeaponInfo] = []
    for index in range(schema.weapon_count):
        if index < len(schema.weapon_names) and schema.weapon_names[index].strip():
            name = schema.weapon_names[index].strip()
        else:
            name = f"{schema.placeholder_prefix} {index + 1:04d}"
        weapons.append(WeaponInfo(index=index, name=name, placeholder_prefix=schema.placeholder_prefix))
    return weapons


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


def element_label(element_id: int) -> str:
    return DW8XL_ELEMENT_NAMES.get(element_id, f"Element ID {element_id}")


def element_description(element_id: int) -> str:
    return DW8XL_ELEMENT_DESC.get(element_id, "No known element description for this id yet.")


def format_element_option(value: int) -> str:
    if value in DW8XL_ELEMENT_NAMES:
        return f"{DW8XL_ELEMENT_NAMES[value]}: {value}"
    return f"Element ID {value}: {value}"


def parse_element_option(text: str) -> int:
    raw = (text or "").strip()
    if ":" in raw:
        suffix = raw.rsplit(":", 1)[1].strip()
        if suffix.lstrip("+-").isdigit():
            return int(suffix, 10)
    raise ValueError("Select an element from the dropdown list.")


def build_window_schema(schema: WeaponEditorSchema) -> EditorWindowSchema:
    return EditorWindowSchema(
        window_title=f"{schema.game_id} Weapon Editor",
        hero=EditorHeroSchema(
            title=f"{schema.game_id} Weapon Editor",
            subtitle=f"Mod the weapon data for {schema.display_name}, then export a safe file copy under the project root.",
            star_seed=schema.hero_star_seed,
            star_count=schema.hero_star_count,
        ),
        left_panel=EditorPanelSchema("Weapon Lattice", f"Select the {schema.game_id} weapon slot you want to edit.", SELECT_BLUE),
        center_panel=EditorPanelSchema("Weapon Constellation", f"Navigate the {schema.weapon_count} weapon slots for {schema.game_id}.", SELECT_GOLD),
        right_panel=EditorPanelSchema("Weapon Field Editor", f"Edit the schema-driven weapon data for {schema.game_id}.", SELECT_GREEN),
        column_weights=(2, 3, 6),
    )


def build_center_schema(schema: WeaponEditorSchema) -> EditorCenterSchema:
    hint = f"Changed weapon slots glow green after they are applied to memory. Drag inside the constellation to pan, use the mouse wheel to zoom, and zoom further in if you want weapon slot ids to appear above each node. Save File exports a full copy of {schema.section.file_label} under the project root."
    return EditorCenterSchema(prev_label="Prev Weapon", next_label="Next Weapon", apply_label="Apply Weapon", hint_text=hint)


class WeaponConstellationCanvas(tk.Canvas):
    def __init__(self, parent: tk.Misc, controller: "WeaponEditorWindow"):
        super().__init__(parent, bg=SELECT_BG, highlightthickness=0, bd=0, relief="flat")
        self.controller = controller
        self.item_to_weapon: Dict[int, int] = {}
        self.phase = 0.0
        self.stars = make_stars(controller.schema.constellation_star_seed, controller.schema.constellation_star_count)
        self.zoom = 1.0
        self.min_zoom = 0.35
        self.max_zoom = 4.5
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
        self.after(200, self.tick)

    def tick(self):
        self.phase += 0.08
        if self.winfo_exists():
            self.render()
            self.after(200, self.tick)

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
        hit = self.find_overlapping(event.x - 8, event.y - 8, event.x + 8, event.y + 8)
        for item_id in reversed(hit):
            weapon_index = self.item_to_weapon.get(item_id)
            if weapon_index is not None:
                self.controller.select_weapon(weapon_index)
                return

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

    def weapon_positions(self, width: int, height: int) -> List[Tuple[int, float, float]]:
        arms = self.controller.schema.constellation_arms
        per_arm = ceil(self.controller.schema.weapon_count / arms)
        scale_factor = math.sqrt(self.controller.schema.weapon_count / 100)
        outer = max(200.0, min(width, height) * 0.46 * scale_factor)
        step_spacing = 1.25 if self.controller.schema.weapon_count >= 1800 else 1.15
        positions: List[Tuple[int, float, float]] = []
        for arm in range(arms):
            angle = (-math.pi / 2.0) + (arm * ((math.pi * 2.0) / arms))
            for step in range(per_arm):
                weapon_index = arm * per_arm + step
                if weapon_index >= self.controller.schema.weapon_count:
                    break
                t = step / max(1, per_arm - 1)
                radius = 40.0 + (t * outer * step_spacing)
                bend = math.sin((step * 0.34) + (arm * 0.52)) * 0.14
                px = math.cos(angle + bend) * radius
                py = math.sin(angle + bend) * radius * 0.80
                positions.append((weapon_index, px, py))
        return positions

    def project_point(self, width: int, height: int, world_x: float, world_y: float) -> Tuple[float, float]:
        center_x = (width * 0.50) + self.pan_x
        center_y = (height * 0.54) + self.pan_y
        return center_x + (world_x * self.zoom), center_y + (world_y * self.zoom)

    def focus_on_weapon(self, weapon_index: int):
        width = max(1, self.winfo_width())
        height = max(1, self.winfo_height())
        for idx, wx, wy in self.weapon_positions(width, height):
            if idx == weapon_index:
                self.pan_x = (width * 0.50) - ((width * 0.50) + (wx * self.zoom))
                self.pan_y = (height * 0.54) - ((height * 0.54) + (wy * self.zoom))
                self.render()
                return

    def render(self):
        self.delete("all")
        self.item_to_weapon.clear()
        width = max(1, self.winfo_width())
        height = max(1, self.winfo_height())
        draw_constellation_backdrop(self, width, height, self.stars, self.phase)
        self.create_text(18, 16, anchor="nw", text="Weapon Constellation", fill=SELECT_TEXT, font=("Segoe UI", 15, "bold"))
        self.create_text(
            20,
            44,
            anchor="nw",
            text="Gold is selected, green is modded, and violet is loaded. Drag to pan, wheel to zoom, and zoom further in to reveal weapon slot ids.",
            fill=SELECT_SUBTEXT,
            font=("Segoe UI", 9),
            width=max(200, width - 40),
        )
        positions = [(weapon_index, *self.project_point(width, height, wx, wy)) for weapon_index, wx, wy in self.weapon_positions(width, height)]
        if self.controller.current_bytes is None:
            self.create_text(width * 0.5, height * 0.56, text=f"Load {self.controller.schema.section.file_label} to light the weapon lattice.", fill=SELECT_SUBTEXT, font=("Segoe UI", 11))
            return

        per_arm = ceil(self.controller.schema.weapon_count / self.controller.schema.constellation_arms)
        zoom_scale = max(0.65, min(2.4, self.zoom))
        show_labels = self.zoom >= 2.6
        line_width = 1 if self.zoom < 1.7 else 2
        for arm in range(self.controller.schema.constellation_arms):
            start = arm * per_arm
            end = min(start + per_arm, len(positions))
            arm_positions = positions[start:end]
            for idx in range(len(arm_positions) - 1):
                _, ax, ay = arm_positions[idx]
                _, bx, by = arm_positions[idx + 1]
                self.create_line(ax, ay, bx, by, fill=SELECT_LINE, width=line_width)

        for weapon_index, px, py in positions:
            selected = self.controller.current_weapon_index == weapon_index
            changed = self.controller.weapon_is_changed(weapon_index)
            if selected:
                fill = SELECT_NODE_SEL
                outline = SELECT_GOLD
                radius = max(6, min(14, int(8 * zoom_scale)))
                pulse = max(12, min(24, (15 + math.sin(self.phase * 2.0 + (weapon_index * 0.05)) * 2) * zoom_scale))
                halo = self.create_oval(px - pulse, py - pulse, px + pulse, py + pulse, outline=outline, width=1, stipple="gray25")
                self.item_to_weapon[halo] = weapon_index
            elif changed:
                fill = SELECT_GREEN
                outline = "#A8E3B9"
                radius = max(4, min(11, int(6 * zoom_scale)))
            else:
                fill = SELECT_NODE
                outline = SELECT_NODE_RING
                radius = max(3, min(9, int(5 * zoom_scale)))
            orb = self.create_oval(px - radius, py - radius, px + radius, py + radius, fill=fill, outline=outline, width=2 if selected else 1)
            self.item_to_weapon[orb] = weapon_index
            if show_labels:
                label_fill = SELECT_TEXT if selected else SELECT_SUBTEXT
                label_size = max(7, min(10, int(7 * zoom_scale)))
                label = self.create_text(px, py - max(11, int(11 * zoom_scale)), text=str(weapon_index + 1), fill=label_fill, font=("Segoe UI", label_size, "bold"))
                self.item_to_weapon[label] = weapon_index


class WeaponEditorWindow(tk.Toplevel):
    def __init__(self, parent: tk.Misc, game_id: str):
        super().__init__(parent)
        self.schema = get_weapon_editor_schema(game_id)
        self.weapons = build_weapon_infos(self.schema)
        self.filtered_weapons = list(self.weapons)
        self.current_bytes: Optional[bytearray] = None
        self.original_bytes = b""
        self.current_weapon_index = 0
        self.files_dirty = False
        self.weapon_dirty = False
        self._loading_fields = False
        self._suppress_list_event = False
        self.field_index = {field_name: idx for idx, (field_name, _byte_width) in enumerate(self.schema.section.fields)}
        self.element_field_indices = [
            idx
            for idx, (field_name, _byte_width) in enumerate(self.schema.section.fields)
            if field_name.startswith("Element ") and not field_name.endswith("Level")
        ]
        self.show_description_panel = bool(self.element_field_indices)
        self.numeric_field_indices = [idx for idx in range(len(self.schema.section.fields)) if idx not in self.element_field_indices]
        self.core_size = sum(byte_width for _field_name, byte_width in self.schema.section.fields)
        self.toggle_offset = self.schema.section.toggle_offset if self.schema.section.toggle_offset is not None else self.core_size

        self.status_var = tk.StringVar(value=f"Ready to edit the {self.schema.display_name} weapon data.")
        self.dirty_var = tk.StringVar(value="Disk state: clean")
        self.weapon_search_var = tk.StringVar(value="")
        self.weapon_jump_var = tk.StringVar(value="1")
        self.weapon_title_var = tk.StringVar(value="No weapon loaded")
        self.weapon_meta_var = tk.StringVar(value=f"Load {self.schema.display_name} weapon data to begin.")
        self.weapon_desc_var = tk.StringVar(value="")

        self.core_field_vars: List[Optional[tk.StringVar]] = [None] * len(self.schema.section.fields)
        self.core_field_entries: List[Optional[tk.Entry]] = [None] * len(self.schema.section.fields)
        self.core_field_helpers: List[Optional[tk.Label]] = [None] * len(self.schema.section.fields)
        self.flag_vars: List[tk.IntVar] = []

        self.build_gui()
        self.weapon_search_var.trace_add("write", lambda *_: self.refresh_weapon_list())
        self.load_files()
        self.refresh_weapon_list()
        self.protocol("WM_DELETE_WINDOW", self.on_close_request)

    def build_gui(self):
        shell = build_editor_shell(self, build_window_schema(self.schema), self.status_var)
        self.status_label = shell.status_label

        list_handles = build_editor_list_panel(
            shell.left_body,
            title_var=self.weapon_title_var,
            meta_var=self.weapon_meta_var,
            search_var=self.weapon_search_var,
            on_select=self.on_weapon_list_select,
            on_clear=lambda: self.weapon_search_var.set(""),
            on_prev=lambda: self.change_weapon(-1),
            on_next=lambda: self.change_weapon(1),
            schema=WEAPON_LIST_SCHEMA,
        )
        self.weapon_listbox = list_handles.listbox
        self.batch_controller = EditorBatchSelectionController(
            self,
            listbox=self.weapon_listbox,
            get_visible_ids=lambda: [weapon.index for weapon in self.filtered_weapons],
            get_current_id=lambda: self.current_weapon_index if self.current_bytes is not None else None,
            select_id=self.select_weapon,
            fields=self.batch_fields(),
            read_values=self.batch_read_values,
            apply_updates=self.apply_batch_updates,
            restore_values=self.restore_batch_snapshot,
            format_value=self.format_batch_value,
            parse_value=self.parse_batch_value,
            set_status=self.set_status,
            title="Weapon Multi-Slot Editor",
            noun="weapons",
        )

        self.weapon_canvas = WeaponConstellationCanvas(shell.center_body, self)
        build_editor_center_panel(
            shell.center_body,
            canvas=self.weapon_canvas,
            jump_var=self.weapon_jump_var,
            jump_command=self.jump_to_weapon,
            on_prev=lambda: self.change_weapon(-1),
            on_next=lambda: self.change_weapon(1),
            on_apply=self.apply_current_weapon,
            schema=build_center_schema(self.schema),
        )

        intro = f"Mod the {self.schema.section.file_label} weapon fields"
        if self.schema.section.toggle_names:
            intro += f" and the {len(self.schema.section.toggle_names)} flags"
        if self.element_field_indices:
            intro += ". Element ids use readonly dropdowns so only known safe element values can be selected."
        else:
            intro += "."
        scroll_handles = build_scrollable_editor_panel(
            shell.right_body,
            dirty_var=self.dirty_var,
            schema=EditorRightSchema(
                intro_text=intro,
                actions=[
                    EditorActionSchema("Save File", self.save_current_files, SELECT_GREEN),
                    EditorActionSchema("Reload File", self.reload_files, SELECT_GOLD, fg="#180E2B"),
                    EditorActionSchema("Close Editor", self.on_close_request, SELECT_BLUE),
                ],
            ),
        )

        if self.numeric_field_indices:
            field_handles = build_field_section(
                scroll_handles.fields_wrap,
                schema=EditorFieldSectionSchema(
                    self.schema.section.section_title,
                    self.schema.section.section_subtitle,
                    [EditorFieldSchema(self.schema.section.fields[idx][0], self.schema.section.fields[idx][1]) for idx in self.numeric_field_indices],
                    self.schema.section.columns,
                ),
                on_change=lambda section_index: self.on_core_field_changed(self.numeric_field_indices[section_index]),
                helper_text_factory=lambda byte_width: helper_text_for_sized_value(0, byte_width),
            )
            for actual_index, var, entry, helper in zip(self.numeric_field_indices, field_handles.vars, field_handles.entries, field_handles.helpers):
                self.core_field_vars[actual_index] = var
                self.core_field_entries[actual_index] = entry
                self.core_field_helpers[actual_index] = helper

        if self.element_field_indices:
            element_options = [format_element_option(value) for value in sorted(DW8XL_ELEMENT_NAMES)]
            dropdown_handles = build_dropdown_section(
                scroll_handles.fields_wrap,
                schema=EditorDropdownSectionSchema(
                    title="Weapon Elements",
                    subtitle="Element ids use readonly dropdowns so only known safe element values can be selected.",
                    fields=[
                        EditorDropdownFieldSchema(
                            label=self.schema.section.fields[idx][0],
                            options=element_options,
                            default_text=element_options[0],
                        )
                        for idx in self.element_field_indices
                    ],
                    columns=self.schema.section.columns,
                ),
                on_change=lambda section_index: self.on_core_field_changed(self.element_field_indices[section_index]),
            )
            for actual_index, var in zip(self.element_field_indices, dropdown_handles.vars):
                self.core_field_vars[actual_index] = var

        if self.schema.section.toggle_names:
            self.flag_vars = build_toggle_section(
                scroll_handles.fields_wrap,
                schema=EditorToggleSectionSchema(
                    title=self.schema.section.toggle_title,
                    subtitle=self.schema.section.toggle_subtitle,
                    toggle_names=self.schema.section.toggle_names,
                    columns=self.schema.section.toggle_columns,
                ),
                on_toggle=self.on_flag_changed,
            )

        if self.show_description_panel:
            build_description_section(
                scroll_handles.fields_wrap,
                title="Element Descriptions",
                textvariable=self.weapon_desc_var,
                wraplength=500,
            )

    def set_status(self, text: str, color: str = STATUS_GOOD):
        self.status_var.set(text)
        self.status_label.config(fg=color)

    def get_weapon_display_name(self, weapon_index: int) -> str:
        return self.weapons[weapon_index].title

    def get_weapon_slot_label(self, weapon_index: int) -> str:
        return self.weapons[weapon_index].label

    def weapon_offset(self, weapon_index: int) -> int:
        return self.schema.section.offset + (weapon_index * self.schema.section.record_size)

    def read_record(self, weapon_index: int, blob: Optional[bytes] = None) -> bytes:
        source = blob if blob is not None else self.current_bytes
        if source is None:
            return b""
        start = self.weapon_offset(weapon_index)
        return bytes(source[start : start + self.schema.section.record_size])

    def read_core_values(self, weapon_index: int, blob: Optional[bytes] = None) -> List[int]:
        record = self.read_record(weapon_index, blob)
        if len(record) < self.schema.section.record_size:
            return [0] * len(self.schema.section.fields)
        values: List[int] = []
        cursor = 0
        for _field_name, byte_width in self.schema.section.fields:
            if self.schema.section.toggle_names and cursor == self.toggle_offset:
                cursor += len(self.schema.section.toggle_names)
            values.append(int.from_bytes(record[cursor : cursor + byte_width], "little", signed=False))
            cursor += byte_width
        return values

    def read_flag_values(self, weapon_index: int, blob: Optional[bytes] = None) -> List[int]:
        if not self.schema.section.toggle_names:
            return []
        record = self.read_record(weapon_index, blob)
        if len(record) < self.schema.section.record_size:
            return [0] * len(self.schema.section.toggle_names)
        start = self.toggle_offset
        end = start + len(self.schema.section.toggle_names)
        return list(record[start:end])

    def batch_fields(self) -> List[EditorBatchField]:
        return [EditorBatchField(label, byte_width) for label, byte_width in self.schema.section.fields] + [
            EditorBatchField(name, 1) for name in self.schema.section.toggle_names
        ]

    def batch_field_offsets(self) -> List[Tuple[int, int]]:
        offsets: List[Tuple[int, int]] = []
        cursor = 0
        for _field_name, byte_width in self.schema.section.fields:
            if self.schema.section.toggle_names and cursor == self.toggle_offset:
                cursor += len(self.schema.section.toggle_names)
            offsets.append((cursor, byte_width))
            cursor += byte_width
        for idx, _name in enumerate(self.schema.section.toggle_names):
            offsets.append((self.toggle_offset + idx, 1))
        return offsets

    def batch_read_values(self, weapon_index: int) -> List[int]:
        return self.read_core_values(weapon_index) + self.read_flag_values(weapon_index)

    def format_batch_value(self, field_index: int, value: int) -> str:
        core_count = len(self.schema.section.fields)
        if field_index >= core_count:
            return "1" if value else "0"
        field_name, byte_width = self.schema.section.fields[field_index]
        if field_index in self.element_field_indices:
            return format_element_option(value)
        return format_field_value(self.schema.section, field_name, byte_width, value)

    def parse_batch_value(self, field_index: int, raw: str) -> int:
        core_count = len(self.schema.section.fields)
        if field_index >= core_count:
            return 1 if parse_sized_int(raw, 1) else 0
        _field_name, byte_width = self.schema.section.fields[field_index]
        if field_index in self.element_field_indices:
            try:
                return parse_element_option(raw)
            except ValueError:
                return parse_sized_int(raw, byte_width)
        return parse_sized_int(raw, byte_width)

    def apply_batch_updates(self, weapon_indices: Sequence[int], updates: Sequence[Tuple[int, int]]) -> bool:
        if self.current_bytes is None:
            return False
        write_batch_record_updates(
            self.current_bytes,
            record_offset=self.weapon_offset,
            record_size=self.schema.section.record_size,
            field_offsets=self.batch_field_offsets(),
            slots=weapon_indices,
            updates=updates,
        )
        self.files_dirty = bytes(self.current_bytes) != self.original_bytes
        self.weapon_dirty = False
        self.load_weapon_into_fields(self.current_weapon_index)
        self.sync_weapon_selection()
        return True

    def restore_batch_snapshot(self, snapshot: Dict[int, List[int]]) -> bool:
        if self.current_bytes is None:
            return False
        write_batch_record_snapshots(
            self.current_bytes,
            record_offset=self.weapon_offset,
            record_size=self.schema.section.record_size,
            field_offsets=self.batch_field_offsets(),
            snapshots=snapshot,
        )
        self.files_dirty = bytes(self.current_bytes) != self.original_bytes
        self.weapon_dirty = False
        self.load_weapon_into_fields(self.current_weapon_index)
        self.sync_weapon_selection()
        return True

    def weapon_is_changed(self, weapon_index: int) -> bool:
        return self.current_bytes is not None and bool(self.original_bytes) and self.read_record(weapon_index) != self.read_record(weapon_index, self.original_bytes)

    def dirty_weapon_count(self) -> int:
        return sum(1 for weapon_index in range(self.schema.weapon_count) if self.weapon_is_changed(weapon_index))

    def build_weapon_notes(self, core_values: Optional[List[int]] = None) -> str:
        if self.current_bytes is None:
            return ""
        if core_values is None:
            core_values = self.read_core_values(self.current_weapon_index)
        if not self.element_field_indices:
            return "No mapped element descriptions are available for this game's weapon format yet."
        lines: List[str] = []
        for field_index in self.element_field_indices:
            field_name, _byte_width = self.schema.section.fields[field_index]
            element_id = core_values[field_index]
            element_level_name = f"{field_name} Level"
            level_value = core_values[self.field_index[element_level_name]] if element_level_name in self.field_index else 0
            lines.append(f"{field_name} : {element_label(element_id)} ({element_id}) | Level {level_value}")
            lines.append(element_description(element_id))
            lines.append("")
        while lines and not lines[-1]:
            lines.pop()
        return "\n".join(lines)

    def preview_core_values(self) -> Optional[List[int]]:
        if self.current_bytes is None:
            return None
        preview = self.read_core_values(self.current_weapon_index)
        for idx, (_field_name, byte_width) in enumerate(self.schema.section.fields):
            var = self.core_field_vars[idx]
            if var is None:
                continue
            try:
                preview[idx] = parse_element_option(var.get()) if idx in self.element_field_indices else parse_sized_int(var.get(), byte_width)
            except ValueError:
                pass
        return preview

    def update_dirty_banner(self):
        if self.weapon_dirty and self.files_dirty:
            self.dirty_var.set("Disk state: unapplied weapon edits + unsaved file changes")
        elif self.weapon_dirty:
            self.dirty_var.set("Disk state: unapplied weapon edits")
        elif self.files_dirty:
            self.dirty_var.set("Disk state: unsaved file changes in memory")
        else:
            self.dirty_var.set("Disk state: clean")

    def update_meta(self):
        if self.current_bytes is None:
            self.weapon_title_var.set("No weapon loaded")
            self.weapon_meta_var.set(f"Load {self.schema.display_name} weapon data to begin.")
            if self.show_description_panel:
                self.weapon_desc_var.set("")
            return
        self.weapon_title_var.set(self.get_weapon_slot_label(self.current_weapon_index))
        self.weapon_meta_var.set(
            "\n".join(
                [
                    f"Weapon Slot   : {self.get_weapon_slot_label(self.current_weapon_index)}",
                    f"Main Path     : {os.path.relpath(self.schema.section.file_path, PROJECT_ROOT)}",
                    f"Export Path   : {os.path.relpath(self.schema.section.export_path, PROJECT_ROOT)}",
                    f"Weapon Slots  : {self.schema.weapon_count}",
                    f"Dirty Weapons : {self.dirty_weapon_count()}",
                ]
            )
        )
        if self.show_description_panel:
            self.weapon_desc_var.set(self.build_weapon_notes())

    def update_core_field_helper(self, field_index: int):
        if field_index in self.element_field_indices:
            return
        var = self.core_field_vars[field_index]
        entry = self.core_field_entries[field_index]
        helper = self.core_field_helpers[field_index]
        if var is None or entry is None or helper is None:
            return
        field_name, byte_width = self.schema.section.fields[field_index]
        try:
            value = parse_sized_int(var.get(), byte_width)
        except ValueError:
            entry.config(bg=FIELD_INVALID)
            helper.config(text="Invalid value. Use decimal, -1, or 0x-prefixed hex.", fg=STATUS_BAD)
            return
        row = field_index // max(1, self.schema.section.columns)
        entry.config(bg=FIELD_BG if row % 2 == 0 else FIELD_ALT_BG)
        helper.config(text=helper_text_for_sized_value(value, byte_width), fg=SELECT_MUTED)

    def load_weapon_into_fields(self, weapon_index: int):
        if self.current_bytes is None:
            return
        core_values = self.read_core_values(weapon_index)
        flag_values = self.read_flag_values(weapon_index)
        self._loading_fields = True
        for idx, value in enumerate(core_values):
            var = self.core_field_vars[idx]
            if var is None:
                continue
            field_name, byte_width = self.schema.section.fields[idx]
            if idx in self.element_field_indices:
                var.set(format_element_option(value))
            else:
                var.set(format_field_value(self.schema.section, field_name, byte_width, value))
        for idx, value in enumerate(flag_values):
            self.flag_vars[idx].set(1 if value else 0)
        self._loading_fields = False
        for idx in self.numeric_field_indices:
            self.update_core_field_helper(idx)
        self.weapon_dirty = False
        self.update_dirty_banner()
        self.weapon_jump_var.set(str(weapon_index + 1))
        self.weapon_canvas.render()
        self.update_meta()

    def parse_core_field_values(self) -> Optional[List[int]]:
        values: List[int] = []
        for idx, (field_name, byte_width) in enumerate(self.schema.section.fields):
            var = self.core_field_vars[idx]
            if var is None:
                values.append(0)
                continue
            try:
                values.append(parse_element_option(var.get()) if idx in self.element_field_indices else parse_sized_int(var.get(), byte_width))
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

    def apply_current_weapon(self, *, show_status: bool = True) -> bool:
        if self.current_bytes is None:
            return False
        core_values = self.parse_core_field_values()
        if core_values is None:
            return False

        record = bytearray(self.read_record(self.current_weapon_index))
        if len(record) < self.schema.section.record_size:
            record = bytearray(self.schema.section.record_size)
        cursor = 0
        for value, (_field_name, byte_width) in zip(core_values, self.schema.section.fields):
            if self.schema.section.toggle_names and cursor == self.toggle_offset:
                cursor += len(self.schema.section.toggle_names)
            record[cursor : cursor + byte_width] = value.to_bytes(byte_width, "little", signed=False)
            cursor += byte_width
        for idx, flag_var in enumerate(self.flag_vars):
            record[self.toggle_offset + idx] = 1 if flag_var.get() else 0

        start = self.weapon_offset(self.current_weapon_index)
        end = start + self.schema.section.record_size
        changed = bytes(self.current_bytes[start:end]) != bytes(record)
        if changed:
            self.current_bytes[start:end] = record
        self.files_dirty = bytes(self.current_bytes) != self.original_bytes
        self.weapon_dirty = False
        self.update_meta()
        self.update_dirty_banner()
        self.weapon_canvas.render()
        if show_status:
            self.set_status(f"Applied {self.get_weapon_slot_label(self.current_weapon_index)} to memory. Save File when you're ready.", STATUS_GOOD if changed else STATUS_WARN)
        return True

    def save_current_files(self) -> bool:
        if self.current_bytes is None:
            return False
        if self.weapon_dirty and not self.apply_current_weapon(show_status=False):
            return False
        had_unsaved_changes = self.files_dirty
        try:
            os.makedirs(self.schema.section.export_dir, exist_ok=True)
            with open(self.schema.section.export_path, "wb") as handle:
                handle.write(self.current_bytes)
        except OSError as exc:
            messagebox.showerror("Save Failed", f"Could not export weapon file:\n{exc}")
            self.set_status("Could not export the weapon file.", STATUS_BAD)
            return False
        self.original_bytes = bytes(self.current_bytes)
        self.files_dirty = False
        self.weapon_dirty = False
        self.update_meta()
        self.update_dirty_banner()
        self.weapon_canvas.render()
        suffix = " (clean copy)" if not had_unsaved_changes else ""
        self.set_status(f"Exported {os.path.relpath(self.schema.section.export_path, PROJECT_ROOT)}{suffix}.", STATUS_GOOD)
        return True

    def load_files(self) -> bool:
        if not os.path.isfile(self.schema.section.file_path):
            messagebox.showerror("Missing Weapon File", f"Could not find:\n{self.schema.section.file_path}")
            self.set_status(f"Missing {self.schema.display_name} weapon file.", STATUS_BAD)
            return False
        try:
            with open(self.schema.section.file_path, "rb") as handle:
                blob = handle.read()
        except OSError as exc:
            messagebox.showerror("Read Failed", f"Could not read the weapon file:\n{exc}")
            self.set_status(f"Could not read the {self.schema.display_name} weapon file.", STATUS_BAD)
            return False

        required = self.schema.section.offset + (self.schema.weapon_count * self.schema.section.record_size)
        if len(blob) < required:
            messagebox.showerror("Weapon File Too Small", f"{self.schema.section.file_label} does not contain the full reversed weapon block.")
            self.set_status(f"{self.schema.display_name} weapon file is too small for the reversed block.", STATUS_BAD)
            return False

        self.current_bytes = bytearray(blob)
        self.original_bytes = bytes(blob)
        self.current_weapon_index = 0
        self.files_dirty = False
        self.weapon_dirty = False
        self.update_meta()
        self.load_weapon_into_fields(0)
        self.sync_weapon_selection()
        self.set_status(f"Loaded {self.schema.section.file_label}.", STATUS_GOOD)
        return True

    def confirm_file_transition(self, reason: str) -> bool:
        if self.current_bytes is None:
            return True
        if self.weapon_dirty and not self.apply_current_weapon(show_status=False):
            return False
        if not self.files_dirty:
            return True
        choice = messagebox.askyesnocancel("Unsaved Weapon Changes", f"Export changes from {self.schema.section.file_label} before {reason}?")
        if choice is None:
            return False
        return self.save_current_files() if choice else True

    def reload_files(self):
        if self.current_bytes is None:
            return
        if self.weapon_dirty or self.files_dirty:
            if not messagebox.askyesno("Reload Weapon File", f"Reloading {self.schema.section.file_label} will discard unapplied and unsaved changes. Continue?"):
                return
        self.load_files()

    def refresh_weapon_list(self):
        query = self.weapon_search_var.get().strip().lower()
        self.filtered_weapons = [
            weapon
            for weapon in self.weapons
            if not query
            or query in weapon.label.lower()
            or query in weapon.title.lower()
            or query in f"{weapon.index + 1}"
            or query in f"{weapon.index + 1:04d}"
        ]
        self._suppress_list_event = True
        try:
            self.weapon_listbox.delete(0, tk.END)
            for weapon in self.filtered_weapons:
                self.weapon_listbox.insert(tk.END, weapon.label)
        finally:
            self._suppress_list_event = False
        self.sync_weapon_selection()

    def sync_weapon_selection(self):
        self._suppress_list_event = True
        try:
            if hasattr(self, "batch_controller"):
                self.batch_controller.sync_from_editor()
                return
            self.weapon_listbox.selection_clear(0, tk.END)
            visible_index = next((idx for idx, weapon in enumerate(self.filtered_weapons) if weapon.index == self.current_weapon_index), None)
            if visible_index is not None:
                self.weapon_listbox.selection_set(visible_index)
                self.weapon_listbox.activate(visible_index)
                self.weapon_listbox.see(visible_index)
        finally:
            self._suppress_list_event = False

    def on_weapon_list_select(self, _event):
        if self._suppress_list_event:
            return
        selection = self.weapon_listbox.curselection()
        if not selection:
            return
        self.select_weapon(self.filtered_weapons[selection[0]].index)

    def select_weapon(self, weapon_index: int):
        if self.current_bytes is None or weapon_index < 0 or weapon_index >= self.schema.weapon_count:
            return
        if weapon_index == self.current_weapon_index:
            self.sync_weapon_selection()
            return
        if self.weapon_dirty and not self.apply_current_weapon(show_status=False):
            self.sync_weapon_selection()
            return
        self.current_weapon_index = weapon_index
        self.load_weapon_into_fields(weapon_index)
        self.sync_weapon_selection()
        self.weapon_canvas.focus_on_weapon(weapon_index)
        self.set_status(f"Selected {self.get_weapon_slot_label(weapon_index)}.", STATUS_GOOD)

    def change_weapon(self, delta: int):
        if self.current_bytes is None:
            return
        self.select_weapon(max(0, min(self.schema.weapon_count - 1, self.current_weapon_index + delta)))

    def jump_to_weapon(self):
        if self.current_bytes is None:
            return
        try:
            weapon_number = int(self.weapon_jump_var.get().strip(), 10)
        except ValueError:
            messagebox.showerror("Invalid Weapon Slot", f"Enter a number from 1 to {self.schema.weapon_count}.")
            self.set_status(f"Weapon jump failed. Use a decimal number from 1 to {self.schema.weapon_count}.", STATUS_BAD)
            return
        if weapon_number < 1 or weapon_number > self.schema.weapon_count:
            messagebox.showerror("Invalid Weapon Slot", f"Weapon slot number must be between 1 and {self.schema.weapon_count}.")
            self.set_status(f"Weapon jump failed. Weapon slot number must be between 1 and {self.schema.weapon_count}.", STATUS_BAD)
            return
        self.select_weapon(weapon_number - 1)

    def on_core_field_changed(self, field_index: int):
        self.update_core_field_helper(field_index)
        if self._loading_fields:
            return
        if self.show_description_panel:
            preview = self.preview_core_values()
            if preview is not None:
                self.weapon_desc_var.set(self.build_weapon_notes(preview))
        self.weapon_dirty = True
        self.update_dirty_banner()

    def on_flag_changed(self):
        if self._loading_fields:
            return
        self.weapon_dirty = True
        self.update_dirty_banner()

    def on_close_request(self):
        if not self.confirm_file_transition("closing the weapon editor"):
            return
        self.destroy()


class DW8XLWeaponEditorWindow(WeaponEditorWindow):
    def __init__(self, parent: tk.Misc):
        super().__init__(parent, "DW8XL")


class WO3WeaponEditorWindow(WeaponEditorWindow):
    def __init__(self, parent: tk.Misc):
        super().__init__(parent, "WO3")


if __name__ == "__main__":
    raise SystemExit("Run AE/main.pyw to launch Aldnoah Engine tools.")
