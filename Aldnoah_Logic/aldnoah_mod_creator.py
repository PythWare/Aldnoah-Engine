# Aldnoah_Logic/aldnoah_mod_creator.py

import os
import tkinter as tk
from tkinter import filedialog, ttk

LILAC = "#C8A2C8"
# Aldnoah_Logic folder -> parent is repo root (where main.pyw lives)
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir))
BASE_MODS_DIR = os.path.join(PROJECT_ROOT, "Mods_Folder")

# Per game profiles: display name, single-ext, package-ext, metadata .MODS file
MOD_PROFILES = {
    "DW7XL": {
        "display_name": "Dynasty Warriors 7 XL (PC)",
        "single_ext": ".DW7XLM",   # single-file mods
        "package_ext": ".DW7XLP",  # multi-file mod packages
        "mods_file":  "DW7XL.MODS",
    },
    "DW8XL": {
        "display_name": "Dynasty Warriors 8 XL (PC)",
        "single_ext": ".DW8XLM",
        "package_ext": ".DW8XLP",
        "mods_file":  "DW8XL.MODS",
    },
    "DW8E": {
        "display_name": "Dynasty Warriors 8 Empires (PC)",
        "single_ext": ".DW8EM",
        "package_ext": ".DW8EP",
        "mods_file":  "DW8E.MODS",
    },
    "WO3": {
        "display_name": "Warriors Orochi 3 (PC)",
        "single_ext": ".WO3M",
        "package_ext": ".WO3P",
        "mods_file":  "WO3.MODS",
    },
    "BN": {
        "display_name": "Bladestorm Nightmare (PC)",
        "single_ext": ".BNM",
        "package_ext": ".BNP",
        "mods_file":  "BSN.MODS",
    },
    "WAS": {
        "display_name": "Warriors All Stars (PC)",
        "single_ext": ".WASM",
        "package_ext": ".WASP",
        "mods_file":  "WAS.MODS",
    },
}


def setup_lilac_styles_if_needed(root: tk.Misc):
    """Ensure a basic lilac ttk style exists for this window"""
    style = ttk.Style(master=root)
    try:
        style.theme_use("clam")
    except tk.TclError:
        pass
    style.configure("Lilac.TFrame",  background=LILAC)
    style.configure("Lilac.TLabel",  background=LILAC, foreground="black", padding=0)
    style.map("Lilac.TLabel", background=[("active", LILAC)])


class ToolTip:
    """tooltip helper pattern"""
    def __init__(self, widget, text: str):
        self.widget = widget
        self.text = text
        self.tip_window = None
        widget.bind("<Enter>", self.show_tip)
        widget.bind("<Leave>", self.hide_tip)

    def show_tip(self, event=None):
        if self.tip_window or not self.text:
            return
        x, y, _, _ = self.widget.bbox("insert") if self.widget.bbox("insert") else (0, 0, 0, 0)
        x += self.widget.winfo_rootx() + 25
        y += self.widget.winfo_rooty() + 20

        self.tip_window = tw = tk.Toplevel(self.widget)
        tw.wm_overrideredirect(True)
        tw.wm_geometry(f"+{x}+{y}")
        label = tk.Label(
            tw,
            text=self.text,
            justify="left",
            background="#ffffe0",
            relief="solid",
            borderwidth=1,
            font=("tahoma", "8", "normal"),
        )
        label.pack(ipadx=1)

    def hide_tip(self, event=None):
        if self.tip_window:
            self.tip_window.destroy()
            self.tip_window = None


class ModCreatorWindow(tk.Toplevel):
    """
    One window instance per game
    title, labels, extensions, and .MODS file are per game
    """

    def __init__(self, parent, game_id: str, profile: dict):
        super().__init__(parent)
        self.game_id = game_id
        self.profile = profile

        self.single_ext = profile["single_ext"]
        self.package_ext = profile["package_ext"]
        self.mods_file = profile["mods_file"]

        self.configure(bg=LILAC)
        self.title(f"{profile['display_name']} Mod Creator")
        self.minsize(750, 700)
        self.resizable(False, False)

        setup_lilac_styles_if_needed(self)

        self.modname = tk.StringVar()
        self.authorname = tk.StringVar()
        self.version = tk.StringVar()

        self._ensure_metadata_file()
        self._build_gui()

    # GUI helpers

    def lilac_label(self, parent, **kw):
        base = dict(bg=LILAC, bd=0, relief="flat", highlightthickness=0, takefocus=0)
        base.update(kw)
        return tk.Label(parent, **base)

    def _ensure_metadata_file(self):
        game_dir = os.path.join(BASE_MODS_DIR, self.game_id)
        os.makedirs(game_dir, exist_ok=True)

        mods_path = os.path.join(game_dir, self.mods_file)
        self.mods_path = mods_path  # remember for later

        if not os.path.isfile(mods_path):
            with open(mods_path, "a", encoding="utf-8"):
                pass

    def _build_gui(self):
        top_text = (
            f"Mod Creator for applying mods to {self.profile['display_name']}.\n"
            f"Single mods use *{self.single_ext}*, packages use *{self.package_ext}*."
        )
        self.lilac_label(self, text=top_text).place(x=10, y=10)

        self.lilac_label(self, text="Author of Mod:").place(x=10, y=60)
        self.lilac_label(self, text="Mod Name (without extension):").place(x=10, y=110)
        self.lilac_label(self, text="Version Number for mod:").place(x=10, y=160)
        self.lilac_label(self, text="Mod Description:").place(x=10, y=210)

        tk.Entry(self, textvariable=self.authorname, width=40).place(x=140, y=60)
        tk.Entry(self, textvariable=self.modname, width=40).place(x=260, y=110)
        tk.Entry(self, textvariable=self.version, width=20).place(x=190, y=160)

        self.description = tk.Text(self, height=18, width=52)
        self.description.place(x=140, y=210)

        self.status_label = self.lilac_label(self, text="", fg="green")
        self.status_label.place(x=10, y=650)

        btn_single = tk.Button(
            self,
            text=f"Create Single Mod ({self.single_ext})",
            command=self.create_single_mod,
            height=2,
            width=26,
        )
        btn_single.place(x=520, y=60)

        btn_package = tk.Button(
            self,
            text=f"Create Mod Package ({self.package_ext})",
            command=self.create_package_mod,
            height=2,
            width=26,
        )
        btn_package.place(x=520, y=210)

        ToolTip(btn_single, "Create a single-file mod from one edited file.")
        ToolTip(btn_package, "Create a package mod from multiple files in a folder.")

    # Core helpers

    def _build_header_common(self):
        """Return mod_filename/header_bytes without file payload"""
        mod_name_str = self.modname.get().strip() or "Unnamed"
        mod_filename = mod_name_str  # actual file name will add ext

        author_name = self.authorname.get().strip().encode("utf-8")
        version_number = self.version.get().strip().encode("utf-8")

        description_text = self.description.get("1.0", tk.END).strip()
        description_bytes = description_text.encode("utf-8")

        mod_name_bytes = mod_filename.encode("utf-8")
        mod_name_len = len(mod_name_bytes)
        author_len = len(author_name)
        version_len = len(version_number)
        desc_len = len(description_bytes)

        header = bytearray()
        # 1 byte: mod file name length
        header.extend(mod_name_len.to_bytes(1, "little"))
        # N bytes: mod file name (no extension)
        header.extend(mod_name_bytes)
        # file count: caller appends this
        # author metadata
        header.extend(author_len.to_bytes(1, "little"))
        header.extend(author_name)
        header.extend(version_len.to_bytes(1, "little"))
        header.extend(version_number)
        header.extend(desc_len.to_bytes(2, "little"))
        header.extend(description_bytes)

        return mod_filename, header

    # Single file mod creation

    def create_single_mod(self):
        """Single mod: name, file_count, meta, size, data"""
        target_name = self.modname.get().strip() or "Unnamed"
        new_mod = target_name + self.single_ext

        file_path = filedialog.askopenfilename(
            parent=self,
            initialdir=BASE_MODS_DIR,
            title=f"Select a file to wrap into {self.single_ext}",
            filetypes=(("All files", "*.*"),),
        )
        if not file_path:
            self.status_label.config(text="Canceled.", fg="red")
            return

        try:
            file_size = os.path.getsize(file_path)
            # Common header (without file_count)
            mod_filename, header = self._build_header_common()

            with open(new_mod, "wb") as f_out, open(file_path, "rb") as f_in:
                # prepend name_len+name
                # then 4 byte file count
                name_len = len(mod_filename.encode("utf-8"))
                # header currently: name_len, name, author desc
                # We want: name_len, name, file_count, author, desc
                # So rewrite: name_len + name, then file_count, then rest
                name_len_byte = header[0:1]
                name_bytes = header[1:1 + name_len]
                meta_rest = header[1 + name_len:]

                f_out.write(name_len_byte)
                f_out.write(name_bytes)
                f_out.write((1).to_bytes(4, "little"))  # file_count = 1
                f_out.write(meta_rest)

                # payload: size, data
                f_out.write(file_size.to_bytes(4, "little"))
                f_out.write(f_in.read())

            self.status_label.config(
                text=f"Single mod created: {new_mod}",
                fg="green",
            )
        except Exception as e:
            self.status_label.config(text=f"Error: {e}", fg="red")

    # Package mod creation

    def create_package_mod(self):
        """
        Package mod: same header but file_count = N, then repeated:
        
          4 byte size, raw data x N
        """
        target_name = self.modname.get().strip() or "Unnamed"
        new_mod = target_name + self.package_ext

        folder = filedialog.askdirectory(
            parent=self,
            initialdir=BASE_MODS_DIR,
            title=f"Select a folder of files to pack into {self.package_ext}",
        )
        if not folder:
            self.status_label.config(text="Canceled.", fg="red")
            return

        files = [
            f for f in os.listdir(folder)
            if os.path.isfile(os.path.join(folder, f))
        ]
        if not files:
            self.status_label.config(text="Folder has no files.", fg="red")
            return

        try:
            file_count = len(files)
            mod_filename, header = self._build_header_common()
            name_len = len(mod_filename.encode("utf-8"))
            name_len_byte = header[0:1]
            name_bytes = header[1:1 + name_len]
            meta_rest = header[1 + name_len:]

            with open(new_mod, "wb") as f_out:
                # header: name_len, name, file_count, meta
                f_out.write(name_len_byte)
                f_out.write(name_bytes)
                f_out.write(file_count.to_bytes(4, "little"))
                f_out.write(meta_rest)

                # payload
                for fname in files:
                    full_path = os.path.join(folder, fname)
                    size = os.path.getsize(full_path)
                    f_out.write(size.to_bytes(4, "little"))
                    with open(full_path, "rb") as f_in:
                        f_out.write(f_in.read())

            self.status_label.config(
                text=f"Package mod created: {new_mod} ({file_count} files)",
                fg="green",
            )
        except Exception as e:
            self.status_label.config(text=f"Error: {e}", fg="red")


class ModCreatorGameSelect(tk.Toplevel):
    """
    Simple selector window: choose which game you want a Mod Creator for
    Opened from the main Aldnoah GUI
    """

    def __init__(self, parent):
        super().__init__(parent)
        self.child_windows = {}  # game_id -> ModCreatorWindow
        self.title("Aldnoah Mod Creator, Select Game")
        self.configure(bg=LILAC)
        self.resizable(False, False)
        self.geometry("520x420")

        setup_lilac_styles_if_needed(self)

        lbl = tk.Label(
            self,
            text="Select a game to open its Mod Creator:",
            bg=LILAC,
        )
        lbl.place(x=20, y=20)

        # grid of buttons
        row_h = 40
        col_w = 240
        left_x = 20
        right_x = 260
        top_y = 70
        max_cols = 2

        sorted_items = sorted(
            MOD_PROFILES.items(),
            key=lambda kv: kv[1]["display_name"]
        )

        for idx, (game_id, profile) in enumerate(sorted_items):
            row = idx // max_cols
            col = idx % max_cols

            x = left_x if col == 0 else right_x
            y = top_y + row * row_h

            btn = tk.Button(
                self,
                text=profile["display_name"],
                width=30,
                command=lambda gid=game_id: self.open_creator(gid),
            )
            btn.place(x=x, y=y)

    def open_creator(self, game_id: str):
        # If already open just raise it
        win = self.child_windows.get(game_id)
        if win is not None and win.winfo_exists():
            win.lift()
            win.focus_force()
            return

        # Otherwise create and track it
        profile = MOD_PROFILES[game_id]
        win = ModCreatorWindow(self, game_id, profile)
        self.child_windows[game_id] = win

        def on_close():
            win.destroy()
            self.child_windows[game_id] = None

        win.protocol("WM_DELETE_WINDOW", on_close)
