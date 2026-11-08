"""Khaltron's look: a sentinel drone that watches your jobs. Near-black gunmetal, one laser-red eye, red as the
accent; green stays for running jobs and amber for warnings, so the lists stay easy to read. Also its logo (the
drone's eye) and a dark Windows title bar. Everything about colours and fonts lives here; ui.py and sentinel.py
only use the names below.

tkinter's default Windows look ("vista") is drawn by Windows and ignores colours, so the theme is built on
"clam", the built-in look that lets every colour be set."""

import ctypes
import sys
import tkinter as tk
from tkinter import ttk

from PIL import Image, ImageDraw, ImageFilter

NAME = "Khaltron"
TAGLINE = "sentinel online  ·  watching every job on this machine"

# the palette
BG = "#07080b"        # window: almost black
PANEL = "#0e1015"     # lists, inputs, the header
RAISED = "#181b22"    # buttons, headings, tabs (gunmetal)
METAL = "#2b303b"     # the drone's armour edges
LINE = "#262a33"      # borders, separators
TEXT = "#e8e9ee"
MUTED = "#8d909c"
DIM = "#545866"       # disabled text
LASER = "#ff2a3d"     # the accent: the eye and its laser
LASER_DARK = "#7a0d18"
LASER_HOT = "#ffb3b8"  # the white-hot centre of the eye
GREEN = "#4ade80"     # running
AMBER = "#fbbf24"     # warnings
RED = "#ff5b6b"       # failed
SELECT = "#3a0f16"    # a selected row: dark red

FONT = "Segoe UI"
MONO = "Cascadia Mono" if sys.platform == "win32" else "Courier"


def apply(root: tk.Tk) -> ttk.Style:
    """Dark colours for every ttk widget the window uses, and for the plain tk ones (menus, text)."""
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
    """Khaltron's mark: the sentinel drone seen from the front. A round armoured body with side fins, and one
    laser-red eye narrowed by two slanted armour plates, so it looks like it is glaring at you. Drawn 4x and
    shrunk, so its edges are smooth at any size (tray, window, desktop icon)."""
    big = size * 4
    s = big / 64
    c = 32 * s
    image = Image.new("RGBA", (big, big), (0, 0, 0, 0))

    def solid(colour: str) -> tuple:
        return _rgb(colour) + (255,)

    draw = ImageDraw.Draw(image)
    # side fins (the drone's arms), behind the body, each with a small red light
    for side in (-1, 1):
        x0 = c + side * 20 * s
        x1 = c + side * 31 * s
        draw.polygon([(x0, c - 7 * s), (x1, c - 3 * s), (x1, c + 3 * s), (x0, c + 7 * s)], fill=solid(RAISED),
                     outline=solid(METAL), width=int(1.2 * s))
        lx = c + side * 27.5 * s
        draw.ellipse((lx - 1.4 * s, c - 1.4 * s, lx + 1.4 * s, c + 1.4 * s), fill=solid(LASER))
    # the body: armour rim, dark visor
    draw.ellipse((c - 22 * s, c - 22 * s, c + 22 * s, c + 22 * s), fill=solid(RAISED), outline=solid(METAL),
                 width=int(2 * s))

    # the visor is drawn on its own layer and cut to a circle at the end, so the plates never stick out
    visor = Image.new("RGBA", (big, big), solid("#050608"))
    # the glow of the eye, blurred so it bleeds over the visor
    glow = Image.new("RGBA", (big, big), (0, 0, 0, 0))
    ImageDraw.Draw(glow).ellipse((c - 13 * s, c - 9 * s, c + 13 * s, c + 9 * s), fill=_rgb(LASER) + (210,))
    visor.alpha_composite(glow.filter(ImageFilter.GaussianBlur(4 * s)))
    draw = ImageDraw.Draw(visor)
    # the eye: red iris, white-hot centre
    draw.ellipse((c - 10 * s, c - 10 * s, c + 10 * s, c + 10 * s), fill=solid(LASER))
    draw.ellipse((c - 4.5 * s, c - 4.5 * s, c + 4.5 * s, c + 4.5 * s), fill=solid(LASER_HOT))
    draw.ellipse((c - 2 * s, c - 2 * s, c + 2 * s, c + 2 * s), fill=(255, 255, 255, 255))
    # two armour plates slanting down to the middle: an angry, narrowed eye
    lid = solid("#050608")
    draw.polygon([(c - 17 * s, c - 17 * s), (c + 17 * s, c - 17 * s), (c + 17 * s, c - 9 * s), (c, c - 4 * s),
                  (c - 17 * s, c - 9 * s)], fill=lid)
    draw.polygon([(c - 17 * s, c + 17 * s), (c + 17 * s, c + 17 * s), (c + 17 * s, c + 7 * s), (c, c + 5 * s),
                  (c - 17 * s, c + 7 * s)], fill=lid)
    # the plates' edges catch a little light
    draw.line([(c - 17 * s, c - 9 * s), (c, c - 4 * s), (c + 17 * s, c - 9 * s)], fill=solid(METAL), width=int(1.2 * s))
    mask = Image.new("L", (big, big), 0)
    ImageDraw.Draw(mask).ellipse((c - 16 * s, c - 16 * s, c + 16 * s, c + 16 * s), fill=255)
    image.paste(visor, (0, 0), mask)
    draw = ImageDraw.Draw(image)
    draw.ellipse((c - 16 * s, c - 16 * s, c + 16 * s, c + 16 * s), outline=solid(METAL), width=int(1.5 * s))
    return image.resize((size, size), Image.LANCZOS)


def save_icon(path) -> None:
    """A Windows .ico with every usual size, for the desktop shortcut."""
    logo(256).save(path, sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)])

