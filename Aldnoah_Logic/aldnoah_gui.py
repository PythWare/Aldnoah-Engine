# Aldnoah_Logic/aldnoah_gui.py
import os
import threading
import tkinter as tk
from tkinter import ttk, filedialog, messagebox

from .aldnoah_config import load_ref_config
from .aldnoah_unpack   import unpack_from_config
from .aldnoah_mod_creator import ModCreatorGameSelect
from .aldnoah_mod_manager import ModManagerGameSelect
from .aldnoah_repacks import repack_from_folder, update_kvs_metadata

LILAC = "#C8A2C8"

def setup_lilac_styles():
    style = ttk.Style()
    try:
        style.theme_use("clam")
    except tk.TclError:
        pass
    style.configure("Lilac.TFrame",  background=LILAC)
    style.configure("Lilac.TLabel",  background=LILAC, foreground="black", padding=0)
    style.map("Lilac.TLabel", background=[("active", LILAC)])


class Core_Tools():
    def __init__(self, root):
        self.root = root
        self.root.title("Aldnoah Engine Version 0.9")
        self.mod_creator_window = None
        self.mod_manager_window = None
        self.root.geometry("1020x800")
        self.root.resizable(False, False)

        setup_lilac_styles()

        self.progress = None  # will hold progress bar + text
        self.game_buttons = []  # filled in gui_setup

        self.gui_setup()
        self.init_progress()   # set up status bar + progress bar

    def gui_setup(self):
        self.bg = ttk.Frame(self.root, style="Lilac.TFrame")
        self.bg.place(x=0, y=0, relwidth=1, relheight=1)

        self.explainer_1 = ttk.Label(
            self.bg,
            text="Select game you want unpacked/decompressed.",
            style="Lilac.TLabel"
        )
        self.explainer_1.place(x=50, y=20)

        # Status line (text messages)
        self.status_label = ttk.Label(
            self.bg,
            text="",
            style="Lilac.TLabel",
            foreground="green"
        )
        self.status_label.place(x=400, y=24)

        # Mod Creator launcher
        tools_btn = ttk.Button(
            self.bg,
            text="Open Mod Creator",
            command=self.open_mod_creator_window
        )
        tools_btn.place(x=50, y=60)

        # Mod Manager launcher
        manager_btn = ttk.Button(
            self.bg,
            text="Open Mod Manager",
            command=self.open_mod_manager_window
        )
        manager_btn.place(x=50, y=100)

        # Repackers (g1pack2/KVS) launcher
        repack_btn = ttk.Button(
            self.bg,
            text="Repack Subcontainer",
            command=self.start_repack_thread,
        )
        repack_btn.place(x=220, y=60)
        self.repack_button = repack_btn

        # KVS metadata updater (WO3 audio)
        kvs_meta_btn = ttk.Button(
            self.bg,
            text="Update KVS Metadata",
            command=self.start_kvs_metadata_flow,
        )
        kvs_meta_btn.place(x=220, y=100)
        self.kvs_meta_button = kvs_meta_btn

        self.games = [
            {"name": "Dynasty Warriors 7 XL (PC)",      "id": "DW7XL"},
            {"name": "Dynasty Warriors 8 XL (PC)",      "id": "DW8XL"},
            {"name": "Dynasty Warriors 8 Empires (PC)", "id": "DW8E"},
            {"name": "Warriors Orochi 3 (PC)",          "id": "WO3"},
            {"name": "Bladestorm Nightmare (PC)",       "id": "BN"},
            {"name": "Warriors All Stars (PC)",         "id": "WAS"},
        ]

        top_y = 150
        row_spacing = 60
        col_spacing = 420
        left_margin = 180
        max_cols = 2

        for i, game in enumerate(self.games):
            row = i // max_cols
            col = i % max_cols

            x = left_margin + col * col_spacing
            y = top_y + row * row_spacing

            btn = ttk.Button(
                self.bg,
                text=game["name"],
                width=35,
                command=lambda gid=game["id"]: self.start_unpack_thread(gid)
            )
            btn.place(x=x, y=y)

            self.game_buttons.append(btn)
            
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
        Create a progress bar + label at the bottom of the window
        """
        self.progress = {}
        self.progress["var"] = tk.StringVar(value="Idle")

        # Progress bar
        bar = ttk.Progressbar(self.bg, mode="determinate", length=600)
        bar.place(x=210, y=600)
        self.progress["bar"] = bar

        # Progress text label (under the bar)
        prog_label = ttk.Label(
            self.bg,
            textvariable=self.progress["var"],
            style="Lilac.TLabel"
        )
        prog_label.place(x=210, y=630)

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
        for b in self.game_buttons:
            b.config(state=state)
        # Also lock repack + metadata tools if present
        for attr in ("repack_button", "kvs_meta_button"):
            btn = getattr(self, attr, None)
            if btn is not None:
                try:
                    btn.config(state=state)
                except Exception:
                    pass

    # Threaded unpack flow

    def start_unpack_thread(self, game_id: str):
        """
        Main entry when a game button is clicked:
        
        load .ref
        ask for base directory
        start unpack thread
        """
        # Load config (.ref)
        try:
            cfg = load_ref_config(game_id)
        except Exception as e:
            self.status_label.config(
                text=f"Error loading {game_id}.ref: {e}",
                foreground="red"
            )
            return

        game_name = cfg.get("Game", game_id)

        # Ask user for the game folder (must be on the main thread)
        base_dir = filedialog.askdirectory(
            title=f"Select the install folder for {game_name}"
        )
        if not base_dir:
            self.status_label.config(
                text="Action cancelled. No folder selected.",
                foreground="red"
            )
            return

        # Disable buttons and bootstrap progress
        self.set_buttons_state("disabled")
        self.set_progress(0, 1, f"Preparing unpack for {game_name}…")
        self.status_label.config(
            text=f"Using base folder: {base_dir}",
            foreground="blue"
        )

        # Notification function: worker thread -> main thread
        def notify(msg):
            # marshal back into Tk's thread safely
            self.root.after(0, self.handle_msg, msg)

        # Start the worker thread
        t = threading.Thread(
            target=self.unpack_worker,
            args=(cfg, base_dir, notify),
            daemon=True
        )
        t.start()

    def unpack_worker(self, cfg, base_dir, notify):
        """
        Background thread:
        
        wraps core_unpack.unpack_from_config
        sends (status, text, color), (progress), (done, note)
        """
        def status_cb(text, color="blue"):
            notify(("status", text, color))

        def progress_cb(done, total, note=None):
            notify(("progress", done, total, note or "Unpacking"))

        try:
            # kick off progress at 0
            notify(("progress", 0, 1, "Unpacking"))
            unpack_from_config(
                cfg,
                base_dir=base_dir,
                status_callback=status_cb,
                progress_callback=progress_cb,
            )
            notify(("done", "Unpack complete."))
        except Exception as e:
            notify(("status", f"Error during unpack: {e}", "red"))
            notify(("done", "Error."))

        # Threaded repack flow (g1pack2/KVS)

    def start_repack_thread(self):
        """
        Ask the user for a folder and a base subcontainer file, then start
        a background repack task:
        
        If the folder contains .kvs files, build a KVS container
        Otherwise, build a g1pack2 container
        Taildata (last 6 bytes) comes from the selected base file
        """
        folder = filedialog.askdirectory(
            title="Select folder to repack (g1pack2 or KVS)"
        )
        if not folder:
            self.status_label.config(
                text="Repack cancelled. No folder selected.",
                foreground="red",
            )
            return

        base_file = filedialog.askopenfilename(
            title="Select base subcontainer (source of 6-byte taildata)",
            filetypes=[("All files", "*.*")],
        )
        if not base_file:
            self.status_label.config(
                text="Repack cancelled. No base file selected.",
                foreground="red",
            )
            return

        self.set_buttons_state("disabled")
        self.set_progress(0, 1, "Preparing repack…")
        self.status_label.config(
            text=f"Repacking from folder: {folder}",
            foreground="blue",
        )

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

    
    # Threaded KVS metadata update flow (WO3 audio)

    def start_kvs_metadata_flow(self):
        """
        UI flow:
          1) choose game (only WO3 enabled right now)
          2) select repacked KVS subcontainer (Pack_03 entry_XXXXX.kvs)
          3) select paired metadata file from Pack_00 (entry_XXXXX.bin)
          4) run metadata updater in a background thread
        """
        selector = tk.Toplevel(self.root)
        selector.title("Update KVS Metadata")
        selector.configure(bg=LILAC)
        selector.resizable(False, False)
        selector.geometry("560x360")

        lbl = tk.Label(
            selector,
            text="Select which game you want KVS subcontainer metadata updated for:",
            bg=LILAC,
        )
        lbl.place(x=20, y=20)

        game_var = tk.StringVar(value="WO3")

        y = 60
        for g in self.games:
            gid = g["id"]
            state = "normal" if gid == "WO3" else "disabled"
            rb = ttk.Radiobutton(
                selector,
                text=g["name"],
                variable=game_var,
                value=gid,
                state=state,
            )
            rb.place(x=30, y=y)
            y += 28

        note = tk.Label(
            selector,
            text="Only Warriors Orochi 3 supported for now, stay tuned.",
            bg=LILAC,
            fg="blue",
        )
        note.place(x=20, y=250)

        def do_continue():
            gid = (game_var.get() or "").strip()
            if gid != "WO3":
                messagebox.showinfo(
                    "Not Supported",
                    "Only Warriors Orochi 3 is supported for now, stay tuned.",
                )
                return

            selector.destroy()

            kvs_path = filedialog.askopenfilename(
                title="Select the repacked KVS subcontainer",
                filetypes=[("KVS subcontainer", "*.kvs"), ("All files", "*.*")],
            )
            if not kvs_path:
                self.status_label.config(
                    text="KVS metadata update cancelled. No KVS subcontainer selected.",
                    foreground="red",
                )
                return

            paired_meta = os.path.basename(kvs_path)
            if paired_meta.lower().endswith(".kvs"):
                paired_meta = paired_meta[:-4] + ".bin"

            meta_path = filedialog.askopenfilename(
                title=f"Select {paired_meta} from Pack_00",
                filetypes=[("BIN metadata", "*.bin"), ("All files", "*.*")],
            )
            if not meta_path:
                self.status_label.config(
                    text="KVS metadata update cancelled. No metadata .bin selected.",
                    foreground="red",
                )
                return

            self.start_kvs_metadata_thread(gid, kvs_path, meta_path)

        btn_ok = ttk.Button(selector, text="Continue", command=do_continue)
        btn_ok.place(x=420, y=300)

        btn_cancel = ttk.Button(selector, text="Cancel", command=selector.destroy)
        btn_cancel.place(x=320, y=300)

    def start_kvs_metadata_thread(self, game_id: str, kvs_path: str, meta_path: str):
        """
        Start the metadata patch in a background thread
        """
        self.set_buttons_state("disabled")
        self.set_progress(0, 1, "Preparing metadata update")
        self.status_label.config(
            text=f"Updating KVS metadata: {os.path.basename(meta_path)}",
            foreground="blue",
        )

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
                self.status_label.config(text=text, foreground=color)

            elif kind == "progress":
                _, done, total, note = msg
                self.set_progress(done, total, note)

            elif kind == "done":
                _, note = msg
                # finalize bar + re-enable buttons
                self.set_progress(1, 1, note)
                self.set_buttons_state("normal")
