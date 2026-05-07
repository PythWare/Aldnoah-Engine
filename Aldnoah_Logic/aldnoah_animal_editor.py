from __future__ import annotations

import math, os
import tkinter as tk
from dataclasses import dataclass
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
from .aldnoah_infos import DW8XL_SUPPORT_SKILL_NAMES
from .aldnoah_energy import AnimalEditorSchema, PROJECT_ROOT, get_animal_editor_schema
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

__all__ = ["AnimalEditorWindow", "DW8XLAnimalEditorWindow", "DW8EAnimalEditorWindow"]


ANIMAL_LIST_SCHEMA = EditorListSchema(prev_label="Prev Animal", next_label="Next Animal")
ABILITY_FIELD_PREFIX = "Ability "


@dataclass(frozen=True)
class AnimalInfo:
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


def build_window_schema(schema: AnimalEditorSchema) -> EditorWindowSchema:
    return EditorWindowSchema(
        window_title=f"{schema.game_id} Animal Editor",
        hero=EditorHeroSchema(
            title=f"{schema.game_id} Animal Editor",
            subtitle=f"Mod the animal data for {schema.display_name}, then export a safe file copy under the project root.",
            star_seed=schema.hero_star_seed,
            star_count=schema.hero_star_count,
        ),
        left_panel=EditorPanelSchema("Animal Lattice", f"Select the {schema.game_id} animal slot you want to edit.", SELECT_BLUE),
        center_panel=EditorPanelSchema("Animal Constellation", f"Navigate the {schema.animal_count} animal slots for {schema.game_id}.", SELECT_GOLD),
        right_panel=EditorPanelSchema("Animal Field Editor", f"Edit the schema-driven animal data for {schema.game_id}.", SELECT_GREEN),
    )


def build_center_schema(schema: AnimalEditorSchema) -> EditorCenterSchema:
    return EditorCenterSchema(
        prev_label="Prev Animal",
        next_label="Next Animal",
        apply_label="Apply Animal",
        hint_text=f"Changed animal slots glow green after they are applied to memory. Drag inside the constellation to pan, use the mouse wheel to zoom, and zoom further in if you want animal slot ids to appear above each node. Save File exports a full copy of {schema.section.file_label} under the project root.",
    )


def build_animal_infos(schema: AnimalEditorSchema) -> List[AnimalInfo]:
    animals: List[AnimalInfo] = []
    for index in range(schema.animal_count):
        name = schema.animal_names.get(index, f"{schema.placeholder_prefix} {index + 1:03d}")
        animals.append(AnimalInfo(index=index, name=name, placeholder_prefix=schema.placeholder_prefix))
    return animals


def format_ability_option(value: int) -> str:
    return f"{DW8XL_SUPPORT_SKILL_NAMES.get(value, f'Unknown {value}')}: {value}"


class AnimalConstellationCanvas(tk.Canvas):
    def __init__(self, parent: tk.Misc, controller: "AnimalEditorWindow"):
        super().__init__(parent, bg=SELECT_BG, highlightthickness=0, bd=0, relief="flat")
        self.controller = controller
        self.item_to_animal: Dict[int, int] = {}
        self.phase = 0.0
        self.stars = make_stars(controller.schema.constellation_star_seed, controller.schema.constellation_star_count)
        self.zoom = 1.0
        self.min_zoom = 0.55
        self.max_zoom = 3.5
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
        hit = self.find_overlapping(event.x - 8, event.y - 8, event.x + 8, event.y + 8)
        for item_id in reversed(hit):
            animal_index = self.item_to_animal.get(item_id)
            if animal_index is not None:
                self.controller.select_animal(animal_index)
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

    def animal_positions(self, width: int, height: int) -> List[Tuple[int, float, float]]:
        arms = self.controller.schema.constellation_arms
        per_arm = self.controller.schema.slots_per_arm
        outer = max(140.0, min(width, height) * 0.42 * math.sqrt(self.controller.schema.animal_count / 80))
        positions: List[Tuple[int, float, float]] = []
        for arm in range(arms):
            angle = (-math.pi / 2.0) + (arm * ((math.pi * 2.0) / arms))
            for step in range(per_arm):
                animal_index = arm * per_arm + step
                if animal_index >= self.controller.schema.animal_count:
                    break
                t = step / max(1, per_arm - 1)
                radius = 34.0 + (t * outer)
                bend = math.sin((step * 0.52) + (arm * 0.74)) * 0.19
                px = math.cos(angle + bend) * radius
                py = math.sin(angle + bend) * radius * 0.78
                positions.append((animal_index, px, py))
        return positions

    def project_point(self, width: int, height: int, world_x: float, world_y: float) -> Tuple[float, float]:
        center_x = (width * 0.50) + self.pan_x
        center_y = (height * 0.54) + self.pan_y
        return center_x + (world_x * self.zoom), center_y + (world_y * self.zoom)

    def focus_on_animal(self, animal_index: int):
        width = max(1, self.winfo_width())
        height = max(1, self.winfo_height())
        for idx, wx, wy in self.animal_positions(width, height):
            if idx == animal_index:
                self.pan_x = -(wx * self.zoom)
                self.pan_y = -(wy * self.zoom)
                self.render()
                return

    def render(self):
        self.delete("all")
        self.item_to_animal.clear()
        width = max(1, self.winfo_width())
        height = max(1, self.winfo_height())
        draw_constellation_backdrop(self, width, height, self.stars, self.phase)
        self.create_text(18, 16, anchor="nw", text="Animal Constellation", fill=SELECT_TEXT, font=("Segoe UI", 15, "bold"))
        self.create_text(
            20,
            44,
            anchor="nw",
            text="Gold is selected, green is modded, and violet is loaded. Drag to pan, wheel to zoom, and zoom further in to reveal animal slot ids.",
            fill=SELECT_SUBTEXT,
            font=("Segoe UI", 9),
            width=max(200, width - 40),
        )
        positions = [(animal_index, *self.project_point(width, height, wx, wy)) for animal_index, wx, wy in self.animal_positions(width, height)]
        if self.controller.current_bytes is None:
            self.create_text(width * 0.5, height * 0.56, text=f"Load {self.controller.schema.section.file_label} to light the animal lattice.", fill=SELECT_SUBTEXT, font=("Segoe UI", 11))
            return

        arms = self.controller.schema.constellation_arms
        per_arm = self.controller.schema.slots_per_arm
        zoom_scale = max(0.8, min(2.0, self.zoom))
        show_labels = self.zoom >= 1.6
        line_width = 1 if self.zoom < 1.5 else 2
        for arm in range(arms):
            arm_positions = positions[arm * per_arm : (arm + 1) * per_arm]
            for idx in range(len(arm_positions) - 1):
                _, ax, ay = arm_positions[idx]
                _, bx, by = arm_positions[idx + 1]
                self.create_line(ax, ay, bx, by, fill=SELECT_LINE, width=line_width)

        for animal_index, px, py in positions:
            selected = self.controller.current_animal_index == animal_index
            changed = self.controller.animal_is_changed(animal_index)
            if selected:
                fill = SELECT_NODE_SEL
                outline = SELECT_GOLD
                radius = max(8, min(18, int(10 * zoom_scale)))
                pulse = max(14, min(28, (17 + math.sin(self.phase * 2.0 + (animal_index * 0.3)) * 2) * zoom_scale))
                halo = self.create_oval(px - pulse, py - pulse, px + pulse, py + pulse, outline=outline, width=1, stipple="gray25")
                self.item_to_animal[halo] = animal_index
            elif changed:
                fill = SELECT_GREEN
                outline = "#A8E3B9"
                radius = max(6, min(14, int(8 * zoom_scale)))
            else:
                fill = SELECT_NODE
                outline = SELECT_NODE_RING
                radius = max(5, min(12, int(7 * zoom_scale)))
            orb = self.create_oval(px - radius, py - radius, px + radius, py + radius, fill=fill, outline=outline, width=2 if selected else 1)
            self.item_to_animal[orb] = animal_index
            if show_labels:
                label_fill = SELECT_TEXT if selected else SELECT_SUBTEXT
                label_size = max(8, min(11, int(8 * zoom_scale)))
                label = self.create_text(px, py - max(14, int(14 * zoom_scale)), text=str(animal_index + 1), fill=label_fill, font=("Segoe UI", label_size, "bold"))
                self.item_to_animal[label] = animal_index


class AnimalEditorWindow(tk.Toplevel):
    def __init__(self, parent: tk.Misc, game_id: str = "DW8XL"):
        super().__init__(parent)
        self.schema = get_animal_editor_schema(game_id)
        self.animals = build_animal_infos(self.schema)
        self.filtered_animals = list(self.animals)
        self.current_bytes: Optional[bytearray] = None
        self.original_bytes = b""
        self.current_animal_index = 0
        self.files_dirty = False
        self.animal_dirty = False
        self._loading_fields = False
        self._suppress_list_event = False

        self.animal_desc_var = tk.StringVar(value="")
        self.animal_search_var = tk.StringVar(value="")
        self.animal_title_var = tk.StringVar(value="No animal loaded")
        self.animal_meta_var = tk.StringVar(value=f"Load {self.schema.display_name} animal data to begin.")
        self.status_var = tk.StringVar(value=f"Ready to edit the {self.schema.display_name} animal data.")
        self.dirty_var = tk.StringVar(value="Disk state: clean")
        self.animal_jump_var = tk.StringVar(value="1")

        self.ability_field_indices = [idx for idx, (field_name, _byte_width) in enumerate(self.core_fields) if field_name.startswith(ABILITY_FIELD_PREFIX)]
        self.numeric_field_indices = [idx for idx in range(len(self.core_fields)) if idx not in self.ability_field_indices]
        self.numeric_field_positions = {field_index: pos for pos, field_index in enumerate(self.numeric_field_indices)}
        self.ability_field_positions = {field_index: pos for pos, field_index in enumerate(self.ability_field_indices)}
        self.ability_option_to_value = {format_ability_option(value): value for value in sorted(DW8XL_SUPPORT_SKILL_NAMES)}
        self.ability_value_to_option = {value: option for option, value in self.ability_option_to_value.items()}
        self.ability_base_options = list(self.ability_option_to_value.keys())

        self.core_field_vars: List[Optional[tk.StringVar]] = [None] * len(self.core_fields)
        self.core_field_entries: List[Optional[tk.Entry]] = [None] * len(self.core_fields)
        self.core_field_helpers: List[Optional[tk.Label]] = [None] * len(self.core_fields)
        self.ability_comboboxes: List[Optional[ttk.Combobox]] = [None] * len(self.core_fields)
        self.flag_vars: List[tk.IntVar] = []

        self.build_gui()
        self.animal_search_var.trace_add("write", lambda *_: self.refresh_animal_list())
        self.load_files()
        self.refresh_animal_list()
        self.protocol("WM_DELETE_WINDOW", self.on_close_request)

    @property
    def core_fields(self) -> Tuple[Tuple[str, int], ...]:
        return self.schema.section.fields

    @property
    def animal_count(self) -> int:
        return self.schema.animal_count

    @property
    def record_size(self) -> int:
        return self.schema.section.record_size

    @property
    def core_size(self) -> int:
        return sum(byte_width for _field_name, byte_width in self.core_fields)

    def build_gui(self):
        shell = build_editor_shell(self, build_window_schema(self.schema), self.status_var)
        self.status_label = shell.status_label

        list_handles = build_editor_list_panel(
            shell.left_body,
            title_var=self.animal_title_var,
            meta_var=self.animal_meta_var,
            search_var=self.animal_search_var,
            on_select=self.on_animal_list_select,
            on_clear=lambda: self.animal_search_var.set(""),
            on_prev=lambda: self.change_animal(-1),
            on_next=lambda: self.change_animal(1),
            schema=ANIMAL_LIST_SCHEMA,
        )
        self.animal_listbox = list_handles.listbox
        self.batch_controller = EditorBatchSelectionController(
            self,
            listbox=self.animal_listbox,
            get_visible_ids=lambda: [animal.index for animal in self.filtered_animals],
            get_current_id=lambda: self.current_animal_index if self.current_bytes is not None else None,
            select_id=self.select_animal,
            fields=self.batch_fields(),
            read_values=self.batch_read_values,
            apply_updates=self.apply_batch_updates,
            restore_values=self.restore_batch_snapshot,
            format_value=self.format_batch_value,
            parse_value=self.parse_batch_value,
            set_status=self.set_status,
            title="Animal Multi-Slot Editor",
            noun="animals",
        )

        self.animal_canvas = AnimalConstellationCanvas(shell.center_body, self)
        build_editor_center_panel(
            shell.center_body,
            canvas=self.animal_canvas,
            jump_var=self.animal_jump_var,
            jump_command=self.jump_to_animal,
            on_prev=lambda: self.change_animal(-1),
            on_next=lambda: self.change_animal(1),
            on_apply=self.apply_current_animal,
            schema=build_center_schema(self.schema),
        )

        scroll_handles = build_scrollable_editor_panel(
            shell.right_body,
            dirty_var=self.dirty_var,
            schema=EditorRightSchema(
                intro_text="Mod the core fields, 8 flag toggles, and description-backed animal slots. Scroll to reach the lower sections.",
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
                    title=self.schema.section.section_title,
                    subtitle=self.schema.section.section_subtitle,
                    fields=[EditorFieldSchema(self.core_fields[idx][0], self.core_fields[idx][1]) for idx in self.numeric_field_indices],
                    columns=self.schema.section.columns,
                ),
                on_change=lambda section_index: self.on_core_field_changed(self.numeric_field_indices[section_index]),
                helper_text_factory=lambda byte_width: helper_text_for_sized_value(0, byte_width),
            )
            for actual_index, var, entry, helper in zip(self.numeric_field_indices, field_handles.vars, field_handles.entries, field_handles.helpers):
                self.core_field_vars[actual_index] = var
                self.core_field_entries[actual_index] = entry
                self.core_field_helpers[actual_index] = helper

        if self.ability_field_indices:
            dropdown_handles = build_dropdown_section(
                scroll_handles.fields_wrap,
                schema=EditorDropdownSectionSchema(
                    title="Animal Abilities",
                    subtitle="Ability fields use readonly dropdowns backed by the support skill names so only known safe ability ids are selected.",
                    fields=[
                        EditorDropdownFieldSchema(
                            label=self.core_fields[idx][0],
                            options=self.ability_base_options,
                            default_text=self.ability_base_options[0],
                        )
                        for idx in self.ability_field_indices
                    ],
                    columns=self.schema.section.columns,
                ),
                on_change=lambda section_index: self.on_core_field_changed(self.ability_field_indices[section_index]),
            )
            for actual_index, var, combo in zip(self.ability_field_indices, dropdown_handles.vars, dropdown_handles.comboboxes):
                self.core_field_vars[actual_index] = var
                self.ability_comboboxes[actual_index] = combo

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

        build_description_section(scroll_handles.fields_wrap, title="Animal Description", textvariable=self.animal_desc_var, wraplength=500)

    def set_status(self, text: str, color: str = STATUS_GOOD):
        self.status_var.set(text)
        self.status_label.config(fg=color)

    def get_animal_display_name(self, animal_index: int) -> str:
        return self.animals[animal_index].title

    def get_animal_slot_label(self, animal_index: int) -> str:
        return self.animals[animal_index].label

    def animal_main_offset(self, animal_index: int) -> int:
        return self.schema.section.offset + (animal_index * self.record_size)

    def read_main_record(self, animal_index: int, blob: Optional[bytes] = None) -> bytes:
        source = blob if blob is not None else self.current_bytes
        if source is None:
            return b""
        start = self.animal_main_offset(animal_index)
        return bytes(source[start : start + self.record_size])

    def read_core_values(self, animal_index: int, blob: Optional[bytes] = None) -> List[int]:
        record = self.read_main_record(animal_index, blob)
        if len(record) < self.record_size:
            return [0] * len(self.core_fields)
        values: List[int] = []
        cursor = 0
        for _field_name, byte_width in self.core_fields:
            values.append(int.from_bytes(record[cursor : cursor + byte_width], "little", signed=False))
            cursor += byte_width
        return values

    def read_flag_values(self, animal_index: int, blob: Optional[bytes] = None) -> List[int]:
        record = self.read_main_record(animal_index, blob)
        if len(record) < self.record_size:
            return [0] * len(self.schema.section.toggle_names)
        start = self.core_size
        end = start + len(self.schema.section.toggle_names)
        return list(record[start:end])

    def batch_fields(self) -> List[EditorBatchField]:
        return [EditorBatchField(label, byte_width) for label, byte_width in self.core_fields] + [
            EditorBatchField(name, 1) for name in self.schema.section.toggle_names
        ]

    def batch_field_offsets(self) -> List[Tuple[int, int]]:
        return linear_field_offsets(self.core_fields, extra_flags=self.schema.section.toggle_names)

    def batch_read_values(self, animal_index: int) -> List[int]:
        return self.read_core_values(animal_index) + self.read_flag_values(animal_index)

    def format_batch_value(self, field_index: int, value: int) -> str:
        core_count = len(self.core_fields)
        if field_index >= core_count:
            return "1" if value else "0"
        field_name, byte_width = self.core_fields[field_index]
        if field_index in self.ability_field_positions:
            return self.ensure_ability_option(field_index, value)
        return format_field_value(self.schema.section, field_name, byte_width, value)

    def parse_batch_value(self, field_index: int, raw: str) -> int:
        core_count = len(self.core_fields)
        if field_index >= core_count:
            return 1 if parse_sized_int(raw, 1) else 0
        _field_name, byte_width = self.core_fields[field_index]
        if field_index in self.ability_field_positions:
            if raw in self.ability_option_to_value:
                return self.ability_option_to_value[raw] & ((1 << (byte_width * 8)) - 1)
            return parse_sized_int(raw, byte_width)
        return parse_sized_int(raw, byte_width)

    def apply_batch_updates(self, animal_indices: Sequence[int], updates: Sequence[Tuple[int, int]]) -> bool:
        if self.current_bytes is None:
            return False
        write_batch_record_updates(
            self.current_bytes,
            record_offset=self.animal_main_offset,
            record_size=self.record_size,
            field_offsets=self.batch_field_offsets(),
            slots=animal_indices,
            updates=updates,
        )
        self.files_dirty = bytes(self.current_bytes) != self.original_bytes
        self.animal_dirty = False
        self.load_animal_into_fields(self.current_animal_index)
        self.sync_animal_selection()
        return True

    def restore_batch_snapshot(self, snapshot: Dict[int, List[int]]) -> bool:
        if self.current_bytes is None:
            return False
        write_batch_record_snapshots(
            self.current_bytes,
            record_offset=self.animal_main_offset,
            record_size=self.record_size,
            field_offsets=self.batch_field_offsets(),
            snapshots=snapshot,
        )
        self.files_dirty = bytes(self.current_bytes) != self.original_bytes
        self.animal_dirty = False
        self.load_animal_into_fields(self.current_animal_index)
        self.sync_animal_selection()
        return True

    def animal_is_changed(self, animal_index: int) -> bool:
        if self.current_bytes is None or not self.original_bytes:
            return False
        return self.read_main_record(animal_index) != self.read_main_record(animal_index, self.original_bytes)

    def dirty_animal_count(self) -> int:
        return sum(1 for animal_index in range(self.animal_count) if self.animal_is_changed(animal_index))

    def update_dirty_banner(self):
        if self.animal_dirty and self.files_dirty:
            self.dirty_var.set("Disk state: unapplied animal edits + unsaved file changes")
        elif self.animal_dirty:
            self.dirty_var.set("Disk state: unapplied animal edits")
        elif self.files_dirty:
            self.dirty_var.set("Disk state: unsaved file changes in memory")
        else:
            self.dirty_var.set("Disk state: clean")

    def update_meta(self):
        if self.current_bytes is None:
            self.animal_title_var.set("No animal loaded")
            self.animal_meta_var.set(f"Load {self.schema.display_name} animal data to begin.")
            self.animal_desc_var.set("")
            return

        animal_name = self.get_animal_display_name(self.current_animal_index)
        slot_number = self.current_animal_index + 1
        self.animal_title_var.set(self.get_animal_slot_label(self.current_animal_index))
        self.animal_meta_var.set(
            "\n".join(
                [
                    f"Animal Slot    : {animal_name} | {slot_number:03d}",
                    f"Main Path      : {os.path.relpath(self.schema.section.file_path, PROJECT_ROOT)}",
                    f"Export Path    : {os.path.relpath(self.schema.section.export_path, PROJECT_ROOT)}",
                    f"Animal Slots   : {self.animal_count}",
                    f"Dirty Animals  : {self.dirty_animal_count()}",
                ]
            )
        )
        self.animal_desc_var.set(self.schema.animal_descriptions.get(self.current_animal_index, "No description available for this animal slot."))

    def update_core_field_helper(self, field_index: int):
        entry = self.core_field_entries[field_index]
        helper = self.core_field_helpers[field_index]
        if entry is None or helper is None:
            return
        raw = self.core_field_vars[field_index].get()
        field_name, byte_width = self.core_fields[field_index]
        try:
            value = parse_sized_int(raw, byte_width)
        except ValueError:
            entry.config(bg=FIELD_INVALID)
            helper.config(text="Invalid value. Use decimal, -1, or 0x-prefixed hex.", fg=STATUS_BAD)
            return
        row = self.numeric_field_positions[field_index] // max(1, self.schema.section.columns)
        entry.config(bg=FIELD_BG if row % 2 == 0 else FIELD_ALT_BG)
        helper.config(text=helper_text_for_sized_value(value, byte_width), fg=SELECT_MUTED)

    def ensure_ability_option(self, field_index: int, value: int) -> str:
        option = self.ability_value_to_option.get(value)
        combo = self.ability_comboboxes[field_index]
        if option is None:
            option = f"Unknown {value}: {value}"
            self.ability_option_to_value[option] = value
            self.ability_value_to_option[value] = option
            if combo is not None:
                current_options = list(combo.cget("values"))
                if option not in current_options:
                    combo.configure(values=tuple(current_options + [option]))
        elif combo is not None:
            combo.configure(values=tuple(self.ability_base_options))
        return option

    def load_animal_into_fields(self, animal_index: int):
        if self.current_bytes is None:
            return
        core_values = self.read_core_values(animal_index)
        flag_values = self.read_flag_values(animal_index)
        self._loading_fields = True
        for idx, value in enumerate(core_values):
            field_name, byte_width = self.core_fields[idx]
            if idx in self.ability_field_positions:
                self.core_field_vars[idx].set(self.ensure_ability_option(idx, value))
            else:
                self.core_field_vars[idx].set(format_field_value(self.schema.section, field_name, byte_width, value))
        for idx, value in enumerate(flag_values):
            self.flag_vars[idx].set(1 if value else 0)
        self._loading_fields = False
        for idx in self.numeric_field_indices:
            self.update_core_field_helper(idx)
        self.animal_dirty = False
        self.update_dirty_banner()
        self.animal_jump_var.set(str(animal_index + 1))
        self.animal_canvas.render()
        self.update_meta()

    def parse_core_field_values(self) -> Optional[List[int]]:
        values: List[int] = []
        for idx, (field_name, byte_width) in enumerate(self.core_fields):
            if idx in self.ability_field_positions:
                option = self.core_field_vars[idx].get()
                if option not in self.ability_option_to_value:
                    messagebox.showerror("Invalid Field Value", f"{field_name}: choose a value from the dropdown.")
                    self.set_status(f"{field_name} could not be applied. Choose an ability from the dropdown.", STATUS_BAD)
                    return None
                values.append(self.ability_option_to_value[option] & ((1 << (byte_width * 8)) - 1))
                continue
            try:
                values.append(parse_sized_int(self.core_field_vars[idx].get(), byte_width))
            except ValueError as exc:
                entry = self.core_field_entries[idx]
                entry.focus_set()
                try:
                    entry.selection_range(0, "end")
                except Exception:
                    pass
                messagebox.showerror("Invalid Field Value", f"{field_name}: {exc}")
                self.set_status(f"{field_name} could not be applied. Fix the field and try again.", STATUS_BAD)
                return None
        return values

    def apply_current_animal(self, *, show_status: bool = True) -> bool:
        if self.current_bytes is None:
            return False
        core_values = self.parse_core_field_values()
        if core_values is None:
            return False

        record = bytearray(self.record_size)
        cursor = 0
        for value, (_field_name, byte_width) in zip(core_values, self.core_fields):
            record[cursor : cursor + byte_width] = value.to_bytes(byte_width, "little", signed=False)
            cursor += byte_width
        for idx, flag_var in enumerate(self.flag_vars):
            record[cursor + idx] = 1 if flag_var.get() else 0

        start = self.animal_main_offset(self.current_animal_index)
        end = start + self.record_size
        changed = bytes(self.current_bytes[start:end]) != bytes(record)
        if changed:
            self.current_bytes[start:end] = record
        self.files_dirty = bytes(self.current_bytes) != self.original_bytes
        self.animal_dirty = False
        self.update_meta()
        self.update_dirty_banner()
        self.animal_canvas.render()
        if show_status:
            self.set_status(f"Applied {self.get_animal_slot_label(self.current_animal_index)} to memory. Save File when you're ready.", STATUS_GOOD if changed else STATUS_WARN)
        return True

    def save_current_files(self) -> bool:
        if self.current_bytes is None:
            return False
        if self.animal_dirty and not self.apply_current_animal(show_status=False):
            return False
        had_unsaved_changes = self.files_dirty
        try:
            os.makedirs(self.schema.section.export_dir, exist_ok=True)
            with open(self.schema.section.export_path, "wb") as handle:
                handle.write(self.current_bytes)
        except OSError as exc:
            messagebox.showerror("Save Failed", f"Could not export animal file:\n{exc}")
            self.set_status("Could not export the animal file.", STATUS_BAD)
            return False
        self.original_bytes = bytes(self.current_bytes)
        self.files_dirty = False
        self.animal_dirty = False
        self.update_dirty_banner()
        self.update_meta()
        suffix = " (updated existing export)" if had_unsaved_changes else ""
        self.set_status(f"Exported {os.path.relpath(self.schema.section.export_path, PROJECT_ROOT)}{suffix}.", STATUS_GOOD)
        return True

    def load_files(self) -> bool:
        if not os.path.isfile(self.schema.section.file_path):
            messagebox.showerror("Missing Animal File", f"Could not find:\n{self.schema.section.file_path}")
            self.set_status(f"Missing {self.schema.display_name} animal file.", STATUS_BAD)
            return False
        try:
            with open(self.schema.section.file_path, "rb") as handle:
                main_blob = handle.read()
        except OSError as exc:
            messagebox.showerror("Read Failed", f"Could not read animal file:\n{exc}")
            self.set_status(f"Could not read the {self.schema.display_name} animal file.", STATUS_BAD)
            return False
        required = self.schema.section.offset + (self.animal_count * self.record_size)
        if len(main_blob) < required:
            messagebox.showerror("Animal File Too Small", f"{self.schema.section.file_label} does not contain the full reversed animal block.")
            self.set_status(f"{self.schema.display_name} animal file is too small for the reversed block.", STATUS_BAD)
            return False

        self.current_bytes = bytearray(main_blob)
        self.original_bytes = bytes(main_blob)
        self.current_animal_index = 0
        self.files_dirty = False
        self.animal_dirty = False
        self.load_animal_into_fields(0)
        self.sync_animal_selection()
        self.animal_canvas.focus_on_animal(0)
        self.update_dirty_banner()
        self.set_status(f"Loaded {self.schema.section.file_label}.", STATUS_GOOD)
        return True

    def confirm_file_transition(self, action_name: str) -> bool:
        if not (self.animal_dirty or self.files_dirty):
            return True
        choice = messagebox.askyesnocancel(
            "Unsaved Animal Changes",
            f"You have unapplied or unsaved animal changes before {action_name}.\n\nYes = Save export now\nNo = Discard changes\nCancel = Stay here",
        )
        if choice is None:
            return False
        return self.save_current_files() if choice else True

    def reload_files(self):
        if not self.confirm_file_transition("reloading the animal file"):
            return
        self.load_files()
        self.refresh_animal_list()

    def refresh_animal_list(self):
        query = self.animal_search_var.get().strip().lower()
        self.filtered_animals = [
            animal
            for animal in self.animals
            if not query
            or query in animal.label.lower()
            or query in animal.title.lower()
            or query in f"{animal.index + 1}"
            or query in f"{animal.index + 1:03d}"
        ]
        self._suppress_list_event = True
        try:
            self.animal_listbox.delete(0, tk.END)
            for animal in self.filtered_animals:
                self.animal_listbox.insert(tk.END, animal.label)
        finally:
            self._suppress_list_event = False
        self.sync_animal_selection()

    def sync_animal_selection(self):
        self._suppress_list_event = True
        try:
            if hasattr(self, "batch_controller"):
                self.batch_controller.sync_from_editor()
                return
            self.animal_listbox.selection_clear(0, tk.END)
            visible_index = next((idx for idx, animal in enumerate(self.filtered_animals) if animal.index == self.current_animal_index), None)
            if visible_index is not None:
                self.animal_listbox.selection_set(visible_index)
                self.animal_listbox.activate(visible_index)
                self.animal_listbox.see(visible_index)
        finally:
            self._suppress_list_event = False

    def on_animal_list_select(self, _event):
        if self._suppress_list_event:
            return
        selection = self.animal_listbox.curselection()
        if not selection:
            return
        target = self.filtered_animals[selection[0]]
        self.select_animal(target.index)

    def select_animal(self, animal_index: int):
        if self.current_bytes is None or animal_index < 0 or animal_index >= self.animal_count:
            return
        if animal_index == self.current_animal_index:
            self.sync_animal_selection()
            return
        if self.animal_dirty and not self.apply_current_animal(show_status=False):
            self.sync_animal_selection()
            return
        self.current_animal_index = animal_index
        self.load_animal_into_fields(animal_index)
        self.sync_animal_selection()
        self.animal_canvas.focus_on_animal(animal_index)
        self.set_status(f"Selected {self.get_animal_slot_label(animal_index)}.", STATUS_GOOD)

    def change_animal(self, delta: int):
        if self.current_bytes is None:
            return
        self.select_animal(max(0, min(self.animal_count - 1, self.current_animal_index + delta)))

    def jump_to_animal(self):
        if self.current_bytes is None:
            return
        try:
            animal_number = int(self.animal_jump_var.get().strip(), 10)
        except ValueError:
            messagebox.showerror("Invalid Animal Slot", f"Enter a number from 1 to {self.animal_count}.")
            self.set_status(f"Animal jump failed. Use a decimal number from 1 to {self.animal_count}.", STATUS_BAD)
            return
        if animal_number < 1 or animal_number > self.animal_count:
            messagebox.showerror("Invalid Animal Slot", f"Animal slot number must be between 1 and {self.animal_count}.")
            self.set_status(f"Animal jump failed. Animal slot number must be between 1 and {self.animal_count}.", STATUS_BAD)
            return
        self.select_animal(animal_number - 1)

    def on_core_field_changed(self, field_index: int):
        self.update_core_field_helper(field_index)
        if self._loading_fields:
            return
        self.animal_dirty = True
        self.update_dirty_banner()

    def on_flag_changed(self):
        if self._loading_fields:
            return
        self.animal_dirty = True
        self.update_dirty_banner()

    def on_close_request(self):
        if not self.confirm_file_transition("closing the animal editor"):
            return
        self.destroy()


class DW8XLAnimalEditorWindow(AnimalEditorWindow):
    def __init__(self, parent: tk.Misc):
        super().__init__(parent, "DW8XL")


class DW8EAnimalEditorWindow(AnimalEditorWindow):
    def __init__(self, parent: tk.Misc):
        super().__init__(parent, "DW8E")
