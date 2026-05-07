from __future__ import annotations

import math, os, random
import tkinter as tk
from dataclasses import dataclass
from tkinter import messagebox
from typing import Dict, List, Optional, Sequence, Set, Tuple

from .aldnoah_energy import apply_lilac_to_root, setup_lilac_styles


PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir))

SELECT_BG = "#0F0C18"
SELECT_BG_2 = "#171224"
SELECT_PANEL = "#1C1530"
SELECT_PANEL_2 = "#281D44"
SELECT_PANEL_3 = "#D7C2EC"
SELECT_TEXT = "#F6F1FF"
SELECT_SUBTEXT = "#CDBCE3"
SELECT_MUTED = "#9D89B8"
SELECT_LINE = "#8E7AE2"
SELECT_STAR = "#EFE8FF"
SELECT_GOLD = "#C9972D"
SELECT_BLUE = "#3F5CA8"
SELECT_GREEN = "#41A35A"
SELECT_NODE = "#6B57C8"
SELECT_NODE_SEL = "#F5D889"
SELECT_NODE_RING = "#A89AF0"
SELECT_AQUA = "#53A0FF"
SELECT_ROSE = "#A6526C"
STATUS_GOOD = "#8FE7A7"
STATUS_WARN = "#F5D889"
STATUS_BAD = "#F08D91"
DISABLED_FILL = "#45395F"
DISABLED_OUTLINE = "#6F618D"
DISABLED_TEXT = "#B8ACD0"
FIELD_BG = "#F7F1FF"
FIELD_ALT_BG = "#EFE2FA"
FIELD_INVALID = "#F4D1D9"
FIELD_OUTLINE = "#C6B0DE"
FIELD_TEXT = "#20152D"

EDITOR_GAME_PROFILES = {
    "DW7XL": {
        "display_name": "Dynasty Warriors 7 XL (PC)",
        "supported": True,
        "summary": "DW7XL GUI Editors for modding.",
    },
    "DW8XL": {
        "display_name": "Dynasty Warriors 8 XL (PC)",
        "supported": True,
        "summary": "DW8XL GUI Editors for modding",
    },
    "DW8E": {
        "display_name": "Dynasty Warriors 8 Empires (PC)",
        "supported": True,
        "summary": "DW8E GUI Editors for modding.",
    },
    "WO3": {
        "display_name": "Warriors Orochi 3 (PC)",
        "supported": True,
        "summary": "WO3 GUI Editors for modding.",
    },
    "WO4": {
        "display_name": "Warriors Orochi 4 (PC)",
        "supported": False,
        "summary": "WO4 keeps its place in the constellation but its editor profiles are not active yet.",
    },
    "BN": {
        "display_name": "Bladestorm Nightmare (PC)",
        "supported": True,
        "summary": "BN GUI Editors for modding.",
    },
    "WAS": {
        "display_name": "Warriors All Stars (PC)",
        "supported": True,
        "summary": "WAS GUI Editors for modding.",
    },
}


@dataclass(frozen=True)
class EditorSpec:
    editor_id: str
    title: str
    summary: str
    accent: str
    supported_games: Tuple[str, ...] = ()


EDITOR_SPECS = [
    EditorSpec(
        "stage",
        "Stage Editor",
        "Mod Stage Data.",
        SELECT_GOLD,
        ("DW7XL", "DW8XL"),
    ),
    EditorSpec("officer", "Officer Editor", "Playable Officer data.", SELECT_BLUE, ("DW7XL", "DW8XL", "DW8E", "WO3", "WAS")),
    EditorSpec("weapon", "Weapon Editor", "Weapon data.", SELECT_BLUE, ("DW8XL", "DW8E", "WO3")),
    EditorSpec("bodyguard", "Bodyguard Editor", "Bodyguard data.", SELECT_GREEN, ("DW8XL",)),
    EditorSpec("npc", "NPC Editor", "CPU controlled data", SELECT_ROSE, ("DW7XL", "DW8XL", "DW8E", "WO3", "BN", "WAS")),
    EditorSpec("npc_tactic", "NPC Tactic Editor", "NPC tactic data.", SELECT_AQUA, ("DW8E",)),
    EditorSpec("animal", "Animal Editor", "Animal data.", SELECT_GREEN, ("DW8XL", "DW8E")),
    EditorSpec("officer_skill", "Officer Skill Editor", "Officer skill data.", SELECT_AQUA, ("DW8XL",)),
    EditorSpec("weapon_element", "Weapon Element Editor", "Weapon element data.", SELECT_AQUA, ("DW8XL", "DW8E")),
    EditorSpec("support_skill", "Support Skill Editor", "Support skill data.", SELECT_ROSE, ("DW8XL", "DW8E")),
]

EDITOR_SPEC_MAP = {spec.editor_id: spec for spec in EDITOR_SPECS}

GAME_EDITOR_SKIES: Dict[str, Tuple[str, ...]] = {
    "DW7XL": ("stage", "officer", "npc"),
    "DW8XL": ("stage", "officer", "weapon", "bodyguard", "npc", "animal", "officer_skill", "weapon_element", "support_skill"),
    "DW8E": ("officer", "weapon", "npc", "npc_tactic", "animal", "weapon_element", "support_skill"),
    "WO3": ("officer", "weapon", "npc"),
    "WO4": (),
    "BN": ("npc",),
    "WAS": ("officer", "npc"),
}

LIVE_GAME_EDITOR_IDS: Dict[str, Tuple[str, ...]] = {
    "DW7XL": ("stage", "officer", "npc"),
    "DW8XL": ("stage", "officer", "weapon", "bodyguard", "npc", "animal", "officer_skill", "weapon_element", "support_skill"),
    "DW8E": ("officer", "weapon", "npc", "npc_tactic", "animal", "weapon_element", "support_skill"),
    "WO3": ("officer", "weapon", "npc"),
    "BN": ("npc",),
    "WAS": ("officer", "npc"),
}


def game_editor_specs(game_id: str) -> List[EditorSpec]:
    return [EDITOR_SPEC_MAP[editor_id] for editor_id in GAME_EDITOR_SKIES.get(game_id, ()) if editor_id in EDITOR_SPEC_MAP]


def live_game_editor_ids(game_id: str) -> Set[str]:
    return set(LIVE_GAME_EDITOR_IDS.get(game_id, ()))
def make_stars(seed: int, count: int) -> List[Tuple[float, float, int]]:
    rnd = random.Random(seed)
    return [(rnd.uniform(0.04, 0.96), rnd.uniform(0.06, 0.94), rnd.randint(1, 3)) for _ in range(count)]


def game_coords(width: int, height: int) -> Dict[str, Tuple[float, float]]:
    return {
        "DW7XL": (width * 0.15, height * 0.29),
        "DW8XL": (width * 0.37, height * 0.20),
        "DW8E": (width * 0.69, height * 0.24),
        "WO3": (width * 0.23, height * 0.66),
        "WO4": (width * 0.52, height * 0.56),
        "BN": (width * 0.52, height * 0.82),
        "WAS": (width * 0.83, height * 0.62),
    }


def draw_constellation_backdrop(canvas: tk.Canvas, width: int, height: int, stars: Sequence[Tuple[float, float, int]], phase: float):
    canvas.create_rectangle(0, 0, width, height, fill=SELECT_BG, outline="")
    canvas.create_rectangle(0, 0, width, int(height * 0.24), fill=SELECT_BG_2, outline="")
    for idx in range(8):
        y = int(height * 0.16) + idx * 72
        sway = math.sin(phase * 0.7 + idx * 0.8) * 11
        canvas.create_line(0, y + sway, width, y - sway, fill="#211A34", width=1)
    ring_w = max(240, int(width * 0.34))
    ring_h = max(170, int(height * 0.30))
    canvas.create_arc(22, 24, 22 + ring_w, 24 + ring_h, start=65, extent=242, style=tk.ARC, outline=SELECT_LINE, width=2)
    canvas.create_arc(width - ring_w - 30, 18, width - 30, 18 + ring_h, start=248, extent=232, style=tk.ARC, outline=SELECT_AQUA, width=2)
    for x, y, radius in stars:
        sx = int(x * width)
        sy = int(y * height)
        canvas.create_oval(sx - radius, sy - radius, sx + radius, sy + radius, fill=SELECT_STAR, outline="")


def draw_panel_header(canvas: tk.Canvas, width: int, height: int, title: str, subtitle: str, accent: str):
    canvas.delete("all")
    canvas.create_rectangle(0, 0, width, height, fill=SELECT_PANEL, outline="")
    canvas.create_rectangle(0, 0, width, height, fill=SELECT_PANEL_2, outline="")
    for idx in range(18):
        x = ((idx * 63) + 26) % max(1, width)
        y = 14 + ((idx * 29) % max(1, height - 22))
        radius = 1 + (idx % 2)
        canvas.create_oval(x - radius, y - radius, x + radius, y + radius, fill=SELECT_STAR, outline="")
    canvas.create_line(18, height - 26, width - 18, height - 26, fill=accent, width=2)
    canvas.create_text(16, 16, anchor="nw", text=title, fill=SELECT_TEXT, font=("Segoe UI", 15, "bold"))
    canvas.create_text(16, 46, anchor="nw", text=subtitle, fill=SELECT_SUBTEXT, font=("Segoe UI", 9), width=max(160, width - 32))


def build_panel(parent: tk.Misc, title: str, subtitle: str, accent: str, *, body_bg: str = SELECT_PANEL_3):
    panel = tk.Frame(parent, bg=SELECT_PANEL, highlightthickness=1, highlightbackground=SELECT_LINE)
    panel.grid_rowconfigure(1, weight=1)
    panel.grid_columnconfigure(0, weight=1)
    header = tk.Canvas(panel, height=96, bg=SELECT_PANEL, highlightthickness=0, bd=0, relief="flat")
    header.grid(row=0, column=0, sticky="ew")
    header.bind("<Configure>", lambda e, c=header, t=title, s=subtitle, a=accent: draw_panel_header(c, e.width, e.height, t, s, a))
    body = tk.Frame(panel, bg=body_bg)
    body.grid(row=1, column=0, sticky="nsew")
    return {"panel": panel, "header": header, "body": body}


def action_button(parent: tk.Misc, text: str, command, bg: str, *, fg: str = SELECT_TEXT):
    active_bg = bg if bg not in (SELECT_BLUE, SELECT_GREEN) else ("#5075D0" if bg == SELECT_BLUE else "#57B771")
    if bg == SELECT_GOLD:
        active_bg = "#E4C970"
    return tk.Button(
        parent,
        text=text,
        command=command,
        bg=bg,
        fg=fg,
        activebackground=active_bg,
        activeforeground=fg,
        relief="flat",
        bd=0,
        padx=12,
        pady=10,
        font=("Segoe UI", 10, "bold"),
        cursor="hand2",
    )
class EditorsSelectConstellationCanvas(tk.Canvas):
    def __init__(self, parent: tk.Misc, controller: "EditorsGameSelect"):
        super().__init__(parent, bg=SELECT_BG, highlightthickness=0, bd=0, relief="flat")
        self.controller = controller
        self.item_to_game: Dict[int, str] = {}
        self.phase = 0.0
        self.stars = make_stars(313, 96)
        self.bind("<Configure>", lambda _e: self.render())
        self.bind("<Button-1>", self.on_click)
        self.bind("<Double-Button-1>", lambda _e: self.controller.open_selected_game())
        self.after(120, self.tick)

    def tick(self):
        self.phase += 0.08
        if self.winfo_exists():
            self.render()
            self.after(120, self.tick)

    def on_click(self, event):
        hit = self.find_overlapping(event.x - 5, event.y - 5, event.x + 5, event.y + 5)
        for item_id in reversed(hit):
            game_id = self.item_to_game.get(item_id)
            if game_id:
                self.controller.select_game(game_id)
                return

    def render(self):
        self.delete("all")
        self.item_to_game.clear()
        width = max(1, self.winfo_width())
        height = max(1, self.winfo_height())
        coords = game_coords(width, height)

        draw_constellation_backdrop(self, width, height, self.stars, self.phase)
        links = [
            ("DW7XL", "DW8XL"),
            ("DW8XL", "DW8E"),
            ("DW7XL", "WO3"),
            ("WO3", "WO4"),
            ("WO4", "BN"),
            ("BN", "WAS"),
            ("DW8E", "WAS"),
            ("DW8XL", "WO4"),
            ("DW8XL", "BN"),
        ]
        for left, right in links:
            ax, ay = coords[left]
            bx, by = coords[right]
            self.create_line(ax, ay, bx, by, fill=SELECT_LINE, width=2)

        self.create_text(20, 18, anchor="nw", text="Editor Constellation Gateway", fill=SELECT_TEXT, font=("Segoe UI", 17, "bold"))
        self.create_text(
            22,
            48,
            anchor="nw",
            text="Choose the game sky whose editor tools you want to launch.",
            fill=SELECT_SUBTEXT,
            font=("Segoe UI", 9),
            width=max(220, width - 260),
        )
        self.create_text(width - 18, 22, anchor="ne", text="Select a game sky for editors", fill=SELECT_SUBTEXT, font=("Segoe UI", 10, "italic"))

        for game_id, profile in EDITOR_GAME_PROFILES.items():
            gx, gy = coords[game_id]
            selected = self.controller.selected_game_id == game_id
            active = self.controller.is_hub_open(game_id)
            supported = profile["supported"]
            pulse = 13 + math.sin(self.phase * 2.0 + gx * 0.01) * 3
            radius = 13 if selected else 10
            if supported:
                fill = SELECT_NODE_SEL if selected else (SELECT_GREEN if active else SELECT_NODE)
                outline = SELECT_GOLD if selected else (SELECT_GREEN if active else SELECT_NODE_RING)
                label_fill = SELECT_TEXT
                sub_fill = SELECT_SUBTEXT
                badge_text = "OPEN" if active else "LIVE"
                badge_fill = "#D8FFEA" if active else STATUS_GOOD
            else:
                fill = "#64577D" if selected else DISABLED_FILL
                outline = STATUS_WARN if selected else DISABLED_OUTLINE
                label_fill = "#DDD2EE" if selected else DISABLED_TEXT
                sub_fill = "#B9AED0" if selected else "#9889B7"
                badge_text = "SOON"
                badge_fill = "#D8CCE8"

            halo = self.create_oval(gx - pulse * 2, gy - pulse * 2, gx + pulse * 2, gy + pulse * 2, outline=outline, width=1, stipple="gray25")
            orb = self.create_oval(gx - radius, gy - radius, gx + radius, gy + radius, fill=fill, outline=outline, width=2)
            short = self.create_text(gx, gy - 26, text=game_id, fill=label_fill, font=("Segoe UI", 10, "bold"))
            label = self.create_text(gx, gy + 30, text=profile["display_name"].replace(" (PC)", ""), fill=sub_fill, font=("Segoe UI", 9), width=180)
            badge = self.create_text(gx + 20, gy - 14, text=badge_text, fill=badge_fill, font=("Segoe UI", 8, "bold"))
            for item in (halo, orb, short, label, badge):
                self.item_to_game[item] = game_id


class EditorOrbitCanvas(tk.Canvas):
    def __init__(self, parent: tk.Misc, controller: "GameEditorsWindow"):
        super().__init__(parent, bg=SELECT_BG, highlightthickness=0, bd=0, relief="flat")
        self.controller = controller
        self.item_to_editor: Dict[int, str] = {}
        self.phase = 0.0
        self.stars = make_stars(417, 84)
        self.bind("<Configure>", lambda _e: self.render())
        self.bind("<Button-1>", self.on_click)
        self.bind("<Double-Button-1>", lambda _e: self.controller.open_selected_editor())
        self.after(120, self.tick)

    def tick(self):
        self.phase += 0.08
        if self.winfo_exists():
            self.render()
            self.after(120, self.tick)

    def editor_coords(self, width: int, height: int) -> Dict[str, Tuple[float, float]]:
        return {
            "stage": (width * 0.16, height * 0.28),
            "officer": (width * 0.42, height * 0.17),
            "weapon": (width * 0.73, height * 0.22),
            "bodyguard": (width * 0.31, height * 0.48),
            "npc": (width * 0.58, height * 0.45),
            "npc_tactic": (width * 0.83, height * 0.54),
            "animal": (width * 0.16, height * 0.73),
            "officer_skill": (width * 0.41, height * 0.78),
            "weapon_element": (width * 0.64, height * 0.76),
            "support_skill": (width * 0.87, height * 0.64),
        }

    def on_click(self, event):
        hit = self.find_overlapping(event.x - 5, event.y - 5, event.x + 5, event.y + 5)
        for item_id in reversed(hit):
            editor_id = self.item_to_editor.get(item_id)
            if editor_id:
                self.controller.select_editor(editor_id)
                return

    def render(self):
        self.delete("all")
        self.item_to_editor.clear()
        width = max(1, self.winfo_width())
        height = max(1, self.winfo_height())
        coords = self.editor_coords(width, height)
        visible_ids = {spec.editor_id for spec in self.controller.editor_specs}

        draw_constellation_backdrop(self, width, height, self.stars, self.phase)
        links = [
            ("stage", "officer"),
            ("officer", "weapon"),
            ("stage", "weapon"),
            ("weapon", "bodyguard"),
            ("bodyguard", "npc"),
            ("weapon", "animal"),
            ("animal", "officer_skill"),
            ("officer_skill", "weapon_element"),
            ("weapon_element", "support_skill"),
            ("bodyguard", "weapon_element"),
            ("officer", "npc"),
            ("npc", "support_skill"),
            ("weapon", "npc_tactic"),
            ("npc", "npc_tactic"),
            ("officer", "npc_tactic"),
        ]
        for left, right in links:
            if left not in visible_ids or right not in visible_ids:
                continue
            ax, ay = coords[left]
            bx, by = coords[right]
            self.create_line(ax, ay, bx, by, fill=SELECT_LINE, width=2)

        self.create_text(20, 18, anchor="nw", text="Editor Orbit", fill=SELECT_TEXT, font=("Segoe UI", 17, "bold"))
        self.create_text(width - 18, 22, anchor="ne", text=f"{self.controller.profile['display_name']} editor sky", fill=SELECT_SUBTEXT, font=("Segoe UI", 10, "italic"))

        if not self.controller.editor_specs:
            self.create_text(width * 0.5, height * 0.56, text="This game's editor sky has not been mapped yet.", fill=SELECT_SUBTEXT, font=("Segoe UI", 11))
            return

        for spec in self.controller.editor_specs:
            gx, gy = coords[spec.editor_id]
            selected = self.controller.selected_editor_id == spec.editor_id
            active = self.controller.is_editor_open(spec.editor_id)
            available = self.controller.is_editor_available(spec.editor_id)
            pulse = 13 + math.sin(self.phase * 2.0 + gx * 0.01) * 3
            radius = 13 if selected else 10
            if available:
                fill = SELECT_NODE_SEL if selected else (SELECT_GREEN if active else SELECT_NODE)
                outline = SELECT_GOLD if selected else (SELECT_GREEN if active else SELECT_NODE_RING)
                title_fill = SELECT_TEXT
                sub_fill = SELECT_SUBTEXT
                badge_text = "OPEN" if active else "LIVE"
                badge_fill = "#D8FFEA" if active else STATUS_GOOD
            else:
                fill = "#64577D" if selected else DISABLED_FILL
                outline = STATUS_WARN if selected else DISABLED_OUTLINE
                title_fill = "#DDD2EE" if selected else DISABLED_TEXT
                sub_fill = "#B9AED0" if selected else "#9889B7"
                badge_text = "SOON"
                badge_fill = "#D8CCE8"

            halo = self.create_oval(gx - pulse * 2, gy - pulse * 2, gx + pulse * 2, gy + pulse * 2, outline=outline, width=1, stipple="gray25")
            orb = self.create_oval(gx - radius, gy - radius, gx + radius, gy + radius, fill=fill, outline=outline, width=2)
            short = self.create_text(gx, gy - 26, text=spec.title.replace(" Editor", ""), fill=title_fill, font=("Segoe UI", 9, "bold"), width=160)
            label = self.create_text(gx, gy + 30, text=spec.title, fill=sub_fill, font=("Segoe UI", 9), width=170)
            badge = self.create_text(gx + 20, gy - 14, text=badge_text, fill=badge_fill, font=("Segoe UI", 8, "bold"))
            for item in (halo, orb, short, label, badge):
                self.item_to_editor[item] = spec.editor_id


class EditorsGameSelect(tk.Toplevel):
    def __init__(self, parent: tk.Misc):
        super().__init__(parent)
        self.child_windows: Dict[str, Optional["GameEditorsWindow"]] = {}
        self.selected_game_id = "DW8XL"
        self.status_var = tk.StringVar(value="Select a constellation to open its editors.")
        self.selected_title_var = tk.StringVar(value="")
        self.selected_meta_var = tk.StringVar(value="")
        self.selected_desc_var = tk.StringVar(value="")
        self.game_buttons: Dict[str, tk.Button] = {}

        self.title("Aldnoah Editor Constellation Gateway")
        self.configure(bg=SELECT_BG)
        self.geometry("1220x1000")
        self.minsize(1080, 900)

        setup_lilac_styles(self)
        apply_lilac_to_root(self)

        self.build_gui()
        self.select_game(self.selected_game_id, update_status=False)

    def build_gui(self):
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(1, weight=1)

        hero = tk.Canvas(self, height=168, bg=SELECT_BG, highlightthickness=0, bd=0, relief="flat")
        hero.grid(row=0, column=0, sticky="ew", padx=12, pady=(12, 10))
        hero.bind("<Configure>", lambda e: self.draw_hero(hero, e.width, e.height))

        content = tk.Frame(self, bg=SELECT_BG)
        content.grid(row=1, column=0, sticky="nsew", padx=12, pady=(0, 10))
        content.grid_columnconfigure(0, weight=3)
        content.grid_columnconfigure(1, weight=2)
        content.grid_rowconfigure(0, weight=1)

        left = build_panel(content, "Game Field of Stars", "Launch the game-specific editor hub from a live constellation map.", SELECT_BLUE)
        left["panel"].grid(row=0, column=0, sticky="nsew", padx=(0, 8))
        left["body"].grid_rowconfigure(0, weight=1)
        left["body"].grid_columnconfigure(0, weight=1)

        self.selector_canvas = EditorsSelectConstellationCanvas(left["body"], self)
        self.selector_canvas.grid(row=0, column=0, sticky="nsew", padx=14, pady=(14, 10))

        hint = tk.Label(left["body"], text="Tip: double click a live game star to jump straight into its editor hub.", bg=SELECT_PANEL_3, fg=SELECT_MUTED, anchor="w", font=("Segoe UI", 9, "italic"))
        hint.grid(row=1, column=0, sticky="ew", padx=16, pady=(0, 14))

        right = build_panel(content, "Selected Editor Sky", "Review support, live editor count, and launch state before opening a game hub.", SELECT_GOLD)
        right["panel"].grid(row=0, column=1, sticky="nsew", padx=(8, 0))
        right["body"].grid_columnconfigure(0, weight=1)

        tk.Label(right["body"], textvariable=self.selected_title_var, bg=SELECT_PANEL_3, fg="#180E2B", font=("Segoe UI", 18, "bold"), anchor="w", justify="left").grid(row=0, column=0, sticky="ew", padx=18, pady=(18, 6))
        tk.Label(right["body"], textvariable=self.selected_meta_var, bg=SELECT_PANEL_3, fg="#3B2E57", font=("Consolas", 10), anchor="w", justify="left").grid(row=1, column=0, sticky="ew", padx=18)
        tk.Label(right["body"], textvariable=self.selected_desc_var, bg=SELECT_PANEL_3, fg="#33254D", wraplength=360, justify="left", anchor="nw", font=("Segoe UI", 10), height=6).grid(row=2, column=0, sticky="ew", padx=18, pady=(14, 12))

        button_row = tk.Frame(right["body"], bg=SELECT_PANEL_3)
        button_row.grid(row=3, column=0, sticky="ew", padx=18)
        button_row.grid_columnconfigure(0, weight=1)
        button_row.grid_columnconfigure(1, weight=1)

        self.open_button = action_button(button_row, "Open Selected Editor Hub", self.open_selected_game, SELECT_GREEN)
        self.open_button.grid(row=0, column=0, sticky="ew", padx=(0, 6))
        action_button(button_row, "Close Gateway", self.destroy, SELECT_BLUE).grid(row=0, column=1, sticky="ew", padx=(6, 0))

        quick_wrap = tk.Frame(right["body"], bg=SELECT_PANEL_2, highlightthickness=1, highlightbackground=SELECT_LINE)
        quick_wrap.grid(row=4, column=0, sticky="nsew", padx=18, pady=(18, 18))
        quick_wrap.grid_columnconfigure(0, weight=1)
        quick_wrap.grid_columnconfigure(1, weight=1)
        tk.Label(quick_wrap, text="Quick Launch Grid", bg=SELECT_PANEL_2, fg=SELECT_TEXT, font=("Segoe UI", 11, "bold")).grid(row=0, column=0, columnspan=2, sticky="w", padx=12, pady=(12, 4))
        tk.Label(quick_wrap, text="Each game keeps its own editor sky. Greyed nodes stay in place per game until that specific editor work is ready.", bg=SELECT_PANEL_2, fg=SELECT_SUBTEXT, font=("Segoe UI", 9), anchor="w", justify="left", wraplength=340).grid(row=1, column=0, columnspan=2, sticky="ew", padx=12, pady=(0, 10))

        for idx, (game_id, profile) in enumerate(EDITOR_GAME_PROFILES.items()):
            row = 2 + idx // 2
            col = idx % 2
            btn = tk.Button(quick_wrap, text=profile["display_name"], command=lambda gid=game_id: self.select_game(gid), relief="flat", bd=0, padx=10, pady=9, cursor="hand2", wraplength=170, justify="center", font=("Segoe UI", 9, "bold"))
            btn.grid(row=row, column=col, sticky="ew", padx=12, pady=6)
            self.game_buttons[game_id] = btn

        footer = tk.Frame(self, bg=SELECT_PANEL_2, height=38)
        footer.grid(row=2, column=0, sticky="ew", padx=12, pady=(0, 12))
        footer.grid_propagate(False)
        footer.grid_columnconfigure(0, weight=1)
        tk.Label(footer, textvariable=self.status_var, bg=SELECT_PANEL_2, fg=SELECT_TEXT, anchor="w", font=("Segoe UI", 9)).grid(row=0, column=0, sticky="ew", padx=14, pady=8)

    def draw_hero(self, canvas: tk.Canvas, width: int, height: int):
        canvas.delete("all")
        draw_constellation_backdrop(canvas, width, height, make_stars(271, 38), 0.0)
        points = [(width * 0.08, height * 0.30), (width * 0.19, height * 0.16), (width * 0.34, height * 0.38), (width * 0.52, height * 0.20), (width * 0.69, height * 0.33), (width * 0.84, height * 0.13), (width * 0.92, height * 0.33)]
        for idx in range(len(points) - 1):
            canvas.create_line(*points[idx], *points[idx + 1], fill=SELECT_LINE, width=1)
        for x, y in points:
            canvas.create_oval(x - 3, y - 3, x + 3, y + 3, fill=SELECT_STAR, outline="")
        canvas.create_text(34, 34, anchor="nw", text="Aldnoah Editor Observatory", fill=SELECT_TEXT, font=("Segoe UI", 24, "bold"))
        canvas.create_text(36, 76, anchor="nw", text="Choose the game sky whose editor tools you want to orbit through.", fill=SELECT_SUBTEXT, font=("Segoe UI", 10))
        canvas.create_text(width - 20, height - 24, anchor="se", text="Editor gateway selector", fill=SELECT_SUBTEXT, font=("Segoe UI", 10, "italic"))

    def is_hub_open(self, game_id: str) -> bool:
        win = self.child_windows.get(game_id)
        return bool(win is not None and win.winfo_exists())

    def set_status(self, text: str):
        self.status_var.set(text)

    def update_game_buttons(self):
        for game_id, button in self.game_buttons.items():
            profile = EDITOR_GAME_PROFILES[game_id]
            selected = self.selected_game_id == game_id
            active = self.is_hub_open(game_id)
            if profile["supported"]:
                bg = SELECT_NODE_SEL if selected else (SELECT_GREEN if active else SELECT_PANEL)
                fg = "#180E2B" if selected else SELECT_TEXT
                active_bg = "#F7E6A9" if selected else ("#57B771" if active else SELECT_PANEL_2)
                button.config(state="normal", bg=bg, fg=fg, activebackground=active_bg, activeforeground=fg, highlightthickness=1, highlightbackground=SELECT_GOLD if selected else (SELECT_GREEN if active else SELECT_LINE), cursor="hand2")
            else:
                button.config(state="disabled", bg=DISABLED_FILL, fg=DISABLED_TEXT, activebackground=DISABLED_FILL, activeforeground=DISABLED_TEXT, highlightthickness=1, highlightbackground=DISABLED_OUTLINE, cursor="arrow")

    def update_open_button(self):
        if EDITOR_GAME_PROFILES[self.selected_game_id]["supported"]:
            self.open_button.config(state="normal", text="Open Selected Editor Hub", bg=SELECT_GREEN, fg=SELECT_TEXT, activebackground="#57B771", activeforeground=SELECT_TEXT, cursor="hand2")
        else:
            self.open_button.config(state="disabled", text="Editor Hub Locked", bg=DISABLED_FILL, fg=DISABLED_TEXT, activebackground=DISABLED_FILL, activeforeground=DISABLED_TEXT, cursor="arrow")

    def select_game(self, game_id: str, *, update_status: bool = True):
        self.selected_game_id = game_id
        profile = EDITOR_GAME_PROFILES[game_id]
        total_specs = len(game_editor_specs(game_id))
        ready_count = len(live_game_editor_ids(game_id))
        self.selected_title_var.set(profile["display_name"])
        self.selected_meta_var.set(
            "\n".join(
                [
                    f"Game ID      : {game_id}",
                    f"Support      : {'LIVE' if profile['supported'] else 'DORMANT'}",
                    f"Live Editors : {ready_count}/{total_specs}",
                    "Source Root  : project root",
                ]
            )
        )
        desc = profile["summary"]
        extra = "Editor hub already open." if self.is_hub_open(game_id) else ("Editor hub not open yet." if profile["supported"] else "This game stays visible but greyed out until its editor formats are reversed.")
        self.selected_desc_var.set(f"{desc}\n\n{extra}")
        self.update_game_buttons()
        self.update_open_button()
        try:
            self.selector_canvas.render()
        except Exception:
            pass
        if update_status:
            self.set_status(f"Selected {profile['display_name']}." if profile["supported"] else f"{profile['display_name']} is visible, but its editor sky is still dormant.")

    def open_selected_game(self):
        self.open_game_hub(self.selected_game_id)

    def open_game_hub(self, game_id: str):
        profile = EDITOR_GAME_PROFILES[game_id]
        self.select_game(game_id, update_status=False)
        if not profile["supported"]:
            messagebox.showinfo("Not Supported", f"{profile['display_name']} does not have a live editor hub yet.")
            self.set_status(f"{profile['display_name']} is not supported by the editor hub yet.")
            return
        win = self.child_windows.get(game_id)
        if win is not None and win.winfo_exists():
            win.lift()
            win.focus_force()
            self.set_status(f"{profile['display_name']} editor hub is already open.")
            self.update_game_buttons()
            try:
                self.selector_canvas.render()
            except Exception:
                pass
            return
        win = GameEditorsWindow(self, game_id, profile)
        self.child_windows[game_id] = win
        self.set_status(f"Opened editor hub for {profile['display_name']}.")
        self.update_game_buttons()
        try:
            self.selector_canvas.render()
        except Exception:
            pass

        def on_close():
            try:
                win.destroy()
            finally:
                self.child_windows[game_id] = None
                self.update_game_buttons()
                self.update_open_button()
                try:
                    self.selector_canvas.render()
                except Exception:
                    pass
                self.set_status(f"Closed editor hub for {profile['display_name']}.")

        win.protocol("WM_DELETE_WINDOW", on_close)


class GameEditorsWindow(tk.Toplevel):
    def __init__(self, parent: tk.Misc, game_id: str, profile: dict):
        super().__init__(parent)
        self.game_id = game_id
        self.profile = profile
        self.editor_specs = game_editor_specs(game_id)
        self.available_editor_ids = live_game_editor_ids(game_id)
        self.child_windows: Dict[str, Optional[tk.Toplevel]] = {}
        self.selected_editor_id = (
            "stage"
            if "stage" in self.available_editor_ids
            else next((spec.editor_id for spec in self.editor_specs if spec.editor_id in self.available_editor_ids), self.editor_specs[0].editor_id if self.editor_specs else "")
        )
        self.status_var = tk.StringVar(value="Select an editor star to inspect or open it.")
        self.selected_title_var = tk.StringVar(value="")
        self.selected_meta_var = tk.StringVar(value="")
        self.selected_desc_var = tk.StringVar(value="")
        self.editor_buttons: Dict[str, tk.Button] = {}

        self.title(f"{profile['display_name']} Editor Orbit")
        self.configure(bg=SELECT_BG)
        self.geometry("1280x1020")
        self.minsize(1140, 920)

        setup_lilac_styles(self)
        apply_lilac_to_root(self)

        self.build_gui()
        self.select_editor(self.selected_editor_id, update_status=False)

    def build_gui(self):
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(1, weight=1)

        hero = tk.Canvas(self, height=168, bg=SELECT_BG, highlightthickness=0, bd=0, relief="flat")
        hero.grid(row=0, column=0, sticky="ew", padx=12, pady=(12, 10))
        hero.bind("<Configure>", lambda e: self.draw_hero(hero, e.width, e.height))

        content = tk.Frame(self, bg=SELECT_BG)
        content.grid(row=1, column=0, sticky="nsew", padx=12, pady=(0, 10))
        content.grid_columnconfigure(0, weight=3)
        content.grid_columnconfigure(1, weight=2)
        content.grid_rowconfigure(0, weight=1)

        left = build_panel(content, "Editor Field of Stars", "Launch live editors from the game-specific constellation map.", SELECT_BLUE)
        left["panel"].grid(row=0, column=0, sticky="nsew", padx=(0, 8))
        left["body"].grid_rowconfigure(0, weight=1)
        left["body"].grid_columnconfigure(0, weight=1)

        self.selector_canvas = EditorOrbitCanvas(left["body"], self)
        self.selector_canvas.grid(row=0, column=0, sticky="nsew", padx=14, pady=14)

        right = build_panel(content, "Selected Editor Node", "Review the editor scope, live state, and launch action before opening a tool.", SELECT_GOLD)
        right["panel"].grid(row=0, column=1, sticky="nsew", padx=(8, 0))
        right["body"].grid_columnconfigure(0, weight=1)
        right["body"].grid_rowconfigure(4, weight=1)

        tk.Label(right["body"], textvariable=self.selected_title_var, bg=SELECT_PANEL_3, fg="#180E2B", font=("Segoe UI", 18, "bold"), anchor="w", justify="left").grid(row=0, column=0, sticky="ew", padx=18, pady=(18, 6))
        tk.Label(right["body"], textvariable=self.selected_meta_var, bg=SELECT_PANEL_3, fg="#3B2E57", font=("Consolas", 10), anchor="w", justify="left").grid(row=1, column=0, sticky="ew", padx=18)
        tk.Label(right["body"], textvariable=self.selected_desc_var, bg=SELECT_PANEL_3, fg="#33254D", wraplength=360, justify="left", anchor="nw", font=("Segoe UI", 10), height=7).grid(row=2, column=0, sticky="ew", padx=18, pady=(14, 12))

        button_row = tk.Frame(right["body"], bg=SELECT_PANEL_3)
        button_row.grid(row=3, column=0, sticky="ew", padx=18)
        button_row.grid_columnconfigure(0, weight=1)
        button_row.grid_columnconfigure(1, weight=1)

        self.open_button = action_button(button_row, "Open Selected Editor", self.open_selected_editor, SELECT_GREEN)
        self.open_button.grid(row=0, column=0, sticky="ew", padx=(0, 6))
        action_button(button_row, "Close Editor Hub", self.destroy, SELECT_BLUE).grid(row=0, column=1, sticky="ew", padx=(6, 0))

        quick_shell = tk.Frame(right["body"], bg=SELECT_PANEL_2, highlightthickness=1, highlightbackground=SELECT_LINE)
        quick_shell.grid(row=4, column=0, sticky="nsew", padx=18, pady=(18, 18))
        quick_shell.grid_rowconfigure(0, weight=1)
        quick_shell.grid_columnconfigure(0, weight=1)

        self.editor_grid_canvas = tk.Canvas(quick_shell, bg=SELECT_PANEL_2, highlightthickness=0, bd=0, relief="flat")
        self.editor_grid_canvas.grid(row=0, column=0, sticky="nsew")

        editor_grid_scroll = tk.Scrollbar(quick_shell, orient="vertical", command=self.editor_grid_canvas.yview)
        editor_grid_scroll.grid(row=0, column=1, sticky="ns")
        self.editor_grid_canvas.configure(yscrollcommand=editor_grid_scroll.set)

        quick_wrap = tk.Frame(self.editor_grid_canvas, bg=SELECT_PANEL_2)
        self.editor_grid_window = self.editor_grid_canvas.create_window((0, 0), window=quick_wrap, anchor="nw")
        quick_wrap.grid_columnconfigure(0, weight=1)
        quick_wrap.grid_columnconfigure(1, weight=1)
        quick_wrap.bind("<Configure>", lambda _e: self.editor_grid_canvas.configure(scrollregion=self.editor_grid_canvas.bbox("all")))
        self.editor_grid_canvas.bind("<Configure>", lambda e: self.editor_grid_canvas.itemconfigure(self.editor_grid_window, width=e.width))

        tk.Label(quick_wrap, text="Editor Grid", bg=SELECT_PANEL_2, fg=SELECT_TEXT, font=("Segoe UI", 11, "bold")).grid(row=0, column=0, columnspan=2, sticky="w", padx=12, pady=(12, 4))
        tk.Label(quick_wrap, text="More Editors are planned to be added. Scroll to reach the lower nodes.", bg=SELECT_PANEL_2, fg=SELECT_SUBTEXT, font=("Segoe UI", 9), anchor="w", justify="left", wraplength=340).grid(row=1, column=0, columnspan=2, sticky="ew", padx=12, pady=(0, 10))

        for idx, spec in enumerate(self.editor_specs):
            row = 2 + idx // 2
            col = idx % 2
            btn = tk.Button(quick_wrap, text=spec.title, command=lambda eid=spec.editor_id: self.select_editor(eid), relief="flat", bd=0, padx=10, pady=9, cursor="hand2", wraplength=170, justify="center", font=("Segoe UI", 9, "bold"))
            btn.grid(row=row, column=col, sticky="ew", padx=12, pady=6)
            self.editor_buttons[spec.editor_id] = btn

        footer = tk.Frame(self, bg=SELECT_PANEL_2, height=38)
        footer.grid(row=2, column=0, sticky="ew", padx=12, pady=(0, 12))
        footer.grid_propagate(False)
        footer.grid_columnconfigure(0, weight=1)
        tk.Label(footer, textvariable=self.status_var, bg=SELECT_PANEL_2, fg=SELECT_TEXT, anchor="w", font=("Segoe UI", 9)).grid(row=0, column=0, sticky="ew", padx=14, pady=8)

    def draw_hero(self, canvas: tk.Canvas, width: int, height: int):
        canvas.delete("all")
        draw_constellation_backdrop(canvas, width, height, make_stars(761, 38), 0.0)
        points = [(width * 0.06, height * 0.34), (width * 0.18, height * 0.18), (width * 0.36, height * 0.40), (width * 0.54, height * 0.18), (width * 0.72, height * 0.34), (width * 0.88, height * 0.14), (width * 0.94, height * 0.34)]
        for idx in range(len(points) - 1):
            canvas.create_line(*points[idx], *points[idx + 1], fill=SELECT_LINE, width=1)
        for x, y in points:
            canvas.create_oval(x - 3, y - 3, x + 3, y + 3, fill=SELECT_STAR, outline="")
        canvas.create_text(34, 34, anchor="nw", text=f"{self.profile['display_name']} Editor Orbit", fill=SELECT_TEXT, font=("Segoe UI", 24, "bold"))
        canvas.create_text(36, 76, anchor="nw", text="Launch the live tools for this game.", fill=SELECT_SUBTEXT, font=("Segoe UI", 10))
        canvas.create_text(width - 20, height - 24, anchor="se", text="Game-specific editor hub", fill=SELECT_SUBTEXT, font=("Segoe UI", 10, "italic"))

    def set_status(self, text: str):
        self.status_var.set(text)

    def is_editor_available(self, editor_id: str) -> bool:
        return editor_id in self.available_editor_ids

    def is_editor_open(self, editor_id: str) -> bool:
        win = self.child_windows.get(editor_id)
        return bool(win is not None and win.winfo_exists())

    def update_editor_buttons(self):
        for spec in self.editor_specs:
            button = self.editor_buttons[spec.editor_id]
            selected = self.selected_editor_id == spec.editor_id
            active = self.is_editor_open(spec.editor_id)
            if self.is_editor_available(spec.editor_id):
                bg = SELECT_NODE_SEL if selected else (SELECT_GREEN if active else SELECT_PANEL)
                fg = "#180E2B" if selected else SELECT_TEXT
                active_bg = "#F7E6A9" if selected else ("#57B771" if active else SELECT_PANEL_2)
                button.config(state="normal", bg=bg, fg=fg, activebackground=active_bg, activeforeground=fg, highlightthickness=1, highlightbackground=SELECT_GOLD if selected else (SELECT_GREEN if active else SELECT_LINE), cursor="hand2")
            else:
                button.config(state="disabled", bg=DISABLED_FILL, fg=DISABLED_TEXT, activebackground=DISABLED_FILL, activeforeground=DISABLED_TEXT, highlightthickness=1, highlightbackground=DISABLED_OUTLINE, cursor="arrow")

    def update_open_button(self):
        if not self.selected_editor_id:
            self.open_button.config(state="disabled", text="No Editor Selected", bg=DISABLED_FILL, fg=DISABLED_TEXT, activebackground=DISABLED_FILL, activeforeground=DISABLED_TEXT, cursor="arrow")
            return
        spec = EDITOR_SPEC_MAP[self.selected_editor_id]
        if self.is_editor_available(self.selected_editor_id):
            self.open_button.config(state="normal", text=f"Open {spec.title}", bg=SELECT_GREEN, fg=SELECT_TEXT, activebackground="#57B771", activeforeground=SELECT_TEXT, cursor="hand2")
        else:
            self.open_button.config(state="disabled", text=f"{spec.title} Locked", bg=DISABLED_FILL, fg=DISABLED_TEXT, activebackground=DISABLED_FILL, activeforeground=DISABLED_TEXT, cursor="arrow")

    def select_editor(self, editor_id: str, *, update_status: bool = True):
        if not editor_id:
            self.selected_title_var.set("No editor nodes mapped")
            self.selected_meta_var.set(f"Game          : {self.game_id}\nStatus        : DORMANT")
            self.selected_desc_var.set("This game does not have editor nodes mapped into its sky yet.")
            self.update_editor_buttons()
            self.update_open_button()
            return
        self.selected_editor_id = editor_id
        spec = EDITOR_SPEC_MAP[editor_id]
        available = self.is_editor_available(editor_id)
        open_state = "Editor window already open." if self.is_editor_open(editor_id) else ("Editor window not open yet." if available else "This node stays greyed out for now.")
        if editor_id == "stage":
            self.selected_meta_var.set(
                "\n".join(
                    [
                        f"Editor        : {spec.title}",
                        f"Status        : {'LIVE' if available else 'DORMANT'}",
                        f"Game          : {self.game_id}",
                    ]
                )
            )
            desc = "Mod each stage file, the battlefield data."
        elif editor_id == "officer":
            self.selected_meta_var.set(
                "\n".join(
                    [
                        f"Editor        : {spec.title}",
                        f"Status        : {'LIVE' if available else 'DORMANT'}",
                        f"Game          : {self.game_id}",
                    ]
                )
            )
            desc = "Mod playable officer data."
        elif editor_id == "weapon":
            self.selected_meta_var.set(
                "\n".join(
                    [
                        f"Editor        : {spec.title}",
                        f"Status        : {'LIVE' if available else 'DORMANT'}",
                        f"Game          : {self.game_id}",
                    ]
                )
            )
            desc = "Mod the weapon data."

        elif editor_id == "npc":
            self.selected_meta_var.set(
                "\n".join(
                    [
                        f"Editor        : {spec.title}",
                        f"Status        : {'LIVE' if available else 'DORMANT'}",
                        f"Game          : {self.game_id}",
                    ]
                )
            )
            desc = "Mod the CPU controlled officers/troops"
        elif editor_id == "npc_tactic":
            self.selected_meta_var.set(
                "\n".join(
                    [
                        f"Editor        : {spec.title}",
                        f"Status        : {'LIVE' if available else 'DORMANT'}",
                        f"Game          : {self.game_id}",
                    ]
                )
            )
            desc = "Mod the NPC tactic data."
        elif editor_id == "bodyguard":
            self.selected_meta_var.set(
                "\n".join(
                    [
                        f"Editor        : {spec.title}",
                        f"Status        : {'LIVE' if available else 'DORMANT'}",
                        f"Game          : {self.game_id}",
                    ]
                )
            )
            desc = "Mod the Bodyguards."
        elif editor_id == "animal":
            self.selected_meta_var.set(
                "\n".join(
                    [
                        f"Editor        : {spec.title}",
                        f"Status        : {'LIVE' if available else 'DORMANT'}",
                        f"Game          : {self.game_id}",
                    ]
                )
            )
            desc = "Mod the animals."
        elif editor_id == "officer_skill":
            self.selected_meta_var.set(
                "\n".join(
                    [
                        f"Editor        : {spec.title}",
                        f"Status        : {'LIVE' if available else 'DORMANT'}",
                        f"Game          : {self.game_id}",
                    ]
                )
            )
            desc = "Mod the Officer Skills."
        elif editor_id == "weapon_element":
            self.selected_meta_var.set(
                "\n".join(
                    [
                        f"Editor        : {spec.title}",
                        f"Status        : {'LIVE' if available else 'DORMANT'}",
                        f"Game          : {self.game_id}",
                    ]
                )
            )
            desc = "Mod the weapon elements."
        elif editor_id == "support_skill":
            self.selected_meta_var.set(
                "\n".join(
                    [
                        f"Editor        : {spec.title}",
                        f"Status        : {'LIVE' if available else 'DORMANT'}",
                        f"Game          : {self.game_id}",
                    ]
                )
            )
            desc = "Mod the support skills."
        else:
            self.selected_meta_var.set(
                "\n".join(
                    [
                        f"Editor        : {spec.title}",
                        f"Status        : {'LIVE' if available else 'DORMANT'}",
                        f"Game          : {self.game_id}",
                        "Launch        : Disabled until format reversal is ready",
                        "Future Slot   : Reserved in this editor orbit",
                        "Scope         : Waiting on dedicated data mapping",
                    ]
                )
            )
            desc = "This editor node is already represented in the GUI so future data work can plug into the same orbit without reshaping the hub."
        self.selected_title_var.set(spec.title)
        self.selected_desc_var.set(f"{spec.summary}\n\n{desc}\n\n{open_state}")
        self.update_editor_buttons()
        self.update_open_button()
        try:
            self.selector_canvas.render()
        except Exception:
            pass
        if update_status:
            self.set_status(f"Selected {spec.title}.")

    def open_selected_editor(self):
        if self.selected_editor_id:
            self.open_editor(self.selected_editor_id)

    def open_editor(self, editor_id: str):
        spec = EDITOR_SPEC_MAP[editor_id]
        self.select_editor(editor_id, update_status=False)
        if not self.is_editor_available(editor_id):
            messagebox.showinfo("Not Supported", f"{spec.title} is displayed for the future but is not live yet.")
            self.set_status(f"{spec.title} is not live yet.")
            return
        win = self.child_windows.get(editor_id)
        if win is not None and win.winfo_exists():
            win.lift()
            win.focus_force()
            self.set_status(f"{spec.title} is already open.")
            self.update_editor_buttons()
            try:
                self.selector_canvas.render()
            except Exception:
                pass
            return
        if editor_id == "stage":
            from .aldnoah_stage_editor import StageEditorWindow

            win = StageEditorWindow(self, self.game_id)
        elif editor_id == "officer" and self.game_id in {"DW7XL", "DW8XL", "DW8E", "WO3", "WAS"}:
            from .aldnoah_officer_editor import OfficerEditorWindow

            win = OfficerEditorWindow(self, self.game_id)
        elif editor_id == "weapon" and self.game_id in {"DW8XL", "DW8E", "WO3"}:
            from .aldnoah_weapon import WeaponEditorWindow

            win = WeaponEditorWindow(self, self.game_id)
        elif editor_id == "bodyguard" and self.game_id == "DW8XL":
            from .aldnoah_bodyguard import DW8XLBodyguardEditorWindow

            win = DW8XLBodyguardEditorWindow(self)
        elif editor_id == "npc" and self.game_id in {"DW7XL", "DW8XL", "DW8E", "WO3", "BN", "WAS"}:
            from .aldnoah_npc_editor import NPCEditorWindow

            win = NPCEditorWindow(self, self.game_id)
        elif editor_id == "npc_tactic" and self.game_id == "DW8E":
            from .aldnoah_npc_tactic import NPCTacticEditorWindow

            win = NPCTacticEditorWindow(self, self.game_id)
        elif editor_id == "officer_skill" and self.game_id == "DW8XL":
            from .aldnoah_officer_skill import DW8XLOFFSKILLEditorWindow

            win = DW8XLOFFSKILLEditorWindow(self)
        elif editor_id == "animal" and self.game_id in {"DW8XL", "DW8E"}:
            from .aldnoah_animal_editor import AnimalEditorWindow

            win = AnimalEditorWindow(self, self.game_id)
        elif editor_id == "weapon_element" and self.game_id in {"DW8XL", "DW8E"}:
            from .aldnoah_weapon_element import WeaponElementEditorWindow

            win = WeaponElementEditorWindow(self, self.game_id)
        elif editor_id == "support_skill" and self.game_id in {"DW8XL", "DW8E"}:
            from .aldnoah_support_skill import SupportSkillEditorWindow

            win = SupportSkillEditorWindow(self, self.game_id)
        else:
            messagebox.showinfo("Not Supported", f"{spec.title} does not have a live implementation yet.")
            self.set_status(f"{spec.title} does not have a live implementation yet.")
            return
        self.child_windows[editor_id] = win
        self.set_status(f"Opened {spec.title}.")
        self.update_editor_buttons()
        try:
            self.selector_canvas.render()
        except Exception:
            pass

        def on_close():
            try:
                win.destroy()
            finally:
                self.child_windows[editor_id] = None
                self.update_editor_buttons()
                self.update_open_button()
                try:
                    self.selector_canvas.render()
                except Exception:
                    pass
                self.set_status(f"Closed {spec.title}.")

        win.protocol("WM_DELETE_WINDOW", on_close)


if __name__ == "__main__":
    raise SystemExit("Run AE/main.pyw to launch Aldnoah Engine tools.")
