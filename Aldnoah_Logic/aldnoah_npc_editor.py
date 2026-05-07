from __future__ import annotations

import math, os
import tkinter as tk
from math import ceil
from tkinter import messagebox, ttk
from typing import Dict, List, Optional, Sequence, Tuple

from .aldnoah_editors import (
    FIELD_ALT_BG,
    FIELD_BG,
    FIELD_INVALID,
    FIELD_OUTLINE,
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
    SELECT_SUBTEXT,
    SELECT_TEXT,
    STATUS_BAD,
    STATUS_GOOD,
    STATUS_WARN,
    draw_constellation_backdrop,
    make_stars,
)
from .aldnoah_energy import PROJECT_ROOT, BinaryRecordSectionSchema, NpcEditorSchema, get_npc_editor_schema
from .aldnoah_infos import UNIT_NAMES
from .aldnoah_officer_editor import format_field_value, helper_text_for_sized_value, parse_sized_int
from .aldnoah_reusables import (
    EditorBatchField,
    EditorBatchSelectionController,
    EditorActionSchema,
    EditorCenterSchema,
    EditorFieldSchema,
    EditorHeroSchema,
    EditorListSchema,
    EditorPanelSchema,
    EditorRightSchema,
    EditorToggleSectionSchema,
    EditorWindowSchema,
    build_editor_center_panel,
    build_editor_list_panel,
    build_editor_shell,
    ensure_combobox_style,
    build_scrollable_editor_panel,
    build_toggle_section,
    linear_field_offsets,
    write_batch_record_snapshots,
    write_batch_record_updates,
)

__all__ = ["NPCEditorWindow", "DW8XLNPCEditorWindow", "WO3NPCEditorWindow"]

NPC_LIST_SCHEMA = EditorListSchema(prev_label="Prev Unit", next_label="Next Unit")


def load_indexed_lines(path: str) -> Tuple[str, ...]:
    if not path or not os.path.isfile(path):
        return ()
    numbered: Dict[int, str] = {}
    plain: List[str] = []
    with open(path, "r", encoding="utf-8", errors="replace") as handle:
        for raw_line in handle:
            line = raw_line.rstrip("\r\n")
            stripped = line.strip()
            if ":" in stripped:
                left, right = stripped.split(":", 1)
                if left.strip().isdigit():
                    numbered[int(left.strip(), 10)] = right.strip()
                    continue
            plain.append(line)
    if numbered:
        names = [""] * (max(numbered) + 1)
        for index, name in numbered.items():
            names[index] = name
        names.extend(plain)
        return tuple(names)
    return tuple(plain)


def load_id_name_map(path: str) -> Dict[int, str]:
    mapping: Dict[int, str] = {}
    if not path or not os.path.isfile(path):
        return mapping
    with open(path, "r", encoding="utf-8", errors="replace") as handle:
        for raw_line in handle:
            line = raw_line.strip()
            if not line or ":" not in line:
                continue
            left, right = line.split(":", 1)
            try:
                mapping[int(left.strip(), 10)] = right.strip()
            except ValueError:
                continue
    return mapping


def format_lookup_option(name: str, value: int, *, blank_label: str) -> str:
    title = (name or "").strip() or blank_label
    return f"{title}: {value}"


def parse_lookup_option(text: str) -> int:
    raw = (text or "").strip()
    if ":" in raw:
        suffix = raw.rsplit(":", 1)[1].strip()
        if suffix.lstrip("+-").isdigit():
            return int(suffix, 10)
    raise ValueError("Select a value from the dropdown list.")


def build_window_schema(schema: NpcEditorSchema) -> EditorWindowSchema:
    return EditorWindowSchema(
        window_title=f"{schema.game_id} NPC Editor",
        hero=EditorHeroSchema(
            title=f"{schema.game_id} NPC Editor",
            subtitle=f"Mod the CPU controlled data for {schema.display_name}.",
            star_seed=schema.hero_star_seed,
            star_count=schema.hero_star_count,
        ),
        left_panel=EditorPanelSchema("NPC Lattice", f"Select the {schema.game_id} unit slot you want to edit.", SELECT_BLUE),
        center_panel=EditorPanelSchema("NPC Constellation", f"Navigate the {schema.npc_count} {schema.game_id} unit slots.", SELECT_GOLD),
        right_panel=EditorPanelSchema("NPC Field Editor", f"Edit the schema-driven unit data for {schema.game_id}.", SELECT_GREEN),
        column_weights=(2, 3, 6),
    )


def build_center_schema(schema: NpcEditorSchema) -> EditorCenterSchema:
    return EditorCenterSchema(
        prev_label="Prev Unit",
        next_label="Next Unit",
        apply_label="Apply Unit",
        hint_text=f"Changed unit slots glow green after they are applied to memory. Drag inside the constellation to pan, use the mouse wheel to zoom, and zoom further in if you want slot ids to appear above each node. Save NPC File exports a full copy of {schema.section.file_label} under the project root.",
    )


class NpcConstellationCanvas(tk.Canvas):
    def __init__(self, parent: tk.Misc, controller: "NPCEditorWindow"):
        super().__init__(parent, bg=SELECT_BG, highlightthickness=0, bd=0, relief="flat")
        self.controller = controller
        self.items: Dict[int, int] = {}
        self.phase = 0.0
        self.stars = make_stars(controller.schema.constellation_star_seed, controller.schema.constellation_star_count)
        self.zoom = 1.0
        self.min_zoom = 0.55
        self.max_zoom = 3.45
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

    def positions(self, width: int, height: int) -> List[Tuple[int, float, float]]:
        arms = self.controller.schema.constellation_arms
        per_arm = ceil(self.controller.schema.npc_count / arms)
        outer = max(160.0, min(width, height) * 0.42 * math.sqrt(self.controller.schema.npc_count / 100))
        spacing = 1.25 if self.controller.schema.npc_count >= 1000 else 1.0
        points: List[Tuple[int, float, float]] = []
        for arm in range(arms):
            angle = (-math.pi / 2.0) + (arm * ((math.pi * 2.0) / arms))
            for step in range(per_arm):
                slot_index = arm * per_arm + step
                if slot_index >= self.controller.schema.npc_count:
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
        self.create_text(18, 16, anchor="nw", text="NPC Constellation", fill=SELECT_TEXT, font=("Segoe UI", 15, "bold"))
        self.create_text(20, 44, anchor="nw", text="Gold is selected, green is modded, and violet is loaded. Drag to pan, wheel to zoom, and zoom further in to reveal slot ids.", fill=SELECT_SUBTEXT, font=("Segoe UI", 9), width=max(200, width - 40))
        if self.controller.current_bytes is None:
            self.create_text(width * 0.5, height * 0.56, text=f"Load {self.controller.schema.section.file_label} to light the NPC lattice.", fill=SELECT_SUBTEXT, font=("Segoe UI", 11))
            return
        projected = []
        for slot_index, wx, wy in self.positions(width, height):
            projected.append((slot_index, (width * 0.50) + self.pan_x + (wx * self.zoom), (height * 0.54) + self.pan_y + (wy * self.zoom)))
        per_arm = ceil(self.controller.schema.npc_count / self.controller.schema.constellation_arms)
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


class NPCEditorWindow(tk.Toplevel):
    def __init__(self, parent: tk.Misc, game_id: str):
        super().__init__(parent)
        self.schema = get_npc_editor_schema(game_id)
        self.current_bytes: Optional[bytearray] = None
        self.original_bytes = b""
        self.current_slot_index = 0
        self.files_dirty = False
        self.slot_dirty = False
        self._loading = False
        self._suppress_list = False
        self.name_lines = load_indexed_lines(self.schema.name_list_path)
        self.lookup_maps = {
            "Voice ID": load_id_name_map(self.schema.voice_map_path),
            "Model ID": load_id_name_map(self.schema.model_map_path),
            "Moveset": load_id_name_map(self.schema.moveset_map_path),
        }
        self.dropdown_option_maps = self.build_dropdown_option_maps()
        self.dropdown_field_indices = [idx for idx, (field_name, _byte_width) in enumerate(self.schema.section.fields) if field_name in self.dropdown_option_maps]
        self.numeric_field_indices = [idx for idx in range(len(self.schema.section.fields)) if idx not in self.dropdown_field_indices]
        self.dropdown_base_values = {field_name: tuple(option_map[value] for value in sorted(option_map)) for field_name, option_map in self.dropdown_option_maps.items()}
        self.offsets: Dict[str, Tuple[int, int]] = {}
        cursor = 0
        for field_name, byte_width in self.schema.section.fields:
            self.offsets[field_name] = (cursor, byte_width)
            cursor += byte_width
        self.slot_digits = max(3, len(str(self.schema.npc_count)))
        self.filtered_slots: List[Tuple[int, str, str]] = []
        self.search_var = tk.StringVar(value="")
        self.title_var = tk.StringVar(value="No unit loaded")
        self.meta_var = tk.StringVar(value=f"Load {self.schema.display_name} NPC data to begin.")
        self.status_var = tk.StringVar(value=f"Ready to edit the {self.schema.display_name} unit data.")
        self.dirty_var = tk.StringVar(value="Disk state: clean")
        self.jump_var = tk.StringVar(value="1")
        self.field_vars: List[Optional[tk.StringVar]] = [None] * len(self.schema.section.fields)
        self.field_entries: List[Optional[tk.Entry]] = [None] * len(self.schema.section.fields)
        self.field_helpers: List[Optional[tk.Label]] = [None] * len(self.schema.section.fields)
        self.dropdown_combos: List[Optional[ttk.Combobox]] = [None] * len(self.schema.section.fields)
        self.flag_vars: List[tk.IntVar] = []
        self.build_gui()
        self.search_var.trace_add("write", lambda *_: self.refresh_slot_list())
        self.load_files()
        self.refresh_slot_list()
        self.protocol("WM_DELETE_WINDOW", self.on_close_request)

    def build_gui(self):
        shell = build_editor_shell(self, build_window_schema(self.schema), self.status_var)
        self.status_label = shell.status_label
        self.slot_listbox = build_editor_list_panel(shell.left_body, title_var=self.title_var, meta_var=self.meta_var, search_var=self.search_var, on_select=self.on_slot_list_select, on_clear=lambda: self.search_var.set(""), on_prev=lambda: self.change_slot(-1), on_next=lambda: self.change_slot(1), schema=NPC_LIST_SCHEMA).listbox
        self.batch_controller = EditorBatchSelectionController(
            self,
            listbox=self.slot_listbox,
            get_visible_ids=lambda: [item[0] for item in self.filtered_slots],
            get_current_id=lambda: self.current_slot_index if self.current_bytes is not None else None,
            select_id=self.select_slot,
            fields=self.batch_fields(),
            read_values=self.batch_read_values,
            apply_updates=self.apply_batch_updates,
            restore_values=self.restore_batch_snapshot,
            format_value=self.format_batch_value,
            parse_value=self.parse_batch_value,
            set_status=self.set_status,
            title="NPC Multi-Slot Editor",
            noun="units",
        )
        self.canvas = NpcConstellationCanvas(shell.center_body, self)
        build_editor_center_panel(shell.center_body, canvas=self.canvas, jump_var=self.jump_var, jump_command=self.jump_to_slot, on_prev=lambda: self.change_slot(-1), on_next=lambda: self.change_slot(1), on_apply=self.apply_current_slot, schema=build_center_schema(self.schema))
        intro = f"Mod the {self.schema.section.file_label} unit fields" + (f" and the {len(self.schema.section.toggle_names)} flags" if self.schema.section.toggle_names else "") + ". Known id backed fields use readonly dropdowns so only mapped values are selected."
        scroll = build_scrollable_editor_panel(shell.right_body, dirty_var=self.dirty_var, schema=EditorRightSchema(intro_text=intro, actions=[EditorActionSchema("Save NPC File", self.save_current_files, SELECT_GREEN), EditorActionSchema("Reload NPC File", self.reload_files, SELECT_GOLD, fg="#180E2B"), EditorActionSchema("Close Editor", self.on_close_request, SELECT_BLUE)]))
        self.build_schema_field_section(scroll.fields_wrap)
        if self.schema.section.toggle_names:
            self.flag_vars = build_toggle_section(scroll.fields_wrap, schema=EditorToggleSectionSchema(self.schema.section.toggle_title, self.schema.section.toggle_subtitle, self.schema.section.toggle_names, self.schema.section.toggle_columns), on_toggle=self.on_flag_changed)

    def build_schema_field_section(self, parent: tk.Frame):
        section = tk.Frame(parent, bg=SELECT_PANEL_2, highlightthickness=1, highlightbackground=SELECT_LINE)
        section.pack(fill="x", pady=(0, 12))
        for column in range(self.schema.section.columns):
            section.grid_columnconfigure(column, weight=1)

        tk.Label(section, text=self.schema.section.section_title, bg=SELECT_PANEL_2, fg=SELECT_TEXT, font=("Segoe UI", 11, "bold")).grid(row=0, column=0, columnspan=self.schema.section.columns, sticky="w", padx=12, pady=(12, 4))
        tk.Label(section, text=self.schema.section.section_subtitle, bg=SELECT_PANEL_2, fg=SELECT_SUBTEXT, font=("Segoe UI", 9), anchor="w", justify="left", wraplength=620).grid(row=1, column=0, columnspan=self.schema.section.columns, sticky="ew", padx=12, pady=(0, 10))

        columns: List[tk.Frame] = []
        for column in range(self.schema.section.columns):
            frame = tk.Frame(section, bg=SELECT_PANEL_2)
            left_pad = 12 if column == 0 else 6
            right_pad = 12 if column == self.schema.section.columns - 1 else 6
            frame.grid(row=2, column=column, sticky="nsew", padx=(left_pad, right_pad), pady=(0, 12))
            columns.append(frame)

        for field_index, (field_name, byte_width) in enumerate(self.schema.section.fields):
            row = field_index // self.schema.section.columns
            bg = FIELD_BG if row % 2 == 0 else FIELD_ALT_BG
            block = tk.Frame(columns[field_index % self.schema.section.columns], bg=bg, highlightthickness=1, highlightbackground=FIELD_OUTLINE, padx=8, pady=8)
            block.pack(fill="x", pady=4)
            tk.Label(block, text=field_name, bg=bg, fg="#24183C", font=("Segoe UI", 10, "bold"), anchor="w").pack(fill="x")
            if field_index in self.dropdown_field_indices:
                style_name = "AldnoahEven.TCombobox" if row % 2 == 0 else "AldnoahOdd.TCombobox"
                ensure_combobox_style(parent, style_name, bg)
                default_values = list(self.dropdown_base_values.get(field_name, ()))
                var = tk.StringVar(value=default_values[0] if default_values else "")
                combo = ttk.Combobox(block, textvariable=var, values=default_values, state="readonly", font=("Segoe UI", 9), style=style_name)
                combo.pack(fill="x", pady=(4, 0))
                helper = tk.Label(block, text="Mapped values only. The selected option writes its numeric id.", bg=bg, fg=SELECT_MUTED, font=("Segoe UI", 8), anchor="w", justify="left")
                helper.pack(fill="x", pady=(3, 0))
                var.trace_add("write", lambda *_args, i=field_index: self.on_field_changed(i))
                self.field_vars[field_index] = var
                self.field_helpers[field_index] = helper
                self.dropdown_combos[field_index] = combo
            else:
                field_schema = EditorFieldSchema(field_name, byte_width)
                var = tk.StringVar(value=field_schema.default_text)
                entry = tk.Entry(block, textvariable=var, bg=bg, fg="#20152D", insertbackground="#20152D", relief="flat", bd=0, font=("Consolas", 10))
                entry.pack(fill="x", ipady=6, pady=(4, 3))
                helper = tk.Label(block, text=helper_text_for_sized_value(0, byte_width), bg=bg, fg=SELECT_MUTED, font=("Segoe UI", 8), anchor="w", justify="left")
                helper.pack(fill="x")
                var.trace_add("write", lambda *_args, i=field_index: self.on_field_changed(i))
                self.field_vars[field_index] = var
                self.field_entries[field_index] = entry
                self.field_helpers[field_index] = helper

    def build_dropdown_option_maps(self) -> Dict[str, Dict[int, str]]:
        option_maps: Dict[str, Dict[int, str]] = {}
        field_names = {field_name for field_name, _byte_width in self.schema.section.fields}
        if self.schema.name_field in field_names and not self.schema.names_use_slot_index:
            if self.schema.game_id == "DW8XL":
                option_maps[self.schema.name_field] = {value: format_lookup_option(name, value, blank_label="Unnamed Unit") for value, name in sorted(UNIT_NAMES.items())}
            elif self.name_lines:
                option_maps[self.schema.name_field] = {index: format_lookup_option(name, index, blank_label="Blank Entry") for index, name in enumerate(self.name_lines)}
        for field_name, lookup_map in self.lookup_maps.items():
            if field_name in field_names and lookup_map:
                option_maps[field_name] = {value: format_lookup_option(name, value, blank_label=field_name) for value, name in sorted(lookup_map.items())}
        return option_maps

    def dropdown_label_for_value(self, field_name: str, value: int) -> str:
        option_map = self.dropdown_option_maps.get(field_name, {})
        if value in option_map:
            return option_map[value]
        if field_name == self.schema.name_field:
            return format_lookup_option(self.resolve_name(value), value, blank_label="Blank Entry" if self.name_lines else "Unnamed Unit")
        return format_lookup_option(self.lookup_maps.get(field_name, {}).get(value, ""), value, blank_label=field_name)

    def set_dropdown_value(self, field_index: int, value: int):
        field_name, _byte_width = self.schema.section.fields[field_index]
        combo = self.dropdown_combos[field_index]
        var = self.field_vars[field_index]
        if combo is None or var is None:
            return
        label = self.dropdown_label_for_value(field_name, value)
        values = list(self.dropdown_base_values.get(field_name, ()))
        if label not in values:
            values.append(label)
        combo.configure(values=tuple(values))
        var.set(label)

    def set_status(self, text: str, color: str = STATUS_GOOD):
        self.status_var.set(text)
        self.status_label.config(fg=color)

    def record_offset(self, slot_index: int) -> int:
        return self.schema.section.offset + (slot_index * self.schema.section.record_size)

    def read_record(self, slot_index: int, blob: Optional[bytes] = None) -> bytes:
        source = blob if blob is not None else self.current_bytes
        if source is None:
            return b""
        start = self.record_offset(slot_index)
        return bytes(source[start : start + self.schema.section.record_size])

    def read_values(self, slot_index: int, blob: Optional[bytes] = None) -> List[int]:
        record = self.read_record(slot_index, blob)
        if len(record) < self.schema.section.record_size:
            return [0] * len(self.schema.section.fields)
        values: List[int] = []
        cursor = 0
        for _field_name, byte_width in self.schema.section.fields:
            values.append(int.from_bytes(record[cursor : cursor + byte_width], "little", signed=False))
            cursor += byte_width
        return values

    def read_field(self, slot_index: int, field_name: str, blob: Optional[bytes] = None) -> int:
        record = self.read_record(slot_index, blob)
        if len(record) < self.schema.section.record_size or field_name not in self.offsets:
            return 0
        offset, byte_width = self.offsets[field_name]
        return int.from_bytes(record[offset : offset + byte_width], "little", signed=False)

    def read_flags(self, slot_index: int, blob: Optional[bytes] = None) -> List[int]:
        if not self.schema.section.toggle_names:
            return []
        record = self.read_record(slot_index, blob)
        if len(record) < self.schema.section.record_size:
            return [0] * len(self.schema.section.toggle_names)
        start = sum(byte_width for _field_name, byte_width in self.schema.section.fields)
        return list(record[start : start + len(self.schema.section.toggle_names)])

    def batch_fields(self) -> List[EditorBatchField]:
        return [EditorBatchField(label, byte_width) for label, byte_width in self.schema.section.fields] + [
            EditorBatchField(name, 1) for name in self.schema.section.toggle_names
        ]

    def batch_field_offsets(self) -> List[Tuple[int, int]]:
        return linear_field_offsets(self.schema.section.fields, extra_flags=self.schema.section.toggle_names)

    def batch_read_values(self, slot_index: int) -> List[int]:
        return self.read_values(slot_index) + self.read_flags(slot_index)

    def format_batch_value(self, field_index: int, value: int) -> str:
        core_count = len(self.schema.section.fields)
        if field_index >= core_count:
            return "1" if value else "0"
        field_name, byte_width = self.schema.section.fields[field_index]
        if field_index in self.dropdown_field_indices:
            return self.dropdown_label_for_value(field_name, value)
        return format_field_value(self.schema.section, field_name, byte_width, value)

    def parse_batch_value(self, field_index: int, raw: str) -> int:
        core_count = len(self.schema.section.fields)
        if field_index >= core_count:
            return 1 if parse_sized_int(raw, 1) else 0
        _field_name, byte_width = self.schema.section.fields[field_index]
        if field_index in self.dropdown_field_indices:
            try:
                return parse_lookup_option(raw)
            except ValueError:
                return parse_sized_int(raw, byte_width)
        return parse_sized_int(raw, byte_width)

    def apply_batch_updates(self, slot_indices: Sequence[int], updates: Sequence[Tuple[int, int]]) -> bool:
        if self.current_bytes is None:
            return False
        write_batch_record_updates(
            self.current_bytes,
            record_offset=self.record_offset,
            record_size=self.schema.section.record_size,
            field_offsets=self.batch_field_offsets(),
            slots=slot_indices,
            updates=updates,
        )
        self.files_dirty = bytes(self.current_bytes) != self.original_bytes
        self.slot_dirty = False
        self.load_slot(self.current_slot_index)
        self.refresh_slot_list()
        self.sync_slot_selection()
        return True

    def restore_batch_snapshot(self, snapshot: Dict[int, List[int]]) -> bool:
        if self.current_bytes is None:
            return False
        write_batch_record_snapshots(
            self.current_bytes,
            record_offset=self.record_offset,
            record_size=self.schema.section.record_size,
            field_offsets=self.batch_field_offsets(),
            snapshots=snapshot,
        )
        self.files_dirty = bytes(self.current_bytes) != self.original_bytes
        self.slot_dirty = False
        self.load_slot(self.current_slot_index)
        self.refresh_slot_list()
        self.sync_slot_selection()
        return True

    def resolve_name(self, value: int, slot_index: Optional[int] = None) -> str:
        if self.schema.names_use_slot_index and slot_index is not None:
            return self.name_lines[slot_index].strip() if 0 <= slot_index < len(self.name_lines) else ""
        if self.schema.game_id == "DW8XL":
            return UNIT_NAMES.get(value, "")
        return self.name_lines[value].strip() if 0 <= value < len(self.name_lines) else ""

    def slot_label(self, slot_index: int, values: Optional[Dict[str, int]] = None) -> str:
        if values is None and self.current_bytes is None:
            return f"{self.schema.placeholder_prefix} Slot {slot_index + 1:0{self.slot_digits}d}"
        name_value = (values or {}).get(self.schema.name_field, self.read_field(slot_index, self.schema.name_field))
        resolved = self.resolve_name(name_value, slot_index=slot_index)
        return f"{resolved} | Slot {slot_index + 1:0{self.slot_digits}d}" if resolved else f"{self.schema.placeholder_prefix} Slot {slot_index + 1:0{self.slot_digits}d}"

    def slot_changed(self, slot_index: int) -> bool:
        return self.current_bytes is not None and bool(self.original_bytes) and self.read_record(slot_index) != self.read_record(slot_index, self.original_bytes)

    def dirty_count(self) -> int:
        return sum(1 for slot_index in range(self.schema.npc_count) if self.slot_changed(slot_index))

    def update_dirty(self):
        self.dirty_var.set("Disk state: unapplied unit edits + unsaved file changes" if self.slot_dirty and self.files_dirty else "Disk state: unapplied unit edits" if self.slot_dirty else "Disk state: unsaved file changes in memory" if self.files_dirty else "Disk state: clean")

    def update_meta(self):
        if self.current_bytes is None:
            self.title_var.set("No unit loaded")
            self.meta_var.set(f"Load {self.schema.display_name} NPC data to begin.")
            return
        name_value = self.read_field(self.current_slot_index, self.schema.name_field)
        self.title_var.set(self.slot_label(self.current_slot_index))
        self.meta_var.set("\n".join([f"Unit Slot      : {self.slot_label(self.current_slot_index)}", f"{self.schema.name_field:<14}: {name_value}", f"Main Path      : {os.path.relpath(self.schema.section.file_path, PROJECT_ROOT)}", f"Export Path    : {os.path.relpath(self.schema.section.export_path, PROJECT_ROOT)}", f"Unit Slots     : {self.schema.npc_count}", f"Dirty Units    : {self.dirty_count()}"]))

    def update_helper(self, field_index: int):
        if field_index in self.dropdown_field_indices:
            return
        field_name, byte_width = self.schema.section.fields[field_index]
        entry = self.field_entries[field_index]
        helper = self.field_helpers[field_index]
        var = self.field_vars[field_index]
        if entry is None or helper is None or var is None:
            return
        try:
            value = parse_sized_int(var.get(), byte_width)
        except ValueError:
            entry.config(bg=FIELD_INVALID)
            helper.config(text="Invalid value. Use decimal, -1, or 0x-prefixed hex.", fg=STATUS_BAD)
            return
        entry.config(bg=FIELD_BG if (field_index // self.schema.section.columns) % 2 == 0 else FIELD_ALT_BG)
        helper.config(text=helper_text_for_sized_value(value, byte_width), fg=SELECT_MUTED)

    def load_slot(self, slot_index: int):
        if self.current_bytes is None:
            return
        self._loading = True
        for idx, value in enumerate(self.read_values(slot_index)):
            field_name, byte_width = self.schema.section.fields[idx]
            if idx in self.dropdown_field_indices:
                self.set_dropdown_value(idx, value)
            elif self.field_vars[idx] is not None:
                self.field_vars[idx].set(format_field_value(self.schema.section, field_name, byte_width, value))
        for idx, value in enumerate(self.read_flags(slot_index)):
            self.flag_vars[idx].set(1 if value else 0)
        self._loading = False
        for idx in self.numeric_field_indices:
            self.update_helper(idx)
        self.slot_dirty = False
        self.jump_var.set(str(slot_index + 1))
        self.update_dirty()
        self.canvas.render()
        self.update_meta()

    def parse_values(self) -> Optional[List[int]]:
        values: List[int] = []
        for idx, (field_name, byte_width) in enumerate(self.schema.section.fields):
            var = self.field_vars[idx]
            if var is None:
                values.append(0)
                continue
            if idx in self.dropdown_field_indices:
                try:
                    values.append(parse_lookup_option(var.get()))
                except ValueError as exc:
                    combo = self.dropdown_combos[idx]
                    if combo is not None:
                        combo.focus_set()
                    messagebox.showerror("Invalid Dropdown Value", f"{field_name}: {exc}")
                    self.set_status(f"{field_name} could not be applied. Select a value from the dropdown list.", STATUS_BAD)
                    return None
            else:
                try:
                    values.append(parse_sized_int(var.get(), byte_width))
                except ValueError as exc:
                    entry = self.field_entries[idx]
                    if entry is not None:
                        entry.focus_set()
                    messagebox.showerror("Invalid Field Value", f"{field_name}: {exc}")
                    self.set_status(f"{field_name} could not be applied. Fix the field and try again.", STATUS_BAD)
                    return None
        return values

    def apply_current_slot(self, *, show_status: bool = True) -> bool:
        if self.current_bytes is None:
            return False
        values = self.parse_values()
        if values is None:
            return False
        record = bytearray(self.schema.section.record_size)
        cursor = 0
        for value, (_field_name, byte_width) in zip(values, self.schema.section.fields):
            record[cursor : cursor + byte_width] = value.to_bytes(byte_width, "little", signed=False)
            cursor += byte_width
        for idx, flag_var in enumerate(self.flag_vars):
            record[cursor + idx] = 1 if flag_var.get() else 0
        start = self.record_offset(self.current_slot_index)
        end = start + self.schema.section.record_size
        changed = bytes(self.current_bytes[start:end]) != bytes(record)
        if changed:
            self.current_bytes[start:end] = record
        self.files_dirty = bytes(self.current_bytes) != self.original_bytes
        self.slot_dirty = False
        self.refresh_slot_list()
        self.update_dirty()
        self.update_meta()
        self.canvas.render()
        self.sync_slot_selection()
        if show_status:
            self.set_status(f"Applied {self.slot_label(self.current_slot_index)} to memory. Save NPC File when you're ready.", STATUS_GOOD if changed else STATUS_WARN)
        return True

    def save_current_files(self) -> bool:
        if self.current_bytes is None:
            return False
        if self.slot_dirty and not self.apply_current_slot(show_status=False):
            return False
        had_changes = self.files_dirty
        try:
            os.makedirs(self.schema.section.export_dir, exist_ok=True)
            with open(self.schema.section.export_path, "wb") as handle:
                handle.write(self.current_bytes)
        except OSError as exc:
            messagebox.showerror("Save Failed", f"Could not export NPC file data:\n{exc}")
            self.set_status("Could not export the NPC file.", STATUS_BAD)
            return False
        self.original_bytes = bytes(self.current_bytes)
        self.files_dirty = False
        self.slot_dirty = False
        self.refresh_slot_list()
        self.update_dirty()
        self.update_meta()
        self.canvas.render()
        self.set_status(f"Exported {os.path.relpath(self.schema.section.export_path, PROJECT_ROOT)}" + (" (clean copy)." if not had_changes else "."), STATUS_GOOD)
        return True

    def load_files(self) -> bool:
        if not os.path.isfile(self.schema.section.file_path):
            messagebox.showerror("Missing NPC File", f"Could not find:\n{self.schema.section.file_path}")
            self.set_status(f"Missing {self.schema.game_id} NPC file.", STATUS_BAD)
            return False
        try:
            with open(self.schema.section.file_path, "rb") as handle:
                blob = handle.read()
        except OSError as exc:
            messagebox.showerror("Read Failed", f"Could not read the NPC file:\n{exc}")
            self.set_status(f"Could not read the {self.schema.game_id} NPC file.", STATUS_BAD)
            return False
        required = self.schema.section.offset + (self.schema.npc_count * self.schema.section.record_size)
        if len(blob) < required:
            messagebox.showerror("NPC File Too Small", f"{self.schema.section.file_label} does not contain the full reversed NPC block.")
            self.set_status(f"{self.schema.game_id} NPC file is too small for the reversed block.", STATUS_BAD)
            return False
        self.current_bytes = bytearray(blob)
        self.original_bytes = bytes(blob)
        self.current_slot_index = 0
        self.files_dirty = False
        self.slot_dirty = False
        self.refresh_slot_list()
        self.load_slot(0)
        self.sync_slot_selection()
        self.set_status(f"Loaded {self.schema.section.file_label}.", STATUS_GOOD)
        return True

    def confirm_transition(self, reason: str) -> bool:
        if self.current_bytes is None:
            return True
        if self.slot_dirty and not self.apply_current_slot(show_status=False):
            return False
        if not self.files_dirty:
            return True
        choice = messagebox.askyesnocancel("Unsaved NPC Changes", f"Export changes from {self.schema.section.file_label} before {reason}?")
        return False if choice is None else self.save_current_files() if choice else True

    def reload_files(self):
        if self.current_bytes is None:
            return
        if (self.slot_dirty or self.files_dirty) and not messagebox.askyesno("Reload NPC File", f"Reloading {self.schema.section.file_label} will discard unapplied and unsaved changes. Continue?"):
            return
        self.load_files()

    def refresh_slot_list(self):
        query = self.search_var.get().strip().lower()
        filtered: List[Tuple[int, str, str]] = []
        for slot_index in range(self.schema.npc_count):
            label = self.slot_label(slot_index)
            name_value = self.read_field(slot_index, self.schema.name_field) if self.current_bytes is not None else 0
            resolved = self.resolve_name(name_value, slot_index=slot_index).lower() if self.current_bytes is not None else ""
            search = f"{label.lower()} {slot_index + 1} {slot_index + 1:0{self.slot_digits}d} {name_value} {resolved}"
            if not query or query in search:
                filtered.append((slot_index, label, search))
        self.filtered_slots = filtered
        self._suppress_list = True
        try:
            self.slot_listbox.delete(0, tk.END)
            for _slot_index, label, _search in filtered:
                self.slot_listbox.insert(tk.END, label)
        finally:
            self._suppress_list = False
        self.sync_slot_selection()

    def sync_slot_selection(self):
        self._suppress_list = True
        try:
            if hasattr(self, "batch_controller"):
                self.batch_controller.sync_from_editor()
                return
            self.slot_listbox.selection_clear(0, tk.END)
            visible = next((idx for idx, item in enumerate(self.filtered_slots) if item[0] == self.current_slot_index), None)
            if visible is not None:
                self.slot_listbox.selection_set(visible)
                self.slot_listbox.activate(visible)
                self.slot_listbox.see(visible)
        finally:
            self._suppress_list = False

    def on_slot_list_select(self, _event):
        if not self._suppress_list:
            selection = self.slot_listbox.curselection()
            if selection:
                self.select_slot(self.filtered_slots[selection[0]][0])

    def select_slot(self, slot_index: int):
        if self.current_bytes is None or not (0 <= slot_index < self.schema.npc_count):
            return
        if slot_index == self.current_slot_index:
            self.sync_slot_selection()
            return
        if self.slot_dirty and not self.apply_current_slot(show_status=False):
            self.sync_slot_selection()
            return
        self.current_slot_index = slot_index
        self.load_slot(slot_index)
        self.sync_slot_selection()
        self.canvas.focus_on_slot(slot_index)
        self.set_status(f"Selected {self.slot_label(slot_index)}.", STATUS_GOOD)

    def change_slot(self, delta: int):
        if self.current_bytes is not None:
            self.select_slot(max(0, min(self.schema.npc_count - 1, self.current_slot_index + delta)))

    def jump_to_slot(self):
        raw = self.jump_var.get().strip()
        if self.current_bytes is None or not raw.isdigit():
            self.set_status(f"Unit jump failed. Enter a slot number between 1 and {self.schema.npc_count}.", STATUS_BAD)
            return
        slot_number = int(raw)
        if not (1 <= slot_number <= self.schema.npc_count):
            self.set_status(f"Unit jump failed. Slot number must be between 1 and {self.schema.npc_count}.", STATUS_BAD)
            return
        self.select_slot(slot_number - 1)

    def on_field_changed(self, field_index: int):
        self.update_helper(field_index)
        if not self._loading:
            self.slot_dirty = True
            self.update_dirty()

    def on_flag_changed(self):
        if not self._loading:
            self.slot_dirty = True
            self.update_dirty()

    def on_close_request(self):
        if self.confirm_transition("closing the NPC editor"):
            self.destroy()


class DW8XLNPCEditorWindow(NPCEditorWindow):
    def __init__(self, parent: tk.Misc):
        super().__init__(parent, "DW8XL")


class WO3NPCEditorWindow(NPCEditorWindow):
    def __init__(self, parent: tk.Misc):
        super().__init__(parent, "WO3")
