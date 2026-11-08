"""Khaltron's look: a dark theme (near-black navy, neon cyan accent, a touch of violet), its logo, and a dark
Windows title bar. Everything about colours and fonts lives here; ui.py only uses the names below.

tkinter's default Windows look ("vista") is drawn by Windows and ignores colours, so the theme is built on
"clam", the built-in look that lets every colour be set."""

import ctypes
import sys
import tkinter as tk
from tkinter import ttk

from PIL import Image, ImageDraw, ImageFilter

NAME = "Khaltron"
TAGLINE = "background job control"

# the palette
BG = "#0a0e17"        # window
PANEL = "#111827"     # lists, inputs
RAISED = "#1a2233"    # buttons, headings, tabs
LINE = "#263247"      # borders, separators
TEXT = "#e6edf7"
MUTED = "#8a96ab"
DIM = "#566178"       # disabled text
CYAN = "#22d3ee"      # the accent
CYAN_DARK = "#0e7490"
VIOLET = "#a78bfa"
GREEN = "#34d399"
AMBER = "#fbbf24"
RED = "#f87171"
SELECT = "#164e63"    # a selected row

FONT = "Segoe UI"
MONO = "Cascadia Mono" if sys.platform == "win32" else "Courier"


def apply(root: tk.Tk) -> ttk.Style:
    """Dark colours for every ttk widget the window uses, and for the plain tk ones (menus, text)."""
    root.configure(bg=BG)
    style = ttk.Style(root)
    style.theme_use("clam")
    base = {"background": BG, "foreground": TEXT, "bordercolor": LINE, "lightcolor": LINE, "darkcolor": LINE,
            "troughcolor": PANEL, "fieldbackground": PANEL, "selectbackground": SELECT, "selectforeground": TEXT,
            "insertcolor": CYAN, "font": (FONT, 10)}
    style.configure(".", **base)
    style.map(".", foreground=[("disabled", DIM)])
    style.configure("TFrame", background=BG)
    style.configure("TLabel", background=BG, foreground=TEXT)
    style.configure("Section.TLabel", font=(FONT, 11, "bold"), foreground=CYAN)
    style.configure("Small.TLabel", foreground=MUTED, font=(FONT, 9))
    style.configure("Stat.TLabel", font=(MONO, 10), foreground=TEXT)
    style.configure("Flag.TLabel", foreground=AMBER, font=(FONT, 9, "bold"))

    style.configure("TButton", background=RAISED, foreground=TEXT, bordercolor=LINE, focusthickness=0,
                    padding=(10, 4), relief="flat", font=(FONT, 9))
    style.map("TButton", background=[("disabled", BG), ("pressed", CYAN_DARK), ("active", "#22304a")],
              foreground=[("disabled", DIM), ("active", CYAN)], bordercolor=[("active", CYAN), ("disabled", LINE)])
    style.configure("Accent.TButton", background=CYAN_DARK, foreground="#ecfeff", bordercolor=CYAN)
    style.map("Accent.TButton", background=[("active", "#0891b2"), ("pressed", CYAN)])
    style.configure("TMenubutton", background=CYAN_DARK, foreground="#ecfeff", bordercolor=CYAN, arrowcolor="#ecfeff",
                    padding=(10, 4), relief="flat", font=(FONT, 9, "bold"))
    style.map("TMenubutton", background=[("active", "#0891b2")])

    style.configure("Treeview", background=PANEL, fieldbackground=PANEL, foreground=TEXT, rowheight=26,
                    bordercolor=LINE, borderwidth=0, font=(FONT, 10))
    style.map("Treeview", background=[("selected", SELECT)], foreground=[("selected", "#ffffff")])
    style.configure("Treeview.Heading", background=RAISED, foreground=MUTED, bordercolor=LINE, relief="flat",
                    font=(FONT, 9, "bold"), padding=(6, 4))
    style.map("Treeview.Heading", background=[("active", RAISED)], foreground=[("active", CYAN)])

    style.configure("TNotebook", background=BG, bordercolor=LINE, tabmargins=(0, 6, 0, 0))
    style.configure("TNotebook.Tab", background=BG, foreground=MUTED, bordercolor=LINE, padding=(14, 5),
                    font=(FONT, 9, "bold"))
    style.map("TNotebook.Tab", background=[("selected", PANEL)], foreground=[("selected", CYAN)],
              lightcolor=[("selected", CYAN)])
    style.configure("Vertical.TScrollbar", background=RAISED, troughcolor=BG, bordercolor=BG, arrowcolor=MUTED,
                    gripcount=0)
    style.map("Vertical.TScrollbar", background=[("active", LINE)])
    style.configure("TPanedwindow", background=BG)
    style.configure("Sash", sashthickness=6, background=BG, bordercolor=BG, lightcolor=BG, darkcolor=BG)
    style.configure("TEntry", fieldbackground=PANEL, foreground=TEXT, bordercolor=LINE, insertcolor=CYAN)
    style.map("TEntry", bordercolor=[("focus", CYAN)])
    style.configure("TCombobox", fieldbackground=PANEL, background=RAISED, foreground=TEXT, arrowcolor=CYAN,
                    bordercolor=LINE)
    style.map("TCombobox", fieldbackground=[("readonly", PANEL)], foreground=[("readonly", TEXT)])
    style.configure("TCheckbutton", background=BG, foreground=TEXT, indicatorbackground=PANEL,
                    indicatorforeground=CYAN)
    style.map("TCheckbutton", background=[("active", BG)])

    # plain tk widgets: menus (the Start / control menu, the combobox list) and text boxes
    root.option_add("*Menu.background", PANEL)
    root.option_add("*Menu.foreground", TEXT)
    root.option_add("*Menu.activeBackground", SELECT)
    root.option_add("*Menu.activeForeground", "#ffffff")
    root.option_add("*Menu.relief", "flat")
    root.option_add("*Menu.borderWidth", 0)
    root.option_add("*TCombobox*Listbox.background", PANEL)
    root.option_add("*TCombobox*Listbox.foreground", TEXT)
    root.option_add("*TCombobox*Listbox.selectBackground", SELECT)
    return style


def dark_title_bar(window: tk.Misc) -> None:
    """Ask Windows 10/11 to draw this window's title bar dark (it ignores tkinter's colours)."""
    if sys.platform != "win32":
        return
    try:
        window.update_idletasks()
        hwnd = ctypes.windll.user32.GetParent(window.winfo_id()) or window.winfo_id()
        on = ctypes.c_int(1)
        for attribute in (20, 19):  # DWMWA_USE_IMMERSIVE_DARK_MODE (19 on older Windows 10)
            if ctypes.windll.dwmapi.DwmSetWindowAttribute(hwnd, attribute, ctypes.byref(on), ctypes.sizeof(on)) == 0:
                break
        colour = ctypes.c_int(0x00170E0A)  # DWMWA_CAPTION_COLOR (Windows 11), as 0x00BBGGRR: BG
        ctypes.windll.dwmapi.DwmSetWindowAttribute(hwnd, 35, ctypes.byref(colour), ctypes.sizeof(colour))
    except (AttributeError, OSError):
        pass


def _rgb(hex_colour: str) -> tuple[int, int, int]:
    return tuple(int(hex_colour[i:i + 2], 16) for i in (1, 3, 5))


def _hexagon(cx: float, cy: float, r: float) -> list[tuple[float, float]]:
    import math
    return [(cx + r * math.cos(math.radians(60 * i - 90)), cy + r * math.sin(math.radians(60 * i - 90))) for i in range(6)]


def logo(size: int = 64) -> Image.Image:
    """Khaltron's mark: a glowing cyan hexagon with a 'K' cut from cyan and violet strokes. Drawn 4x and shrunk,
    so its edges are smooth at any size (tray, window, desktop icon)."""
    big = size * 4
    s = big / 64
    image = Image.new("RGBA", (big, big), (0, 0, 0, 0))
    glow = Image.new("RGBA", (big, big), (0, 0, 0, 0))
    ImageDraw.Draw(glow).polygon(_hexagon(32 * s, 32 * s, 29 * s), fill=_rgb(CYAN) + (150,))
    image.alpha_composite(glow.filter(ImageFilter.GaussianBlur(3 * s)))
    draw = ImageDraw.Draw(image)
    # one closed outline (a line through the corners left a notch where it started and ended)
    draw.polygon(_hexagon(32 * s, 32 * s, 28 * s), fill=_rgb(BG) + (255,), outline=_rgb(CYAN) + (255,),
                 width=int(3.2 * s))
    w = int(6 * s)
    draw.line([(31 * s, 30 * s), (42 * s, 46 * s)], fill=_rgb(VIOLET) + (255,), width=w)        # K: lower leg
    draw.line([(23 * s, 18 * s), (23 * s, 46 * s)], fill=_rgb(CYAN) + (255,), width=w)          # the stem
    draw.line([(24 * s, 35 * s), (41 * s, 18 * s)], fill=_rgb(CYAN) + (255,), width=w)          # upper arm, on top
    return image.resize((size, size), Image.LANCZOS)


def save_icon(path) -> None:
    """A Windows .ico with every usual size, for the desktop shortcut."""
    logo(256).save(path, sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)])
