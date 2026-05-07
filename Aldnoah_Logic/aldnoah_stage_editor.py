from __future__ import annotations

import math, os, re
import tkinter as tk
from dataclasses import dataclass
from tkinter import messagebox
from typing import Dict, List, Optional, Sequence, Tuple

from .aldnoah_editors import (
    DISABLED_FILL,
    DISABLED_OUTLINE,
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
    SELECT_PANEL_3,
    SELECT_STAR,
    SELECT_SUBTEXT,
    SELECT_TEXT,
    STATUS_BAD,
    STATUS_GOOD,
    STATUS_WARN,
    draw_constellation_backdrop,
    make_stars,
)
from .aldnoah_energy import PROJECT_ROOT, STAGE_EDITOR_SCHEMAS, StageEditorSchema
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
    build_editor_center_panel,
    build_editor_list_panel,
    build_editor_shell,
    build_field_section,
    build_scrollable_editor_panel,
    linear_field_offsets,
    write_batch_record_snapshots,
    write_batch_record_updates,
)


UNUSED_LEADER_ID = 0xFFFFFFFF
STAGE_LIST_SCHEMA = EditorListSchema(prev_label="Prev Stage", next_label="Next Stage")


@dataclass(frozen=True)
class StageInfo:
    ordinal: int
    entry_id: int
    file_rel_path: str
    file_path: str
    export_path: str
    placeholder_prefix: str = "Stage"
    stage_name: Optional[str] = None
    offset: int = 0x7C
    slot_count: int = 120
    slot_size: int = 104

    @property
    def label(self) -> str:
        title = (self.stage_name or "").strip() or f"{self.placeholder_prefix} {self.ordinal}"
        return f"{title} | {self.file_label}"

    @property
    def file_label(self) -> str:
        parts = self.file_rel_path.replace("\\", "/").split("/")
        if len(parts) >= 2 and parts[-2].startswith("entry_"):
            return f"{parts[-2]}/{parts[-1]}"
        return parts[-1]

    @property
    def slot_block_end(self) -> int:
        return self.offset + (self.slot_count * self.slot_size)


def extract_stage_entry_id(path: str) -> int:
    match = re.search(r"entry_(\d+)", path.replace("\\", "/"))
    return int(match.group(1)) if match else -1


def stage_export_path(schema: StageEditorSchema, file_rel_path: str) -> str:
    source_root = os.path.normpath(os.path.join(PROJECT_ROOT, schema.source_root_rel))
    source_path = os.path.normpath(os.path.join(PROJECT_ROOT, file_rel_path))
    try:
        suffix = os.path.relpath(source_path, source_root)
    except ValueError:
        suffix = os.path.basename(source_path)
    return os.path.normpath(os.path.join(schema.export_dir, suffix))


def build_stage_infos(schema: StageEditorSchema) -> List[StageInfo]:
    stage_infos: List[StageInfo] = []
    for ordinal, file_rel_path in enumerate(schema.stage_file_rels, start=1):
        stage_name = schema.stage_names[ordinal - 1] if ordinal <= len(schema.stage_names) else ""
        stage_infos.append(
            StageInfo(
                ordinal=ordinal,
                entry_id=extract_stage_entry_id(file_rel_path),
                file_rel_path=file_rel_path,
                file_path=os.path.normpath(os.path.join(PROJECT_ROOT, file_rel_path)),
                export_path=stage_export_path(schema, file_rel_path),
                placeholder_prefix=schema.placeholder_prefix,
                stage_name=stage_name,
                offset=schema.offset,
                slot_count=schema.slot_count,
                slot_size=schema.slot_size,
            )
        )
    return stage_infos


def exported_stage_path(stage_info: StageInfo) -> str:
    return stage_info.export_path


def u32_to_s32(value: int) -> int:
    return value - 0x100000000 if value & 0x80000000 else value


def parse_u32_text(text: str) -> int:
    raw = (text or "").strip().replace("_", "")
    if not raw:
        raise ValueError("Value cannot be empty.")
    base = 16 if raw.lower().startswith(("0x", "-0x", "+0x")) else 10
    try:
        value = int(raw, base)
    except ValueError as exc:
        raise ValueError("Use decimal, -1, or 0x-prefixed hex.") from exc
    if value < -0x80000000 or value > 0xFFFFFFFF:
        raise ValueError("Value must stay within signed 32-bit or unsigned 32-bit range.")
    return value & 0xFFFFFFFF


def format_stage_value(field_name: str, value: int) -> str:
    if "Coord" in field_name:
        return str(u32_to_s32(value))
    if field_name.startswith("Unknown"):
        return f"0x{value:08X}"
    signed = u32_to_s32(value)
    return str(signed if signed < 0 else value)


def helper_text_for_value(value: int) -> str:
    return f"u32 {value} | i32 {u32_to_s32(value)} | 0x{value:08X}"


def build_slot_bytes(values: Sequence[int]) -> bytes:
    blob = bytearray()
    for value in values:
        blob.extend((value & 0xFFFFFFFF).to_bytes(4, "little", signed=False))
    return bytes(blob)


def build_window_schema(schema: StageEditorSchema) -> EditorWindowSchema:
    return EditorWindowSchema(
        window_title=f"{schema.display_name} Stage Editor",
        hero=EditorHeroSchema(
            title=f"{schema.display_name} Stage Editor",
            subtitle=f"Navigate the {schema.display_name} stage files, select a squad slot, and mod every field in the reversed stage block.",
            star_seed=schema.hero_star_seed,
            star_count=schema.hero_star_count,
        ),
        left_panel=EditorPanelSchema("Stage Lattice", f"Select the {schema.display_name} stage file you want to edit.", SELECT_BLUE),
        center_panel=EditorPanelSchema("Squad Constellation", f"Navigate the {schema.slot_count} squad slots.", SELECT_GOLD),
        right_panel=EditorPanelSchema("Squad Field Editor", "Edit every field for the selected slot and export a full stage file copy.", SELECT_GREEN),
        geometry="1700x1080",
        min_width=1500,
        min_height=940,
        column_weights=(2, 3, 4),
        uniform="stage",
    )


def build_center_schema() -> EditorCenterSchema:
    return EditorCenterSchema(
        prev_label="Prev Slot",
        next_label="Next Slot",
        apply_label="Apply Slot",
        hint_text="Changed slots glow green after they are applied to memory. Drag inside the constellation to pan, use the mouse wheel to zoom, and zoom further in if you want slot ids to appear above each node. Save Stage File creates a full exported stage copy under the project root.",
    )


class StageSlotConstellationCanvas(tk.Canvas):
    def __init__(self, parent: tk.Misc, controller: "StageEditorWindow"):
        super().__init__(parent, bg=SELECT_BG, highlightthickness=0, bd=0, relief="flat")
        self.controller = controller
        self.item_to_slot: Dict[int, int] = {}
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
        if self._dragging:
            self.pan_x = self._press_pan[0] + dx
            self.pan_y = self._press_pan[1] + dy
            self.render()

    def on_release(self, event):
        if self._dragging:
            return
        for item_id in reversed(self.find_overlapping(event.x - 8, event.y - 8, event.x + 8, event.y + 8)):
            slot_index = self.item_to_slot.get(item_id)
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

    def position_groups(self, width: int, height: int) -> List[List[Tuple[int, float, float]]]:
        slot_count = self.controller.current_stage.slot_count if self.controller.current_stage is not None else self.controller.schema.slot_count
        arms = max(1, min(self.controller.schema.constellation_arms, slot_count))
        slots_per_arm = max(1, math.ceil(slot_count / arms))
        groups: List[List[Tuple[int, float, float]]] = []
        for arm in range(arms):
            angle = (-math.pi / 2.0) + (arm * ((math.pi * 2.0) / arms))
            arm_points: List[Tuple[int, float, float]] = []
            for step in range(slots_per_arm):
                slot_index = arm * slots_per_arm + step
                if slot_index >= slot_count:
                    break
                t = step / max(1, slots_per_arm - 1)
                radius = 32.0 + (t * max(120.0, min(width, height) * 0.42))
                bend = math.sin((step * 0.55) + (arm * 0.85)) * 0.18
                arm_points.append((slot_index, math.cos(angle + bend) * radius, math.sin(angle + bend) * radius * 0.76))
            if arm_points:
                groups.append(arm_points)
        return groups

    def positions(self, width: int, height: int) -> List[Tuple[int, float, float]]:
        return [point for group in self.position_groups(width, height) for point in group]

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
        self.item_to_slot.clear()
        width = max(1, self.winfo_width())
        height = max(1, self.winfo_height())
        draw_constellation_backdrop(self, width, height, self.stars, self.phase)
        self.create_text(18, 16, anchor="nw", text="Squad Constellation", fill=SELECT_TEXT, font=("Segoe UI", 15, "bold"))
        self.create_text(20, 44, anchor="nw", text="Gold is selected, green is modded, violet is active data, and grey is dormant. Drag to pan, wheel to zoom, and zoom further in to reveal slot ids.", fill=SELECT_SUBTEXT, font=("Segoe UI", 9), width=max(200, width - 40))
        if self.controller.current_stage is None or self.controller.current_stage_bytes is None:
            self.create_text(width * 0.5, height * 0.56, text="Load a stage file to light the squad lattice.", fill=SELECT_SUBTEXT, font=("Segoe UI", 11))
            return
        projected_groups = [
            [
                (slot_index, (width * 0.50) + self.pan_x + (wx * self.zoom), (height * 0.54) + self.pan_y + (wy * self.zoom))
                for slot_index, wx, wy in group
            ]
            for group in self.position_groups(width, height)
        ]
        projected = [point for group in projected_groups for point in group]
        for arm_points in projected_groups:
            for idx in range(len(arm_points) - 1):
                _, ax, ay = arm_points[idx]
                _, bx, by = arm_points[idx + 1]
                self.create_line(ax, ay, bx, by, fill=SELECT_LINE, width=1 if self.zoom < 1.5 else 2)
        zoom_scale = max(0.8, min(2.0, self.zoom))
        for slot_index, px, py in projected:
            selected = self.controller.current_slot_index == slot_index
            changed = self.controller.slot_is_changed(slot_index)
            active = self.controller.slot_has_data(slot_index)
            if selected:
                halo_r = max(14, min(28, (17 + math.sin(self.phase * 2.0 + (slot_index * 0.3)) * 2) * zoom_scale))
                halo = self.create_oval(px - halo_r, py - halo_r, px + halo_r, py + halo_r, outline=SELECT_GOLD, width=1, stipple="gray25")
                self.item_to_slot[halo] = slot_index
            radius = max(8, min(18, int(10 * zoom_scale))) if selected else max(6 if changed else (5 if active else 4), min(14 if changed else (12 if active else 10), int((8 if changed else (7 if active else 5)) * zoom_scale)))
            fill = SELECT_NODE_SEL if selected else (SELECT_GREEN if changed else (SELECT_NODE if active else DISABLED_FILL))
            outline = SELECT_GOLD if selected else ("#A8E3B9" if changed else (SELECT_NODE_RING if active else DISABLED_OUTLINE))
            orb = self.create_oval(px - radius, py - radius, px + radius, py + radius, fill=fill, outline=outline, width=2 if selected else 1)
            self.item_to_slot[orb] = slot_index
            if self.zoom >= 1.6:
                label = self.create_text(px, py - max(14, int(14 * zoom_scale)), text=str(slot_index), fill=SELECT_TEXT if selected else SELECT_SUBTEXT, font=("Segoe UI", max(8, min(11, int(8 * zoom_scale))), "bold"))
                self.item_to_slot[label] = slot_index


class StageEditorWindow(tk.Toplevel):
    def __init__(self, parent: tk.Misc, game_id: str):
        schema = STAGE_EDITOR_SCHEMAS.get(game_id)
        if schema is None:
            raise ValueError(f"{game_id} stage data is not wired into Aldnoah yet.")
        super().__init__(parent)
        self.game_id = game_id
        self.schema = schema
        self.field_names = tuple(schema.fields)
        self.leader_field_index = self.field_names.index(schema.leader_field)
        self.stage_infos = build_stage_infos(schema)
        self.filtered_stage_infos = list(self.stage_infos)
        self.current_stage: Optional[StageInfo] = None
        self.current_stage_bytes: Optional[bytearray] = None
        self.original_stage_bytes = b""
        self.current_slot_index = 0
        self.stage_dirty = False
        self.slot_dirty = False
        self._loading_fields = False
        self._suppress_stage_list_event = False
        self.stage_search_var = tk.StringVar(value="")
        self.stage_title_var = tk.StringVar(value="No stage loaded")
        self.stage_meta_var = tk.StringVar(value=f"Select a {self.schema.display_name} stage file to begin.")
        self.status_var = tk.StringVar(value=f"Ready to edit the {self.schema.display_name} stage squad block.")
        self.dirty_var = tk.StringVar(value="Disk state: clean")
        self.slot_jump_var = tk.StringVar(value="0")
        self.field_vars: List[tk.StringVar] = []
        self.field_entries: List[tk.Entry] = []
        self.field_helper_labels: List[tk.Label] = []
        self.build_gui()
        self.stage_search_var.trace_add("write", lambda *_: self.refresh_stage_list())
        self.refresh_stage_list()
        first_stage = next((stage for stage in self.stage_infos if os.path.isfile(stage.file_path)), self.stage_infos[0] if self.stage_infos else None)
        if first_stage is not None:
            self.load_stage(first_stage)
        self.protocol("WM_DELETE_WINDOW", self.on_close_request)

    def build_gui(self):
        shell = build_editor_shell(self, build_window_schema(self.schema), self.status_var)
        self.status_label = shell.status_label
        list_handles = build_editor_list_panel(shell.left_body, title_var=self.stage_title_var, meta_var=self.stage_meta_var, search_var=self.stage_search_var, on_select=self.on_stage_list_select, on_clear=lambda: self.stage_search_var.set(""), on_prev=lambda: self.change_stage(-1), on_next=lambda: self.change_stage(1), schema=STAGE_LIST_SCHEMA)
        self.stage_listbox = list_handles.listbox
        self.build_slot_list_panel(shell.left_body)
        self.slot_batch_controller = EditorBatchSelectionController(
            self,
            listbox=self.slot_listbox,
            get_visible_ids=lambda: list(range(self.current_stage.slot_count)) if self.current_stage is not None else [],
            get_current_id=lambda: self.current_slot_index if self.current_stage is not None and self.current_stage_bytes is not None else None,
            select_id=self.select_slot,
            fields=[EditorBatchField(field_name, 4) for field_name in self.field_names],
            read_values=self.read_slot_values,
            apply_updates=self.apply_batch_updates,
            restore_values=self.restore_batch_snapshot,
            set_status=self.set_status,
            title="Stage Squad Multi-Slot Editor",
            noun="slots",
            one_based_ranges=False,
        )
        self.slot_canvas = StageSlotConstellationCanvas(shell.center_body, self)
        build_editor_center_panel(shell.center_body, canvas=self.slot_canvas, jump_var=self.slot_jump_var, jump_command=self.jump_to_slot, on_prev=lambda: self.change_slot(-1), on_next=lambda: self.change_slot(1), on_apply=self.apply_current_slot, schema=build_center_schema())
        scroll = build_scrollable_editor_panel(shell.right_body, dirty_var=self.dirty_var, schema=EditorRightSchema(intro_text="Every field is moddable.", actions=[EditorActionSchema("Save Stage File", self.save_current_stage, SELECT_GREEN), EditorActionSchema("Reload Stage File", self.reload_current_stage, SELECT_GOLD, fg="#180E2B"), EditorActionSchema("Close Editor", self.on_close_request, SELECT_BLUE)]))
        handles = build_field_section(scroll.fields_wrap, schema=EditorFieldSectionSchema("Stage Squad Fields", "Mod every field for the selected squad slot.", [EditorFieldSchema(field_name, 4) for field_name in self.field_names], 2), on_change=self.on_field_changed, helper_text_factory=lambda _byte_width: helper_text_for_value(0))
        self.field_vars, self.field_entries, self.field_helper_labels = handles.vars, handles.entries, handles.helpers

    def build_slot_list_panel(self, parent: tk.Frame):
        slot_shell = tk.Frame(parent, bg=SELECT_PANEL_3, highlightthickness=1, highlightbackground=SELECT_LINE)
        slot_shell.grid(row=6, column=0, sticky="ew", padx=18, pady=(8, 18))
        slot_shell.grid_columnconfigure(0, weight=1)
        tk.Label(slot_shell, text="Squad Slot Range", bg=SELECT_PANEL_3, fg="#180E2B", font=("Segoe UI", 10, "bold"), anchor="w").grid(row=0, column=0, sticky="ew", padx=10, pady=(8, 4))
        slot_wrap = tk.Frame(slot_shell, bg=SELECT_PANEL_3)
        slot_wrap.grid(row=1, column=0, sticky="ew", padx=10, pady=(0, 10))
        slot_wrap.grid_columnconfigure(0, weight=1)
        self.slot_listbox = tk.Listbox(
            slot_wrap,
            height=8,
            selectmode=tk.EXTENDED,
            bg="#120E1B",
            fg="#E9DEF5",
            activestyle="none",
            font=("Consolas", 9),
            relief="flat",
            bd=0,
            highlightthickness=1,
            highlightbackground=SELECT_LINE,
            selectbackground="#6B57C8",
            selectforeground=SELECT_TEXT,
        )
        self.slot_listbox.grid(row=0, column=0, sticky="ew")
        slot_scroll = tk.Scrollbar(slot_wrap, orient="vertical", command=self.slot_listbox.yview)
        slot_scroll.grid(row=0, column=1, sticky="ns")
        self.slot_listbox.config(yscrollcommand=slot_scroll.set)

    def set_status(self, text: str, color: str = STATUS_GOOD):
        self.status_var.set(text)
        self.status_label.config(fg=color)

    def slot_offset(self, slot_index: int) -> int:
        return self.current_stage.offset + (slot_index * self.current_stage.slot_size)

    def read_slot_values(self, slot_index: int, blob: Optional[bytes] = None) -> List[int]:
        if self.current_stage is None:
            return [0] * len(self.field_names)
        source = blob if blob is not None else self.current_stage_bytes
        if source is None:
            return [0] * len(self.field_names)
        base = self.slot_offset(slot_index)
        return [int.from_bytes(source[base + (idx * 4) : base + ((idx + 1) * 4)], "little", signed=False) for idx in range(len(self.field_names))]

    def batch_field_offsets(self) -> List[Tuple[int, int]]:
        return linear_field_offsets([(field_name, 4) for field_name in self.field_names])

    def apply_batch_updates(self, slot_indices: Sequence[int], updates: Sequence[Tuple[int, int]]) -> bool:
        if self.current_stage is None or self.current_stage_bytes is None:
            return False
        write_batch_record_updates(
            self.current_stage_bytes,
            record_offset=self.slot_offset,
            record_size=self.current_stage.slot_size,
            field_offsets=self.batch_field_offsets(),
            slots=slot_indices,
            updates=updates,
        )
        self.stage_dirty = bytes(self.current_stage_bytes) != self.original_stage_bytes
        self.slot_dirty = False
        self.load_slot_into_fields(self.current_slot_index)
        self.refresh_slot_list()
        self.sync_slot_range_selection()
        return True

    def restore_batch_snapshot(self, snapshot: Dict[int, List[int]]) -> bool:
        if self.current_stage is None or self.current_stage_bytes is None:
            return False
        write_batch_record_snapshots(
            self.current_stage_bytes,
            record_offset=self.slot_offset,
            record_size=self.current_stage.slot_size,
            field_offsets=self.batch_field_offsets(),
            snapshots=snapshot,
        )
        self.stage_dirty = bytes(self.current_stage_bytes) != self.original_stage_bytes
        self.slot_dirty = False
        self.load_slot_into_fields(self.current_slot_index)
        self.refresh_slot_list()
        self.sync_slot_range_selection()
        return True

    def slot_has_data(self, slot_index: int) -> bool:
        return bool(self.current_stage is not None and self.current_stage_bytes is not None and self.read_slot_values(slot_index)[self.leader_field_index] != UNUSED_LEADER_ID)

    def slot_is_changed(self, slot_index: int) -> bool:
        if self.current_stage is None or self.current_stage_bytes is None or not self.original_stage_bytes:
            return False
        base = self.slot_offset(slot_index)
        return bytes(self.current_stage_bytes[base : base + self.current_stage.slot_size]) != self.original_stage_bytes[base : base + self.current_stage.slot_size]

    def dirty_slot_count(self) -> int:
        return 0 if self.current_stage is None else sum(1 for slot_index in range(self.current_stage.slot_count) if self.slot_is_changed(slot_index))

    def active_slot_count(self) -> int:
        return 0 if self.current_stage is None or self.current_stage_bytes is None else sum(1 for slot_index in range(self.current_stage.slot_count) if self.slot_has_data(slot_index))

    def update_dirty_banner(self):
        self.dirty_var.set("Disk state: unapplied slot edits + unsaved stage changes" if self.slot_dirty and self.stage_dirty else "Disk state: unapplied slot edits" if self.slot_dirty else "Disk state: unsaved stage changes in memory" if self.stage_dirty else "Disk state: clean")

    def update_stage_meta(self):
        if self.current_stage is None:
            self.stage_title_var.set("No stage loaded")
            self.stage_meta_var.set(f"Select a {self.schema.display_name} stage file to begin.")
            return
        self.stage_title_var.set(self.current_stage.label)
        self.stage_meta_var.set("\n".join([f"Entry ID      : {self.current_stage.entry_id}", f"File Path     : {os.path.relpath(self.current_stage.file_path, PROJECT_ROOT)}", f"Export Path   : {os.path.relpath(exported_stage_path(self.current_stage), PROJECT_ROOT)}", f"Squad Count   : {self.current_stage.slot_count}", f"Active Slots  : {self.active_slot_count()}", f"Unused Slots  : {max(0, self.current_stage.slot_count - self.active_slot_count())}", f"Dirty Slots   : {self.dirty_slot_count()}"]))

    def update_field_helper(self, field_index: int):
        try:
            value = parse_u32_text(self.field_vars[field_index].get())
        except ValueError:
            self.field_entries[field_index].config(bg=FIELD_INVALID)
            self.field_helper_labels[field_index].config(text="Invalid value. Use decimal, -1, or 0x-prefixed hex.", fg=STATUS_BAD)
            return
        self.field_entries[field_index].config(bg=FIELD_BG if (field_index // 2) % 2 == 0 else FIELD_ALT_BG)
        self.field_helper_labels[field_index].config(text=helper_text_for_value(value), fg=SELECT_MUTED)

    def load_slot_into_fields(self, slot_index: int):
        if self.current_stage is None or self.current_stage_bytes is None:
            return
        self._loading_fields = True
        for idx, value in enumerate(self.read_slot_values(slot_index)):
            self.field_vars[idx].set(format_stage_value(self.field_names[idx], value))
        self._loading_fields = False
        for idx in range(len(self.field_names)):
            self.update_field_helper(idx)
        self.slot_dirty = False
        self.slot_jump_var.set(str(slot_index))
        self.update_dirty_banner()
        self.slot_canvas.render()
        self.sync_slot_range_selection()

    def apply_current_slot(self, *, show_status: bool = True) -> bool:
        if self.current_stage is None or self.current_stage_bytes is None:
            return False
        values = []
        for idx, field_name in enumerate(self.field_names):
            try:
                values.append(parse_u32_text(self.field_vars[idx].get()))
            except ValueError as exc:
                self.field_entries[idx].focus_set()
                messagebox.showerror("Invalid Field Value", f"{field_name}: {exc}")
                self.set_status(f"{field_name} could not be applied. Fix the field and try again.", STATUS_BAD)
                return False
        start = self.slot_offset(self.current_slot_index)
        new_slot = build_slot_bytes(values)
        changed = bytes(self.current_stage_bytes[start : start + self.current_stage.slot_size]) != new_slot
        if changed:
            self.current_stage_bytes[start : start + self.current_stage.slot_size] = new_slot
        self.stage_dirty = bytes(self.current_stage_bytes) != self.original_stage_bytes
        self.slot_dirty = False
        self.update_stage_meta()
        self.update_dirty_banner()
        self.slot_canvas.render()
        self.refresh_slot_list()
        if show_status:
            self.set_status(f"Applied slot {self.current_slot_index} to memory. Save the stage file when you're ready.", STATUS_GOOD if changed else STATUS_WARN)
        return True

    def save_current_stage(self) -> bool:
        if self.current_stage is None or self.current_stage_bytes is None:
            return False
        if self.slot_dirty and not self.apply_current_slot(show_status=False):
            return False
        export_path = exported_stage_path(self.current_stage)
        had_changes = self.stage_dirty
        try:
            os.makedirs(os.path.dirname(export_path), exist_ok=True)
            with open(export_path, "wb") as handle:
                handle.write(self.current_stage_bytes)
        except OSError as exc:
            messagebox.showerror("Save Failed", f"Could not export {os.path.basename(export_path)}:\n{exc}")
            self.set_status(f"Could not export {os.path.basename(export_path)}.", STATUS_BAD)
            return False
        self.original_stage_bytes = bytes(self.current_stage_bytes)
        self.stage_dirty = False
        self.slot_dirty = False
        self.update_stage_meta()
        self.update_dirty_banner()
        self.slot_canvas.render()
        self.refresh_slot_list()
        self.set_status(f"Exported {os.path.relpath(export_path, PROJECT_ROOT)}" + (" (clean copy)." if not had_changes else "."), STATUS_GOOD)
        return True

    def confirm_stage_transition(self, reason: str) -> bool:
        if self.current_stage is None:
            return True
        if self.slot_dirty and not self.apply_current_slot(show_status=False):
            return False
        if not self.stage_dirty:
            return True
        choice = messagebox.askyesnocancel("Unsaved Stage Changes", f"Export changes from {os.path.basename(self.current_stage.file_path)} before {reason}?")
        return False if choice is None else self.save_current_stage() if choice else True

    def load_stage(self, stage_info: StageInfo) -> bool:
        if not os.path.isfile(stage_info.file_path):
            messagebox.showerror("Missing Stage File", f"Could not find:\n{stage_info.file_path}")
            self.set_status(f"Missing stage file: {os.path.basename(stage_info.file_path)}", STATUS_BAD)
            return False
        try:
            with open(stage_info.file_path, "rb") as handle:
                blob = handle.read()
        except OSError as exc:
            messagebox.showerror("Read Failed", f"Could not read {os.path.basename(stage_info.file_path)}:\n{exc}")
            self.set_status(f"Could not read {os.path.basename(stage_info.file_path)}.", STATUS_BAD)
            return False
        if len(blob) < stage_info.slot_block_end:
            messagebox.showerror("Stage File Too Small", f"{os.path.basename(stage_info.file_path)} does not contain the full reversed slot block.")
            self.set_status(f"{os.path.basename(stage_info.file_path)} is too small for the reversed slot block.", STATUS_BAD)
            return False
        self.current_stage = stage_info
        self.current_stage_bytes = bytearray(blob)
        self.original_stage_bytes = bytes(blob)
        self.current_slot_index = 0
        self.stage_dirty = False
        self.slot_dirty = False
        self.update_stage_meta()
        self.load_slot_into_fields(0)
        self.sync_stage_selection()
        self.refresh_slot_list()
        self.set_status(f"Loaded {os.path.basename(stage_info.file_path)}.", STATUS_GOOD)
        return True

    def reload_current_stage(self):
        if self.current_stage is None:
            return
        if (self.slot_dirty or self.stage_dirty) and not messagebox.askyesno("Reload Stage File", f"Reloading {os.path.basename(self.current_stage.file_path)} will discard unapplied and unsaved changes. Continue?"):
            return
        self.load_stage(self.current_stage)

    def sync_stage_selection(self):
        if self.current_stage is None:
            return
        self._suppress_stage_list_event = True
        try:
            self.stage_listbox.selection_clear(0, "end")
            visible = next((idx for idx, stage in enumerate(self.filtered_stage_infos) if stage.ordinal == self.current_stage.ordinal), None)
            if visible is not None:
                self.stage_listbox.selection_set(visible)
                self.stage_listbox.activate(visible)
                self.stage_listbox.see(visible)
        finally:
            self._suppress_stage_list_event = False

    def refresh_stage_list(self):
        query = self.stage_search_var.get().strip().lower()
        self.filtered_stage_infos = [stage for stage in self.stage_infos if not query or query in stage.label.lower() or query in str(stage.entry_id)]
        self._suppress_stage_list_event = True
        try:
            self.stage_listbox.delete(0, "end")
            for stage_info in self.filtered_stage_infos:
                self.stage_listbox.insert("end", stage_info.label + (" [Missing]" if not os.path.isfile(stage_info.file_path) else ""))
        finally:
            self._suppress_stage_list_event = False
        self.sync_stage_selection()

    def refresh_slot_list(self):
        if not hasattr(self, "slot_listbox"):
            return
        self.slot_listbox.delete(0, "end")
        if self.current_stage is None:
            return
        for slot_index in range(self.current_stage.slot_count):
            state = "active" if self.slot_has_data(slot_index) else "unused"
            changed = " *" if self.slot_is_changed(slot_index) else ""
            self.slot_listbox.insert("end", f"Slot {slot_index:04d} | {state}{changed}")
        self.sync_slot_range_selection()

    def sync_slot_range_selection(self):
        if hasattr(self, "slot_batch_controller"):
            self.slot_batch_controller.sync_from_editor()

    def on_stage_list_select(self, _event):
        if self._suppress_stage_list_event:
            return
        selection = self.stage_listbox.curselection()
        if not selection:
            return
        target = self.filtered_stage_infos[selection[0]]
        if self.current_stage and target.ordinal == self.current_stage.ordinal:
            return
        if not self.confirm_stage_transition(f"loading {os.path.basename(target.file_path)}"):
            self.sync_stage_selection()
            return
        if not self.load_stage(target):
            self.sync_stage_selection()

    def change_stage(self, delta: int):
        if not self.stage_infos:
            return
        if self.current_stage is None:
            self.load_stage(self.stage_infos[0])
            return
        current_index = next((idx for idx, stage in enumerate(self.stage_infos) if stage.ordinal == self.current_stage.ordinal), 0)
        target = self.stage_infos[max(0, min(len(self.stage_infos) - 1, current_index + delta))]
        if target.ordinal != self.current_stage.ordinal and self.confirm_stage_transition(f"loading {os.path.basename(target.file_path)}"):
            self.load_stage(target)

    def select_slot(self, slot_index: int):
        if self.current_stage is None or self.current_stage_bytes is None or not (0 <= slot_index < self.current_stage.slot_count):
            return
        if slot_index == self.current_slot_index:
            self.sync_slot_range_selection()
            return
        if self.slot_dirty and not self.apply_current_slot(show_status=False):
            return
        self.current_slot_index = slot_index
        self.load_slot_into_fields(slot_index)
        self.slot_canvas.focus_on_slot(slot_index)
        self.sync_slot_range_selection()
        self.set_status(f"Selected slot {slot_index}.", STATUS_GOOD)

    def change_slot(self, delta: int):
        if self.current_stage is not None:
            self.select_slot(max(0, min(self.current_stage.slot_count - 1, self.current_slot_index + delta)))

    def jump_to_slot(self):
        if self.current_stage is None:
            return
        try:
            slot_index = int(self.slot_jump_var.get().strip(), 10)
        except ValueError:
            max_slot = self.current_stage.slot_count - 1
            messagebox.showerror("Invalid Slot", f"Enter a slot index from 0 to {max_slot}.")
            self.set_status(f"Slot jump failed. Use a decimal slot index from 0 to {max_slot}.", STATUS_BAD)
            return
        if not (0 <= slot_index < self.current_stage.slot_count):
            max_slot = self.current_stage.slot_count - 1
            messagebox.showerror("Invalid Slot", f"Slot index must stay between 0 and {max_slot}.")
            self.set_status(f"Slot jump failed. Slot index must stay between 0 and {max_slot}.", STATUS_BAD)
            return
        self.select_slot(slot_index)

    def on_field_changed(self, field_index: int):
        self.update_field_helper(field_index)
        if not self._loading_fields:
            self.slot_dirty = True
            self.update_dirty_banner()

    def on_close_request(self):
        if self.confirm_stage_transition("closing the stage editor"):
            self.destroy()


class DW8XLStageEditorWindow(StageEditorWindow):
    def __init__(self, parent: tk.Misc):
        super().__init__(parent, "DW8XL")
