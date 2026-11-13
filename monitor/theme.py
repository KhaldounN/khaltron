"""Khaltron 9000's look, after the owner's design (design/khaltron-header/README.md, "Design tokens"): a near-black
background, cyan as the single accent colour, red only for gaming mode and alerts, monospace caps labels with wide
letter-spacing, thin glowing borders; Orbitron for the wordmark and buttons, JetBrains Mono for everything else
(both bundled in assets/fonts, OFL licence, loaded privately: nothing is installed in Windows). Also the logo (the
raccoon's face from the header artwork) and a dark Windows title bar. ui.py, hud.py and hunter.py only use the
names below.

tkinter's default Windows look ("vista") is drawn by Windows and ignores colours, so the theme is built on
"clam", the built-in look that lets every colour be set."""

import ctypes
import sys
import tkinter as tk
from pathlib import Path
from tkinter import ttk

from PIL import Image, ImageDraw, ImageFilter

NAME = "Khaltron 9000"
ASSETS = Path(__file__).resolve().parent.parent / "assets"

# the palette (the design's tokens)
BG = "#05070A"        # page background
PANEL = "#0A0E14"     # lists, inputs, cards
RAISED = "#121821"    # buttons, headings, tabs
METAL = "#2C2E32"     # the ledge's steel
LINE = "#1B2631"      # borders, separators
TEXT = "#F2F7FB"      # text primary
MUTED = "#93A5B6"     # text secondary
DIM = "#4F5D6B"       # disabled text
LASER = "#35E0FF"     # THE accent (cyan; the name stays from the red version)
LASER_DARK = "#0E5566"
LASER_HOT = "#BDF6FF"
HUNT = "#FF3B3B"      # gaming mode and alerts only
GREEN = "#7FE9FF"     # running / fine: the cyan family ("monitored")
AMBER = "#FBBF24"     # warnings
RED = "#FF7A7A"       # failed ("warned")
SELECT = "#0D2C36"    # a selected row: dark cyan

FONT = "JetBrains Mono"          # everything (the design: monospace UI)
MONO = "JetBrains Mono"
DISPLAY = "Orbitron ExtraBold"   # the wordmark (Orbitron 800)
DISPLAY_SEMI = "Orbitron SemiBold"  # buttons (Orbitron 600)
_loaded = False


def load_fonts() -> None:
    """Make the bundled fonts usable by this program only (FR_PRIVATE): no installing, gone when it ends.
    Falls back to Windows' own fonts if they can't be loaded."""
    global _loaded, FONT, MONO, DISPLAY, DISPLAY_SEMI
    if _loaded:
        return
    _loaded = True
    ok = 0
    if sys.platform == "win32":
        for font in (ASSETS / "fonts").glob("*.ttf"):
            ok += bool(ctypes.windll.gdi32.AddFontResourceExW(str(font), 0x10, 0))  # FR_PRIVATE
    if not ok:
        FONT = MONO = "Consolas"
        DISPLAY = DISPLAY_SEMI = "Bahnschrift"


def apply(root: tk.Tk) -> ttk.Style:
    """Dark colours for every ttk widget the window uses, and for the plain tk ones (menus, text)."""
    load_fonts()
    root.configure(bg=BG)
    style = ttk.Style(root)
    style.theme_use("clam")
    base = {"background": BG, "foreground": TEXT, "bordercolor": LINE, "lightcolor": LINE, "darkcolor": LINE,
            "troughcolor": PANEL, "fieldbackground": PANEL, "selectbackground": SELECT, "selectforeground": TEXT,
            "insertcolor": LASER, "font": (FONT, 10)}
    style.configure(".", **base)
    style.map(".", foreground=[("disabled", DIM)])
    style.configure("TFrame", background=BG)
    style.configure("TLabel", background=BG, foreground=TEXT)
    style.configure("Section.TLabel", font=(FONT, 11, "bold"), foreground=LASER)
    style.configure("Small.TLabel", foreground=MUTED, font=(FONT, 9))
    style.configure("Stat.TLabel", font=(MONO, 10), foreground=TEXT)
    style.configure("Flag.TLabel", foreground=AMBER, font=(FONT, 9, "bold"))

    style.configure("TButton", background=RAISED, foreground=TEXT, bordercolor=LINE, focusthickness=0,
                    padding=(10, 4), relief="flat", font=(FONT, 9))
    style.map("TButton", background=[("disabled", BG), ("pressed", LASER_DARK), ("active", "#22252e")],
              foreground=[("disabled", DIM), ("active", LASER)], bordercolor=[("active", LASER), ("disabled", LINE)])
    style.configure("Card.TButton", padding=(8, 2), font=(FONT, 8))
    # the development mode switch: bold; filled cyan while it is on
    style.configure("Dev.TButton", font=(FONT, 9, "bold"))
    style.configure("DevOn.TButton", background=LASER, foreground=BG, bordercolor=LASER, font=(FONT, 9, "bold"))
    style.map("DevOn.TButton", background=[("active", GREEN)], foreground=[("active", BG)])
    style.configure("TMenubutton", background=LASER_DARK, foreground="#fff1f2", bordercolor=LASER, arrowcolor="#fff1f2",
                    padding=(10, 4), relief="flat", font=(FONT, 9, "bold"))
    style.map("TMenubutton", background=[("active", "#a3121f")])

    style.configure("Treeview", background=PANEL, fieldbackground=PANEL, foreground=TEXT, rowheight=26,
                    bordercolor=LINE, borderwidth=0, font=(FONT, 10))
    style.map("Treeview", background=[("selected", SELECT)], foreground=[("selected", "#ffffff")])
    style.configure("Treeview.Heading", background=RAISED, foreground=MUTED, bordercolor=LINE, relief="flat",
                    font=(FONT, 9, "bold"), padding=(6, 4))
    style.map("Treeview.Heading", background=[("active", RAISED)], foreground=[("active", LASER)])

    style.configure("TNotebook", background=BG, bordercolor=LINE, tabmargins=(0, 6, 0, 0))
    style.configure("TNotebook.Tab", background=BG, foreground=MUTED, bordercolor=LINE, padding=(14, 5),
                    font=(FONT, 9, "bold"))
    style.map("TNotebook.Tab", background=[("selected", PANEL)], foreground=[("selected", LASER)],
              lightcolor=[("selected", LASER)])
    style.configure("Vertical.TScrollbar", background=RAISED, troughcolor=BG, bordercolor=BG, arrowcolor=MUTED,
                    gripcount=0)
    style.map("Vertical.TScrollbar", background=[("active", METAL)])
    style.configure("TPanedwindow", background=BG)
    style.configure("Sash", sashthickness=6, background=BG, bordercolor=BG, lightcolor=BG, darkcolor=BG)
    style.configure("TEntry", fieldbackground=PANEL, foreground=TEXT, bordercolor=LINE, insertcolor=LASER)
    style.map("TEntry", bordercolor=[("focus", LASER)])
    style.configure("TCombobox", fieldbackground=PANEL, background=RAISED, foreground=TEXT, arrowcolor=LASER,
                    bordercolor=LINE)
    style.map("TCombobox", fieldbackground=[("readonly", PANEL)], foreground=[("readonly", TEXT)])
    style.configure("TCheckbutton", background=BG, foreground=TEXT, indicatorbackground=PANEL,
                    indicatorforeground=LASER)
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
        r, g, b = _rgb(BG)
        colour = ctypes.c_int(b << 16 | g << 8 | r)  # DWMWA_CAPTION_COLOR (Windows 11), as 0x00BBGGRR
        ctypes.windll.dwmapi.DwmSetWindowAttribute(hwnd, 35, ctypes.byref(colour), ctypes.sizeof(colour))
    except (AttributeError, OSError):
        pass


def _rgb(hex_colour: str) -> tuple[int, int, int]:
    return tuple(int(hex_colour[i:i + 2], 16) for i in (1, 3, 5))


def mix(a: str, b: str, t: float) -> str:
    """The colour t of the way from a to b (0 = a, 1 = b)."""
    return "#%02x%02x%02x" % tuple(round(x + (y - x) * t) for x, y in zip(_rgb(a), _rgb(b)))


def logo(size: int = 64) -> Image.Image:
    """Khaltron 9000's mark: the raccoon's face, cut from the header artwork (glowing cyan eyes), in a rounded
    square with a thin cyan border. Falls back to a plain cyan ring if the artwork is missing."""
    art = ASSETS / "khaltron-raccoon.jpg"
    big = size * 4
    canvas = Image.new("RGBA", (big, big), (0, 0, 0, 0))
    mask = Image.new("L", (big, big), 0)
    ImageDraw.Draw(mask).rounded_rectangle((0, 0, big - 1, big - 1), radius=big // 5, fill=255)
    if art.exists():
        photo = Image.open(art).convert("RGB")
        # the face: around the eyes (the design's (799, 114) on its 960x320 crop of the 3:1 artwork)
        cx, cy = (799 - 320) / 960 * photo.width, 114 / 320 * photo.height + photo.height * 0.04
        half = photo.height * 0.30
        face = photo.crop((int(cx - half), int(cy - half), int(cx + half), int(cy + half))).resize((big, big))
        canvas.paste(face, (0, 0), mask)
    else:
        ImageDraw.Draw(canvas).ellipse((big * .2, big * .2, big * .8, big * .8), outline=_rgb(LASER) + (255,),
                                       width=big // 12)
    ImageDraw.Draw(canvas).rounded_rectangle((1, 1, big - 2, big - 2), radius=big // 5,
                                            outline=_rgb(LASER) + (255,), width=max(2, big // 40))
    return canvas.resize((size, size), Image.LANCZOS)


def save_icon(path) -> None:
    """A Windows .ico with every usual size, for the desktop shortcut."""
    logo(256).save(path, sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)])



def pace(widget: tk.Misc, fast_ms: int, background: int = 250) -> int:
    """How long to wait before an animation's next frame: smooth while you look at the window, slow when another
    window has the focus, nearly stopped while it is hidden in the tray. (An animation nobody sees is wasted CPU.)"""
    try:
        if not widget.winfo_viewable():
            return 600
        if widget.focus_get() is None:  # another program has the focus
            return background
    except (tk.TclError, KeyError):
        return 600
    return fast_ms
