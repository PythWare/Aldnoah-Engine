# Aldnoah_Logic/aldnoah_gui.py
import math, os, random, threading
import tkinter as tk
from tkinter import ttk, filedialog, messagebox

from .aldnoah_energy import LILAC, get_game_schema, setup_lilac_styles, apply_lilac_to_root
from .aldnoah_unpack import unpack_from_schema
from .aldnoah_mod_creator import ModCreatorGameSelect
from .aldnoah_mod_manager import ModManagerGameSelect
from .aldnoah_repacks import repack_from_folder, update_kvs_metadata

HUB_BG = "#0F0C18"
HUB_BG_2 = "#171224"
HUB_PANEL = "#1C1530"
HUB_PANEL_2 = "#281D44"
HUB_PANEL_3 = "#D7C2EC"
HUB_TEXT = "#F6F1FF"
HUB_SUBTEXT = "#CDBCE3"
HUB_MUTED = "#9D89B8"
HUB_LINE = "#8E7AE2"
HUB_STAR = "#EFE8FF"
HUB_GOLD = "#C9972D"
HUB_BLUE = "#3F5CA8"
HUB_GREEN = "#41A35A"
HUB_ROSE = "#A6526C"
HUB_NODE = "#6B57C8"
HUB_NODE_SEL = "#F5D889"
HUB_NODE_RING = "#A89AF0"
HUB_SUCCESS = "#8FE7A7"


class HubConstellationCanvas(tk.Canvas):
    def __init__(self, parent: tk.Misc, controller: "Core_Tools"):
        super().__init__(parent, bg=HUB_BG, highlightthickness=0, bd=0, relief="flat")
        self.controller = controller
        self.item_to_game = {}
        self.phase = 0.0
        self.stars = self.make_stars()
        self.bind("<Configure>", lambda _e: self.render())
        self.bind("<Button-1>", self.on_click)
        self.bind("<Double-Button-1>", self.on_double_click)
        self.after(120, self._tick)

    def make_stars(self):
        rnd = random.Random(44)
        return [(rnd.uniform(0.04, 0.96), rnd.uniform(0.06, 0.92), rnd.randint(1, 3)) for _ in range(74)]

    def _tick(self):
        self.phase += 0.08
        if self.winfo_exists():
            self.render()
            self.after(120, self._tick)

    def on_click(self, event):
        if self.controller.ui_locked:
            return
        hit = self.find_overlapping(event.x - 4, event.y - 4, event.x + 4, event.y + 4)
        for item_id in reversed(hit):
            gid = self.item_to_game.get(item_id)
            if gid:
                self.controller.select_game(gid)
                return

    def on_double_click(self, _event):
        if self.controller.ui_locked:
            return
        self.controller.launch_selected_unpack()

    def coords(self, width: int, height: int):
        return {
            "DW7XL": (width * 0.15, height * 0.29),
            "DW8XL": (width * 0.37, height * 0.20),
            "DW8E": (width * 0.69, height * 0.24),
            "WO3": (width * 0.23, height * 0.66),
            "TK": (width * 0.52, height * 0.56),
            "BN": (width * 0.52, height * 0.82),
            "WAS": (width * 0.83, height * 0.62),
        }

    def render(self):
        self.delete("all")
        self.item_to_game.clear()
        width = max(1, self.winfo_width())
        height = max(1, self.winfo_height())

        self.create_rectangle(0, 0, width, height, fill=HUB_BG, outline="")
        self.create_rectangle(0, 0, width, int(height * 0.24), fill=HUB_BG_2, outline="")
        for idx in range(7):
            y = int(height * 0.18) + idx * 78
            sway = math.sin(self.phase * 0.7 + idx * 0.9) * 12
            self.create_line(0, y + sway, width, y - sway, fill="#211A34", width=1)

        for x, y, radius in self.stars:
            sx = int(x * width)
            sy = int(y * height)
            self.create_oval(sx - radius, sy - radius, sx + radius, sy + radius, fill=HUB_STAR, outline="")

        coords = self.coords(width, height)
        links = [("DW7XL", "DW8XL"), ("DW8XL", "DW8E"), ("DW7XL", "WO3"), ("WO3", "TK"), ("TK", "BN"), ("BN", "WAS"), ("DW8E", "WAS"), ("DW8XL", "TK"), ("DW8XL", "BN")]
        for left, right in links:
            ax, ay = coords[left]
            bx, by = coords[right]
            self.create_line(ax, ay, bx, by, fill=HUB_LINE, width=2)

        self.create_text(22, 20, anchor="nw", text="Aldnoah Engine Nexus", fill=HUB_TEXT, font=("Segoe UI", 24, "bold"))
        self.create_text(24, 56, anchor="nw", text="Select a game star to inspect its schema, then launch unpacking or use the side tools.", fill=HUB_SUBTEXT, font=("Segoe UI", 10))
        self.create_text(width - 18, 24, anchor="ne", text="Constellation Hub", fill=HUB_SUBTEXT, font=("Segoe UI", 10, "italic"))

        for game in self.controller.games:
            gid = game["id"]
            gx, gy = coords[gid]
            selected = self.controller.selected_game_id == gid
            pulse = 12 + (math.sin(self.phase * 2.0 + gx * 0.01) * 3)
            radius = 11 if selected else 9
            fill = HUB_NODE_SEL if selected else HUB_NODE
            outline = HUB_GOLD if selected else HUB_NODE_RING
            halo = self.create_oval(gx - pulse * 2, gy - pulse * 2, gx + pulse * 2, gy + pulse * 2, outline=outline, width=1, stipple="gray25")
            orb = self.create_oval(gx - radius, gy - radius, gx + radius, gy + radius, fill=fill, outline=outline, width=2)
            label = self.create_text(gx, gy - 24, text=game["short"], fill=HUB_TEXT, font=("Segoe UI", 10, "bold"))
            sub = self.create_text(gx, gy + 28, text=game["name"], fill=HUB_SUBTEXT, font=("Segoe UI", 9), width=170)
            for item in (halo, orb, label, sub):
                self.item_to_game[item] = gid


class KVSMetadataGatewayCanvas(tk.Canvas):
    def __init__(self, parent: tk.Misc, controller: "KVSMetadataGameSelect"):
        super().__init__(parent, bg=HUB_BG, highlightthickness=0, bd=0, relief="flat")
        self.controller = controller
        self.item_to_game = {}
        self.phase = 0.0
        self.stars = self.make_stars()
        self.bind("<Configure>", lambda _e: self.render())
        self.bind("<Button-1>", self.on_click)
        self.bind("<Double-Button-1>", self.on_double_click)
        self.after(120, self._tick)

    def make_stars(self):
        rnd = random.Random(91)
        return [(rnd.uniform(0.04, 0.96), rnd.uniform(0.06, 0.92), rnd.randint(1, 3)) for _ in range(88)]

    def _tick(self):
        self.phase += 0.08
        if self.winfo_exists():
            self.render()
            self.after(120, self._tick)

    def coords(self, width: int, height: int):
        return {
            "DW7XL": (width * 0.15, height * 0.29),
            "DW8XL": (width * 0.37, height * 0.20),
            "DW8E": (width * 0.69, height * 0.24),
            "WO3": (width * 0.23, height * 0.66),
            "TK": (width * 0.52, height * 0.56),
            "BN": (width * 0.52, height * 0.82),
            "WAS": (width * 0.83, height * 0.62),
        }

    def on_click(self, event):
        hit = self.find_overlapping(event.x - 4, event.y - 4, event.x + 4, event.y + 4)
        for item_id in reversed(hit):
            gid = self.item_to_game.get(item_id)
            if gid:
                self.controller.select_game(gid)
                return

    def on_double_click(self, _event):
        self.controller.open_selected_game()

    def render(self):
        self.delete("all")
        self.item_to_game.clear()
        width = max(1, self.winfo_width())
        height = max(1, self.winfo_height())

        self.create_rectangle(0, 0, width, height, fill=HUB_BG, outline="")
        self.create_rectangle(0, 0, width, int(height * 0.24), fill=HUB_BG_2, outline="")
        for idx in range(7):
            y = int(height * 0.18) + idx * 78
            sway = math.sin(self.phase * 0.7 + idx * 0.9) * 12
            self.create_line(0, y + sway, width, y - sway, fill="#211A34", width=1)

        for x, y, radius in self.stars:
            sx = int(x * width)
            sy = int(y * height)
            self.create_oval(sx - radius, sy - radius, sx + radius, sy + radius, fill=HUB_STAR, outline="")

        coords = self.coords(width, height)
        links = [
            ("DW7XL", "DW8XL"),
            ("DW8XL", "DW8E"),
            ("DW7XL", "WO3"),
            ("WO3", "TK"),
            ("TK", "BN"),
            ("BN", "WAS"),
            ("DW8E", "WAS"),
            ("DW8XL", "TK"),
            ("DW8XL", "BN"),
        ]
        for left, right in links:
            ax, ay = coords[left]
            bx, by = coords[right]
            self.create_line(ax, ay, bx, by, fill=HUB_LINE, width=2)

        self.create_text(22, 20, anchor="nw", text="KVS Metadata Starfield", fill=HUB_TEXT, font=("Segoe UI", 24, "bold"))
        self.create_text(
            24,
            56,
            anchor="nw",
            text="WO3 is the live KVS lane today. Other skies stay visible so the gateway still feels part of the same constellation.",
            fill=HUB_SUBTEXT,
            font=("Segoe UI", 10),
            width=max(240, width - 80),
        )
        self.create_text(width - 18, 24, anchor="ne", text="Metadata Relay", fill=HUB_SUBTEXT, font=("Segoe UI", 10, "italic"))

        for game in self.controller.games:
            gid = game["id"]
            gx, gy = coords[gid]
            selected = self.controller.selected_game_id == gid
            supported = gid == "WO3"
            pulse = 12 + (math.sin(self.phase * 2.0 + gx * 0.01) * 3)
            radius = 11 if selected else 9
            if supported:
                fill = HUB_NODE_SEL if selected else HUB_NODE
                outline = HUB_GOLD if selected else HUB_NODE_RING
                halo_outline = outline
            else:
                fill = "#3E345B"
                outline = "#6A5D90"
                halo_outline = "#534770"
            halo = self.create_oval(
                gx - pulse * 2,
                gy - pulse * 2,
                gx + pulse * 2,
                gy + pulse * 2,
                outline=halo_outline,
                width=1,
                stipple="gray25",
            )
            orb = self.create_oval(gx - radius, gy - radius, gx + radius, gy + radius, fill=fill, outline=outline, width=2)
            label_fill = HUB_TEXT if supported or selected else "#C8B9E2"
            sub_fill = HUB_SUBTEXT if supported else "#9788B8"
            label = self.create_text(gx, gy - 24, text=game["short"], fill=label_fill, font=("Segoe UI", 10, "bold"))
            sub = self.create_text(gx, gy + 28, text=game["name"], fill=sub_fill, font=("Segoe UI", 9), width=170)
            for item in (halo, orb, label, sub):
                self.item_to_game[item] = gid
            if supported:
                badge = self.create_text(gx + 18, gy - 16, text="Live", fill=HUB_SUCCESS, font=("Segoe UI", 8, "bold"))
                self.item_to_game[badge] = gid


class KVSMetadataGameSelect(tk.Toplevel):
    def __init__(self, parent: tk.Misc, controller: "Core_Tools"):
        super().__init__(parent)
        self.controller = controller
        self.games = list(controller.games)
        self.selected_game_id = "WO3"
        self.status_var = tk.StringVar(value="Select the WO3 star to continue into KVS metadata relinking.")
        self.selected_title_var = tk.StringVar(value="")
        self.selected_meta_var = tk.StringVar(value="")
        self.selected_desc_var = tk.StringVar(value="")
        self.game_buttons = {}

        self.title("Aldnoah KVS Metadata Gateway")
        self.configure(bg=HUB_BG)
        self.geometry("1200x1000")
        self.minsize(1060, 860)

        setup_lilac_styles(self)
        apply_lilac_to_root(self)

        self.build_gui()
        self.select_game(self.selected_game_id, update_status=False)

    def build_gui(self):
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(1, weight=1)

        hero = tk.Canvas(self, height=168, bg=HUB_BG, highlightthickness=0, bd=0, relief="flat")
        hero.grid(row=0, column=0, sticky="ew", padx=12, pady=(12, 10))
        hero.bind("<Configure>", lambda e: self.draw_hero(hero, e.width, e.height))

        content = tk.Frame(self, bg=HUB_BG)
        content.grid(row=1, column=0, sticky="nsew", padx=12, pady=(0, 10))
        content.grid_columnconfigure(0, weight=3)
        content.grid_columnconfigure(1, weight=2)
        content.grid_rowconfigure(0, weight=1)

        left = self.build_panel(content, "Game Field of Stars", "Double click the live sky to jump straight into metadata file selection.", HUB_BLUE)
        left["panel"].grid(row=0, column=0, sticky="nsew", padx=(0, 8))
        left["body"].grid_rowconfigure(0, weight=1)
        left["body"].grid_columnconfigure(0, weight=1)

        self.selector_canvas = KVSMetadataGatewayCanvas(left["body"], self)
        self.selector_canvas.grid(row=0, column=0, sticky="nsew", padx=14, pady=(14, 10))

        hint = tk.Label(
            left["body"],
            text="Tip: the rest of the skies stay visible as dormant nodes so the relay still matches the main constellation language.",
            bg=HUB_PANEL_3,
            fg=HUB_MUTED,
            anchor="w",
            font=("Segoe UI", 9, "italic"),
        )
        hint.grid(row=1, column=0, sticky="ew", padx=16, pady=(0, 14))

        right = self.build_panel(content, "Selected Relay Profile", "Review KVS metadata support and the file-pick sequence before continuing.", HUB_ROSE)
        right["panel"].grid(row=0, column=1, sticky="nsew", padx=(8, 0))
        right["body"].grid_columnconfigure(0, weight=1)

        title = tk.Label(right["body"], textvariable=self.selected_title_var, bg=HUB_PANEL_3, fg="#180E2B", font=("Segoe UI", 18, "bold"), anchor="w", justify="left")
        title.grid(row=0, column=0, sticky="ew", padx=18, pady=(18, 6))

        meta = tk.Label(
            right["body"],
            textvariable=self.selected_meta_var,
            bg=HUB_PANEL_3,
            fg="#3B2E57",
            font=("Consolas", 10),
            anchor="w",
            justify="left",
        )
        meta.grid(row=1, column=0, sticky="ew", padx=18)

        desc = tk.Label(
            right["body"],
            textvariable=self.selected_desc_var,
            bg=HUB_PANEL_3,
            fg="#33254D",
            wraplength=360,
            justify="left",
            anchor="nw",
            font=("Segoe UI", 10),
            height=6,
        )
        desc.grid(row=2, column=0, sticky="ew", padx=18, pady=(14, 12))

        button_row = tk.Frame(right["body"], bg=HUB_PANEL_3)
        button_row.grid(row=3, column=0, sticky="ew", padx=18)
        button_row.grid_columnconfigure(0, weight=1)
        button_row.grid_columnconfigure(1, weight=1)

        self.open_button = tk.Button(
            button_row,
            text="Continue to File Select",
            command=self.open_selected_game,
            bg=HUB_GREEN,
            fg=HUB_TEXT,
            activebackground="#57B771",
            activeforeground=HUB_TEXT,
            relief="flat",
            bd=0,
            padx=12,
            pady=10,
            font=("Segoe UI", 10, "bold"),
            cursor="hand2",
        )
        self.open_button.grid(row=0, column=0, sticky="ew", padx=(0, 6))

        close_button = tk.Button(
            button_row,
            text="Close Gateway",
            command=self.destroy,
            bg=HUB_BLUE,
            fg=HUB_TEXT,
            activebackground="#5075D0",
            activeforeground=HUB_TEXT,
            relief="flat",
            bd=0,
            padx=12,
            pady=10,
            font=("Segoe UI", 10, "bold"),
            cursor="hand2",
        )
        close_button.grid(row=0, column=1, sticky="ew", padx=(6, 0))

        quick_wrap = tk.Frame(right["body"], bg=HUB_PANEL_2, highlightthickness=1, highlightbackground=HUB_LINE)
        quick_wrap.grid(row=4, column=0, sticky="nsew", padx=18, pady=(18, 18))
        quick_wrap.grid_columnconfigure(0, weight=1)
        quick_wrap.grid_columnconfigure(1, weight=1)

        quick_title = tk.Label(quick_wrap, text="Relay Grid", bg=HUB_PANEL_2, fg=HUB_TEXT, font=("Segoe UI", 11, "bold"))
        quick_title.grid(row=0, column=0, columnspan=2, sticky="w", padx=12, pady=(12, 4))

        quick_sub = tk.Label(
            quick_wrap,
            text="WO3 is currently the only live metadata relay. Other skies stay dormant until dedicated KVS metadata logic exists.",
            bg=HUB_PANEL_2,
            fg=HUB_SUBTEXT,
            font=("Segoe UI", 9),
            anchor="w",
            justify="left",
            wraplength=340,
        )
        quick_sub.grid(row=1, column=0, columnspan=2, sticky="ew", padx=12, pady=(0, 10))

        for idx, game in enumerate(sorted(self.games, key=lambda item: item["name"])):
            row = 2 + idx // 2
            col = idx % 2
            btn = tk.Button(
                quick_wrap,
                text=game["name"],
                command=lambda gid=game["id"]: self.select_game(gid),
                relief="flat",
                bd=0,
                padx=10,
                pady=9,
                cursor="hand2",
                wraplength=170,
                justify="center",
                font=("Segoe UI", 9, "bold"),
            )
            btn.grid(row=row, column=col, sticky="ew", padx=12, pady=6)
            self.game_buttons[game["id"]] = btn

        footer = tk.Frame(self, bg=HUB_PANEL_2, height=38)
        footer.grid(row=2, column=0, sticky="ew", padx=12, pady=(0, 12))
        footer.grid_propagate(False)
        footer.grid_columnconfigure(0, weight=1)
        status = tk.Label(footer, textvariable=self.status_var, bg=HUB_PANEL_2, fg=HUB_TEXT, anchor="w", font=("Segoe UI", 9))
        status.grid(row=0, column=0, sticky="ew", padx=14, pady=8)

    def build_panel(self, parent: tk.Misc, title: str, subtitle: str, accent: str):
        panel = tk.Frame(parent, bg=HUB_PANEL, highlightthickness=1, highlightbackground=HUB_LINE)
        panel.grid_rowconfigure(1, weight=1)
        panel.grid_columnconfigure(0, weight=1)

        header = tk.Canvas(panel, height=96, bg=HUB_PANEL, highlightthickness=0, bd=0, relief="flat")
        header.grid(row=0, column=0, sticky="ew")
        header.bind("<Configure>", lambda e, c=header, t=title, s=subtitle, a=accent: self.draw_panel_header(c, e.width, e.height, t, s, a))

        body = tk.Frame(panel, bg=HUB_PANEL_3)
        body.grid(row=1, column=0, sticky="nsew")
        return {"panel": panel, "header": header, "body": body}

    def draw_hero(self, canvas: tk.Canvas, width: int, height: int):
        canvas.delete("all")
        canvas.create_rectangle(0, 0, width, height, fill=HUB_BG, outline="")
        canvas.create_rectangle(0, 42, width, height, fill=HUB_BG_2, outline="")
        for idx in range(38):
            x = ((idx * 91) + 48) % max(1, width)
            y = 22 + ((idx * 41) % max(1, height - 34))
            radius = 1 + (idx % 3)
            canvas.create_oval(x - radius, y - radius, x + radius, y + radius, fill=HUB_STAR, outline="")

        points = [
            (width * 0.08, height * 0.30),
            (width * 0.19, height * 0.16),
            (width * 0.34, height * 0.38),
            (width * 0.52, height * 0.20),
            (width * 0.69, height * 0.33),
            (width * 0.84, height * 0.13),
            (width * 0.92, height * 0.33),
        ]
        for idx in range(len(points) - 1):
            ax, ay = points[idx]
            bx, by = points[idx + 1]
            canvas.create_line(ax, ay, bx, by, fill=HUB_LINE, width=1)
        for x, y in points:
            canvas.create_oval(x - 3, y - 3, x + 3, y + 3, fill=HUB_STAR, outline="")

        canvas.create_arc(36, 18, 196, 148, start=60, extent=250, style=tk.ARC, outline=HUB_LINE, width=2)
        canvas.create_arc(width - 210, 12, width - 24, 154, start=250, extent=225, style=tk.ARC, outline="#53A0FF", width=2)
        canvas.create_text(34, 34, anchor="nw", text="Aldnoah KVS Metadata Gateway", fill=HUB_TEXT, font=("Segoe UI", 24, "bold"))
        canvas.create_text(
            36,
            76,
            anchor="nw",
            text="Choose the game sky whose rebuilt KVS audio container needs its paired metadata relinked.",
            fill=HUB_SUBTEXT,
            font=("Segoe UI", 10),
        )
        canvas.create_text(width - 20, height - 24, anchor="se", text="KVS metadata launch selector", fill=HUB_SUBTEXT, font=("Segoe UI", 10, "italic"))

    def draw_panel_header(self, canvas: tk.Canvas, width: int, height: int, title: str, subtitle: str, accent: str):
        canvas.delete("all")
        canvas.create_rectangle(0, 0, width, height, fill=HUB_PANEL, outline="")
        canvas.create_rectangle(0, 0, width, height, fill=HUB_PANEL_2, outline="")
        for idx in range(18):
            x = ((idx * 63) + 26) % max(1, width)
            y = 14 + ((idx * 29) % max(1, height - 22))
            radius = 1 + (idx % 2)
            canvas.create_oval(x - radius, y - radius, x + radius, y + radius, fill=HUB_STAR, outline="")
        canvas.create_line(18, height - 26, width - 18, height - 26, fill=accent, width=2)
        canvas.create_text(16, 16, anchor="nw", text=title, fill=HUB_TEXT, font=("Segoe UI", 15, "bold"))
        canvas.create_text(16, 46, anchor="nw", text=subtitle, fill=HUB_SUBTEXT, font=("Segoe UI", 9), width=max(220, width - 32))

    def set_status(self, text: str):
        self.status_var.set(text)

    def update_game_buttons(self):
        for game_id, button in self.game_buttons.items():
            selected = self.selected_game_id == game_id
            supported = game_id == "WO3"
            if selected:
                bg = HUB_NODE_SEL
                fg = "#180E2B"
                active_bg = "#F7E6A9"
                highlight = HUB_GOLD
            elif supported:
                bg = HUB_GREEN
                fg = HUB_TEXT
                active_bg = "#57B771"
                highlight = HUB_GREEN
            else:
                bg = HUB_PANEL
                fg = "#C8B9E2"
                active_bg = HUB_PANEL_2
                highlight = HUB_LINE
            button.config(
                bg=bg,
                fg=fg,
                activebackground=active_bg,
                activeforeground=fg,
                highlightthickness=1,
                highlightbackground=highlight,
            )

    def select_game(self, game_id: str, *, update_status: bool = True):
        self.selected_game_id = game_id
        supported = game_id == "WO3"
        game_name = next((game["name"] for game in self.games if game["id"] == game_id), game_id)
        self.selected_title_var.set(game_name)
        self.selected_meta_var.set(
            "\n".join(
                [
                    f"Game ID      : {game_id}",
                    f"Support      : {'Ready' if supported else 'Dormant'}",
                    f"Workflow     : Select rebuilt KVS, then paired metadata .bin",
                    f"Mode         : {'Live WO3 metadata updater' if supported else 'Waiting for dedicated support'}",
                ]
            )
        )
        if supported:
            desc = (
                "Warriors Orochi 3 can relink KVS audio containers with their paired metadata file.\n\n"
                "When you continue, the gateway will ask for the rebuilt .kvs first and then the paired metadata .bin."
            )
            self.open_button.config(state="normal", bg=HUB_GREEN, activebackground="#57B771", text="Continue to File Select", cursor="hand2")
        else:
            desc = (
                "This sky is visible for consistency, but its dedicated KVS metadata patch logic is not implemented yet.\n\n"
                "Only WO3 currently has the paired metadata updater path."
            )
            self.open_button.config(state="disabled", bg="#6C6A75", activebackground="#6C6A75", text="WO3 Only Right Now", cursor="arrow")
        self.selected_desc_var.set(desc)
        self.update_game_buttons()
        try:
            self.selector_canvas.render()
        except Exception:
            pass
        if update_status:
            if supported:
                self.set_status("WO3 selected. Continue to choose the rebuilt KVS and paired metadata file.")
            else:
                self.set_status(f"{game_name} is visible here, but only WO3 is live for KVS metadata updates.")

    def open_selected_game(self):
        if self.selected_game_id != "WO3":
            messagebox.showinfo("Not Supported", "Only Warriors Orochi 3 is supported for KVS metadata updates right now.")
            self.set_status("Only WO3 currently supports KVS metadata relinking.")
            return
        self.controller.kvs_metadata_window = None
        self.destroy()
        self.controller.continue_kvs_metadata_flow(self.selected_game_id)


class Core_Tools():
    def __init__(self, root):
        self.root = root
        self.root.title("Aldnoah Engine Version 2.0")
        self.mod_creator_window = None
        self.mod_manager_window = None
        self.kvs_metadata_window = None
        self.root.geometry("1480x920")
        self.root.minsize(1320, 860)
        self.root.configure(bg=HUB_BG)

        setup_lilac_styles(self.root)
        apply_lilac_to_root(self.root)

        self.progress = None
        self.action_buttons = []
        self.ui_locked = False
        self.selected_game_id = "WO3"
        self.selected_game_title_var = tk.StringVar()
        self.selected_game_meta_var = tk.StringVar()
        self.selected_game_desc_var = tk.StringVar()
        self.status_var = tk.StringVar(value="The constellation hub is standing by.")

        self.gui_setup()
        self.init_progress()
        self.select_game(self.selected_game_id)

    def gui_setup(self):
        self.bg = tk.Frame(self.root, bg=HUB_BG)
        self.bg.pack(fill="both", expand=True)
        self.bg.grid_columnconfigure(0, weight=3, uniform="hub")
        self.bg.grid_columnconfigure(1, weight=5, uniform="hub")
        self.bg.grid_columnconfigure(2, weight=3, uniform="hub")
        self.bg.grid_rowconfigure(1, weight=1)

        self.hero = tk.Canvas(self.bg, bg=HUB_BG, height=148, highlightthickness=0)
        self.hero.grid(row=0, column=0, columnspan=3, sticky="nsew", padx=14, pady=(14, 8))
        self.hero.bind("<Configure>", self.draw_hero)

        self.games = [
            {"name": "Dynasty Warriors 7 XL (PC)", "id": "DW7XL", "short": "DW7XL"},
            {"name": "Dynasty Warriors 8 XL (PC)", "id": "DW8XL", "short": "DW8XL"},
            {"name": "Dynasty Warriors 8 Empires (PC)", "id": "DW8E", "short": "DW8E"},
            {"name": "Warriors Orochi 3 (PC)", "id": "WO3", "short": "WO3"},
            {"name": "Toukiden Kiwami (PC)", "id": "TK", "short": "TK"},
            {"name": "Bladestorm Nightmare (PC)", "id": "BN", "short": "BN"},
            {"name": "Warriors All Stars (PC)", "id": "WAS", "short": "WAS"},
        ]

        left = self.build_panel(self.bg, "Navigator", "Launch creator, manager, rebuilders, and metadata tools.")
        left["panel"].grid(row=1, column=0, sticky="nsew", padx=(14, 8), pady=(0, 8))
        center = self.build_panel(self.bg, "Game Constellation", "Click a star to inspect the schema. Double-click the sky to unpack the selected game.")
        center["panel"].grid(row=1, column=1, sticky="nsew", padx=8, pady=(0, 8))
        right = self.build_panel(self.bg, "Selected Schema", "Review the active game layout before launching the unpack flow.")
        right["panel"].grid(row=1, column=2, sticky="nsew", padx=(8, 14), pady=(0, 8))

        self.build_left_panel(left["body"])
        self.build_center_panel(center["body"])
        self.build_right_panel(right["body"])

        self.footer = tk.Frame(self.bg, bg=HUB_BG_2, highlightthickness=1, highlightbackground="#3D3164")
        self.footer.grid(row=2, column=0, columnspan=3, sticky="nsew", padx=14, pady=(0, 14))
        self.footer.grid_columnconfigure(0, weight=1)

        self.status_label = tk.Label(self.footer, textvariable=self.status_var, bg=HUB_BG_2, fg=HUB_SUCCESS, font=("Segoe UI", 10, "bold"), anchor="w")
        self.status_label.grid(row=0, column=0, sticky="ew", padx=12, pady=(10, 2))

    def build_panel(self, parent: tk.Misc, title: str, subtitle: str):
        panel = tk.Frame(parent, bg=HUB_PANEL_2, highlightthickness=1, highlightbackground="#4A3B74")
        panel.grid_rowconfigure(1, weight=1)
        panel.grid_columnconfigure(0, weight=1)

        header = tk.Canvas(panel, bg=HUB_PANEL, height=92, highlightthickness=0)
        header.grid(row=0, column=0, sticky="ew")
        header.bind("<Configure>", lambda _e, canvas=header, head=title, note=subtitle: self.draw_panel_header(canvas, head, note))

        body = tk.Frame(panel, bg=HUB_PANEL_3, padx=14, pady=14)
        body.grid(row=1, column=0, sticky="nsew")
        return {"panel": panel, "body": body, "header": header}

    def build_left_panel(self, parent: tk.Frame):
        self.tool_button(parent, "Open Mod Creator", "Forge new Aldnoah packages with previews and WAV audio.", self.open_mod_creator_window, HUB_GOLD).pack(fill="x", pady=(0, 10))
        self.tool_button(parent, "Open Mod Manager", "Inspect the constellation library and apply or disable mods.", self.open_mod_manager_window, HUB_GREEN).pack(fill="x", pady=10)
        self.repack_button = self.tool_button(parent, "Repack Subcontainer", "Rebuild a KVS or non-KVS subcontainer from its unpacked folder.", self.start_repack_thread, HUB_BLUE)
        self.repack_button.pack(fill="x", pady=10)
        self.kvs_meta_button = self.tool_button(parent, "Update KVS Metadata", "Patch paired metadata after rebuilding KVS audio subcontainers.", self.start_kvs_metadata_flow, HUB_ROSE)
        self.kvs_meta_button.pack(fill="x", pady=10)

        note = tk.Frame(parent, bg="#D8C9EF", padx=12, pady=12)
        note.pack(fill="x", pady=(18, 0))
        tk.Label(note, text="Operational Notes", bg="#D8C9EF", fg="#24183C", font=("Segoe UI", 11, "bold")).pack(anchor="w")
        tk.Label(note, text="Schemas now live in Python, non-KVS subcontainers use the universal Aldnoah path, and WO3 still keeps dedicated KVS metadata tools.", bg="#D8C9EF", fg=HUB_MUTED, justify="left", wraplength=280, font=("Segoe UI", 9)).pack(anchor="w", pady=(6, 0))

    def build_center_panel(self, parent: tk.Frame):
        self.constellation_canvas = HubConstellationCanvas(parent, self)
        self.constellation_canvas.pack(fill="both", expand=True)

    def build_right_panel(self, parent: tk.Frame):
        top = tk.Frame(parent, bg=HUB_PANEL_3)
        top.pack(fill="x")
        tk.Label(top, textvariable=self.selected_game_title_var, bg=HUB_PANEL_3, fg="#1F1430", font=("Segoe UI", 15, "bold"), anchor="w").pack(fill="x")
        tk.Label(top, textvariable=self.selected_game_meta_var, bg=HUB_PANEL_3, fg=HUB_MUTED, justify="left", anchor="nw", font=("Consolas", 9)).pack(fill="x", pady=(8, 0))

        detail = tk.Frame(parent, bg="#D8C9EF", padx=12, pady=12)
        detail.pack(fill="both", expand=True, pady=(14, 0))
        tk.Label(detail, text="Schema Brief", bg="#D8C9EF", fg="#24183C", font=("Segoe UI", 11, "bold")).pack(anchor="w")
        tk.Label(detail, textvariable=self.selected_game_desc_var, bg="#D8C9EF", fg=HUB_MUTED, justify="left", wraplength=300, font=("Segoe UI", 9)).pack(fill="x", pady=(6, 14))

        self.unpack_button = tk.Button(detail, text="Launch Selected Unpack", command=self.launch_selected_unpack, bg=HUB_GOLD, fg="white", activebackground=HUB_GOLD, activeforeground="white", font=("Segoe UI", 10, "bold"), relief="flat", bd=0, padx=14, pady=10, cursor="hand2")
        self.unpack_button.pack(fill="x")
        self.action_buttons.append(self.unpack_button)

        tk.Label(detail, text="Sky Marks", bg="#D8C9EF", fg="#24183C", font=("Segoe UI", 11, "bold")).pack(anchor="w", pady=(18, 6))
        legend = [
            ("Gold", "Selected game"),
            ("Lilac", "Available unpack target"),
            ("Blue tools", "Subcontainer work"),
            ("Rose tools", "KVS metadata updater"),
        ]
        for color_name, text in legend:
            tk.Label(detail, text=f"{color_name}: {text}", bg="#D8C9EF", fg=HUB_MUTED, anchor="w", font=("Segoe UI", 9)).pack(fill="x")
            
    def open_mod_creator_window(self):
        """
        Open the game selection window for mod creators
        
        If it already exists, just focus/raise it instead of creating another
        """
        # If window exists and hasn't been destroyed, just raise/focus it
        if self.mod_creator_window is not None and self.mod_creator_window.winfo_exists():
            self.mod_creator_window.lift()
            self.mod_creator_window.focus_force()
            return

        # Otherwise create a new one and remember it
        from .aldnoah_mod_creator import ModCreatorGameSelect
        self.mod_creator_window = ModCreatorGameSelect(self.root)

        def on_close():
            # Clear the reference when the window is closed
            self.mod_creator_window.destroy()
            self.mod_creator_window = None

        self.mod_creator_window.protocol("WM_DELETE_WINDOW", on_close)

    def open_mod_manager_window(self):
        """
        Open the game selection window for the Mod Manager
        If it already exists, just focus/raise it instead of creating another
        """
        if self.mod_manager_window is not None and self.mod_manager_window.winfo_exists():
            self.mod_manager_window.lift()
            self.mod_manager_window.focus_force()
            return

        # Local import to avoid circular imports during package startup
        from .aldnoah_mod_manager import ModManagerGameSelect
        self.mod_manager_window = ModManagerGameSelect(self.root)

        def on_close():
            self.mod_manager_window.destroy()
            self.mod_manager_window = None

        self.mod_manager_window.protocol("WM_DELETE_WINDOW", on_close)

    # Progress/status bar setup

    def init_progress(self):
        """
        Create a progress bar/label at the bottom of the window
        """
        self.progress = {}
        self.progress["var"] = tk.StringVar(value="Idle")
        bar = ttk.Progressbar(self.footer, mode="determinate", length=720)
        bar_style = ttk.Style(master=self.root)
        bar_style.theme_use("clam")
        bar_style.configure("Hub.Horizontal.TProgressbar", troughcolor="#211A34", background=HUB_NODE_SEL, bordercolor="#211A34", lightcolor=HUB_NODE_SEL, darkcolor=HUB_NODE_SEL)
        bar.configure(style="Hub.Horizontal.TProgressbar")
        bar.grid(row=1, column=0, sticky="ew", padx=12, pady=(8, 2))
        self.progress["bar"] = bar
        prog_label = tk.Label(self.footer, textvariable=self.progress["var"], bg=HUB_BG_2, fg=HUB_SUBTEXT, font=("Segoe UI", 9))
        prog_label.grid(row=2, column=0, sticky="w", padx=12, pady=(0, 10))
        self.progress["label"] = prog_label

    def set_progress(self, done, total, note=None):
        """
        Update the progress bar and text
        """
        if self.progress is None:
            return

        bar = self.progress["bar"]
        var = self.progress["var"]

        total = max(1, int(total))
        done = min(int(done), total)

        if int(bar["maximum"] or 0) != total:
            bar.configure(maximum=total)

        bar["value"] = done

        if note is None:
            pct = (done * 100) // total
            var.set(f"Working {done}/{total} ({pct}%)")
        else:
            var.set(note)

        # Keep UI responsive without reentering mainloop
        self.root.update_idletasks()

    def set_buttons_state(self, state):
        """Enable/disable buttons while work is in progress"""
        self.ui_locked = state != "normal"
        for btn in self.action_buttons:
            try:
                btn.config(state=state)
            except Exception:
                pass
        for attr in ("repack_button", "kvs_meta_button"):
            btn = getattr(self, attr, None)
            if btn is not None:
                try:
                    btn.config(state=state)
                except Exception:
                    pass
        if hasattr(self, "constellation_canvas"):
            self.constellation_canvas.render()

    def set_status(self, text: str, color: str = HUB_SUCCESS):
        self.status_var.set(text)
        self.status_label.config(fg=color)

    def tool_button(self, parent: tk.Misc, title: str, subtitle: str, command, color: str):
        outer = tk.Frame(parent, bg=color, highlightthickness=0)
        btn = tk.Button(outer, text=title, command=command, bg=color, fg="white", activebackground=color, activeforeground="white", font=("Segoe UI", 11, "bold"), relief="flat", bd=0, padx=14, pady=12, anchor="w", cursor="hand2")
        btn.pack(fill="x")
        sub = tk.Label(outer, text=subtitle, bg=color, fg="#F6F1FF", wraplength=280, justify="left", anchor="w", font=("Segoe UI", 9))
        sub.pack(fill="x", padx=14, pady=(0, 12))
        self.action_buttons.append(btn)
        return outer

    def draw_hero(self, event=None):
        canvas = event.widget if event else self.hero
        canvas.delete("all")
        width = max(1, canvas.winfo_width())
        height = max(1, canvas.winfo_height())
        bands = [HUB_BG, HUB_BG_2, HUB_PANEL, "#38295F"]
        band_h = max(1, height // len(bands))
        for idx, color in enumerate(bands):
            y0 = idx * band_h
            canvas.create_rectangle(0, y0, width, y0 + band_h + 2, fill=color, outline="")
        rnd = random.Random(12)
        for _ in range(58):
            x = rnd.randint(12, width - 12)
            y = rnd.randint(12, height - 12)
            r = rnd.randint(1, 3)
            canvas.create_oval(x - r, y - r, x + r, y + r, fill=HUB_STAR, outline="")
        links = [(0.04, 0.32, 0.18, 0.18), (0.18, 0.18, 0.43, 0.28), (0.43, 0.28, 0.70, 0.18), (0.70, 0.18, 0.90, 0.38)]
        for ax, ay, bx, by in links:
            canvas.create_line(int(width * ax), int(height * ay), int(width * bx), int(height * by), fill=HUB_LINE, width=1)
        canvas.create_arc(26, 20, 220, 220, start=28, extent=284, style=tk.ARC, outline="#8B76E0", width=2)
        canvas.create_arc(width - 260, -14, width - 18, 200, start=208, extent=264, style=tk.ARC, outline="#6FAFFF", width=2)
        canvas.create_text(22, 24, anchor="nw", text="Aldnoah Engine Hub", fill=HUB_TEXT, font=("Segoe UI", 26, "bold"))
        canvas.create_text(24, 60, anchor="nw", text="Constellation-aligned tool nexus for unpacking, decompressing, rebuilding subcontainers, creating, and managing mods.", fill=HUB_SUBTEXT, font=("Segoe UI", 10))

    def draw_panel_header(self, canvas: tk.Canvas, title: str, subtitle: str):
        canvas.delete("all")
        width = max(1, canvas.winfo_width())
        height = max(1, canvas.winfo_height())
        canvas.create_rectangle(0, 0, width, height, fill=HUB_PANEL, outline="")
        canvas.create_rectangle(0, 0, width, 18, fill=HUB_NODE, outline="")
        rnd = random.Random(len(title) * 7 + 5)
        pts = []
        for _ in range(14):
            pts.append((rnd.uniform(0.05, 0.95), rnd.uniform(0.18, 0.78)))
        for idx in range(0, 10, 2):
            ax, ay = pts[idx]
            bx, by = pts[idx + 1]
            canvas.create_line(int(ax * width), int(ay * height), int(bx * width), int(by * height), fill=HUB_LINE, width=1)
        for x, y in pts:
            sx = int(x * width)
            sy = int(y * height)
            canvas.create_oval(sx - 2, sy - 2, sx + 2, sy + 2, fill=HUB_STAR, outline="")
        canvas.create_text(14, 28, anchor="nw", text=title, fill=HUB_TEXT, font=("Segoe UI", 13, "bold"))
        canvas.create_text(14, 54, anchor="nw", text=subtitle, fill=HUB_SUBTEXT, width=max(140, width - 28), font=("Segoe UI", 9))

    def select_game(self, game_id: str):
        self.selected_game_id = game_id
        schema = get_game_schema(game_id)
        display_name = next((g["name"] for g in self.games if g["id"] == game_id), schema.display_name)
        self.selected_game_title_var.set(display_name)
        self.selected_game_meta_var.set(
            f"ID: {schema.game_id}\n"
            f"Containers: {len(schema.containers)}\n"
            f"IDX Files: {len(schema.idx_files)}\n"
            f"Compression: {schema.compression}\n"
            f"Endian: {schema.endian}\n"
            f"Output: {schema.unpack_folder}"
        )
        self.selected_game_desc_var.set(
            f"This schema drives unpacking directly from Python."
        )
        if hasattr(self, "constellation_canvas"):
            self.constellation_canvas.render()

    def launch_selected_unpack(self):
        self.start_unpack_thread(self.selected_game_id)

    # Threaded unpack flow

    def start_unpack_thread(self, game_id: str):
        """
        Main entry when a game button is clicked:
        resolve the in-code schema, ask for the game folder, and then start unpacking
        """
        try:
            schema = get_game_schema(game_id)
        except Exception as e:
            self.set_status(f"Error loading schema for {game_id}: {e}", HUB_ROSE)
            return

        game_name = schema.display_name or game_id

        # Ask user for the game folder
        base_dir = filedialog.askdirectory(
            title=f"Select the install folder for {game_name}"
        )
        if not base_dir:
            self.set_status("Action cancelled. No folder selected.", HUB_ROSE)
            return

        # Disable buttons and bootstrap progress
        self.set_buttons_state("disabled")
        self.set_progress(0, 1, f"Preparing unpack for {game_name}…")
        self.set_status(f"Using base folder: {base_dir}", "#7FB3FF")

        # Notification function
        def notify(msg):
            # marshal back into Tk's thread safely
            self.root.after(0, self.handle_msg, msg)

        # Start the worker thread
        t = threading.Thread(
            target=self.unpack_worker,
            args=(schema, base_dir, notify),
            daemon=True
        )
        t.start()

    def unpack_worker(self, schema, base_dir, notify):
        """
        Background thread:

        wraps aldnoah_unpack.unpack_from_schema
        sends (status, text, color), (progress), (done, note)
        """
        def status_cb(text, color="blue"):
            notify(("status", text, color))

        def progress_cb(done, total, note=None):
            notify(("progress", done, total, note or "Unpacking"))

        try:
            # kick off progress at 0
            notify(("progress", 0, 1, "Unpacking"))
            unpack_from_schema(
                schema,
                base_dir=base_dir,
                status_callback=status_cb,
                progress_callback=progress_cb,
            )
            notify(("done", "Unpack complete."))
        except Exception as e:
            notify(("status", f"Error during unpack: {e}", "red"))
            notify(("done", "Error."))

        # Threaded repack flow

    def start_repack_thread(self):
        """
        Ask the user for an unpacked subcontainer folder and its original
        unpacked source file, then start a background repack task
        """
        folder = filedialog.askdirectory(
            title="Select folder to repack (generic subcontainer or KVS)"
        )
        if not folder:
            self.set_status("Repack cancelled. No folder selected.", HUB_ROSE)
            return

        base_file = filedialog.askopenfilename(
            title="Select original unpacked source file (provides the 6 byte taildata)",
            filetypes=[("All files", "*.*")],
        )
        if not base_file:
            self.set_status("Repack cancelled. No base file selected.", HUB_ROSE)
            return

        self.set_buttons_state("disabled")
        self.set_progress(0, 1, "Preparing repack")
        self.set_status(f"Repacking from folder: {folder}", "#7FB3FF")

        def notify(msg):
            self.root.after(0, self.handle_msg, msg)

        t = threading.Thread(
            target=self.repack_worker,
            args=(folder, base_file, notify),
            daemon=True,
        )
        t.start()

    def repack_worker(self, folder: str, base_file: str, notify):
        """
        Background thread:

        wraps aldnoah_repacks.repack_from_folder
        sends (status, text, color), (progress), (done, note)
        """

        def status_cb(text, color="blue"):
            notify(("status", text, color))

        def progress_cb(done, total, note=None):
            notify(("progress", done, total, note or "Repacking"))

        try:
            notify(("progress", 0, 1, "Repacking"))
            out_path = repack_from_folder(
                folder,
                base_file_path=base_file,
                status_callback=status_cb,
                progress_callback=progress_cb,
            )
            if out_path:
                notify(("done", f"Repack complete: {out_path}"))
            else:
                notify(("done", "Repack finished (no output created)."))
        except Exception as e:
            notify(("status", f"Error during repack: {e}", "red"))
            notify(("done", "Error during repack."))

    
    # Threaded KVS metadata update flow

    def start_kvs_metadata_flow(self):
        """
        UI flow:
             choose game, only WO3 enabled right now
             select repacked KVS subcontainer
             select paired metadata file
             run metadata updater in a background thread
        """
        if self.kvs_metadata_window is not None and self.kvs_metadata_window.winfo_exists():
            self.kvs_metadata_window.lift()
            self.kvs_metadata_window.focus_force()
            return

        self.kvs_metadata_window = KVSMetadataGameSelect(self.root, self)

        def on_close():
            try:
                self.kvs_metadata_window.destroy()
            finally:
                self.kvs_metadata_window = None

        self.kvs_metadata_window.protocol("WM_DELETE_WINDOW", on_close)

    def continue_kvs_metadata_flow(self, gid: str):
        gid = (gid or "").strip()
        if gid != "WO3":
            messagebox.showinfo(
                "Not Supported",
                "Only Warriors Orochi 3 is supported for KVS metadata updates right now.",
            )
            self.set_status("Only WO3 currently supports KVS metadata relinking.", HUB_ROSE)
            return

        kvs_path = filedialog.askopenfilename(
            title="Select the repacked KVS subcontainer",
            filetypes=[("KVS subcontainer", "*.kvs"), ("All files", "*.*")],
        )
        if not kvs_path:
            self.set_status("KVS metadata update cancelled. No KVS subcontainer selected.", HUB_ROSE)
            return

        paired_meta = os.path.basename(kvs_path)
        if paired_meta.lower().endswith(".kvs"):
            paired_meta = paired_meta[:-4] + ".bin"

        meta_path = filedialog.askopenfilename(
            title=f"Select {paired_meta} from Pack_00",
            filetypes=[("BIN metadata", "*.bin"), ("All files", "*.*")],
        )
        if not meta_path:
            self.set_status("KVS metadata update cancelled. No metadata .bin selected.", HUB_ROSE)
            return

        self.start_kvs_metadata_thread(gid, kvs_path, meta_path)

    def start_kvs_metadata_thread(self, game_id: str, kvs_path: str, meta_path: str):
        """
        Start the metadata patch in a background thread
        """
        self.set_buttons_state("disabled")
        self.set_progress(0, 1, "Preparing metadata update")
        self.set_status(f"Updating KVS metadata: {os.path.basename(meta_path)}", "#7FB3FF")

        def notify(msg):
            self.root.after(0, self.handle_msg, msg)

        t = threading.Thread(
            target=self.kvs_metadata_worker,
            args=(game_id, kvs_path, meta_path, notify),
            daemon=True,
        )
        t.start()

    def kvs_metadata_worker(self, game_id: str, kvs_path: str, meta_path: str, notify):
        """
        Worker thread that calls aldnoah_repacks.update_kvs_metadata
        """
        def status_cb(text, color="blue"):
            notify(("status", text, color))

        def progress_cb(done, total, note=None):
            notify(("progress", done, total, note or "Updating metadata"))

        try:
            notify(("progress", 0, 1, "Scanning KVS"))
            update_kvs_metadata(
                game_id,
                kvs_path,
                meta_path,
                status_callback=status_cb,
                progress_callback=progress_cb,
            )
            notify(("done", f"Metadata updated: {os.path.basename(meta_path)}"))
        except Exception as e:
            notify(("status", f"Error updating metadata: {e}", "red"))
            notify(("done", "Error updating metadata."))

    def handle_msg(self, msg):
            """
            Handle messages coming from worker threads
            """
            kind = msg[0]

            if kind == "status":
                _, text, color = msg
                self.set_status(text, color)

            elif kind == "progress":
                _, done, total, note = msg
                self.set_progress(done, total, note)

            elif kind == "done":
                _, note = msg
                # finalize bar + re-enable buttons
                self.set_progress(1, 1, note)
                self.set_buttons_state("normal")
