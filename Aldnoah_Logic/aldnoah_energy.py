# Aldnoah_Logic/aldnoah_energy.py
import tkinter as tk
from tkinter import ttk

LILAC = "#C8A2C8"

def setup_lilac_styles(root: tk.Misc) -> ttk.Style:
    """
    Create/refresh lilac ttk styles for the given Tk interpreter
    """
    style = ttk.Style(master=root)

    # Pick a theme that supports configure/map well
    try:
        style.theme_use("clam")
    except tk.TclError:
        pass

    style.configure("Lilac.TFrame", background=LILAC)
    style.configure("Lilac.TLabel", background=LILAC, foreground="black", padding=0)
    style.map("Lilac.TLabel", background=[("active", LILAC)])

    return style

def apply_lilac_to_root(root: tk.Misc) -> None:
    """For plain tk widgets (tk.Frame/tk.Label/etc) that rely on root bg"""
    try:
        root.configure(bg=LILAC)
    except tk.TclError:
        pass

def lilac_label(*args, **kw) -> tk.Label:
    """
    Backward-compatible helper

    """
    if len(args) == 1:
        parent = args[0]
    elif len(args) >= 2:
        parent = args[1]
    else:
        raise TypeError("lilac_label requires at least (parent)")

    base = dict(bg=LILAC, bd=0, relief="flat", highlightthickness=0, takefocus=0)
    base.update(kw)
    return tk.Label(parent, **base)
