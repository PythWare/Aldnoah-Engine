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
from .aldnoah_energy import PROJECT_ROOT, WeaponElementEditorSchema, get_weapon_element_editor_schema
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
    EditorWindowSchema,
    build_description_section,
    build_editor_center_panel,
    build_editor_list_panel,
    build_editor_shell,
    build_field_section,
    build_scrollable_editor_panel,
    linear_field_offsets,
    write_batch_record_snapshots,
    write_batch_record_updates,
)


def build_window_schema(schema: WeaponElementEditorSchema) -> EditorWindowSchema:
    return EditorWindowSchema(
        window_title=f"{schema.game_id} Weapon Element Editor",
        hero=EditorHeroSchema(
            title=f"{schema.game_id} Weapon Element Editor",
            subtitle="Mod the element data.",
            star_seed=schema.hero_star_seed,
            star_count=schema.hero_star_count,
        ),
        left_panel=EditorPanelSchema(
            title="Element Lattice",
            subtitle=f"Select the {schema.game_id} weapon element slot you want to mod.",
            accent=SELECT_BLUE,
        ),
        center_panel=EditorPanelSchema(
            title="Element Constellation",
            subtitle=f"Navigate the {schema.element_count} {schema.game_id} weapon elements.",
            accent=SELECT_GOLD,
        ),
        right_panel=EditorPanelSchema(
            title="Element Field Editor",
            subtitle="Mod the weapon element data.",
            accent=SELECT_GREEN,
        ),
    )

WEAPON_ELEMENT_LIST_SCHEMA = EditorListSchema(
    prev_label="Prev Element",
    next_label="Next Element",
)

def build_center_schema(schema: WeaponElementEditorSchema) -> EditorCenterSchema:
    return EditorCenterSchema(
        prev_label="Prev Element",
        next_label="Next Element",
        apply_label="Apply Element",
        hint_text=f"Changed elements glow green after they are applied to memory. Drag inside the constellation to pan, use the mouse wheel to zoom, and zoom further in if you want element slot ids to appear above each node. Save File exports a full copy of {schema.section.file_label} under the project root.",
    )


@dataclass(frozen=True)
class WeaponElementInfo:
    index: int
    name: str

    @property
    def label(self) -> str:
        slot_number = self.index + 1
        fallback = f"Element {slot_number:03d}"
        return self.name if self.name == fallback else f"{self.name} | {slot_number:03d}"


def build_element_infos(schema: WeaponElementEditorSchema) -> List[WeaponElementInfo]:
    return [
        WeaponElementInfo(index, schema.element_names.get(index, f"{schema.placeholder_prefix} {index + 1:03d}"))
        for index in range(schema.element_count)
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


def format_field_value(byte_width: int, value: int) -> str:
    return f"0x{value:0{byte_width * 2}X}"


class WeaponElementConstellationCanvas(tk.Canvas):
    def __init__(self, parent: tk.Misc, controller: "WeaponElementEditorWindow"):
        super().__init__(parent, bg=SELECT_BG, highlightthickness=0, bd=0, relief="flat")
        self.controller = controller
        self.item_to_element: Dict[int, int] = {}
        self.phase = 0.0
        self.stars = make_stars(controller.schema.constellation_star_seed, controller.schema.constellation_star_count)
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
        self.select_element_at(event.x, event.y)

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

    def element_positions(self, width: int, height: int) -> List[Tuple[int, float, float]]:
        arms = self.controller.schema.constellation_arms
        per_arm = self.controller.schema.slots_per_arm
        outer = max(135.0, min(width, height) * 0.42 * math.sqrt(self.controller.schema.element_count / 50))
        positions: List[Tuple[int, float, float]] = []
        for arm in range(arms):
            angle = (-math.pi / 2.0) + (arm * ((math.pi * 2.0) / arms))
            for step in range(per_arm):
                element_index = arm * per_arm + step
                if element_index >= self.controller.element_count:
                    break
                t = step / max(1, per_arm - 1)
                radius = 34.0 + (t * outer)
                bend = math.sin((step * 0.55) + (arm * 0.70)) * 0.20
                px = math.cos(angle + bend) * radius
                py = math.sin(angle + bend) * radius * 0.78
                positions.append((element_index, px, py))
        return positions

    def project_point(self, width: int, height: int, world_x: float, world_y: float) -> Tuple[float, float]:
        center_x = (width * 0.50) + self.pan_x
        center_y = (height * 0.54) + self.pan_y
        return center_x + (world_x * self.zoom), center_y + (world_y * self.zoom)

    def select_element_at(self, x: float, y: float):
        hit = self.find_overlapping(x - 8, y - 8, x + 8, y + 8)
        for item_id in reversed(hit):
            element_index = self.item_to_element.get(item_id)
            if element_index is not None:
                self.controller.select_element(element_index)
                return

    def focus_on_element(self, element_index: int):
        width = max(1, self.winfo_width())
        height = max(1, self.winfo_height())
        for idx, wx, wy in self.element_positions(width, height):
            if idx == element_index:
                self.pan_x = (width * 0.50) - ((width * 0.50) + (wx * self.zoom))
                self.pan_y = (height * 0.54) - ((height * 0.54) + (wy * self.zoom))
                self.render()
                return

    def render(self):
        self.delete("all")
        self.item_to_element.clear()
        width = max(1, self.winfo_width())
        height = max(1, self.winfo_height())
        draw_constellation_backdrop(self, width, height, self.stars, self.phase)
        self.create_text(18, 16, anchor="nw", text="Weapon Element Constellation", fill=SELECT_TEXT, font=("Segoe UI", 15, "bold"))
        self.create_text(
            20,
            44,
            anchor="nw",
            text="Gold is selected, green is modded, and violet is loaded. Drag to pan, wheel to zoom, and zoom further in to reveal element slot ids.",
            fill=SELECT_SUBTEXT,
            font=("Segoe UI", 9),
            width=max(200, width - 40),
        )
        positions = [(element_index, *self.project_point(width, height, wx, wy)) for element_index, wx, wy in self.element_positions(width, height)]
        if self.controller.current_main_bytes is None:
            self.create_text(width * 0.5, height * 0.56, text=f"Load {self.controller.schema.section.file_label} to light the element lattice.", fill=SELECT_SUBTEXT, font=("Segoe UI", 11))
            return

        arms = self.controller.schema.constellation_arms
        per_arm = self.controller.schema.slots_per_arm
        zoom_scale = max(0.8, min(2.0, self.zoom))
        show_labels = self.zoom >= 1.7
        line_width = 1 if self.zoom < 1.5 else 2
        for arm in range(arms):
            arm_positions = positions[arm * per_arm : (arm + 1) * per_arm]
            for idx in range(len(arm_positions) - 1):
                _, ax, ay = arm_positions[idx]
                _, bx, by = arm_positions[idx + 1]
                self.create_line(ax, ay, bx, by, fill=SELECT_LINE, width=line_width)

        for element_index, px, py in positions:
            selected = self.controller.current_element_index == element_index
            changed = self.controller.element_is_changed(element_index)
            if selected:
                fill = SELECT_NODE_SEL
                outline = SELECT_GOLD
                radius = max(8, min(18, int(10 * zoom_scale)))
                pulse = max(14, min(28, (17 + math.sin(self.phase * 2.0 + (element_index * 0.3)) * 2) * zoom_scale))
                halo = self.create_oval(px - pulse, py - pulse, px + pulse, py + pulse, outline=outline, width=1, stipple="gray25")
                self.item_to_element[halo] = element_index
            elif changed:
                fill = SELECT_GREEN
                outline = "#A8E3B9"
                radius = max(6, min(14, int(8 * zoom_scale)))
            else:
                fill = SELECT_NODE
                outline = SELECT_NODE_RING
                radius = max(5, min(12, int(7 * zoom_scale)))
            orb = self.create_oval(px - radius, py - radius, px + radius, py + radius, fill=fill, outline=outline, width=2 if selected else 1)
            self.item_to_element[orb] = element_index
            if show_labels:
                label_fill = SELECT_TEXT if selected else SELECT_SUBTEXT
                label_size = max(8, min(11, int(8 * zoom_scale)))
                label = self.create_text(px, py - max(14, int(14 * zoom_scale)), text=str(element_index + 1), fill=label_fill, font=("Segoe UI", label_size, "bold"))
                self.item_to_element[label] = element_index


class WeaponElementEditorWindow(tk.Toplevel):
    def __init__(self, parent: tk.Misc, game_id: str = "DW8XL"):
        super().__init__(parent)
        self.schema = get_weapon_element_editor_schema(game_id)
        self.elements = build_element_infos(self.schema)
        self.filtered_elements = list(self.elements)
        self.current_main_bytes: Optional[bytearray] = None
        self.original_main_bytes = b""
        self.current_element_index = 0
        self.files_dirty = False
        self.element_dirty = False
        self._loading_fields = False
        self._suppress_list_event = False

        self.status_var = tk.StringVar(value=f"Ready to edit the {self.schema.display_name} weapon element data.")
        self.dirty_var = tk.StringVar(value="Disk state: clean")
        self.element_search_var = tk.StringVar(value="")
        self.element_jump_var = tk.StringVar(value="1")
        self.element_title_var = tk.StringVar(value="No element loaded")
        self.element_meta_var = tk.StringVar(value=f"Load {self.schema.display_name} weapon element data to begin.")
        self.element_desc_var = tk.StringVar(value="")

        self.core_field_vars: List[tk.StringVar] = []
        self.core_field_entries: List[tk.Entry] = []
        self.core_field_helpers: List[tk.Label] = []

        self.build_gui()
        self.element_search_var.trace_add("write", lambda *_: self.refresh_element_list())
        self.load_files()
        self.refresh_element_list()
        self.protocol("WM_DELETE_WINDOW", self.on_close_request)

    @property
    def element_count(self) -> int:
        return self.schema.element_count

    @property
    def record_size(self) -> int:
        return self.schema.section.record_size

    def build_gui(self):
        shell = build_editor_shell(self, build_window_schema(self.schema), self.status_var)
        self.status_label = shell.status_label

        list_handles = build_editor_list_panel(
            shell.left_body,
            title_var=self.element_title_var,
            meta_var=self.element_meta_var,
            search_var=self.element_search_var,
            on_select=self.on_element_list_select,
            on_clear=lambda: self.element_search_var.set(""),
            on_prev=lambda: self.change_element(-1),
            on_next=lambda: self.change_element(1),
            schema=WEAPON_ELEMENT_LIST_SCHEMA,
        )
        self.element_listbox = list_handles.listbox
        self.batch_controller = EditorBatchSelectionController(
            self,
            listbox=self.element_listbox,
            get_visible_ids=lambda: [element.index for element in self.filtered_elements],
            get_current_id=lambda: self.current_element_index if self.current_main_bytes is not None else None,
            select_id=self.select_element,
            fields=[EditorBatchField(label, byte_width) for label, byte_width in self.schema.section.fields],
            read_values=self.read_core_values,
            apply_updates=self.apply_batch_updates,
            restore_values=self.restore_batch_snapshot,
            set_status=self.set_status,
            title="Weapon Element Multi-Slot Editor",
            noun="elements",
        )

        self.element_canvas = WeaponElementConstellationCanvas(shell.center_body, self)
        build_editor_center_panel(
            shell.center_body,
            canvas=self.element_canvas,
            jump_var=self.element_jump_var,
            jump_command=self.jump_to_element,
            on_prev=lambda: self.change_element(-1),
            on_next=lambda: self.change_element(1),
            on_apply=self.apply_current_element,
            schema=build_center_schema(self.schema),
        )

        right_schema = EditorRightSchema(
            intro_text="Mod the element fields. The description panel shows the selected element's known name and effect. Scroll to reach all fields.",
            actions=[
                EditorActionSchema("Save File", self.save_current_files, SELECT_GREEN),
                EditorActionSchema("Reload File", self.reload_files, SELECT_GOLD, fg="#180E2B"),
                EditorActionSchema("Close Editor", self.on_close_request, SELECT_BLUE),
            ],
        )
        scroll_handles = build_scrollable_editor_panel(shell.right_body, dirty_var=self.dirty_var, schema=right_schema)

        field_schema = EditorFieldSectionSchema(
            title=self.schema.section.section_title,
            subtitle=self.schema.section.section_subtitle,
            fields=[EditorFieldSchema(label, byte_width) for label, byte_width in self.schema.section.fields],
            columns=self.schema.section.columns,
        )
        field_handles = build_field_section(
            scroll_handles.fields_wrap,
            schema=field_schema,
            on_change=self.on_core_field_changed,
            helper_text_factory=lambda byte_width: helper_text_for_sized_value(0, byte_width),
        )
        self.core_field_vars = field_handles.vars
        self.core_field_entries = field_handles.entries
        self.core_field_helpers = field_handles.helpers

        build_description_section(
            scroll_handles.fields_wrap,
            title="Element Description",
            textvariable=self.element_desc_var,
            wraplength=500,
        )

    def set_status(self, text: str, color: str = STATUS_GOOD):
        self.status_var.set(text)
        self.status_label.config(fg=color)

    def get_element_display_name(self, element_index: int) -> str:
        return self.schema.element_names.get(element_index, f"{self.schema.placeholder_prefix} {element_index + 1:03d}")

    def get_element_slot_label(self, element_index: int) -> str:
        name = self.get_element_display_name(element_index)
        fallback = f"Element {element_index + 1:03d}"
        return name if name == fallback else f"{name} | {element_index + 1:03d}"

    def element_main_offset(self, element_index: int) -> int:
        return self.schema.section.offset + (element_index * self.record_size)

    def read_main_record(self, element_index: int, blob: Optional[bytes] = None) -> bytes:
        source = blob if blob is not None else self.current_main_bytes
        if source is None:
            return b""
        start = self.element_main_offset(element_index)
        return bytes(source[start : start + self.record_size])

    def read_core_values(self, element_index: int, blob: Optional[bytes] = None) -> List[int]:
        record = self.read_main_record(element_index, blob)
        if len(record) < self.record_size:
            return [0] * len(self.schema.section.fields)
        values: List[int] = []
        cursor = 0
        for _field_name, byte_width in self.schema.section.fields:
            values.append(int.from_bytes(record[cursor : cursor + byte_width], "little", signed=False))
            cursor += byte_width
        return values

    def batch_field_offsets(self) -> List[Tuple[int, int]]:
        return linear_field_offsets(self.schema.section.fields)

    def apply_batch_updates(self, element_indices: Sequence[int], updates: Sequence[Tuple[int, int]]) -> bool:
        if self.current_main_bytes is None:
            return False
        write_batch_record_updates(
            self.current_main_bytes,
            record_offset=self.element_main_offset,
            record_size=self.record_size,
            field_offsets=self.batch_field_offsets(),
            slots=element_indices,
            updates=updates,
        )
        self.files_dirty = bytes(self.current_main_bytes) != self.original_main_bytes
        self.element_dirty = False
        self.load_element_into_fields(self.current_element_index)
        self.sync_element_selection()
        return True

    def restore_batch_snapshot(self, snapshot: Dict[int, List[int]]) -> bool:
        if self.current_main_bytes is None:
            return False
        write_batch_record_snapshots(
            self.current_main_bytes,
            record_offset=self.element_main_offset,
            record_size=self.record_size,
            field_offsets=self.batch_field_offsets(),
            snapshots=snapshot,
        )
        self.files_dirty = bytes(self.current_main_bytes) != self.original_main_bytes
        self.element_dirty = False
        self.load_element_into_fields(self.current_element_index)
        self.sync_element_selection()
        return True

    def element_is_changed(self, element_index: int) -> bool:
        if self.current_main_bytes is None or not self.original_main_bytes:
            return False
        return self.read_main_record(element_index) != self.read_main_record(element_index, self.original_main_bytes)

    def dirty_element_count(self) -> int:
        return sum(1 for element_index in range(self.element_count) if self.element_is_changed(element_index))

    def build_element_description(self) -> str:
        element_name = self.get_element_display_name(self.current_element_index)
        desc = self.schema.element_descriptions.get(self.current_element_index, "No description available for this element slot.")
        return "\n".join(
            [
                f"Element Name : {element_name}",
                "",
                desc,
            ]
        )

    def update_dirty_banner(self):
        if self.element_dirty and self.files_dirty:
            self.dirty_var.set("Disk state: unapplied element edits + unsaved file changes")
        elif self.element_dirty:
            self.dirty_var.set("Disk state: unapplied element edits")
        elif self.files_dirty:
            self.dirty_var.set("Disk state: unsaved file changes in memory")
        else:
            self.dirty_var.set("Disk state: clean")

    def update_meta(self):
        if self.current_main_bytes is None:
            self.element_title_var.set("No element loaded")
            self.element_meta_var.set(f"Load {self.schema.display_name} weapon element data to begin.")
            self.element_desc_var.set("")
            return

        element_name = self.get_element_display_name(self.current_element_index)
        slot_number = self.current_element_index + 1
        self.element_title_var.set(self.get_element_slot_label(self.current_element_index))
        self.element_meta_var.set(
            "\n".join(
                [
                    f"Element Slot   : {element_name} | {slot_number:03d}",
                    f"Main Path      : {os.path.relpath(self.schema.section.file_path, PROJECT_ROOT)}",
                    f"Export Path    : {os.path.relpath(self.schema.section.export_path, PROJECT_ROOT)}",
                    f"Element Slots  : {self.element_count}",
                    f"Dirty Elements : {self.dirty_element_count()}",
                ]
            )
        )
        self.element_desc_var.set(self.build_element_description())

    def update_core_field_helper(self, field_index: int):
        raw = self.core_field_vars[field_index].get()
        entry = self.core_field_entries[field_index]
        helper = self.core_field_helpers[field_index]
        _field_name, byte_width = self.schema.section.fields[field_index]
        try:
            value = parse_sized_int(raw, byte_width)
        except ValueError:
            entry.config(bg=FIELD_INVALID)
            helper.config(text="Invalid value. Use decimal, -1, or 0x-prefixed hex.", fg=STATUS_BAD)
            return
        row = field_index // 2
        entry.config(bg=FIELD_BG if row % 2 == 0 else FIELD_ALT_BG)
        helper.config(text=helper_text_for_sized_value(value, byte_width), fg=SELECT_MUTED)

    def load_element_into_fields(self, element_index: int):
        if self.current_main_bytes is None:
            return
        core_values = self.read_core_values(element_index)
        self._loading_fields = True
        for idx, value in enumerate(core_values):
            _field_name, byte_width = self.schema.section.fields[idx]
            self.core_field_vars[idx].set(format_field_value(byte_width, value))
        self._loading_fields = False
        for idx in range(len(self.schema.section.fields)):
            self.update_core_field_helper(idx)
        self.element_dirty = False
        self.update_dirty_banner()
        self.element_jump_var.set(str(element_index + 1))
        self.element_canvas.render()
        self.update_meta()

    def parse_core_field_values(self) -> Optional[List[int]]:
        values: List[int] = []
        for idx, (field_name, byte_width) in enumerate(self.schema.section.fields):
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

    def apply_current_element(self, *, show_status: bool = True) -> bool:
        if self.current_main_bytes is None:
            return False
        core_values = self.parse_core_field_values()
        if core_values is None:
            return False

        main_record = bytearray(self.read_main_record(self.current_element_index))
        cursor = 0
        for value, (_field_name, byte_width) in zip(core_values, self.schema.section.fields):
            main_record[cursor : cursor + byte_width] = value.to_bytes(byte_width, "little", signed=False)
            cursor += byte_width

        main_start = self.element_main_offset(self.current_element_index)
        main_end = main_start + self.record_size
        main_changed = bytes(self.current_main_bytes[main_start:main_end]) != bytes(main_record)
        if main_changed:
            self.current_main_bytes[main_start:main_end] = main_record
        self.files_dirty = bytes(self.current_main_bytes) != self.original_main_bytes
        self.element_dirty = False
        self.update_meta()
        self.update_dirty_banner()
        self.element_canvas.render()
        if show_status:
            color = STATUS_GOOD if main_changed else STATUS_WARN
            self.set_status(f"Applied {self.elements[self.current_element_index].label} to memory. Save File when you're ready.", color)
        return True

    def save_current_files(self) -> bool:
        if self.current_main_bytes is None:
            return False
        if self.element_dirty and not self.apply_current_element(show_status=False):
            return False
        had_unsaved_changes = self.files_dirty
        try:
            os.makedirs(os.path.dirname(self.schema.section.export_path), exist_ok=True)
            with open(self.schema.section.export_path, "wb") as handle:
                handle.write(self.current_main_bytes)
        except OSError as exc:
            messagebox.showerror("Save Failed", f"Could not export weapon element file:\n{exc}")
            self.set_status("Could not export the weapon element file.", STATUS_BAD)
            return False
        self.original_main_bytes = bytes(self.current_main_bytes)
        self.files_dirty = False
        self.element_dirty = False
        self.update_meta()
        self.update_dirty_banner()
        self.element_canvas.render()
        suffix = " (clean copy)" if not had_unsaved_changes else ""
        self.set_status(f"Exported {os.path.relpath(self.schema.section.export_path, PROJECT_ROOT)}{suffix}.", STATUS_GOOD)
        return True

    def load_files(self) -> bool:
        if not os.path.isfile(self.schema.section.file_path):
            messagebox.showerror("Missing Weapon Element File", f"Could not find:\n{self.schema.section.file_path}")
            self.set_status(f"Missing {self.schema.display_name} weapon element file.", STATUS_BAD)
            return False
        try:
            with open(self.schema.section.file_path, "rb") as handle:
                main_blob = handle.read()
        except OSError as exc:
            messagebox.showerror("Read Failed", f"Could not read the weapon element file:\n{exc}")
            self.set_status(f"Could not read the {self.schema.display_name} weapon element file.", STATUS_BAD)
            return False

        required_main = self.schema.section.offset + (self.element_count * self.record_size)
        if len(main_blob) < required_main:
            messagebox.showerror("Weapon Element File Too Small", f"{self.schema.section.file_label} does not contain the full reversed element block.")
            self.set_status(f"{self.schema.display_name} weapon element file is too small for the reversed block.", STATUS_BAD)
            return False

        self.current_main_bytes = bytearray(main_blob)
        self.original_main_bytes = bytes(main_blob)
        self.current_element_index = 0
        self.files_dirty = False
        self.element_dirty = False
        self.update_meta()
        self.load_element_into_fields(0)
        self.sync_element_selection()
        self.set_status(f"Loaded {self.schema.section.file_label}", STATUS_GOOD)
        return True

    def confirm_file_transition(self, reason: str) -> bool:
        if self.current_main_bytes is None:
            return True
        if self.element_dirty and not self.apply_current_element(show_status=False):
            return False
        if not self.files_dirty:
            return True
        choice = messagebox.askyesnocancel("Unsaved Weapon Element Changes", f"Export changes from {self.schema.section.file_label} before {reason}?")
        if choice is None:
            return False
        return self.save_current_files() if choice else True

    def reload_files(self):
        if self.current_main_bytes is None:
            return
        if self.element_dirty or self.files_dirty:
            if not messagebox.askyesno("Reload Weapon Element File", f"Reloading {self.schema.section.file_label} will discard unapplied and unsaved changes. Continue?"):
                return
        self.load_files()

    def refresh_element_list(self):
        query = self.element_search_var.get().strip().lower()
        self.filtered_elements = [
            element
            for element in self.elements
            if not query
            or query in element.label.lower()
            or query in element.name.lower()
            or query in f"{element.index + 1}"
            or query in f"{element.index + 1:03d}"
        ]
        self._suppress_list_event = True
        try:
            self.element_listbox.delete(0, tk.END)
            for element in self.filtered_elements:
                self.element_listbox.insert(tk.END, element.label)
        finally:
            self._suppress_list_event = False
        self.sync_element_selection()

    def sync_element_selection(self):
        self._suppress_list_event = True
        try:
            if hasattr(self, "batch_controller"):
                self.batch_controller.sync_from_editor()
                return
            self.element_listbox.selection_clear(0, tk.END)
            visible_index = next(
                (idx for idx, element in enumerate(self.filtered_elements) if element.index == self.current_element_index),
                None,
            )
            if visible_index is not None:
                self.element_listbox.selection_set(visible_index)
                self.element_listbox.activate(visible_index)
                self.element_listbox.see(visible_index)
        finally:
            self._suppress_list_event = False

    def on_element_list_select(self, _event):
        if self._suppress_list_event:
            return
        selection = self.element_listbox.curselection()
        if not selection:
            return
        target = self.filtered_elements[selection[0]]
        self.select_element(target.index)

    def select_element(self, element_index: int):
        if self.current_main_bytes is None or element_index < 0 or element_index >= self.element_count:
            return
        if element_index == self.current_element_index:
            self.sync_element_selection()
            return
        if self.element_dirty and not self.apply_current_element(show_status=False):
            self.sync_element_selection()
            return
        self.current_element_index = element_index
        self.load_element_into_fields(element_index)
        self.sync_element_selection()
        self.element_canvas.focus_on_element(element_index)
        self.set_status(f"Selected {self.elements[element_index].label}.", STATUS_GOOD)

    def change_element(self, delta: int):
        if self.current_main_bytes is None:
            return
        self.select_element(max(0, min(self.element_count - 1, self.current_element_index + delta)))

    def jump_to_element(self):
        if self.current_main_bytes is None:
            return
        try:
            element_number = int(self.element_jump_var.get().strip(), 10)
        except ValueError:
            messagebox.showerror("Invalid Element Slot", f"Enter a number from 1 to {self.element_count}.")
            self.set_status(f"Element jump failed. Use a decimal number from 1 to {self.element_count}.", STATUS_BAD)
            return
        if element_number < 1 or element_number > self.element_count:
            messagebox.showerror("Invalid Element Slot", f"Element slot number must be between 1 and {self.element_count}.")
            self.set_status(f"Element jump failed. Element slot number must be between 1 and {self.element_count}.", STATUS_BAD)
            return
        self.select_element(element_number - 1)

    def on_core_field_changed(self, field_index: int):
        self.update_core_field_helper(field_index)
        if self._loading_fields:
            return
        self.element_dirty = True
        self.update_dirty_banner()

    def on_close_request(self):
        if not self.confirm_file_transition("closing the weapon element editor"):
            return
        self.destroy()


class DW8XLWeaponElementEditorWindow(WeaponElementEditorWindow):
    def __init__(self, parent: tk.Misc):
        super().__init__(parent, "DW8XL")


class DW8EWeaponElementEditorWindow(WeaponElementEditorWindow):
    def __init__(self, parent: tk.Misc):
        super().__init__(parent, "DW8E")


if __name__ == "__main__":
    raise SystemExit("Run AE/main.pyw to launch Aldnoah Engine tools.")
