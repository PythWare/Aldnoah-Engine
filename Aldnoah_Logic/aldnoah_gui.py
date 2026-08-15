# Aldnoah_Logic/aldnoah_gui.py
import math, os, random, threading
import tkinter as tk
from tkinter import ttk, filedialog, messagebox

from .aldnoah_energy import LILAC, get_game_schema, setup_lilac_styles, apply_lilac_to_root
from .aldnoah_unpack import generate_taildata_manifest, unpack_from_schema
from .aldnoah_mod_creator import ModCreatorGameSelect
from .aldnoah_mod_manager import ModManagerGameSelect
from .aldnoah_repacks import repack_from_folder
from .aldnoah_tools import diagnose_aldnoah_directory

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
        self.after(120, self.tick)

    def make_stars(self):
        rnd = random.Random(44)
        return [(rnd.uniform(0.04, 0.96), rnd.uniform(0.06, 0.92), rnd.randint(1, 3)) for _ in range(74)]

    def tick(self):
        self.phase += 0.08
        if self.winfo_exists():
            self.render()
            self.after(120, self.tick)

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
            "WO4": (width * 0.52, height * 0.56),
            "BN": (width * 0.52, height * 0.82),
            "WAS": (width * 0.83, height * 0.62),
            "DQB2": (width * 0.84, height * 0.88),
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
        links = [("DW7XL", "DW8XL"), ("DW8XL", "DW8E"), ("DW7XL", "WO3"), ("WO3", "WO4"), ("WO4", "BN"), ("BN", "WAS"), ("DW8E", "WAS"), ("DW8XL", "WO4"), ("DW8XL", "BN"), ("WAS", "DQB2"), ("BN", "DQB2")]
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


class Core_Tools():
    def __init__(self, root):
        self.root = root
        self.root.title("Aldnoah Engine Version 2.025")
        self.mod_creator_window = None
        self.mod_manager_window = None
        self.root.geometry("1480x1000")
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
            {"name": "Warriors Orochi 4 (PC)", "id": "WO4", "short": "WO4"},
            {"name": "Bladestorm Nightmare (PC)", "id": "BN", "short": "BN"},
            {"name": "Warriors All Stars (PC)", "id": "WAS", "short": "WAS"},
            {"name": "Dragon Quest Builders 2 (PC)", "id": "DQB2", "short": "DQB2"},
        ]

        left = self.build_panel(self.bg, "Navigator", "Launch creator, manager, rebuilders, and the metadata tool.")
        left["panel"].grid(row=1, column=0, sticky="nsew", padx=(14, 8), pady=(0, 8))
        center = self.build_panel(self.bg, "Game Constellation", "Click a star to inspect the schema. Double-click the sky to unpack the selected game.")
        center["panel"].grid(row=1, column=1, sticky="nsew", padx=8, pady=(0, 8))
        right_stack = tk.Frame(self.bg, bg=HUB_BG)
        right_stack.grid(row=1, column=2, sticky="nsew", padx=(8, 14), pady=(0, 8))
        right_stack.grid_columnconfigure(0, weight=1)
        right_stack.grid_rowconfigure(0, weight=1, uniform="right_side")
        right_stack.grid_rowconfigure(1, weight=1, uniform="right_side")

        right = self.build_panel(
            right_stack,
            "Selected Schema",
            "Review the active game layout before launching the unpack flow.",
            header_height=74,
            body_pad=12,
        )
        right["panel"].grid(row=0, column=0, sticky="nsew", pady=(0, 6))
        tools = self.build_panel(
            right_stack,
            "Tools",
            "General purpose utilities.",
            header_height=74,
            body_pad=12,
        )
        tools["panel"].grid(row=1, column=0, sticky="nsew", pady=(6, 0))

        self.build_left_panel(left["body"])
        self.build_center_panel(center["body"])
        self.build_right_panel(right["body"])
        self.build_tools_panel(tools["body"])

        self.footer = tk.Frame(self.bg, bg=HUB_BG_2, highlightthickness=1, highlightbackground="#3D3164")
        self.footer.grid(row=2, column=0, columnspan=3, sticky="nsew", padx=14, pady=(0, 14))
        self.footer.grid_columnconfigure(0, weight=1)

        self.status_label = tk.Label(self.footer, textvariable=self.status_var, bg=HUB_BG_2, fg=HUB_SUCCESS, font=("Segoe UI", 10, "bold"), anchor="w")
        self.status_label.grid(row=0, column=0, sticky="ew", padx=12, pady=(10, 2))

    def build_panel(self, parent: tk.Misc, title: str, subtitle: str, header_height: int = 92, body_pad: int = 14):
        panel = tk.Frame(parent, bg=HUB_PANEL_2, highlightthickness=1, highlightbackground="#4A3B74")
        panel.grid_rowconfigure(1, weight=1)
        panel.grid_columnconfigure(0, weight=1)

        header = tk.Canvas(panel, bg=HUB_PANEL, height=header_height, highlightthickness=0)
        header.grid(row=0, column=0, sticky="ew")
        header.bind("<Configure>", lambda _e, canvas=header, head=title, note=subtitle: self.draw_panel_header(canvas, head, note))

        body = tk.Frame(panel, bg=HUB_PANEL_3, padx=body_pad, pady=body_pad)
        body.grid(row=1, column=0, sticky="nsew")
        return {"panel": panel, "body": body, "header": header}

    def build_left_panel(self, parent: tk.Frame):
        self.tool_button(parent, "Open Mod Creator", "Forge new Aldnoah packages with previews and WAV audio.", self.open_mod_creator_window, HUB_GOLD).pack(fill="x", pady=(0, 10))
        self.tool_button(parent, "Open Mod Manager", "Inspect the constellation library and apply or disable mods.", self.open_mod_manager_window, HUB_GREEN).pack(fill="x", pady=10)
        self.repack_button = self.tool_button(parent, "Repack Subcontainer", "Rebuild a KVS or non-KVS subcontainer from its unpacked folder.", self.start_repack_thread, HUB_BLUE)
        self.repack_button.pack(fill="x", pady=10)

        self.merger_button = self.tool_button(
            parent,
            "Open Aldnoah Merger",
            "Combine mods that touch the same file instead of letting one overwrite the other.",
            self.open_merger_window,
            HUB_ROSE,
        )
        self.merger_button.pack(fill="x", pady=10)

    def build_center_panel(self, parent: tk.Frame):
        self.constellation_canvas = HubConstellationCanvas(parent, self)
        self.constellation_canvas.pack(fill="both", expand=True)

    def build_right_panel(self, parent: tk.Frame):
        top = tk.Frame(parent, bg=HUB_PANEL_3)
        top.pack(fill="x")
        tk.Label(top, textvariable=self.selected_game_title_var, bg=HUB_PANEL_3, fg="#1F1430", font=("Segoe UI", 15, "bold"), anchor="w").pack(fill="x")
        tk.Label(top, textvariable=self.selected_game_meta_var, bg=HUB_PANEL_3, fg=HUB_MUTED, justify="left", anchor="nw", font=("Consolas", 8)).pack(fill="x", pady=(6, 0))

        detail = tk.Frame(parent, bg="#D8C9EF", padx=10, pady=10)
        detail.pack(fill="both", expand=True, pady=(10, 0))
        tk.Label(detail, text="Schema Brief", bg="#D8C9EF", fg="#24183C", font=("Segoe UI", 10, "bold")).pack(anchor="w")
        tk.Label(detail, textvariable=self.selected_game_desc_var, bg="#D8C9EF", fg=HUB_MUTED, justify="left", wraplength=280, font=("Segoe UI", 8)).pack(fill="x", pady=(4, 10))

        self.unpack_button = tk.Button(detail, text="Launch Selected Unpack", command=self.launch_selected_unpack, bg=HUB_GOLD, fg="white", activebackground=HUB_GOLD, activeforeground="white", font=("Segoe UI", 9, "bold"), relief="flat", bd=0, padx=12, pady=8, cursor="hand2")
        self.unpack_button.pack(fill="x")
        self.action_buttons.append(self.unpack_button)

    def build_tools_panel(self, parent: tk.Frame):
        self.diagnostics_button = self.compact_tool_button(
            parent,
            "Diagnostics",
            "Utility checker, click this if it's your first time using AE.",
            self.open_diagnostics,
            HUB_BLUE,
        )
        self.diagnostics_button.pack(fill="x")

        self.taildata_button = self.compact_tool_button(
            parent,
            "Generate Taildata JSON",
            "Map the selected game's containers without unpacking, so modding needs no extracted files.",
            self.start_taildata_generation,
            HUB_GREEN,
        )
        self.taildata_button.pack(fill="x", pady=(10, 0))

    def start_taildata_generation(self):
        """
        Build the taildata manifest for the selected game without unpacking it

        The containers still have to be read and decoded so the recorded names
        match a real unpack, but nothing is written except the JSON
        """
        game_id = self.selected_game_id
        if not game_id:
            self.set_status("Select a game star first.", HUB_ROSE)
            return

        try:
            schema = get_game_schema(game_id)
        except KeyError as exc:
            self.set_status(f"Unknown game: {exc}", HUB_ROSE)
            return

        base = filedialog.askdirectory(
            title=f"Select the {schema.display_name} folder holding "
                  f"{schema.containers[0]}"
        )
        if not base:
            self.set_status("Taildata generation cancelled.", HUB_ROSE)
            return

        missing = [n for n in schema.containers + schema.idx_files
                   if not os.path.isfile(os.path.join(base, n))]
        if len(missing) == len(schema.containers) + len(schema.idx_files):
            self.set_status(f"No {schema.display_name} containers found in that folder.", HUB_ROSE)
            messagebox.showerror(
                "Generate Taildata JSON",
                f"None of the expected files were found in:\n{base}\n\n"
                f"Expected: {', '.join(schema.containers + schema.idx_files)}",
            )
            return

        self.set_buttons_state("disabled")
        self.set_progress(0, 1, "Scanning containers")
        self.set_status(f"Scanning {schema.display_name} containers…", "#7FB3FF")

        def notify(msg):
            self.root.after(0, self.handle_msg, msg)

        t = threading.Thread(
            target=self.taildata_worker, args=(schema, base, notify), daemon=True
        )
        t.start()

    def taildata_worker(self, schema, base_dir: str, notify):
        def status_cb(text, color="blue"):
            notify(("status", text, color))

        def progress_cb(done, total, note=None):
            notify(("progress", done, total, note or "Scanning"))

        try:
            notify(("progress", 0, 1, "Scanning"))
            path = generate_taildata_manifest(
                schema, base_dir,
                status_callback=status_cb,
                progress_callback=progress_cb,
            )
            if path:
                notify(("done", f"Taildata written: {path}"))
            else:
                notify(("done", "Taildata generation finished with no manifest written."))
        except Exception as e:
            notify(("status", f"Error generating taildata: {e}", HUB_ROSE))
            notify(("done", "Error generating taildata."))

    def open_mod_creator_window(self):
        if self.mod_creator_window is not None and self.mod_creator_window.winfo_exists():
            self.mod_creator_window.lift()
            self.mod_creator_window.focus_force()
            return

        from .aldnoah_mod_creator import ModCreatorGameSelect
        self.mod_creator_window = ModCreatorGameSelect(self.root)

        def on_close():
            self.mod_creator_window.destroy()
            self.mod_creator_window = None

        self.mod_creator_window.protocol("WM_DELETE_WINDOW", on_close)

    def open_mod_manager_window(self):
        if self.mod_manager_window is not None and self.mod_manager_window.winfo_exists():
            self.mod_manager_window.lift()
            self.mod_manager_window.focus_force()
            return

        from .aldnoah_mod_manager import ModManagerGameSelect
        self.mod_manager_window = ModManagerGameSelect(self.root)

        def on_close():
            self.mod_manager_window.destroy()
            self.mod_manager_window = None

        self.mod_manager_window.protocol("WM_DELETE_WINDOW", on_close)

    def open_merger_window(self):
        from .aldnoah_merger_gui import open_merger
        open_merger(self.root, self.selected_game_id or "")

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

        self.root.update_idletasks()

    def set_buttons_state(self, state):
        """Enable/disable buttons while work is in progress"""
        self.ui_locked = state != "normal"
        for btn in self.action_buttons:
            try:
                btn.config(state=state)
            except Exception:
                pass
        for attr in ("repack_button", "taildata_button"):
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

    def compact_tool_button(self, parent: tk.Misc, title: str, subtitle: str, command, color: str):
        outer = tk.Frame(parent, bg=color, highlightthickness=0)
        btn = tk.Button(outer, text=title, command=command, bg=color, fg="white", activebackground=color, activeforeground="white", font=("Segoe UI", 10, "bold"), relief="flat", bd=0, padx=12, pady=8, anchor="w", cursor="hand2")
        btn.pack(fill="x")
        sub = tk.Label(outer, text=subtitle, bg=color, fg="#F6F1FF", wraplength=260, justify="left", anchor="w", font=("Segoe UI", 8))
        sub.pack(fill="x", padx=12, pady=(0, 8))
        self.action_buttons.append(btn)
        return outer

    def open_diagnostics(self):
        diagnostics = diagnose_aldnoah_directory()
        report = diagnostics.report_text()
        if diagnostics.has_errors:
            messagebox.showerror("Diagnostics", report)
            self.set_status("Diagnostics found a directory problem.", HUB_ROSE)
        elif diagnostics.has_warnings:
            messagebox.showwarning("Diagnostics", report)
            self.set_status("Diagnostics found a directory warning.", "#7FB3FF")
        else:
            messagebox.showinfo("Diagnostics", report)
            self.set_status("Diagnostics passed. AE can read/write in this directory.", HUB_SUCCESS)

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
        compact = height < 84
        bar_height = 16 if compact else 18
        title_y = 23 if compact else 28
        subtitle_y = 45 if compact else 54
        title_font = ("Segoe UI", 12 if compact else 13, "bold")
        subtitle_font = ("Segoe UI", 8 if compact else 9)
        canvas.create_rectangle(0, 0, width, height, fill=HUB_PANEL, outline="")
        canvas.create_rectangle(0, 0, width, bar_height, fill=HUB_NODE, outline="")
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
        canvas.create_text(14, title_y, anchor="nw", text=title, fill=HUB_TEXT, font=title_font)
        canvas.create_text(14, subtitle_y, anchor="nw", text=subtitle, fill=HUB_SUBTEXT, width=max(140, width - 28), font=subtitle_font)

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

        base_dir = filedialog.askdirectory(
            title=f"Select the install folder for {game_name}"
        )
        if not base_dir:
            self.set_status("Action cancelled. No folder selected.", HUB_ROSE)
            return

        self.set_buttons_state("disabled")
        self.set_progress(0, 1, f"Preparing unpack for {game_name}…")
        self.set_status(f"Using base folder: {base_dir}", "#7FB3FF")

        def notify(msg):
            self.root.after(0, self.handle_msg, msg)

        t = threading.Thread(
            target=self.unpack_worker,
            args=(schema, base_dir, notify),
            daemon=True
        )
        t.start()

    def unpack_worker(self, schema, base_dir, notify):
        """
        Background thread
        """
        def status_cb(text, color="blue"):
            notify(("status", text, color))

        def progress_cb(done, total, note=None):
            notify(("progress", done, total, note or "Unpacking"))

        try:
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
            title="Select original unpacked source file (provides the layout and target slot)",
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
            args=(folder, base_file, notify, self.selected_game_id or ""),
            daemon=True,
        )
        t.start()

    def repack_worker(self, folder: str, base_file: str, notify, game_id: str = ""):
        """
        Background thread
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
                game_id=game_id,
            )
            if out_path:
                notify(("done", f"Repack complete: {out_path}"))
            else:
                notify(("done", "Repack finished (no output created)."))
        except Exception as e:
            notify(("status", f"Error during repack: {e}", "red"))
            notify(("done", "Error during repack."))

    
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
                self.set_progress(1, 1, note)
                self.set_buttons_state("normal")
