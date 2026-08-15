# Aldnoah_Logic/aldnoah_merger_gui.py
"""
Aldnoah Merger window
"""
from __future__ import annotations

import os, threading
import tkinter as tk
from tkinter import filedialog, messagebox, ttk
from typing import Dict, List, Optional

from .aldnoah_energy import LILAC, apply_lilac_to_root, setup_lilac_styles
from .aldnoah_merge import (
    KIND_CONFLICT,
    KIND_IDENTICAL,
    KIND_LOOSE,
    KIND_SUBCONTAINER,
    KIND_UNIQUE,
    BaseLibrary,
    MergePlan,
    MergeSource,
    describe_target,
    load_source,
    plan_merge,
    resolve_conflicts_by_priority,
    write_merged_package,
)
from .aldnoah_mod_manager import BASE_MODS_DIR, MOD_PROFILES
from .aldnoah_tools import run_in_background

BG = "#1A1327"
PANEL = "#241A38"
PANEL_2 = "#2E2247"
TEXT = "#EFE8FF"
MUTED = "#B9A9DA"
GOLD = "#F5D889"
GREEN = "#8FE7A7"
ROSE = "#F08D91"
BLUE = "#7FB3FF"
EDGE = "#4A3B74"

KIND_LABEL = {
    KIND_UNIQUE: ("Clean", GREEN),
    KIND_IDENTICAL: ("Same bytes", GREEN),
    KIND_SUBCONTAINER: ("Merged", GOLD),
    KIND_LOOSE: ("Merged", GOLD),
    KIND_CONFLICT: ("Conflict", ROSE),
}

open_window: Optional["AldnoahMergerWindow"] = None


def open_merger(parent: tk.Misc, game_id: str = "") -> "AldnoahMergerWindow":
    """Open the merger or raise the one already on screen"""
    global open_window
    if open_window is not None:
        try:
            if open_window.winfo_exists():
                open_window.lift()
                open_window.focus_force()
                if game_id:
                    open_window.set_game(game_id)
                return open_window
        except tk.TclError:
            pass
        open_window = None

    open_window = AldnoahMergerWindow(parent, game_id)
    return open_window


class AldnoahMergerWindow(tk.Toplevel):
    def __init__(self, parent: tk.Misc, game_id: str = ""):
        super().__init__(parent)
        self.title("Aldnoah Merger")
        self.configure(bg=BG)
        self.geometry("1120x760")
        self.minsize(940, 640)
        setup_lilac_styles(self)

        self.game_id = tk.StringVar(value=game_id or sorted(MOD_PROFILES)[0])
        self.status_var = tk.StringVar(value="Add two or more mods to merge.")
        self.unpack_root = tk.StringVar(value=os.getcwd())

        self.sources: List[MergeSource] = []
        self.plan: Optional[MergePlan] = None
        self.busy = False

        self.build_ui()
        self.protocol("WM_DELETE_WINDOW", self.on_close)
        self.refresh_sources()

    def build_ui(self):
        head = tk.Frame(self, bg=PANEL, padx=16, pady=12)
        head.pack(fill="x")
        tk.Label(head, text="Aldnoah Merger", bg=PANEL, fg=TEXT,
                 font=("Segoe UI", 18, "bold")).pack(anchor="w")
        tk.Label(head, text="Combine mods that touch the same files instead of "
                            "letting the last one applied overwrite the rest.",
                 bg=PANEL, fg=MUTED, font=("Segoe UI", 9)).pack(anchor="w")

        bar = tk.Frame(self, bg=BG, padx=16, pady=10)
        bar.pack(fill="x")
        tk.Label(bar, text="Game", bg=BG, fg=MUTED,
                 font=("Segoe UI", 9, "bold")).pack(side="left")
        self.game_box = ttk.Combobox(bar, textvariable=self.game_id, width=10,
                                     state="readonly", values=sorted(MOD_PROFILES))
        self.game_box.pack(side="left", padx=(6, 16))
        self.game_box.bind("<<ComboboxSelected>>", lambda _e: self.refresh_sources())

        tk.Label(bar, text="Unpack folder", bg=BG, fg=MUTED,
                 font=("Segoe UI", 9, "bold")).pack(side="left")
        tk.Entry(bar, textvariable=self.unpack_root, width=46, bg=PANEL_2, fg=TEXT,
                 insertbackground=TEXT, relief="flat").pack(side="left", padx=6)
        self.button(bar, "Browse", self.pick_unpack_root, BLUE).pack(side="left")

        body = tk.Frame(self, bg=BG, padx=16)
        body.pack(fill="both", expand=True)
        body.grid_columnconfigure(0, weight=2, uniform="m")
        body.grid_columnconfigure(1, weight=3, uniform="m")
        body.grid_rowconfigure(0, weight=1)

        left = self.panel(body, "Mods to merge",
                          "Order sets priority: later wins a forced conflict.")
        left["frame"].grid(row=0, column=0, sticky="nsew", padx=(0, 8), pady=(0, 8))
        self.source_list = tk.Listbox(
            left["body"], bg=PANEL_2, fg=TEXT, selectbackground=GOLD,
            selectforeground="#1A1327", relief="flat", highlightthickness=0,
            activestyle="none", font=("Segoe UI", 10))
        self.source_list.pack(fill="both", expand=True, pady=(0, 8))
        row = tk.Frame(left["body"], bg=PANEL)
        row.pack(fill="x")
        self.button(row, "Add mods", self.add_mods, GOLD).pack(side="left")
        self.button(row, "Remove", self.remove_selected, ROSE).pack(side="left", padx=6)
        self.button(row, "Up", lambda: self.move_selected(-1), BLUE).pack(side="left")
        self.button(row, "Down", lambda: self.move_selected(1), BLUE).pack(side="left", padx=6)

        right = self.panel(body, "Merge plan",
                           "What the engine worked out for every touched slot.")
        right["frame"].grid(row=0, column=1, sticky="nsew", pady=(0, 8))
        cols = ("slot", "state", "mods", "detail")
        self.tree = ttk.Treeview(right["body"], columns=cols, show="headings", height=18)
        for key, text, width in (("slot", "Target", 150), ("state", "State", 90),
                                 ("mods", "Mods", 170), ("detail", "Detail", 330)):
            self.tree.heading(key, text=text)
            self.tree.column(key, width=width, anchor="w")
        self.tree.pack(fill="both", expand=True)
        for kind, (_label, colour) in KIND_LABEL.items():
            self.tree.tag_configure(kind, foreground=colour)

        actions = tk.Frame(self, bg=BG, padx=16, pady=10)
        actions.pack(fill="x")
        self.analyse_btn = self.button(actions, "Analyse", self.start_analyse, BLUE)
        self.analyse_btn.pack(side="left")
        self.force_btn = self.button(actions, "Force remaining by priority",
                                     self.force_priority, ROSE)
        self.force_btn.pack(side="left", padx=8)
        self.write_btn = self.button(actions, "Write merged mod", self.write_merged, GREEN)
        self.write_btn.pack(side="left")

        foot = tk.Frame(self, bg=PANEL, padx=16, pady=10)
        foot.pack(fill="x")
        tk.Label(foot, textvariable=self.status_var, bg=PANEL, fg=GREEN,
                 font=("Segoe UI", 10, "bold"), anchor="w").pack(fill="x")

    def panel(self, parent, title, subtitle):
        frame = tk.Frame(parent, bg=PANEL, highlightthickness=1,
                         highlightbackground=EDGE)
        head = tk.Frame(frame, bg=PANEL, padx=12, pady=10)
        head.pack(fill="x")
        tk.Label(head, text=title, bg=PANEL, fg=TEXT,
                 font=("Segoe UI", 12, "bold")).pack(anchor="w")
        tk.Label(head, text=subtitle, bg=PANEL, fg=MUTED,
                 font=("Segoe UI", 8)).pack(anchor="w")
        body = tk.Frame(frame, bg=PANEL, padx=12)
        body.pack(fill="both", expand=True, pady=(0, 12))
        return {"frame": frame, "body": body}

    def button(self, parent, text, command, colour):
        return tk.Button(parent, text=text, command=command, bg=colour,
                         fg="#1A1327", activebackground=colour,
                         font=("Segoe UI", 9, "bold"), relief="flat", bd=0,
                         padx=12, pady=7, cursor="hand2")

    def set_status(self, text: str, colour: str = GREEN):
        self.status_var.set(text)
        try:
            self.nametowidget(self.winfo_children()[-1].winfo_children()[0]).config(fg=colour)
        except Exception:
            pass

    def set_game(self, game_id: str):
        if game_id in MOD_PROFILES:
            self.game_id.set(game_id)
            self.refresh_sources()

    def set_busy(self, busy: bool):
        self.busy = busy
        state = "disabled" if busy else "normal"
        for btn in (self.analyse_btn, self.force_btn, self.write_btn):
            try:
                btn.config(state=state)
            except tk.TclError:
                pass

    def refresh_sources(self):
        self.source_list.delete(0, tk.END)
        for index, source in enumerate(self.sources, 1):
            self.source_list.insert(tk.END, f"{index}. {source.name}  "
                                            f"({len(source.entries)} file(s))")

    def mods_dir(self) -> str:
        return os.path.join(BASE_MODS_DIR, self.game_id.get())

    def pick_unpack_root(self):
        chosen = filedialog.askdirectory(
            parent=self,
            title="Folder holding the unpack folder and its taildata manifest",
            initialdir=self.unpack_root.get() or os.getcwd())
        if chosen:
            self.unpack_root.set(chosen)

    def add_mods(self):
        profile = MOD_PROFILES.get(self.game_id.get(), {})
        exts = [profile.get("single_ext", ""), profile.get("package_ext", "")]
        patterns = " ".join(f"*{e}" for e in exts if e)
        paths = filedialog.askopenfilenames(
            parent=self, title="Select mods to merge",
            initialdir=self.mods_dir() if os.path.isdir(self.mods_dir()) else os.getcwd(),
            filetypes=[("Aldnoah mods", patterns), ("All files", "*.*")])
        added = 0
        for path in paths:
            if any(s.path == path for s in self.sources):
                continue
            try:
                self.sources.append(load_source(path))
                added += 1
            except Exception as exc:
                messagebox.showwarning("Could not read mod",
                                       f"{os.path.basename(path)}\n\n{exc}",
                                       parent=self)
        if added:
            self.plan = None
            self.tree.delete(*self.tree.get_children())
            self.refresh_sources()
            self.set_status(f"Added {added} mod(s). Analyse when ready.")

    def remove_selected(self):
        sel = list(self.source_list.curselection())
        for index in reversed(sel):
            del self.sources[index]
        if sel:
            self.plan = None
            self.tree.delete(*self.tree.get_children())
            self.refresh_sources()

    def move_selected(self, delta: int):
        sel = list(self.source_list.curselection())
        if len(sel) != 1:
            return
        i = sel[0]
        j = i + delta
        if not (0 <= j < len(self.sources)):
            return
        self.sources[i], self.sources[j] = self.sources[j], self.sources[i]
        self.refresh_sources()
        self.source_list.selection_set(j)
        self.plan = None

    def start_analyse(self):
        if self.busy:
            return
        if len(self.sources) < 2:
            self.set_status("Add at least two mods before analysing.", ROSE)
            return

        self.set_busy(True)
        self.set_status("Analysing…", BLUE)
        game_id = self.game_id.get()
        root = self.unpack_root.get() or os.getcwd()
        sources = list(self.sources)

        def work():
            try:
                base = BaseLibrary(game_id, root)
                plan = plan_merge(sources, base=base)
                self.after(0, self.analyse_done, plan, base, None)
            except Exception as exc:
                self.after(0, self.analyse_done, None, None, exc)

        threading.Thread(target=work, daemon=True).start()

    def analyse_done(self, plan, base, error):
        self.set_busy(False)
        if error is not None:
            self.set_status(f"Analyse failed: {error}", ROSE)
            messagebox.showerror("Merge", str(error), parent=self)
            return

        self.plan = plan
        self.render_plan(plan)
        stats = plan.stats
        note = (f"{stats.get(KIND_UNIQUE,0)} clean, "
                f"{stats.get(KIND_IDENTICAL,0)} identical, "
                f"{stats.get(KIND_SUBCONTAINER,0)+stats.get(KIND_LOOSE,0)} merged, "
                f"{stats.get(KIND_CONFLICT,0)} conflict(s)")
        if not base or not base.available:
            note += " - no unpack manifest found, so subcontainers cannot be merged"
            self.set_status(note, ROSE)
        elif plan.ok:
            self.set_status(note + ". Ready to write.", GREEN)
        else:
            self.set_status(note + ". Resolve or force the conflicts.", ROSE)

    def render_plan(self, plan: MergePlan):
        self.tree.delete(*self.tree.get_children())
        for res in plan.resolutions:
            label, _colour = KIND_LABEL.get(res.kind, (res.kind, TEXT))
            self.tree.insert("", tk.END, tags=(res.kind,), values=(
                describe_target(res.target), label,
                ", ".join(res.sources), res.detail))

    def force_priority(self):
        if not self.plan:
            self.set_status("Analyse first.", ROSE)
            return
        if self.plan.ok:
            self.set_status("Nothing left to force.", GREEN)
            return
        count = len(self.plan.conflicts)
        if not messagebox.askyesno(
                "Force by priority",
                f"{count} conflict(s) cannot be merged structurally.\n\n"
                "Take the lowest mod in the list for each one? "
                "The other mod's version of those files is discarded.",
                parent=self):
            return
        resolve_conflicts_by_priority(self.plan, self.sources)
        self.render_plan(self.plan)
        self.set_status(f"Forced {count} conflict(s) by priority.", GOLD)

    def write_merged(self):
        if self.busy:
            return
        if not self.plan:
            self.set_status("Analyse first.", ROSE)
            return
        if not self.plan.ok:
            self.set_status("Resolve or force the conflicts first.", ROSE)
            return

        profile = MOD_PROFILES.get(self.game_id.get(), {})
        ext = profile.get("package_ext", ".mod")
        out = filedialog.asksaveasfilename(
            parent=self, title="Save merged mod",
            initialdir=self.mods_dir() if os.path.isdir(self.mods_dir()) else os.getcwd(),
            defaultextension=ext, initialfile=f"Merged{ext}",
            filetypes=[("Aldnoah package", f"*{ext}"), ("All files", "*.*")])
        if not out:
            return

        names = ", ".join(s.name for s in self.sources)
        plan = self.plan
        entry_count = len(plan.merged_entries)

        # Rebuilt subcontainers can be sizable; writing the package used to
        # block the window the same way a large plain mod did
        self.set_busy(True)
        self.set_status(f"Writing {os.path.basename(out)}…", BLUE)

        def work():
            write_merged_package(
                plan, out,
                game_id=self.game_id.get(),
                display_name=f"Merged ({len(self.sources)} mods)",
                author="Aldnoah Merger",
                version_text="1.0",
                description=f"Merged from: {names}",
            )

        def done(_result):
            self.set_busy(False)
            self.set_status(f"Wrote {os.path.basename(out)} "
                            f"({entry_count} file(s)).", GREEN)
            messagebox.showinfo("Merge complete",
                                f"Merged mod written to:\n{out}\n\n"
                                "Apply it with the Mod Manager and keep the "
                                "original mods disabled while the merged version is applied.", parent=self)

        def failed(exc):
            self.set_busy(False)
            self.set_status(f"Write failed: {exc}", ROSE)
            messagebox.showerror("Merge", str(exc), parent=self)

        run_in_background(self, work, on_done=done, on_error=failed)

    def on_close(self):
        global open_window
        open_window = None
        self.destroy()
