from __future__ import annotations

import math, os
import tkinter as tk
from dataclasses import dataclass
from math import ceil
from tkinter import messagebox, ttk
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
from .aldnoah_energy import PROJECT_ROOT, NpcTacticEditorSchema, get_npc_tactic_editor_schema
from .aldnoah_officer_editor import format_field_value, helper_text_for_sized_value, parse_sized_int
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
    EditorWindowSchema,
    build_dropdown_section,
    build_editor_center_panel,
    build_editor_list_panel,
    build_editor_shell,
    build_field_section,
    build_scrollable_editor_panel,
    linear_field_offsets,
    write_batch_record_snapshots,
    write_batch_record_updates,
)

__all__ = ["NPCTacticEditorWindow", "DW8ENPCTacticEditorWindow"]


NPC_TACTIC_LIST_SCHEMA = EditorListSchema(prev_label="Prev Slot", next_label="Next Slot")


def load_indexed_lines(path: str) -> tuple[str, ...]:
    if not path or not os.path.isfile(path):
        return ()
    with open(path, "r", encoding="utf-8", errors="replace") as handle:
        return tuple(line.rstrip("\r\n") for line in handle)


def build_window_schema(schema: NpcTacticEditorSchema) -> EditorWindowSchema:
    return EditorWindowSchema(
        window_title=f"{schema.game_id} NPC Tactic Editor",
        hero=EditorHeroSchema(
            title=f"{schema.game_id} NPC Tactic Editor",
            subtitle=f"Mod the CPU tactic data for {schema.display_name}, then export a safe file copy under the project root.",
            star_seed=schema.hero_star_seed,
            star_count=schema.hero_star_count,
        ),
        left_panel=EditorPanelSchema("NPC Tactic Lattice", f"Select the {schema.game_id} tactic slot you want to edit.", SELECT_BLUE),
        center_panel=EditorPanelSchema("NPC Tactic Constellation", f"Navigate the {schema.slot_count} {schema.game_id} tactic slots.", SELECT_GOLD),
        right_panel=EditorPanelSchema("NPC Tactic Field Editor", f"Edit the schema-driven tactic data for {schema.game_id}.", SELECT_GREEN),
        column_weights=(2, 3, 6),
    )


def build_center_schema(schema: NpcTacticEditorSchema) -> EditorCenterSchema:
    return EditorCenterSchema(
        prev_label="Prev Slot",
        next_label="Next Slot",
        apply_label="Apply Slot",
        hint_text=f"Changed tactic slots glow green after they are applied to memory. Drag inside the constellation to pan, use the mouse wheel to zoom, and zoom further in if you want slot ids to appear above each node. Save File exports a full copy of {schema.section.file_label} under the project root.",
    )


@dataclass(frozen=True)
class TacticSlotInfo:
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


def build_slot_infos(schema: NpcTacticEditorSchema) -> List[TacticSlotInfo]:
    raw_names = load_indexed_lines(schema.name_list_path)
    slots: List[TacticSlotInfo] = []
    for index in range(schema.slot_count):
        if index < len(raw_names) and raw_names[index].strip():
            name = raw_names[index].strip()
        else:
            name = f"{schema.placeholder_prefix} {index + 1:04d}"
        slots.append(TacticSlotInfo(index=index, name=name, placeholder_prefix=schema.placeholder_prefix))
    return slots


def parse_dropdown_option(text: str) -> int:
    raw = (text or "").strip()
    if ":" in raw:
        suffix = raw.rsplit(":", 1)[1].strip()
        if suffix.lower().startswith("0x"):
            return int(suffix, 16)
        if suffix.lstrip("+-").isdigit():
            return int(suffix, 10)
    raise ValueError("Select a value from the dropdown list.")


def format_dropdown_option(name: str, value: int, *, none_value: int) -> str:
    if value == none_value:
        return f"None/Unused: {value}"
    title = (name or "").strip() or f"Value {value}"
    return f"{title}: {value}"


class NPCTacticConstellationCanvas(tk.Canvas):
    def __init__(self, parent: tk.Misc, controller: "NPCTacticEditorWindow"):
        super().__init__(parent, bg=SELECT_BG, highlightthickness=0, bd=0, relief="flat")
        self.controller = controller
        self.items: Dict[int, int] = {}
        self.phase = 0.0
        self.stars = make_stars(controller.schema.constellation_star_seed, controller.schema.constellation_star_count)
        self.zoom = 1.0
        self.min_zoom = 0.55
        self.max_zoom = 3.75
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
        if self._dragging:
            self.pan_x = self._press_pan[0] + dx
            self.pan_y = self._press_pan[1] + dy
            self.render()

    def on_release(self, event):
        if self._dragging:
            return
        for item_id in reversed(self.find_overlapping(event.x - 8, event.y - 8, event.x + 8, event.y + 8)):
            slot_index = self.items.get(item_id)
            if slot_index is not None:
                self.controller.select_slot(slot_index)
                return

    def on_mousewheel(self, event):
        self.zoom_at(event.x, event.y, 1.12 if event.delta > 0 else (1 / 1.12))

    def zoom_at(self, screen_x: float, screen_y: float, factor: float):
        width = max(1, self.winfo_width())
        height = max(1, self.winfo_height())
        new_zoom = max(self.min_zoom, min(self.max_zoom, self.zoom * factor))
        if abs(new_zoom - self.zoom) < 1e-6:
            return
        cx = (width * 0.50) + self.pan_x
        cy = (height * 0.54) + self.pan_y
        wx = (screen_x - cx) / self.zoom
        wy = (screen_y - cy) / self.zoom
        self.zoom = new_zoom
        self.pan_x = screen_x - ((width * 0.50) + (wx * self.zoom))
        self.pan_y = screen_y - ((height * 0.54) + (wy * self.zoom))
        self.render()

    def positions(self, width: int, height: int) -> List[tuple[int, float, float]]:
        arms = self.controller.schema.constellation_arms
        per_arm = ceil(self.controller.schema.slot_count / arms)
        outer = max(170.0, min(width, height) * 0.42 * math.sqrt(self.controller.schema.slot_count / 110))
        spacing = 1.22 if self.controller.schema.slot_count >= 2000 else 1.0
        points: List[tuple[int, float, float]] = []
        for arm in range(arms):
            angle = (-math.pi / 2.0) + (arm * ((math.pi * 2.0) / arms))
            for step in range(per_arm):
                slot_index = arm * per_arm + step
                if slot_index >= self.controller.schema.slot_count:
                    break
                t = step / max(1, per_arm - 1)
                radius = 40.0 + (t * outer * spacing)
                bend = math.sin((step * 0.45) + (arm * 0.6)) * 0.18
                points.append((slot_index, math.cos(angle + bend) * radius, math.sin(angle + bend) * radius * 0.78))
        return points

    def focus_on_slot(self, slot_index: int):
        width = max(1, self.winfo_width())
        height = max(1, self.winfo_height())
        for idx, wx, wy in self.positions(width, height):
            if idx == slot_index:
                self.pan_x = -(wx * self.zoom)
                self.pan_y = -(wy * self.zoom)
                self.render()
                return

    def render(self):
        self.delete("all")
        self.items.clear()
        width = max(1, self.winfo_width())
        height = max(1, self.winfo_height())
        draw_constellation_backdrop(self, width, height, self.stars, self.phase)
        self.create_text(18, 16, anchor="nw", text="NPC Tactic Constellation", fill=SELECT_TEXT, font=("Segoe UI", 15, "bold"))
        self.create_text(20, 44, anchor="nw", text="Gold is selected, green is modded, and violet is loaded. Drag to pan, wheel to zoom, and zoom further in to reveal slot ids.", fill=SELECT_SUBTEXT, font=("Segoe UI", 9), width=max(200, width - 40))
        if self.controller.current_bytes is None:
            self.create_text(width * 0.5, height * 0.56, text=f"Load {self.controller.schema.section.file_label} to light the NPC tactic lattice.", fill=SELECT_SUBTEXT, font=("Segoe UI", 11))
            return
        projected = []
        for slot_index, wx, wy in self.positions(width, height):
            projected.append((slot_index, (width * 0.50) + self.pan_x + (wx * self.zoom), (height * 0.54) + self.pan_y + (wy * self.zoom)))
        per_arm = ceil(self.controller.schema.slot_count / self.controller.schema.constellation_arms)
        for arm in range(self.controller.schema.constellation_arms):
            arm_points = projected[arm * per_arm : (arm + 1) * per_arm]
            for idx in range(len(arm_points) - 1):
                _, ax, ay = arm_points[idx]
                _, bx, by = arm_points[idx + 1]
                self.create_line(ax, ay, bx, by, fill=SELECT_LINE, width=1 if self.zoom < 1.5 else 2)
        zoom_scale = max(0.8, min(2.1, self.zoom))
        for slot_index, px, py in projected:
            selected = self.controller.current_slot_index == slot_index
            changed = self.controller.slot_changed(slot_index)
            if selected:
                halo_r = max(14, min(28, (17 + math.sin(self.phase * 2.0 + (slot_index * 0.1)) * 2) * zoom_scale))
                halo = self.create_oval(px - halo_r, py - halo_r, px + halo_r, py + halo_r, outline=SELECT_GOLD, width=1, stipple="gray25")
                self.items[halo] = slot_index
            radius = max(8, min(18, int(10 * zoom_scale))) if selected else max(6 if changed else 5, min(14 if changed else 12, int((8 if changed else 7) * zoom_scale)))
            orb = self.create_oval(px - radius, py - radius, px + radius, py + radius, fill=SELECT_NODE_SEL if selected else (SELECT_GREEN if changed else SELECT_NODE), outline=SELECT_GOLD if selected else ("#A8E3B9" if changed else SELECT_NODE_RING), width=2 if selected else 1)
            self.items[orb] = slot_index
            if self.zoom >= 1.8:
                label = self.create_text(px, py - max(14, int(14 * zoom_scale)), text=str(slot_index + 1), fill=SELECT_TEXT if selected else SELECT_SUBTEXT, font=("Segoe UI", max(8, min(11, int(8 * zoom_scale))), "bold"))
                self.items[label] = slot_index


class NPCTacticEditorWindow(tk.Toplevel):
    def __init__(self, parent: tk.Misc, game_id: str = "DW8E"):
        super().__init__(parent)
        self.parent = parent
        self.schema = get_npc_tactic_editor_schema(game_id)
        self.section = self.schema.section
        self.slot_infos = build_slot_infos(self.schema)

        self.dropdown_option_maps = self.build_dropdown_option_maps()
        self.dropdown_field_indices = [
            idx for idx, (field_name, _byte_width) in enumerate(self.section.fields) if field_name in self.dropdown_option_maps
        ]
        self.numeric_field_indices = [
            idx for idx in range(len(self.section.fields)) if idx not in self.dropdown_field_indices
        ]
        self.numeric_section_rows = {
            field_index: section_index // 2 for section_index, field_index in enumerate(self.numeric_field_indices)
        }
        self.dropdown_base_values = {
            field_name: tuple(option_map[value] for value in sorted(option_map))
            for field_name, option_map in self.dropdown_option_maps.items()
        }

        self.current_slot_index = 0
        self.current_bytes: Optional[bytearray] = None
        self.original_bytes: bytes = b""
        self.files_dirty = False
        self.slot_dirty = False
        self._loading_fields = False
        self._suppress_list_event = False
        self.filtered_slots: List[TacticSlotInfo] = list(self.slot_infos)

        self.status_var = tk.StringVar(value="Load 003.xl to begin.")
        self.dirty_var = tk.StringVar(value="Disk state: clean")
        self.title_var = tk.StringVar(value="No tactic slot loaded")
        self.meta_var = tk.StringVar(value="Load DW8E NPC tactic data to begin.")
        self.search_var = tk.StringVar()
        self.jump_var = tk.StringVar(value="1")

        self.field_vars: List[Optional[tk.StringVar]] = []
        self.field_entries: List[Optional[tk.Entry]] = []
        self.field_helpers: List[Optional[tk.Label]] = []
        self.dropdown_combos: List[Optional[ttk.Combobox]] = []

        shell = build_editor_shell(self, build_window_schema(self.schema), self.status_var)
        self.status_label = shell.status_label
        self.search_var.trace_add("write", lambda *_: self.refresh_slot_list())

        list_handles = build_editor_list_panel(
            shell.left_body,
            title_var=self.title_var,
            meta_var=self.meta_var,
            search_var=self.search_var,
            on_select=self.on_slot_list_select,
            on_clear=lambda: self.search_var.set(""),
            on_prev=lambda: self.change_slot(-1),
            on_next=lambda: self.change_slot(1),
            schema=NPC_TACTIC_LIST_SCHEMA,
        )
        self.slot_listbox = list_handles.listbox
        self.batch_controller = EditorBatchSelectionController(
            self,
            listbox=self.slot_listbox,
            get_visible_ids=lambda: [slot.index for slot in self.filtered_slots],
            get_current_id=lambda: self.current_slot_index if self.current_bytes is not None else None,
            select_id=self.select_slot,
            fields=[EditorBatchField(label, byte_width) for label, byte_width in self.section.fields],
            read_values=self.read_values,
            apply_updates=self.apply_batch_updates,
            restore_values=self.restore_batch_snapshot,
            format_value=self.format_batch_value,
            parse_value=self.parse_batch_value,
            set_status=self.set_status,
            title="NPC Tactic Multi-Slot Editor",
            noun="slots",
        )

        self.slot_canvas = NPCTacticConstellationCanvas(shell.center_body, self)
        build_editor_center_panel(
            shell.center_body,
            canvas=self.slot_canvas,
            jump_var=self.jump_var,
            jump_command=self.jump_to_slot,
            on_prev=lambda: self.change_slot(-1),
            on_next=lambda: self.change_slot(1),
            on_apply=self.apply_current_slot,
            schema=build_center_schema(self.schema),
        )

        right_schema = EditorRightSchema(
            intro_text="Mod the NPC tactic fields. Stratagems and Way of Life use readonly dropdowns so only mapped values are selected, and scroll to reach the lower sections.",
            actions=[
                EditorActionSchema("Save File", self.save_current_file, SELECT_GREEN),
                EditorActionSchema("Reload File", self.reload_file, SELECT_GOLD, fg="#180E2B"),
                EditorActionSchema("Close Editor", self.on_close_request, SELECT_BLUE),
            ],
        )
        scroll_handles = build_scrollable_editor_panel(shell.right_body, dirty_var=self.dirty_var, schema=right_schema)

        dropdown_handles = build_dropdown_section(
            scroll_handles.fields_wrap,
            schema=EditorDropdownSectionSchema(
                title="Stratagems and Way of Life",
                subtitle="Known tactic ids use readonly dropdowns. Value 255 writes FF and means the field is currently unused by the slot.",
                fields=[
                    EditorDropdownFieldSchema(
                        label=self.section.fields[idx][0],
                        options=self.dropdown_base_values[self.section.fields[idx][0]],
                        default_text=self.dropdown_base_values[self.section.fields[idx][0]][0],
                    )
                    for idx in self.dropdown_field_indices
                ],
                columns=2,
            ),
            on_change=lambda section_index: self.on_field_changed(self.dropdown_field_indices[section_index]),
        )

        field_handles = build_field_section(
            scroll_handles.fields_wrap,
            schema=EditorFieldSectionSchema(
                title=self.section.section_title,
                subtitle=self.section.section_subtitle,
                fields=[
                    EditorFieldSchema(self.section.fields[idx][0], self.section.fields[idx][1])
                    for idx in self.numeric_field_indices
                ],
                columns=self.section.columns,
            ),
            on_change=lambda section_index: self.on_field_changed(self.numeric_field_indices[section_index]),
            helper_text_factory=lambda byte_width: helper_text_for_sized_value(0, byte_width),
        )

        self.field_vars = [None] * len(self.section.fields)
        self.field_entries = [None] * len(self.section.fields)
        self.field_helpers = [None] * len(self.section.fields)
        self.dropdown_combos = [None] * len(self.section.fields)

        for actual_index, var, combo in zip(self.dropdown_field_indices, dropdown_handles.vars, dropdown_handles.comboboxes):
            self.field_vars[actual_index] = var
            self.dropdown_combos[actual_index] = combo
        for actual_index, var, entry, helper in zip(self.numeric_field_indices, field_handles.vars, field_handles.entries, field_handles.helpers):
            self.field_vars[actual_index] = var
            self.field_entries[actual_index] = entry
            self.field_helpers[actual_index] = helper

        self.protocol("WM_DELETE_WINDOW", self.on_close_request)

        self.load_file()
        self.refresh_slot_list()

    def build_dropdown_option_maps(self) -> Dict[str, Dict[int, str]]:
        none_value = self.schema.dropdown_none_value
        option_maps: Dict[str, Dict[int, str]] = {}

        stratagem_names = load_indexed_lines(self.schema.stratagem_list_path)
        stratagem_map = {
            value: format_dropdown_option(name.strip() if name.strip() else f"Stratagem {value}", value, none_value=none_value)
            for value, name in enumerate(stratagem_names)
        }
        stratagem_map[none_value] = format_dropdown_option("", none_value, none_value=none_value)

        way_of_life_names = load_indexed_lines(self.schema.way_of_life_list_path)
        way_of_life_map = {
            value: format_dropdown_option(name.strip() if name.strip() else f"Way of Life {value}", value, none_value=none_value)
            for value, name in enumerate(way_of_life_names)
        }
        way_of_life_map[none_value] = format_dropdown_option("", none_value, none_value=none_value)

        for field_name, _byte_width in self.section.fields:
            if field_name.startswith("Stratagem"):
                option_maps[field_name] = dict(stratagem_map)
            elif field_name == "Way of Life":
                option_maps[field_name] = dict(way_of_life_map)
        return option_maps

    def dropdown_label_for_value(self, field_name: str, value: int) -> str:
        option_map = self.dropdown_option_maps.get(field_name, {})
        if value in option_map:
            return option_map[value]
        unknown_label = format_dropdown_option(f"{field_name} Value {value}", value, none_value=self.schema.dropdown_none_value)
        option_map[value] = unknown_label
        self.dropdown_option_maps[field_name] = option_map
        return unknown_label

    def set_dropdown_value(self, field_index: int, value: int):
        field_name = self.section.fields[field_index][0]
        var = self.field_vars[field_index]
        combo = self.dropdown_combos[field_index]
        if var is None or combo is None:
            return
        label = self.dropdown_label_for_value(field_name, value)
        values = list(self.dropdown_base_values.get(field_name, ()))
        if label not in values:
            values.append(label)
            combo.configure(values=values)
        var.set(label)

    def set_status(self, text: str, color: str = STATUS_GOOD):
        self.status_var.set(text)
        self.status_label.config(fg=color)

    def slot_offset(self, slot_index: int) -> int:
        return self.section.offset + (slot_index * self.section.record_size)

    def read_record(self, slot_index: int, blob: Optional[bytes] = None) -> bytes:
        source = blob if blob is not None else self.current_bytes
        if source is None:
            return b""
        start = self.slot_offset(slot_index)
        return bytes(source[start : start + self.section.record_size])

    def read_values(self, slot_index: int, blob: Optional[bytes] = None) -> List[int]:
        record = self.read_record(slot_index, blob)
        if len(record) < self.section.record_size:
            return [0] * len(self.section.fields)
        values: List[int] = []
        cursor = 0
        for _field_name, byte_width in self.section.fields:
            values.append(int.from_bytes(record[cursor : cursor + byte_width], "little", signed=False))
            cursor += byte_width
        return values

    def batch_field_offsets(self) -> List[Tuple[int, int]]:
        return linear_field_offsets(self.section.fields)

    def format_batch_value(self, field_index: int, value: int) -> str:
        field_name, byte_width = self.section.fields[field_index]
        if field_index in self.dropdown_field_indices:
            return self.dropdown_label_for_value(field_name, value)
        return format_field_value(self.section, field_name, byte_width, value)

    def parse_batch_value(self, field_index: int, raw: str) -> int:
        _field_name, byte_width = self.section.fields[field_index]
        if field_index in self.dropdown_field_indices:
            try:
                return parse_dropdown_option(raw)
            except ValueError:
                return parse_sized_int(raw, byte_width)
        return parse_sized_int(raw, byte_width)

    def apply_batch_updates(self, slot_indices: Sequence[int], updates: Sequence[Tuple[int, int]]) -> bool:
        if self.current_bytes is None:
            return False
        write_batch_record_updates(
            self.current_bytes,
            record_offset=self.slot_offset,
            record_size=self.section.record_size,
            field_offsets=self.batch_field_offsets(),
            slots=slot_indices,
            updates=updates,
        )
        self.files_dirty = bytes(self.current_bytes) != self.original_bytes
        self.slot_dirty = False
        self.load_slot_into_fields(self.current_slot_index)
        self.refresh_slot_list()
        self.sync_slot_selection()
        return True

    def restore_batch_snapshot(self, snapshot: Dict[int, List[int]]) -> bool:
        if self.current_bytes is None:
            return False
        write_batch_record_snapshots(
            self.current_bytes,
            record_offset=self.slot_offset,
            record_size=self.section.record_size,
            field_offsets=self.batch_field_offsets(),
            snapshots=snapshot,
        )
        self.files_dirty = bytes(self.current_bytes) != self.original_bytes
        self.slot_dirty = False
        self.load_slot_into_fields(self.current_slot_index)
        self.refresh_slot_list()
        self.sync_slot_selection()
        return True

    def slot_changed(self, slot_index: int) -> bool:
        if self.current_bytes is None or not self.original_bytes:
            return False
        return self.read_record(slot_index) != self.read_record(slot_index, self.original_bytes)

    def dirty_slot_count(self) -> int:
        return sum(1 for slot_index in range(self.schema.slot_count) if self.slot_changed(slot_index))

    def update_dirty_banner(self):
        if self.slot_dirty and self.files_dirty:
            self.dirty_var.set("Disk state: unapplied slot edits + unsaved file changes")
        elif self.slot_dirty:
            self.dirty_var.set("Disk state: unapplied slot edits")
        elif self.files_dirty:
            self.dirty_var.set("Disk state: unsaved file changes in memory")
        else:
            self.dirty_var.set("Disk state: clean")

    def update_meta(self):
        if self.current_bytes is None:
            self.title_var.set("No tactic slot loaded")
            self.meta_var.set("Load DW8E NPC tactic data to begin.")
            return
        slot_info = self.slot_infos[self.current_slot_index]
        self.title_var.set(slot_info.label)
        self.meta_var.set(
            "\n".join(
                [
                    f"Tactic Slot   : {slot_info.label}",
                    f"Main Path     : {os.path.relpath(self.section.file_path, PROJECT_ROOT)}",
                    f"Export Path   : {os.path.relpath(self.section.export_path, PROJECT_ROOT)}",
                    f"Slot Count    : {self.schema.slot_count}",
                    f"Dirty Slots   : {self.dirty_slot_count()}",
                ]
            )
        )

    def update_numeric_field_helper(self, field_index: int):
        if field_index in self.dropdown_field_indices:
            return
        var = self.field_vars[field_index]
        entry = self.field_entries[field_index]
        helper = self.field_helpers[field_index]
        if var is None or entry is None or helper is None:
            return
        _field_name, byte_width = self.section.fields[field_index]
        try:
            value = parse_sized_int(var.get(), byte_width)
        except ValueError:
            entry.config(bg=FIELD_INVALID)
            helper.config(text="Invalid value. Use decimal, -1, or 0x-prefixed hex.", fg=STATUS_BAD)
            return
        row = self.numeric_section_rows.get(field_index, 0)
        entry.config(bg=FIELD_BG if row % 2 == 0 else FIELD_ALT_BG)
        helper.config(text=helper_text_for_sized_value(value, byte_width), fg=SELECT_MUTED)

    def load_slot_into_fields(self, slot_index: int):
        if self.current_bytes is None:
            return
        values = self.read_values(slot_index)
        self._loading_fields = True
        for idx, value in enumerate(values):
            var = self.field_vars[idx]
            if var is None:
                continue
            field_name, byte_width = self.section.fields[idx]
            if idx in self.dropdown_field_indices:
                self.set_dropdown_value(idx, value)
            else:
                var.set(format_field_value(self.section, field_name, byte_width, value))
        self._loading_fields = False
        for idx in self.numeric_field_indices:
            self.update_numeric_field_helper(idx)
        self.slot_dirty = False
        self.update_dirty_banner()
        self.jump_var.set(str(slot_index + 1))
        self.slot_canvas.render()
        self.update_meta()

    def parse_field_values(self) -> Optional[List[int]]:
        values: List[int] = []
        for idx, (field_name, byte_width) in enumerate(self.section.fields):
            var = self.field_vars[idx]
            if var is None:
                values.append(0)
                continue
            try:
                if idx in self.dropdown_field_indices:
                    values.append(parse_dropdown_option(var.get()))
                else:
                    values.append(parse_sized_int(var.get(), byte_width))
            except ValueError as exc:
                entry = self.field_entries[idx]
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

    def apply_current_slot(self, *, show_status: bool = True) -> bool:
        if self.current_bytes is None:
            return False
        values = self.parse_field_values()
        if values is None:
            return False

        record = bytearray(self.read_record(self.current_slot_index))
        cursor = 0
        for value, (_field_name, byte_width) in zip(values, self.section.fields):
            record[cursor : cursor + byte_width] = value.to_bytes(byte_width, "little", signed=False)
            cursor += byte_width

        start = self.slot_offset(self.current_slot_index)
        end = start + self.section.record_size
        record_changed = bytes(self.current_bytes[start:end]) != bytes(record)
        if record_changed:
            self.current_bytes[start:end] = record

        self.files_dirty = bytes(self.current_bytes) != self.original_bytes
        self.slot_dirty = False
        self.update_meta()
        self.update_dirty_banner()
        self.slot_canvas.render()
        if show_status:
            color = STATUS_GOOD if record_changed else STATUS_WARN
            self.set_status(f"Applied {self.slot_infos[self.current_slot_index].label} to memory. Save File when you're ready.", color)
        return True

    def save_current_file(self) -> bool:
        if self.current_bytes is None:
            return False
        if self.slot_dirty and not self.apply_current_slot(show_status=False):
            return False
        had_unsaved_changes = self.files_dirty
        try:
            os.makedirs(os.path.dirname(self.section.export_path), exist_ok=True)
            with open(self.section.export_path, "wb") as handle:
                handle.write(self.current_bytes)
        except OSError:
            self.set_status("Could not export the NPC tactic file.", STATUS_BAD)
            messagebox.showerror("Export Failed", f"Could not write:\n{self.section.export_path}")
            return False
        self.files_dirty = False
        self.slot_dirty = False
        self.update_dirty_banner()
        self.update_meta()
        suffix = " (updated existing export)" if had_unsaved_changes else ""
        self.set_status(f"Exported {os.path.relpath(self.section.export_path, PROJECT_ROOT)}{suffix}.", STATUS_GOOD)
        return True

    def load_file(self):
        if not os.path.isfile(self.section.file_path):
            self.set_status(f"Missing {self.section.file_label}.", STATUS_BAD)
            messagebox.showerror("Missing File", f"Could not find:\n{self.section.file_path}")
            return
        try:
            with open(self.section.file_path, "rb") as handle:
                blob = handle.read()
        except OSError:
            self.set_status(f"Could not read {self.section.file_label}.", STATUS_BAD)
            messagebox.showerror("Read Failed", f"Could not read:\n{self.section.file_path}")
            return
        required_size = self.section.offset + (self.schema.slot_count * self.section.record_size)
        if len(blob) < required_size:
            self.set_status(f"{self.section.file_label} is too small for the reversed block.", STATUS_BAD)
            messagebox.showerror("Unexpected File Size", f"{self.section.file_label} was smaller than the mapped block.")
            return

        self.current_bytes = bytearray(blob)
        self.original_bytes = bytes(blob)
        self.files_dirty = False
        self.slot_dirty = False
        self.current_slot_index = max(0, min(self.schema.slot_count - 1, self.current_slot_index))
        self.load_slot_into_fields(self.current_slot_index)
        self.refresh_slot_list()
        self.slot_canvas.focus_on_slot(self.current_slot_index)
        self.update_dirty_banner()
        self.set_status(f"Loaded {self.section.file_label}", STATUS_GOOD)

    def reload_file(self):
        if self.current_bytes is None:
            return
        if self.slot_dirty or self.files_dirty:
            if not messagebox.askyesno("Reload NPC Tactic File", f"Reloading {self.section.file_label} will discard unapplied and unsaved changes. Continue?"):
                return
        self.load_file()

    def refresh_slot_list(self):
        query = self.search_var.get().strip().lower()
        self.filtered_slots = [
            slot
            for slot in self.slot_infos
            if not query
            or query in slot.label.lower()
            or query in slot.title.lower()
            or query in f"{slot.index + 1}"
            or query in f"{slot.index + 1:04d}"
        ]
        self._suppress_list_event = True
        try:
            self.slot_listbox.delete(0, tk.END)
            for slot in self.filtered_slots:
                self.slot_listbox.insert(tk.END, slot.label)
        finally:
            self._suppress_list_event = False
        self.sync_slot_selection()

    def sync_slot_selection(self):
        self._suppress_list_event = True
        try:
            if hasattr(self, "batch_controller"):
                self.batch_controller.sync_from_editor()
                return
            self.slot_listbox.selection_clear(0, tk.END)
            visible_index = next((idx for idx, slot in enumerate(self.filtered_slots) if slot.index == self.current_slot_index), None)
            if visible_index is not None:
                self.slot_listbox.selection_set(visible_index)
                self.slot_listbox.activate(visible_index)
                self.slot_listbox.see(visible_index)
        finally:
            self._suppress_list_event = False

    def on_slot_list_select(self, _event):
        if self._suppress_list_event:
            return
        selection = self.slot_listbox.curselection()
        if not selection:
            return
        self.select_slot(self.filtered_slots[selection[0]].index)

    def select_slot(self, slot_index: int):
        if self.current_bytes is None or slot_index < 0 or slot_index >= self.schema.slot_count:
            return
        if slot_index == self.current_slot_index:
            self.sync_slot_selection()
            return
        if self.slot_dirty and not self.apply_current_slot(show_status=False):
            self.sync_slot_selection()
            return
        self.current_slot_index = slot_index
        self.load_slot_into_fields(slot_index)
        self.sync_slot_selection()
        self.slot_canvas.focus_on_slot(slot_index)
        self.set_status(f"Selected {self.slot_infos[slot_index].label}.", STATUS_GOOD)

    def change_slot(self, delta: int):
        if self.current_bytes is None:
            return
        self.select_slot(max(0, min(self.schema.slot_count - 1, self.current_slot_index + delta)))

    def jump_to_slot(self):
        if self.current_bytes is None:
            return
        try:
            slot_number = int(self.jump_var.get().strip(), 10)
        except ValueError:
            messagebox.showerror("Invalid Tactic Slot", f"Enter a number from 1 to {self.schema.slot_count}.")
            self.set_status(f"NPC tactic jump failed. Use a decimal number from 1 to {self.schema.slot_count}.", STATUS_BAD)
            return
        if slot_number < 1 or slot_number > self.schema.slot_count:
            messagebox.showerror("Invalid Tactic Slot", f"Tactic slot number must be between 1 and {self.schema.slot_count}.")
            self.set_status(f"NPC tactic jump failed. Tactic slot number must be between 1 and {self.schema.slot_count}.", STATUS_BAD)
            return
        self.select_slot(slot_number - 1)

    def on_field_changed(self, field_index: int):
        if self._loading_fields or self.current_bytes is None:
            return
        if field_index in self.numeric_field_indices:
            self.update_numeric_field_helper(field_index)
        self.slot_dirty = True
        self.update_dirty_banner()
        self.slot_canvas.render()

    def on_close_request(self):
        if self.slot_dirty or self.files_dirty:
            if not messagebox.askyesno("Close NPC Tactic Editor", "You have unapplied or unsaved changes. Close anyway?"):
                return
        self.destroy()


DW8ENPCTacticEditorWindow = NPCTacticEditorWindow
