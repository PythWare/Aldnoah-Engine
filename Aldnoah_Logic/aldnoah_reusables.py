from __future__ import annotations

"""Reusable GUI scaffolding for Aldnoah editors"""

"""
Future editor modules can declare small schemas and import these builders
instead of recreating the same Tk shell for every editor
"""

from dataclasses import dataclass
from typing import Callable, Dict, List, Optional, Sequence, Tuple
import tkinter as tk
from tkinter import messagebox, ttk
from .aldnoah_editors import (
    FIELD_ALT_BG,
    FIELD_BG,
    FIELD_OUTLINE,
    FIELD_TEXT,
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
    action_button,
    build_panel,
    draw_constellation_backdrop,
    make_stars,
)
from .aldnoah_energy import apply_lilac_to_root, setup_lilac_styles


DEFAULT_EDITOR_HERO_POINTS: Tuple[Tuple[float, float], ...] = (
    (0.06, 0.46),
    (0.17, 0.20),
    (0.30, 0.34),
    (0.44, 0.16),
    (0.58, 0.36),
    (0.72, 0.19),
    (0.86, 0.41),
    (0.93, 0.24),
)


Command = Callable[[], object]
FieldChangeCallback = Callable[[int], object]
HelperTextFactory = Callable[[int], str]
SlotIdGetter = Callable[[], Sequence[int]]
CurrentIdGetter = Callable[[], Optional[int]]
SlotSelectCallback = Callable[[int], object]
BatchReadCallback = Callable[[int], List[int]]
BatchApplyCallback = Callable[[Sequence[int], Sequence[Tuple[int, int]]], bool]
BatchRestoreCallback = Callable[[Dict[int, List[int]]], bool]
BatchFormatCallback = Callable[[int, int], str]
BatchParseCallback = Callable[[int, str], int]


MIXED_VALUE_TEXT = "Mixed Value"
SHIFT_MASK = 0x0001
CTRL_MASK = 0x0004


@dataclass(frozen=True)
class EditorHeroSchema:
    title: str
    subtitle: str
    star_seed: int = 901
    star_count: int = 44
    points: Sequence[Tuple[float, float]] = DEFAULT_EDITOR_HERO_POINTS


@dataclass(frozen=True)
class EditorPanelSchema:
    title: str
    subtitle: str
    accent: str


@dataclass(frozen=True)
class EditorWindowSchema:
    window_title: str
    hero: EditorHeroSchema
    left_panel: EditorPanelSchema
    center_panel: EditorPanelSchema
    right_panel: EditorPanelSchema
    geometry: str = "1780x1120"
    min_width: int = 1500
    min_height: int = 960
    column_weights: Tuple[int, int, int] = (2, 3, 5)
    uniform: str = "editor"


@dataclass(frozen=True)
class EditorActionSchema:
    label: str
    command: Command
    accent: str
    fg: str = SELECT_TEXT


@dataclass(frozen=True)
class EditorListSchema:
    prev_label: str = "Prev"
    next_label: str = "Next"
    clear_label: str = "Clear"
    helper_text: str = "Entries accept decimal, -1, or 0x-prefixed hex."
    list_font: Tuple[str, int] = ("Consolas", 9)
    search_font: Tuple[str, int] = ("Segoe UI", 10)


@dataclass(frozen=True)
class EditorCenterSchema:
    prev_label: str = "Prev"
    next_label: str = "Next"
    jump_label: str = "Go"
    apply_label: str = "Apply"
    hint_text: str = ""
    jump_width: int = 8


@dataclass(frozen=True)
class EditorRightSchema:
    intro_text: str
    actions: Sequence[EditorActionSchema]


@dataclass(frozen=True)
class EditorFieldSchema:
    label: str
    byte_width: int
    default_text: str = "0"


@dataclass(frozen=True)
class EditorFieldSectionSchema:
    title: str
    subtitle: str
    fields: Sequence[EditorFieldSchema]
    columns: int = 2


@dataclass(frozen=True)
class EditorDropdownFieldSchema:
    label: str
    options: Sequence[str]
    default_text: str = ""


@dataclass(frozen=True)
class EditorDropdownSectionSchema:
    title: str
    subtitle: str
    fields: Sequence[EditorDropdownFieldSchema]
    columns: int = 2


@dataclass(frozen=True)
class EditorToggleSectionSchema:
    title: str
    subtitle: str
    toggle_names: Sequence[str]
    columns: int = 4


@dataclass
class EditorShellHandles:
    hero_canvas: tk.Canvas
    content: tk.Frame
    left_body: tk.Frame
    center_body: tk.Frame
    right_body: tk.Frame
    footer: tk.Frame
    status_label: tk.Label


@dataclass
class EditorListHandles:
    search_entry: tk.Entry
    listbox: tk.Listbox


@dataclass
class EditorCenterHandles:
    jump_entry: tk.Entry
    nav_frame: tk.Frame


@dataclass
class EditorScrollableHandles:
    fields_canvas: tk.Canvas
    fields_wrap: tk.Frame
    actions_frame: tk.Frame


@dataclass
class EditorFieldSectionHandles:
    section: tk.Frame
    vars: List[tk.StringVar]
    entries: List[tk.Entry]
    helpers: List[tk.Label]


@dataclass
class EditorDropdownSectionHandles:
    section: tk.Frame
    vars: List[tk.StringVar]
    comboboxes: List[ttk.Combobox]


@dataclass(frozen=True)
class EditorBatchField:
    label: str
    byte_width: int = 4


def parse_sized_batch_int(raw: str, byte_width: int) -> int:
    text = raw.strip()
    if not text:
        raise ValueError("Enter a value.")
    if " " in text:
        text = text.split(" ", 1)[0]
    bits = byte_width * 8
    limit = (1 << bits) - 1
    min_signed = -(1 << (bits - 1))
    base = 16 if text.lower().startswith(("0x", "-0x", "+0x")) else 10
    try:
        value = int(text, base)
    except ValueError as exc:
        raise ValueError("Use decimal, signed decimal, or 0x-prefixed hex.") from exc
    if value < min_signed or value > limit:
        raise ValueError(f"Value must stay within signed {bits}-bit or unsigned {bits}-bit range.")
    return value & limit


def format_batch_int(value: int, byte_width: int) -> str:
    mask = (1 << (byte_width * 8)) - 1
    value &= mask
    return f"0x{value:0{byte_width * 2}X} ({value})"


def summarize_integer_ranges(values: Sequence[int], *, limit: int = 8, one_based: bool = True) -> str:
    ordered = sorted(set(values))
    if not ordered:
        return "None"
    ranges: List[str] = []
    start = ordered[0]
    prev = ordered[0]
    for value in ordered[1:]:
        if value == prev + 1:
            prev = value
            continue
        ranges.append(format_range(start, prev, one_based=one_based))
        start = value
        prev = value
    ranges.append(format_range(start, prev, one_based=one_based))
    if len(ranges) > limit:
        return ", ".join(ranges[:limit]) + f", +{len(ranges) - limit} more"
    return ", ".join(ranges)


def format_range(start: int, end: int, *, one_based: bool) -> str:
    offset = 1 if one_based else 0
    if start == end:
        return str(start + offset)
    return f"{start + offset}-{end + offset}"


def write_batch_record_updates(
    blob: bytearray,
    *,
    record_offset: Callable[[int], int],
    record_size: int,
    field_offsets: Sequence[Tuple[int, int]],
    slots: Sequence[int],
    updates: Sequence[Tuple[int, int]],
) -> bool:
    changed = False
    for slot_index in slots:
        base = record_offset(slot_index)
        record = bytearray(blob[base : base + record_size])
        if len(record) < record_size:
            record.extend(b"\x00" * (record_size - len(record)))
        for field_index, value in updates:
            offset, byte_width = field_offsets[field_index]
            record[offset : offset + byte_width] = value.to_bytes(byte_width, "little", signed=False)
        old = bytes(blob[base : base + record_size])
        new = bytes(record)
        if old != new:
            blob[base : base + record_size] = new
            changed = True
    return changed


def write_batch_record_snapshots(
    blob: bytearray,
    *,
    record_offset: Callable[[int], int],
    record_size: int,
    field_offsets: Sequence[Tuple[int, int]],
    snapshots: Dict[int, List[int]],
) -> bool:
    changed = False
    for slot_index, values in snapshots.items():
        base = record_offset(slot_index)
        record = bytearray(blob[base : base + record_size])
        if len(record) < record_size:
            record.extend(b"\x00" * (record_size - len(record)))
        for field_index, value in enumerate(values[: len(field_offsets)]):
            offset, byte_width = field_offsets[field_index]
            record[offset : offset + byte_width] = value.to_bytes(byte_width, "little", signed=False)
        old = bytes(blob[base : base + record_size])
        new = bytes(record)
        if old != new:
            blob[base : base + record_size] = new
            changed = True
    return changed


def linear_field_offsets(fields: Sequence[Tuple[str, int]], *, extra_flags: Sequence[str] = ()) -> List[Tuple[int, int]]:
    offsets: List[Tuple[int, int]] = []
    cursor = 0
    for _field_name, byte_width in fields:
        offsets.append((cursor, byte_width))
        cursor += byte_width
    for _flag_name in extra_flags:
        offsets.append((cursor, 1))
        cursor += 1
    return offsets


class EditorBatchSelectionController:
    """Shared Shift/Ctrl list multi-select plus a mixed value batch editor"""

    def __init__(
        self,
        owner: tk.Toplevel,
        *,
        listbox: tk.Listbox,
        get_visible_ids: SlotIdGetter,
        get_current_id: CurrentIdGetter,
        select_id: SlotSelectCallback,
        fields: Sequence[EditorBatchField],
        read_values: BatchReadCallback,
        apply_updates: BatchApplyCallback,
        restore_values: BatchRestoreCallback,
        format_value: Optional[BatchFormatCallback] = None,
        parse_value: Optional[BatchParseCallback] = None,
        set_status: Optional[Callable[[str, str], object]] = None,
        title: str = "Multi-Slot Editor",
        noun: str = "slots",
        one_based_ranges: bool = True,
    ):
        self.owner = owner
        self.listbox = listbox
        self.get_visible_ids = get_visible_ids
        self.get_current_id = get_current_id
        self.select_id = select_id
        self.fields = list(fields)
        self.read_values = read_values
        self.apply_updates = apply_updates
        self.restore_values = restore_values
        self.format_value = format_value or (lambda idx, value: format_batch_int(value, self.fields[idx].byte_width))
        self.parse_value = parse_value or (lambda idx, raw: parse_sized_batch_int(raw, self.fields[idx].byte_width))
        self.set_status = set_status
        self.title = title
        self.noun = noun
        self.one_based_ranges = one_based_ranges

        self.selected_ids: List[int] = []
        self.selection_anchor: Optional[int] = None
        self.primary_id: Optional[int] = None
        self._pending_ids: Optional[List[int]] = None
        self._pending_primary: Optional[int] = None

        self.window: Optional[tk.Toplevel] = None
        self.title_var = tk.StringVar(value=title)
        self.info_var = tk.StringVar(value="")
        self.vars: List[tk.StringVar] = []
        self.entries: List[tk.Entry] = []
        self.mixed_flags: List[bool] = []
        self.snapshot_ids: List[int] = []
        self.snapshot_values: Dict[int, List[int]] = {}

        self.listbox.configure(selectmode=tk.EXTENDED)
        self.listbox.bind("<Button-1>", self.on_list_click)
        self.listbox.bind("<Control-Button-1>", self.on_list_click)
        self.listbox.bind("<Shift-Button-1>", self.on_list_click)

    def visible_ids(self) -> List[int]:
        return list(self.get_visible_ids())

    def normalize_ids(self, ids: Sequence[int]) -> List[int]:
        visible = self.visible_ids()
        selected = set(ids)
        return [value for value in visible if value in selected]

    def list_index_for_y(self, y: int) -> Optional[int]:
        if self.listbox.size() <= 0:
            return None
        index = self.listbox.nearest(y)
        if index < 0 or index >= self.listbox.size():
            return None
        bbox = self.listbox.bbox(index)
        if bbox is None:
            return None
        _x, row_y, _w, row_h = bbox
        if y < row_y or y > row_y + row_h:
            return None
        return index

    def on_list_click(self, event):
        visible = self.visible_ids()
        index = self.list_index_for_y(event.y)
        if index is None or index >= len(visible):
            return "break"
        target = visible[index]
        primary = target
        if event.state & SHIFT_MASK and self.selection_anchor in visible:
            anchor_index = visible.index(self.selection_anchor)
            start = min(anchor_index, index)
            end = max(anchor_index, index)
            desired = visible[start : end + 1]
        elif event.state & CTRL_MASK:
            selected = set(self.selected_ids)
            if target in selected:
                selected.remove(target)
            else:
                selected.add(target)
            desired = [value for value in visible if value in selected]
            primary = target if target in desired else (desired[-1] if desired else target)
            if not desired:
                desired = [target]
        else:
            desired = [target]

        self._pending_ids = desired
        self._pending_primary = primary
        try:
            self.select_id(primary)
        finally:
            if self.get_current_id() == primary:
                self.selected_ids = self.normalize_ids(desired)
                if primary not in self.selected_ids:
                    self.selected_ids.append(primary)
                self.primary_id = primary
                self.selection_anchor = primary
                self.sync_listbox_selection()
                self.refresh_batch_from_selection(capture_snapshot=True)
            else:
                self.sync_from_editor()
            self._pending_ids = None
            self._pending_primary = None
        return "break"

    def sync_from_editor(self):
        current = self.get_current_id()
        visible = self.visible_ids()
        if current is None or current not in visible:
            self.selected_ids = []
            self.primary_id = None
            self.selection_anchor = None
            self.sync_listbox_selection()
            self.refresh_batch_from_selection()
            return

        if self._pending_ids is not None and self._pending_primary == current:
            self.selected_ids = self.normalize_ids(self._pending_ids)
            self.primary_id = current
            self.selection_anchor = current
        elif current in self.selected_ids:
            self.selected_ids = self.normalize_ids(self.selected_ids)
            self.primary_id = current
            self.selection_anchor = current
        else:
            self.selected_ids = [current]
            self.primary_id = current
            self.selection_anchor = current
        self.sync_listbox_selection()
        self.refresh_batch_from_selection()

    def sync_listbox_selection(self):
        visible = self.visible_ids()
        selected = set(self.selected_ids)
        self.listbox.selection_clear(0, tk.END)
        for index, slot_id in enumerate(visible):
            if slot_id in selected:
                self.listbox.selection_set(index)
        if self.primary_id in visible:
            index = visible.index(self.primary_id)
            self.listbox.activate(index)
            self.listbox.see(index)

    def ensure_window(self):
        if self.window is not None and self.window.winfo_exists():
            return
        window = tk.Toplevel(self.owner)
        window.withdraw()
        window.title(self.title)
        window.configure(bg=SELECT_BG)
        window.transient(self.owner)
        window.minsize(760, 360)
        window.protocol("WM_DELETE_WINDOW", self.hide_window)

        header = tk.Frame(window, bg=SELECT_PANEL_2, highlightthickness=1, highlightbackground=SELECT_LINE)
        header.pack(fill="x", padx=12, pady=(12, 8))
        tk.Label(header, textvariable=self.title_var, bg=SELECT_PANEL_2, fg=SELECT_TEXT, anchor="w", font=("Segoe UI", 13, "bold")).pack(fill="x", padx=12, pady=(10, 2))
        tk.Label(header, textvariable=self.info_var, bg=SELECT_PANEL_2, fg=SELECT_SUBTEXT, anchor="w", font=("Segoe UI", 9)).pack(fill="x", padx=12, pady=(0, 10))

        shell = tk.Frame(window, bg=SELECT_BG)
        shell.pack(fill="both", expand=True, padx=12, pady=(0, 8))
        shell.grid_rowconfigure(0, weight=1)
        shell.grid_columnconfigure(0, weight=1)

        canvas = tk.Canvas(shell, bg=SELECT_PANEL_3, highlightthickness=1, highlightbackground=SELECT_LINE, bd=0)
        canvas.grid(row=0, column=0, sticky="nsew")
        scrollbar = tk.Scrollbar(shell, orient="vertical", command=canvas.yview)
        scrollbar.grid(row=0, column=1, sticky="ns")
        canvas.configure(yscrollcommand=scrollbar.set)

        inner = tk.Frame(canvas, bg=SELECT_PANEL_3)
        window_id = canvas.create_window((0, 0), window=inner, anchor="nw")
        inner.bind("<Configure>", lambda _e: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.bind("<Configure>", lambda e: canvas.itemconfigure(window_id, width=e.width))

        self.vars = []
        self.entries = []
        for row, field in enumerate(self.fields):
            row_bg = FIELD_BG if row % 2 == 0 else FIELD_ALT_BG
            tk.Label(inner, text=field.label, bg=row_bg, fg=FIELD_TEXT, font=("Segoe UI", 9, "bold"), anchor="w").grid(row=row, column=0, sticky="ew", padx=(8, 4), pady=3, ipady=5)
            var = tk.StringVar(value="")
            entry = tk.Entry(inner, textvariable=var, bg=row_bg, fg=FIELD_TEXT, insertbackground=FIELD_TEXT, relief="flat", bd=0, font=("Consolas", 10))
            entry.grid(row=row, column=1, sticky="ew", padx=(4, 8), pady=3, ipady=5)
            entry.bind("<Return>", lambda _e: self.apply_batch_changes())
            tk.Label(inner, text=f"{field.byte_width} byte", bg=row_bg, fg=SELECT_MUTED, font=("Segoe UI", 8), anchor="w").grid(row=row, column=2, sticky="ew", padx=(0, 8), pady=3)
            self.vars.append(var)
            self.entries.append(entry)
        inner.grid_columnconfigure(1, weight=1)

        actions = tk.Frame(window, bg=SELECT_BG)
        actions.pack(fill="x", padx=12, pady=(0, 12))
        action_button(actions, "Apply To Selection", self.apply_batch_changes, SELECT_GREEN).pack(side="left")
        action_button(actions, "Reload Snapshot", self.reload_snapshot, SELECT_GOLD, fg="#180E2B").pack(side="left", padx=(8, 0))
        action_button(actions, "Close", self.hide_window, SELECT_BLUE).pack(side="right")

        self.window = window

    def position_window(self):
        if self.window is None or not self.window.winfo_exists():
            return
        self.owner.update_idletasks()
        self.window.update_idletasks()
        width = max(760, min(1100, self.owner.winfo_width() - 80))
        height = max(360, min(620, self.owner.winfo_height() - 140))
        x = self.owner.winfo_rootx() + max(24, (self.owner.winfo_width() - width) // 2)
        y = self.owner.winfo_rooty() + 90
        self.window.geometry(f"{width}x{height}+{x}+{y}")

    def hide_window(self):
        if self.window is not None and self.window.winfo_exists():
            self.window.withdraw()

    def capture_snapshot(self):
        ids = self.selected_ids[:]
        self.snapshot_ids = ids
        self.snapshot_values = {slot_id: self.read_values(slot_id) for slot_id in ids}

    def refresh_batch_from_selection(self, *, capture_snapshot: bool = False):
        if len(self.selected_ids) <= 1:
            self.snapshot_ids = []
            self.snapshot_values = {}
            self.hide_window()
            return
        self.ensure_window()
        ids = self.selected_ids[:]
        if capture_snapshot or self.snapshot_ids != ids:
            self.capture_snapshot()
        self.title_var.set(f"{self.title} | {len(ids)} {self.noun} selected")
        self.info_var.set(f"Selection: {summarize_integer_ranges(ids, one_based=self.one_based_ranges)}")
        selected_values = [self.read_values(slot_id) for slot_id in ids]
        self.mixed_flags = []
        for index, _field in enumerate(self.fields):
            values = [slot_values[index] for slot_values in selected_values if index < len(slot_values)]
            if not values:
                values = [0]
            mixed = any(value != values[0] for value in values[1:])
            self.mixed_flags.append(mixed)
            self.vars[index].set(MIXED_VALUE_TEXT if mixed else self.format_value(index, values[0]))
            self.entries[index].configure(bg="#F1E7C6" if mixed else (FIELD_BG if index % 2 == 0 else FIELD_ALT_BG))
        self.position_window()
        if self.window is not None:
            self.window.deiconify()
            self.window.lift()

    def apply_batch_changes(self):
        if len(self.selected_ids) <= 1:
            self.hide_window()
            return
        updates: List[Tuple[int, int]] = []
        for index, field in enumerate(self.fields):
            raw = self.vars[index].get().strip()
            if self.mixed_flags[index] and raw == MIXED_VALUE_TEXT:
                continue
            try:
                value = self.parse_value(index, raw)
            except ValueError as exc:
                messagebox.showerror("Invalid Batch Field Value", f"{field.label}: {exc}")
                self._set_status(f"{field.label} is invalid.", "#FF7B9C")
                return
            updates.append((index, value))
        if not updates:
            self._set_status("No multi-edit changes to apply.", "#F1C85C")
            return
        if self.apply_updates(self.selected_ids[:], updates):
            self._set_status(f"Applied {len(updates)} field{'s' if len(updates) != 1 else ''} across {len(self.selected_ids)} {self.noun}.", "#8FE7A7")
            self.refresh_batch_from_selection(capture_snapshot=False)

    def reload_snapshot(self):
        if len(self.snapshot_ids) <= 1 or not self.snapshot_values:
            self._set_status("No multi-slot snapshot is ready to reload.", "#F1C85C")
            return
        if self.restore_values(dict(self.snapshot_values)):
            self._set_status(f"Reloaded snapshot for {len(self.snapshot_ids)} {self.noun}.", "#8FE7A7")
            self.refresh_batch_from_selection(capture_snapshot=True)

    def _set_status(self, text: str, color: str):
        if self.set_status is not None:
            self.set_status(text, color)


def draw_editor_hero(canvas: tk.Canvas, width: int, height: int, schema: EditorHeroSchema):
    """Draw the shared editor hero banner from a compact schema"""

    canvas.delete("all")
    draw_constellation_backdrop(canvas, width, height, make_stars(schema.star_seed, schema.star_count), 0.0)
    points = [(width * px, height * py) for px, py in schema.points]
    for idx in range(len(points) - 1):
        canvas.create_line(*points[idx], *points[idx + 1], fill=SELECT_LINE, width=1)
    for x, y in points:
        canvas.create_oval(x - 3, y - 3, x + 3, y + 3, fill=SELECT_STAR, outline="")
    canvas.create_text(34, 34, anchor="nw", text=schema.title, fill=SELECT_TEXT, font=("Segoe UI", 26, "bold"))
    canvas.create_text(
        36,
        78,
        anchor="nw",
        text=schema.subtitle,
        fill=SELECT_SUBTEXT,
        font=("Segoe UI", 10),
        width=max(380, width - 120),
    )


def install_constellation_virtualization(canvas: tk.Canvas, *, node_limit: int = 100, margin: int = 72):
    """Cull/cap default slot nodes on shared editor constellation canvases"""

    if getattr(canvas, "ae_constellation_virtualized", False):
        return

    canvas.ae_constellation_virtualized = True
    canvas.ae_virtual_node_limit = int(node_limit)
    canvas.ae_virtual_margin = int(margin)
    canvas.ae_virtual_node_count = 0
    canvas.ae_virtual_label_count = 0
    canvas.ae_virtual_line_count = 0

    original_delete = canvas.delete
    original_create_oval = canvas.create_oval
    original_create_line = canvas.create_line
    original_create_text = canvas.create_text

    node_fills = {SELECT_NODE.lower()}
    priority_fills = {SELECT_NODE_SEL.lower(), SELECT_GREEN.lower()}
    node_outlines = {SELECT_NODE_RING.lower()}
    priority_outlines = {SELECT_GOLD.lower(), "#a8e3b9"}

    def reset_counts():
        canvas.ae_virtual_node_count = 0
        canvas.ae_virtual_label_count = 0
        canvas.ae_virtual_line_count = 0

    def visible_bbox(coords: Tuple[float, ...]) -> bool:
        if len(coords) < 4:
            return True
        xs = coords[0::2]
        ys = coords[1::2]
        min_x, max_x = min(xs), max(xs)
        min_y, max_y = min(ys), max(ys)
        width = max(1, canvas.winfo_width())
        height = max(1, canvas.winfo_height())
        pad = int(getattr(canvas, "ae_virtual_margin", margin))
        return not (max_x < -pad or min_x > width + pad or max_y < -pad or min_y > height + pad)

    def virtual_delete(*args):
        if args and args[0] == "all":
            reset_counts()
        return original_delete(*args)

    def virtual_create_oval(*args, **kwargs):
        coords = tuple(float(v) for v in args[:4]) if len(args) >= 4 else ()
        if coords and not visible_bbox(coords):
            return 0
        fill = str(kwargs.get("fill", "")).lower()
        outline = str(kwargs.get("outline", "")).lower()
        is_default_node = fill in node_fills or outline in node_outlines
        is_priority_node = fill in priority_fills or outline in priority_outlines
        if is_default_node and not is_priority_node:
            limit = int(getattr(canvas, "ae_virtual_node_limit", node_limit))
            if canvas.ae_virtual_node_count >= limit:
                return 0
            canvas.ae_virtual_node_count += 1
        return original_create_oval(*args, **kwargs)

    def virtual_create_line(*args, **kwargs):
        coords = tuple(float(v) for v in args) if len(args) >= 4 else ()
        if coords and not visible_bbox(coords):
            return 0
        if str(kwargs.get("fill", "")).lower() == SELECT_LINE.lower():
            limit = int(getattr(canvas, "ae_virtual_node_limit", node_limit)) * 2
            if canvas.ae_virtual_line_count >= limit:
                return 0
            canvas.ae_virtual_line_count += 1
        return original_create_line(*args, **kwargs)

    def virtual_create_text(*args, **kwargs):
        coords = tuple(float(v) for v in args[:2]) if len(args) >= 2 else ()
        if coords and not visible_bbox((coords[0], coords[1], coords[0], coords[1])):
            return 0
        text_value = str(kwargs.get("text", ""))
        fill = str(kwargs.get("fill", "")).lower()
        if text_value.isdigit() and fill != SELECT_TEXT.lower():
            limit = int(getattr(canvas, "ae_virtual_node_limit", node_limit))
            if canvas.ae_virtual_label_count >= limit:
                return 0
            canvas.ae_virtual_label_count += 1
        return original_create_text(*args, **kwargs)

    canvas.delete = virtual_delete
    canvas.create_oval = virtual_create_oval
    canvas.create_line = virtual_create_line
    canvas.create_text = virtual_create_text


def build_editor_shell(window: tk.Toplevel, schema: EditorWindowSchema, status_var: tk.StringVar) -> EditorShellHandles:
    """Build the standard 3 column Aldnoah editor shell"""

    window.title(schema.window_title)
    window.configure(bg=SELECT_BG)
    window.geometry(schema.geometry)
    window.minsize(schema.min_width, schema.min_height)

    setup_lilac_styles(window)
    apply_lilac_to_root(window)

    window.grid_columnconfigure(0, weight=1)
    window.grid_rowconfigure(1, weight=1)

    hero_canvas = tk.Canvas(window, height=172, bg=SELECT_BG, highlightthickness=0, bd=0, relief="flat")
    hero_canvas.grid(row=0, column=0, sticky="ew", padx=12, pady=(12, 10))
    hero_canvas.bind("<Configure>", lambda e: draw_editor_hero(hero_canvas, e.width, e.height, schema.hero))

    content = tk.Frame(window, bg=SELECT_BG)
    content.grid(row=1, column=0, sticky="nsew", padx=12, pady=(0, 10))
    for column, weight in enumerate(schema.column_weights):
        content.grid_columnconfigure(column, weight=weight, uniform=schema.uniform)
    content.grid_rowconfigure(0, weight=1)

    left_panel = build_panel(content, schema.left_panel.title, schema.left_panel.subtitle, schema.left_panel.accent)
    left_panel["panel"].grid(row=0, column=0, sticky="nsew", padx=(0, 8))
    left_panel["body"].grid_columnconfigure(0, weight=1)
    left_panel["body"].grid_rowconfigure(3, weight=1)

    center_panel = build_panel(content, schema.center_panel.title, schema.center_panel.subtitle, schema.center_panel.accent)
    center_panel["panel"].grid(row=0, column=1, sticky="nsew", padx=8)
    center_panel["body"].grid_columnconfigure(0, weight=1)
    center_panel["body"].grid_rowconfigure(0, weight=1)

    right_panel = build_panel(content, schema.right_panel.title, schema.right_panel.subtitle, schema.right_panel.accent)
    right_panel["panel"].grid(row=0, column=2, sticky="nsew", padx=(8, 0))
    right_panel["body"].grid_columnconfigure(0, weight=1)
    right_panel["body"].grid_rowconfigure(2, weight=1)

    footer = tk.Frame(window, bg=SELECT_PANEL_2, height=42)
    footer.grid(row=2, column=0, sticky="ew", padx=12, pady=(0, 12))
    footer.grid_propagate(False)
    footer.grid_columnconfigure(0, weight=1)

    status_label = tk.Label(
        footer,
        textvariable=status_var,
        bg=SELECT_PANEL_2,
        fg="#8FE7A7",
        anchor="w",
        font=("Segoe UI", 9, "bold"),
    )
    status_label.grid(row=0, column=0, sticky="ew", padx=14, pady=10)

    return EditorShellHandles(
        hero_canvas=hero_canvas,
        content=content,
        left_body=left_panel["body"],
        center_body=center_panel["body"],
        right_body=right_panel["body"],
        footer=footer,
        status_label=status_label,
    )


def build_editor_list_panel(
    parent: tk.Frame,
    *,
    title_var: tk.StringVar,
    meta_var: tk.StringVar,
    search_var: tk.StringVar,
    on_select: Callable[[object], object],
    on_clear: Command,
    on_prev: Command,
    on_next: Command,
    schema: Optional[EditorListSchema] = None,
) -> EditorListHandles:
    """Build the shared searchable list pane used by most editors"""

    schema = schema or EditorListSchema()
    tk.Label(parent, textvariable=title_var, bg=SELECT_PANEL_3, fg="#180E2B", font=("Segoe UI", 17, "bold"), anchor="w", justify="left").grid(row=0, column=0, sticky="ew", padx=18, pady=(18, 6))
    tk.Label(parent, textvariable=meta_var, bg=SELECT_PANEL_3, fg="#3B2E57", font=("Consolas", 10), anchor="w", justify="left").grid(row=1, column=0, sticky="ew", padx=18)

    search_wrap = tk.Frame(parent, bg=SELECT_PANEL_3)
    search_wrap.grid(row=2, column=0, sticky="ew", padx=18, pady=(16, 10))
    search_wrap.grid_columnconfigure(0, weight=1)

    search_entry = tk.Entry(
        search_wrap,
        textvariable=search_var,
        bg=FIELD_BG,
        fg=FIELD_TEXT,
        insertbackground=FIELD_TEXT,
        relief="flat",
        bd=0,
        font=schema.search_font,
    )
    search_entry.grid(row=0, column=0, sticky="ew", ipady=7)
    action_button(search_wrap, schema.clear_label, on_clear, SELECT_BLUE).grid(row=0, column=1, padx=(8, 0))

    list_wrap = tk.Frame(parent, bg=SELECT_PANEL_3)
    list_wrap.grid(row=3, column=0, sticky="nsew", padx=18)
    list_wrap.grid_columnconfigure(0, weight=1)
    list_wrap.grid_rowconfigure(0, weight=1)

    listbox = tk.Listbox(
        list_wrap,
        selectmode=tk.SINGLE,
        bg="#120E1B",
        fg="#E9DEF5",
        activestyle="none",
        font=schema.list_font,
        relief="flat",
        bd=0,
        highlightthickness=1,
        highlightbackground=SELECT_LINE,
        selectbackground="#6B57C8",
        selectforeground=SELECT_TEXT,
    )
    listbox.grid(row=0, column=0, sticky="nsew")
    listbox.bind("<<ListboxSelect>>", on_select)

    scrollbar = tk.Scrollbar(list_wrap, orient="vertical", command=listbox.yview)
    scrollbar.grid(row=0, column=1, sticky="ns")
    listbox.config(yscrollcommand=scrollbar.set)

    nav = tk.Frame(parent, bg=SELECT_PANEL_3)
    nav.grid(row=4, column=0, sticky="ew", padx=18, pady=(12, 8))
    nav.grid_columnconfigure(0, weight=1)
    nav.grid_columnconfigure(1, weight=1)
    action_button(nav, schema.prev_label, on_prev, SELECT_BLUE).grid(row=0, column=0, sticky="ew", padx=(0, 6))
    action_button(nav, schema.next_label, on_next, SELECT_BLUE).grid(row=0, column=1, sticky="ew", padx=(6, 0))

    tk.Label(
        parent,
        text=schema.helper_text,
        bg=SELECT_PANEL_3,
        fg=SELECT_MUTED,
        wraplength=320,
        justify="left",
        anchor="w",
        font=("Segoe UI", 9, "italic"),
    ).grid(row=5, column=0, sticky="ew", padx=18, pady=(0, 18))

    return EditorListHandles(search_entry=search_entry, listbox=listbox)


def build_editor_center_panel(
    parent: tk.Frame,
    *,
    canvas: tk.Canvas,
    jump_var: tk.StringVar,
    jump_command: Command,
    on_prev: Command,
    on_next: Command,
    on_apply: Command,
    schema: EditorCenterSchema,
) -> EditorCenterHandles:
    """Build the shared constellation canvas area and bottom navigation"""

    install_constellation_virtualization(canvas, node_limit=100)
    canvas.grid(row=0, column=0, sticky="nsew", padx=14, pady=(18, 10))

    nav = tk.Frame(parent, bg=SELECT_PANEL_3)
    nav.grid(row=1, column=0, sticky="ew", padx=18, pady=(0, 8))
    nav.grid_columnconfigure(1, weight=1)

    action_button(nav, schema.prev_label, on_prev, SELECT_BLUE).grid(row=0, column=0, padx=(0, 8))
    jump_entry = tk.Entry(
        nav,
        textvariable=jump_var,
        bg=FIELD_BG,
        fg=FIELD_TEXT,
        insertbackground=FIELD_TEXT,
        relief="flat",
        bd=0,
        font=("Consolas", 10),
        width=schema.jump_width,
        justify="center",
    )
    jump_entry.grid(row=0, column=1, sticky="ew", ipady=7)
    jump_entry.bind("<Return>", lambda _e: jump_command())

    action_button(nav, schema.jump_label, jump_command, SELECT_GOLD, fg="#180E2B").grid(row=0, column=2, padx=8)
    action_button(nav, schema.next_label, on_next, SELECT_BLUE).grid(row=0, column=3, padx=(0, 8))
    action_button(nav, schema.apply_label, on_apply, SELECT_GREEN).grid(row=0, column=4)

    tk.Label(
        parent,
        text=schema.hint_text,
        bg=SELECT_PANEL_3,
        fg=SELECT_MUTED,
        wraplength=460,
        justify="left",
        anchor="w",
        font=("Segoe UI", 9, "italic"),
    ).grid(row=2, column=0, sticky="ew", padx=18, pady=(0, 18))

    return EditorCenterHandles(jump_entry=jump_entry, nav_frame=nav)


def build_scrollable_editor_panel(
    parent: tk.Frame,
    *,
    dirty_var: tk.StringVar,
    schema: EditorRightSchema,
) -> EditorScrollableHandles:
    """Build the standard right side scrollable editor area"""

    tk.Label(parent, textvariable=dirty_var, bg=SELECT_PANEL_3, fg="#3B2E57", font=("Segoe UI", 10, "bold"), anchor="w", justify="left").grid(row=0, column=0, sticky="ew", padx=18, pady=(18, 6))
    tk.Label(parent, text=schema.intro_text, bg=SELECT_PANEL_3, fg=SELECT_MUTED, wraplength=620, justify="left", anchor="w", font=("Segoe UI", 9)).grid(row=1, column=0, sticky="ew", padx=18, pady=(0, 10))

    scroll_shell = tk.Frame(parent, bg=SELECT_PANEL_3)
    scroll_shell.grid(row=2, column=0, sticky="nsew", padx=18)
    scroll_shell.grid_rowconfigure(0, weight=1)
    scroll_shell.grid_columnconfigure(0, weight=1)

    fields_canvas = tk.Canvas(scroll_shell, bg=SELECT_PANEL_3, highlightthickness=0, bd=0, relief="flat")
    fields_canvas.grid(row=0, column=0, sticky="nsew")

    scrollbar = tk.Scrollbar(scroll_shell, orient="vertical", command=fields_canvas.yview)
    scrollbar.grid(row=0, column=1, sticky="ns")
    fields_canvas.configure(yscrollcommand=scrollbar.set)

    fields_wrap = tk.Frame(fields_canvas, bg=SELECT_PANEL_3)
    window_id = fields_canvas.create_window((0, 0), window=fields_wrap, anchor="nw")
    fields_wrap.bind("<Configure>", lambda _e: fields_canvas.configure(scrollregion=fields_canvas.bbox("all")))
    fields_canvas.bind("<Configure>", lambda e: fields_canvas.itemconfigure(window_id, width=e.width))

    actions_frame = tk.Frame(parent, bg=SELECT_PANEL_3)
    actions_frame.grid(row=3, column=0, sticky="ew", padx=18, pady=(14, 18))
    for column in range(len(schema.actions)):
        actions_frame.grid_columnconfigure(column, weight=1)
    for index, action in enumerate(schema.actions):
        if len(schema.actions) == 1:
            padx = 0
        elif index == 0:
            padx = (0, 6)
        elif index == len(schema.actions) - 1:
            padx = (6, 0)
        else:
            padx = 6
        action_button(actions_frame, action.label, action.command, action.accent, fg=action.fg).grid(row=0, column=index, sticky="ew", padx=padx)

    return EditorScrollableHandles(fields_canvas=fields_canvas, fields_wrap=fields_wrap, actions_frame=actions_frame)


def build_field_section(
    parent: tk.Frame,
    *,
    schema: EditorFieldSectionSchema,
    on_change: FieldChangeCallback,
    helper_text_factory: HelperTextFactory,
) -> EditorFieldSectionHandles:
    """Build the common 1-4 column labeled field grid used by editors"""

    section = tk.Frame(parent, bg=SELECT_PANEL_2, highlightthickness=1, highlightbackground=SELECT_LINE)
    section.pack(fill="x", pady=(0, 12))
    for column in range(schema.columns):
        section.grid_columnconfigure(column, weight=1)

    tk.Label(section, text=schema.title, bg=SELECT_PANEL_2, fg=SELECT_TEXT, font=("Segoe UI", 11, "bold")).grid(row=0, column=0, columnspan=schema.columns, sticky="w", padx=12, pady=(12, 4))
    tk.Label(section, text=schema.subtitle, bg=SELECT_PANEL_2, fg=SELECT_SUBTEXT, font=("Segoe UI", 9), anchor="w", justify="left", wraplength=620).grid(row=1, column=0, columnspan=schema.columns, sticky="ew", padx=12, pady=(0, 10))

    columns: List[tk.Frame] = []
    for column in range(schema.columns):
        frame = tk.Frame(section, bg=SELECT_PANEL_2)
        left_pad = 12 if column == 0 else 6
        right_pad = 12 if column == schema.columns - 1 else 6
        frame.grid(row=2, column=column, sticky="nsew", padx=(left_pad, right_pad), pady=(0, 12))
        columns.append(frame)

    vars_: List[tk.StringVar] = []
    entries: List[tk.Entry] = []
    helpers: List[tk.Label] = []
    for index, field_schema in enumerate(schema.fields):
        row = index // schema.columns
        bg = FIELD_BG if row % 2 == 0 else FIELD_ALT_BG
        block = tk.Frame(columns[index % schema.columns], bg=bg, highlightthickness=1, highlightbackground=FIELD_OUTLINE, padx=8, pady=8)
        block.pack(fill="x", pady=4)
        tk.Label(block, text=field_schema.label, bg=bg, fg="#24183C", font=("Segoe UI", 10, "bold"), anchor="w").pack(fill="x")
        var = tk.StringVar(value=field_schema.default_text)
        entry = tk.Entry(block, textvariable=var, bg=bg, fg=FIELD_TEXT, insertbackground=FIELD_TEXT, relief="flat", bd=0, font=("Consolas", 10))
        entry.pack(fill="x", ipady=6, pady=(4, 3))
        helper = tk.Label(block, text=helper_text_factory(field_schema.byte_width), bg=bg, fg=SELECT_MUTED, font=("Segoe UI", 8), anchor="w", justify="left")
        helper.pack(fill="x")
        var.trace_add("write", lambda *_args, i=index: on_change(i))
        vars_.append(var)
        entries.append(entry)
        helpers.append(helper)

    return EditorFieldSectionHandles(section=section, vars=vars_, entries=entries, helpers=helpers)


def ensure_combobox_style(parent: tk.Misc, style_name: str, field_bg: str):
    style = ttk.Style(master=parent)
    style.configure(
        style_name,
        fieldbackground=field_bg,
        background=field_bg,
        foreground=FIELD_TEXT,
        selectforeground=FIELD_TEXT,
        arrowsize=14,
        padding=2,
    )
    style.map(
        style_name,
        fieldbackground=[("readonly", field_bg), ("!disabled", field_bg)],
        background=[("readonly", field_bg), ("!disabled", field_bg)],
        foreground=[("readonly", FIELD_TEXT), ("!disabled", FIELD_TEXT)],
        selectbackground=[("readonly", field_bg)],
        selectforeground=[("readonly", FIELD_TEXT)],
    )


def build_dropdown_section(
    parent: tk.Frame,
    *,
    schema: EditorDropdownSectionSchema,
    on_change: FieldChangeCallback,
) -> EditorDropdownSectionHandles:
    """Build a reusable dropdown grid for safe enumerated field values"""

    section = tk.Frame(parent, bg=SELECT_PANEL_2, highlightthickness=1, highlightbackground=SELECT_LINE)
    section.pack(fill="x", pady=(0, 12))
    for column in range(schema.columns):
        section.grid_columnconfigure(column, weight=1)

    tk.Label(section, text=schema.title, bg=SELECT_PANEL_2, fg=SELECT_TEXT, font=("Segoe UI", 11, "bold")).grid(row=0, column=0, columnspan=schema.columns, sticky="w", padx=12, pady=(12, 4))
    tk.Label(section, text=schema.subtitle, bg=SELECT_PANEL_2, fg=SELECT_SUBTEXT, font=("Segoe UI", 9), anchor="w", justify="left", wraplength=620).grid(row=1, column=0, columnspan=schema.columns, sticky="ew", padx=12, pady=(0, 10))

    columns: List[tk.Frame] = []
    for column in range(schema.columns):
        frame = tk.Frame(section, bg=SELECT_PANEL_2)
        left_pad = 12 if column == 0 else 6
        right_pad = 12 if column == schema.columns - 1 else 6
        frame.grid(row=2, column=column, sticky="nsew", padx=(left_pad, right_pad), pady=(0, 12))
        columns.append(frame)

    vars_: List[tk.StringVar] = []
    comboboxes: List[ttk.Combobox] = []
    for index, field_schema in enumerate(schema.fields):
        row = index // schema.columns
        bg = FIELD_BG if row % 2 == 0 else FIELD_ALT_BG
        style_name = "AldnoahEven.TCombobox" if row % 2 == 0 else "AldnoahOdd.TCombobox"
        ensure_combobox_style(parent, style_name, bg)
        block = tk.Frame(columns[index % schema.columns], bg=bg, highlightthickness=1, highlightbackground=FIELD_OUTLINE, padx=8, pady=8)
        block.pack(fill="x", pady=4)
        tk.Label(block, text=field_schema.label, bg=bg, fg="#24183C", font=("Segoe UI", 10, "bold"), anchor="w").pack(fill="x")
        var = tk.StringVar(value=field_schema.default_text)
        combo = ttk.Combobox(block, textvariable=var, values=list(field_schema.options), state="readonly", font=("Segoe UI", 9), style=style_name)
        combo.pack(fill="x", pady=(4, 0))
        var.trace_add("write", lambda *_args, i=index: on_change(i))
        vars_.append(var)
        comboboxes.append(combo)

    return EditorDropdownSectionHandles(section=section, vars=vars_, comboboxes=comboboxes)


def build_toggle_section(
    parent: tk.Frame,
    *,
    schema: EditorToggleSectionSchema,
    on_toggle: Command,
) -> List[tk.IntVar]:
    """Build the standard flag/toggle grid section and return the variables"""

    section = tk.Frame(parent, bg=SELECT_PANEL_2, highlightthickness=1, highlightbackground=SELECT_LINE)
    section.pack(fill="x", pady=(0, 12))
    tk.Label(section, text=schema.title, bg=SELECT_PANEL_2, fg=SELECT_TEXT, font=("Segoe UI", 11, "bold")).grid(row=0, column=0, sticky="w", padx=12, pady=(12, 4))
    tk.Label(section, text=schema.subtitle, bg=SELECT_PANEL_2, fg=SELECT_SUBTEXT, font=("Segoe UI", 9), anchor="w", justify="left", wraplength=620).grid(row=1, column=0, sticky="ew", padx=12, pady=(0, 10))

    toggle_grid = tk.Frame(section, bg=SELECT_PANEL_2)
    toggle_grid.grid(row=2, column=0, sticky="ew", padx=12, pady=(0, 12))
    for column in range(schema.columns):
        toggle_grid.grid_columnconfigure(column, weight=1)

    toggle_vars: List[tk.IntVar] = []
    for index, toggle_name in enumerate(schema.toggle_names):
        column = index % schema.columns
        row = index // schema.columns
        bg = FIELD_BG if row % 2 == 0 else FIELD_ALT_BG
        var = tk.IntVar(value=0)
        toggle = tk.Checkbutton(
            toggle_grid,
            text=toggle_name,
            variable=var,
            command=on_toggle,
            indicatoron=False,
            relief="flat",
            bd=0,
            bg=bg,
            fg="#24183C",
            activebackground=FIELD_ALT_BG,
            activeforeground="#24183C",
            selectcolor=SELECT_GREEN,
            font=("Segoe UI", 8, "bold"),
            padx=6,
            pady=6,
            cursor="hand2",
        )
        toggle.grid(row=row, column=column, sticky="ew", padx=4, pady=4)
        toggle_vars.append(var)

    return toggle_vars


def build_description_section(
    parent: tk.Misc,
    *,
    title: str,
    textvariable: tk.StringVar,
    panel_bg: str = SELECT_PANEL_2,
    line_color: str = SELECT_LINE,
    title_fg: str = SELECT_TEXT,
    body_fg: str = SELECT_SUBTEXT,
    wraplength: int = 500,
) -> tk.Label:
    """Build a simple bordered description block and return the body label"""

    section = tk.Frame(parent, bg=panel_bg, highlightthickness=1, highlightbackground=line_color)
    section.pack(fill="x", pady=(0, 12))

    tk.Label(section, text=title, bg=panel_bg, fg=title_fg, font=("Segoe UI", 10, "bold")).pack(anchor="w", padx=10, pady=5)

    body = tk.Label(
        section,
        textvariable=textvariable,
        bg=panel_bg,
        fg=body_fg,
        font=("Segoe UI", 9),
        justify="left",
        wraplength=wraplength,
        anchor="w",
    )
    body.pack(fill="x", padx=10, pady=(0, 10))
    return body
