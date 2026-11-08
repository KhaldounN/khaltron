"""The Khaltron 9000 header, after the owner's design (khaltron-header.css): a robot behind a ledge, watching the
PC's programs as six cards lined up on the ledge, with the gaming-mode toggle in its top-right corner.

Two modes, as in the design:
- MONITOR (gaming mode off): cyan. The eyes glow softly and look from card to card; two scan beams follow the
  eyes; the card being looked at says SCANNING. A few motes drift up.
- HUNT (gaming mode on): red. The camera pushes in and shakes, the picture turns red and dark with a red vignette,
  the eyelids close to slits, the beams turn into lasers and target every card in turn ("LOCKED"); paused programs
  say PAUSED. Then, as the design's "phase-locked" state: everything stops, red, staring down. (A still header
  costs no CPU while you play.)

The design is a web page (CSS + an SVG over a photo); tkinter has no blending or blur, so the parts that never move
(the robot, the ledge, the red grade, the vignette, the grain) are painted once per size and mode into a picture
with Pillow, and only small shapes move on top. The design's photo is not in the project: the robot is drawn
here. A photo saved as assets/header.jpg (1600 x 533, like the design) is used instead when it exists.

Everything is laid out in the design's own 1600 x 533 coordinates and mapped onto the header's real size: the
robot keeps its proportions (centred), the cards, wordmark and toggle spread with the width."""

import math
import random
import time
import tkinter as tk
import tkinter.font as tkfont
from pathlib import Path

from PIL import Image, ImageChops, ImageDraw, ImageEnhance, ImageFilter, ImageTk

from . import theme
from .config import HOME

CYAN, RED = "#35E0FF", "#FF3B3B"
INK, TEXT, MUTED = "#05070A", "#DCE7F0", "#93A5B6"
DESIGN_W, DESIGN_H = 1600, 533
EYES = [(741, 192), (856, 187)]                    # the design's eye centres
SLOTS = [24, 190, 652, 818, 1270, 1436]            # the design's card slots (left edges); hands sit in the gaps
CARD_TOP, CARD_W, CARD_H = 452, 150, 70
LOOK = [(-3, 2), (-2.5, 2), (-1, 2.5), (1, 2.5), (2.5, 2), (3, 2)]  # pupil offsets per card (design px)
PHOTO = HOME / "assets" / "header.jpg"
WORD = "Bahnschrift"  # Windows' squared, technical typeface: closest to the design's Orbitron
STATUS = {"monitored": ("● MONITORED", "#7FE9FF"), "scanning": ("◎ SCANNING", "#C2AEAE"),
          "warned": ("▲ WARNED", "#FF7A7A"), "paused": ("❚❚ PAUSED", "#FFB3B3")}
WARN_CPU = 25  # a program over this much of the CPU is WARNED


def _rgb(colour: str) -> tuple:
    return theme._rgb(colour)


def _round_rect(x0, y0, x1, y1, r):
    """Points for a rounded rectangle drawn as a smoothed polygon."""
    return [x0 + r, y0, x1 - r, y0, x1, y0, x1, y0 + r, x1, y1 - r, x1, y1, x1 - r, y1, x0 + r, y1, x0, y1,
            x0, y1 - r, x0, y0 + r, x0, y0]


# --- the still picture (robot, ledge, grade, vignette, grain), painted once per size and mode ---------------------
def _robot(scale: float = 2.0) -> Image.Image:
    """The robot in the design's coordinates (painted at `scale` for smooth edges): a metal skull with two eye
    sockets, a jaw, a neck of cables, shoulders, a ledge, and two hands gripping the ledge between the cards."""
    w, h = int(DESIGN_W * scale), int(DESIGN_H * scale)
    img = Image.new("RGB", (w, h), INK)

    def S(points):
        return [(x * scale, y * scale) for x, y in points]

    def metal(mask: Image.Image, top: str, bottom: str, light=(799, 90), shine=0.35):
        """Fill a shape with a vertical metal gradient and a soft highlight."""
        grad = Image.linear_gradient("L").resize((w, h))
        a, b = Image.new("RGB", (w, h), top), Image.new("RGB", (w, h), bottom)
        fill = Image.composite(b, a, grad)
        # the highlight is blurred at a quarter of the size, then enlarged: the same soft light, ~16x less work
        q = 4
        glow = Image.new("L", (w // q, h // q), 0)
        lx, ly = light
        ImageDraw.Draw(glow).ellipse([(lx - 120) * scale / q, (ly - 70) * scale / q, (lx + 120) * scale / q,
                                      (ly + 70) * scale / q], fill=int(255 * shine))
        glow = glow.filter(ImageFilter.GaussianBlur(40 * scale / q)).resize((w, h), Image.BILINEAR)
        fill = Image.composite(Image.new("RGB", (w, h), "#9aa6b6"), fill, glow)
        img.paste(fill, (0, 0), mask)

    def shape(draw_fn) -> Image.Image:
        mask = Image.new("L", (w, h), 0)
        draw_fn(ImageDraw.Draw(mask))
        return mask

    # faint background structure: a dark room with vertical panels
    d = ImageDraw.Draw(img)
    for x in range(0, DESIGN_W, 80):
        d.line(S([(x, 0), (x, 440)]), fill="#0a0e14", width=int(2 * scale))
    # shoulders and chest plate (behind the head)
    metal(shape(lambda m: m.polygon(S([(470, 520), (560, 360), (700, 330), (900, 330), (1040, 360), (1130, 520)]),
                                    fill=255)), "#2a313c", "#0b0e13", light=(799, 360), shine=0.18)
    d = ImageDraw.Draw(img)
    for x in (640, 700, 900, 960):  # chest plate seams
        d.line(S([(x, 350), (x + (x - 800) * 0.25, 520)]), fill="#06080b", width=int(3 * scale))
    # neck: hydraulic cables
    for x in (742, 770, 799, 828, 856):
        metal(shape(lambda m, x=x: m.rounded_rectangle(S([(x - 11, 300), (x + 11, 400)]), radius=8 * scale, fill=255)),
              "#3b4452", "#11151b", light=(x, 320), shine=0.25)
    # the skull
    skull = shape(lambda m: (m.ellipse(S([(669, 32), (929, 300)]), fill=255),
                             m.polygon(S([(690, 200), (908, 200), (880, 300), (718, 300)]), fill=255)))
    metal(skull, "#4a5463", "#141820", light=(780, 95), shine=0.55)
    d = ImageDraw.Draw(img)
    # temple plates and cranium seam
    d.arc(S([(689, 52), (909, 280)]), 200, 340, fill="#20262f", width=int(3 * scale))
    d.line(S([(799, 36), (799, 118)]), fill="#20262f", width=int(2 * scale))
    # brow ridge: one angled plate over both eyes (angry, sloping down to the middle)
    metal(shape(lambda m: m.polygon(S([(690, 152), (790, 176), (808, 176), (908, 148), (912, 166), (808, 194),
                                       (790, 194), (688, 172)]), fill=255)), "#5a6576", "#232a34",
          light=(799, 160), shine=0.4)
    d = ImageDraw.Draw(img)
    # eye sockets (the eyes themselves are drawn live on top)
    for ex, ey in EYES:
        d.ellipse(S([(ex - 31, ey - 19), (ex + 31, ey + 19)]), fill="#020304")
        d.ellipse(S([(ex - 31, ey - 19), (ex + 31, ey + 19)]), outline="#262d37", width=int(2 * scale))
    # nose cavity
    d.polygon(S([(788, 222), (810, 222), (799, 246)]), fill="#030405")
    # cheekbones
    d.line(S([(704, 228), (760, 248), (782, 262)]), fill="#1b2028", width=int(3 * scale))
    d.line(S([(894, 224), (838, 246), (816, 262)]), fill="#1b2028", width=int(3 * scale))
    # jaw and teeth
    metal(shape(lambda m: m.rounded_rectangle(S([(728, 262), (870, 318)]), radius=14 * scale, fill=255)),
          "#3c4553", "#101318", light=(799, 270), shine=0.3)
    d = ImageDraw.Draw(img)
    d.rectangle(S([(744, 274), (854, 296)]), fill="#06080b")
    for x in range(748, 852, 9):
        d.rectangle(S([(x, 276), (x + 6, 294)]), fill="#c9d0d8" if x % 2 else "#b4bcc6")
    d.line(S([(744, 285), (854, 285)]), fill="#06080b", width=int(2 * scale))
    # the ledge the cards stand on
    metal(shape(lambda m: m.rectangle(S([(0, 440), (DESIGN_W, DESIGN_H)]), fill=255)), "#1a2029", "#07090c",
          light=(799, 445), shine=0.15)
    d = ImageDraw.Draw(img)
    d.line(S([(0, 440), (DESIGN_W, 440)]), fill="#3d4756", width=int(2 * scale))
    # hands gripping the ledge, in the gaps between the cards
    for cx in (496, 1119):
        metal(shape(lambda m, cx=cx: m.rounded_rectangle(S([(cx - 70, 392), (cx + 70, 444)]), radius=18 * scale,
                                                        fill=255)), "#47515f", "#1a1f27", light=(cx, 400), shine=0.4)
        for i in range(4):  # fingers curling over the edge
            fx = cx - 55 + i * 37
            metal(shape(lambda m, fx=fx: m.rounded_rectangle(S([(fx - 13, 420), (fx + 13, 482)]), radius=10 * scale,
                                                            fill=255)), "#56616f", "#1d232c", light=(fx, 430),
                  shine=0.35)
            d = ImageDraw.Draw(img)
            d.line(S([(fx - 12, 452), (fx + 12, 452)]), fill="#151a21", width=int(2 * scale))
        d.line(S([(cx - 64, 405), (cx + 64, 405)]), fill="#20262f", width=int(2 * scale))
    return img


_scene_cache: dict = {}


ROBOT_VERSION = 1  # bump when _robot() changes: the picture saved on disk is then painted again
ROBOT_FILE = HOME / "state" / f"header-robot-v{ROBOT_VERSION}.png"
_base: Image.Image | None = None


def base_picture() -> Image.Image:
    """The design's photo if saved, else the painted robot: painted once, then kept on disk (painting it takes
    a second or two; loading it a few milliseconds)."""
    global _base
    if _base is None:
        if PHOTO.exists():
            _base = Image.open(PHOTO).convert("RGB").resize((DESIGN_W, DESIGN_H))
        elif ROBOT_FILE.exists():
            _base = Image.open(ROBOT_FILE).convert("RGB")
        else:
            _base = _robot().resize((DESIGN_W, DESIGN_H), Image.LANCZOS)
            ROBOT_FILE.parent.mkdir(parents=True, exist_ok=True)
            _base.save(ROBOT_FILE)
    return _base


def scene(width: int, height: int, hunt: bool) -> Image.Image:
    """The still picture at this size: the robot (or the design's photo, if saved), centred and scaled to the
    height, the ledge stretched to the width; in hunt mode zoomed in 6%, red-graded, darker, with a red vignette.
    Film grain on both. Cached per size and mode."""
    key = (width, height, hunt)
    if key in _scene_cache:
        return _scene_cache[key]
    base = base_picture()
    if hunt:  # the camera pushes in around the eyes
        z = 1.06
        cx, cy = 799, 190
        box = (cx - cx / z, cy - cy / z, cx + (DESIGN_W - cx) / z, cy + (DESIGN_H - cy) / z)
        base = base.resize((DESIGN_W, DESIGN_H), Image.LANCZOS, box=box)
    s = height / DESIGN_H
    out = Image.new("RGB", (width, height), INK)
    robot = base.resize((max(1, int(DESIGN_W * s)), height), Image.LANCZOS)
    out.paste(robot, ((width - robot.width) // 2, 0))
    # the ledge runs the full width (the robot picture is narrower than a wide window)
    ledge = base.crop((0, 440, 300, DESIGN_H)).resize((max(1, int(300 * s)), height - int(440 * s)))
    for x in list(range(0, (width - robot.width) // 2, ledge.width)) + \
            list(range((width + robot.width) // 2, width, ledge.width)):
        out.paste(ledge, (x, int(440 * s)))
    if hunt:
        grey = out.convert("L").convert("RGB")
        red = ImageChops.multiply(grey, Image.new("RGB", out.size, (255, 70, 70)))
        out = Image.blend(out, red, 0.38)                               # the red grade
        out = ImageEnhance.Brightness(out).enhance(0.7)                 # darken .3
        vignette = Image.new("L", out.size, 0)
        ImageDraw.Draw(vignette).rectangle((0, 0, width, height), outline=255, width=int(70 * s) + 10)
        vignette = vignette.filter(ImageFilter.GaussianBlur(60 * s + 10))
        out = Image.composite(Image.new("RGB", out.size, (150, 12, 12)), out, vignette.point(lambda v: v * 0.55))
    noise = Image.effect_noise(out.size, 40).convert("RGB")
    out = Image.blend(out, ImageChops.overlay(out, noise), 0.12)        # grain
    _scene_cache.clear() if len(_scene_cache) > 6 else None
    _scene_cache[key] = out
    return out


# --- the live header ------------------------------------------------------------------------------------------------
class KhaltronHeader(tk.Canvas):
    """The header. The window calls status(), show_programs() and set_state(); a click on the toggle calls
    `on_toggle` (the window switches gaming mode in the background)."""

    FPS_MS = 90

    def __init__(self, parent, on_toggle, height: int = 250):
        super().__init__(parent, height=height, bg=INK, highlightthickness=0)
        self.on_toggle = on_toggle
        self.on, self.busy, self.hover = False, False, False
        self.width, self.height = 1000, height
        self.cards_data: list = []
        self.counts = (0, 0, False)
        self.target, self.look_from, self.look_to, self.look_since = 0, (0.0, 0.0), (0.0, 0.0), 0.0
        self.beam_from = self.beam_to = None
        self.hunt_since: float | None = None
        self.locked = False
        self.started = time.time()
        self.bind("<Configure>", self._resized)
        self.after(self.FPS_MS, self.tick)

    # coordinates: the robot keeps its shape (centred, scaled to the height); cards and edges spread with the width
    @property
    def s(self) -> float:
        return self.height / DESIGN_H

    def rx(self, x: float) -> float:   # robot x
        return self.width / 2 + (x - 800) * self.s

    def ry(self, y: float) -> float:
        return y * self.s

    def cx(self, x: float) -> float:   # card / edge x, stretched to the width
        return x * self.width / DESIGN_W

    @property
    def accent(self) -> str:
        return RED if self.on else CYAN

    def _resized(self, event):
        if (event.width, event.height) != (self.width, self.height):
            self.width, self.height = event.width, event.height
            self.build()
            # the other mode's picture, painted in the background now, so switching is instant
            import threading
            size = (self.width, self.height)
            threading.Thread(target=lambda: scene(size[0], size[1], not self.on), daemon=True).start()

    # --- building ----------------------------------------------------------------------------------------------------
    def build(self):
        """All shapes, made once per size and mode; animation only moves and recolours them."""
        self.delete("all")
        hunt = self.on
        self.photo = ImageTk.PhotoImage(scene(self.width, self.height, hunt))
        self.create_image(0, 0, image=self.photo, anchor="nw")
        s, a = self.s, self.accent
        rng = random.Random(7)
        self.motes = [(self.create_oval(0, 0, 0, 0, fill=a, outline=""), rng.uniform(0, self.width),
                       rng.uniform(self.ry(120), self.ry(440)), rng.uniform(0, 10)) for _ in range(9)]
        # scan beams (from each eye to the card looked at) and the thin lasers of hunt mode
        self.beams = [self.create_polygon(0, 0, 0, 0, 0, 0, fill=a, outline="", stipple="gray25") for _ in EYES]
        self.lasers = [self.create_line(0, 0, 0, 0, fill=a, width=2, state="normal" if hunt else "hidden")
                       for _ in EYES]
        # the eyes: glow rings, iris, hot pupil; the lids of hunt mode
        self.eyes = []
        for ex, ey in EYES:
            x, y = self.rx(ex), self.ry(ey)
            glows = [self.create_oval(x - r * s, y - r * s * .7, x + r * s, y + r * s * .7, fill=INK, outline="")
                     for r in (44, 34, 25)]
            iris = self.create_oval(x - 15 * s, y - 15 * s, x + 15 * s, y + 15 * s, fill=a, outline="")
            pupil = self.create_oval(0, 0, 0, 0, fill="#ffffff", outline="")
            lid = self.create_polygon(x - 33 * s, y - 22 * s, x + 33 * s, y - 22 * s, x + 33 * s, y - 22 * s,
                                      x - 33 * s, y - 22 * s, fill="#020304", outline="")
            low = self.create_polygon(x - 33 * s, y + 22 * s, x + 33 * s, y + 22 * s, x + 33 * s, y + 22 * s,
                                      x - 33 * s, y + 22 * s, fill="#020304", outline="")
            self.eyes.append({"x": x, "y": y, "glows": glows, "iris": iris, "pupil": pupil, "lid": lid, "low": low})
        # the cards on the ledge
        self.card_items = []
        top = self.ry(CARD_TOP) if self.height >= 300 else self.height - CARD_H * max(s, .62) - 6
        ch = max(54, CARD_H * s * 1.0) if self.height >= 300 else self.height - top - 4
        for slot in SLOTS:
            x0 = self.cx(slot)
            x1 = x0 + max(96, self.cx(slot + CARD_W) - x0)
            items = {"box": self.create_polygon(*_round_rect(x0, top, x1, top + ch, 7), smooth=True,
                                               fill="#0a1016", outline=a, width=1),
                     "corners": [self.create_line(x0 - 4, top + 8, x0 - 4, top - 4, x0 + 8, top - 4, fill=RED, width=2,
                                                  state="hidden"),
                                 self.create_line(x1 + 4, top + ch - 8, x1 + 4, top + ch + 4, x1 - 8, top + ch + 4,
                                                  fill=RED, width=2, state="hidden")],
                     "name": self.create_text(x0 + 9, top + 12, text="", anchor="w", fill="#F2F7FB",
                                              font=(theme.FONT, 9, "bold")),
                     "tag": self.create_text(x1 - 8, top + ch - 11, text="", anchor="e", fill=MUTED,
                                             font=(theme.MONO, 7)),  # bottom right: the name has the top row
                     "track": self.create_rectangle(x0 + 9, top + ch / 2, x1 - 9, top + ch / 2 + 4,
                                                    fill="#1a2028", width=0),
                     "fill": self.create_rectangle(x0 + 9, top + ch / 2, x0 + 9, top + ch / 2 + 4, fill=a, width=0),
                     "status": self.create_text(x0 + 9, top + ch - 11, text="", anchor="w",
                                                font=(theme.MONO, 7, "bold")),
                     "lock": self.create_text(x1 - 10, top - 1, text=" LOCKED ", anchor="e", fill="#1A0404",
                                              font=(theme.MONO, 7, "bold"), state="hidden"),
                     "x0": x0, "x1": x1, "top": top, "h": ch}
            items["lock_bg"] = self.create_rectangle(0, 0, 0, 0, fill=RED, width=0, state="hidden")
            self.tag_raise(items["lock"])
            self.card_items.append(items)
        # brand: wordmark, mode line, and the blinking banner of hunt mode
        word = tkfont.Font(family=WORD, size=max(14, int(28 * s * 1.15)), weight="bold")
        self.create_text(22 + 2, 20 + 2, text="KHALTRON 9000", anchor="nw", font=word, fill="#000000")
        self.create_text(22, 20, text="KHALTRON 9000", anchor="nw", font=word, fill="#F2F7FB")
        line_y = 20 + word.metrics("linespace") + 10
        self.dot = self.create_oval(24, line_y - 4, 32, line_y + 4, fill=a, outline="")
        self.mode_line = self.create_text(40, line_y, text="", anchor="w", font=(theme.MONO, 8), fill="#B4C3D1")
        self.banner = self.create_text(22, line_y + 22, text="⚠ HUNT MODE: BACKGROUND PROCESSES SUSPENDED",
                                       anchor="w", font=(theme.MONO, 8, "bold"), fill="#FF6B6B",
                                       state="normal" if hunt else "hidden")
        # the toggle pill (top right)
        tw, th = 230, 40
        x1, y0 = self.width - 22, 20
        self.toggle_box = (x1 - tw, y0, x1, y0 + th)
        self.toggle_shape = self.create_polygon(*_round_rect(x1 - tw, y0, x1, y0 + th, th / 2), smooth=True,
                                                width=1, outline=a, fill="#0b1219")
        self.toggle_text = self.create_text(x1 - tw / 2, y0 + th / 2, text="", font=(WORD, 11, "bold"))
        for item in (self.toggle_shape, self.toggle_text):
            self.tag_bind(item, "<Button-1>", lambda e: None if self.busy else self.on_toggle())
            self.tag_bind(item, "<Enter>", lambda e: self._hover(True))
            self.tag_bind(item, "<Leave>", lambda e: self._hover(False))
        self._paint_toggle()
        self._paint_texts()
        self._paint_cards()
        self.look_since = 0  # beams and pupils jump to their place on the next frame
        self.frame(time.time() - self.started, force=True)

    # --- what the window tells it --------------------------------------------------------------------------------
    def set_state(self, on: bool, busy: bool | None = None):
        """Gaming mode on/off (and switching). Turning it on starts the hunt sequence."""
        if busy is not None and busy != self.busy:
            self.busy = busy
            self._paint_toggle()
        if on != self.on:
            self.on = on
            self.locked = False
            self.build()
            # the sequence (push in, shake, target each card, lock) starts once its picture is on screen
            self.hunt_since = time.time() if on else None

    def status(self, running: int, waiting: int, alert: bool):
        if (running, waiting, alert) != self.counts:
            self.counts = (running, waiting, alert)
            self._paint_texts()

    def show_programs(self, programs, frozen: set[int]):
        """The six busiest programs become the cards on the ledge."""
        top = sorted(programs, key=lambda p: -p.cpu)[:len(SLOTS)]
        data = []
        for p in top:
            name = p.name.replace(" (incl. your background jobs)", " jobs").replace("Windows: ", "Win: ")
            paused = bool(frozen and set(p.pids) & frozen)
            data.append((name, p.cpu, "paused" if paused else "warned" if p.cpu >= WARN_CPU else "monitored"))
        if data != self.cards_data:
            self.cards_data = data
            self._paint_cards()

    # --- painting the parts that change rarely ----------------------------------------------------------------------
    def _hover(self, inside: bool):
        self.hover = inside
        self.configure(cursor="hand2" if inside else "")
        self._paint_toggle()

    def _paint_toggle(self):
        if not hasattr(self, "toggle_shape"):
            return
        on = self.on
        text = "SWITCHING..." if self.busy else ("■  DISENGAGE GAMING" if on else "▶  GAMING MODE")
        fill = ("#4a1214" if self.hover else "#2b0d10") if on else ("#0f2a33" if self.hover else "#0b1219")
        self.itemconfigure(self.toggle_shape, fill=fill, outline=RED if on else CYAN)
        self.itemconfigure(self.toggle_text, text=text, fill="#FFD9D9" if on else "#CFF7FF")

    def _paint_texts(self):
        if not hasattr(self, "mode_line"):
            return
        running, waiting, alert = self.counts
        mode = "HUNT MODE · JOBS FROZEN" if self.on else "MONITOR MODE"
        alert_text = "  ·  ⚠ ALERT" if alert and not self.on else ""
        self.itemconfigure(self.mode_line, text=f"{mode}  ·  {running} ACTIVE  ·  {waiting} QUEUED{alert_text}")

    def _paint_cards(self):
        if not getattr(self, "card_items", None):
            return
        for i, items in enumerate(self.card_items):
            if i < len(self.cards_data):
                name, cpu, state = self.cards_data[i]
                shown = "normal"
            else:
                name, cpu, state, shown = "", 0, "monitored", "hidden"
            for key in ("box", "name", "tag", "track", "fill", "status"):
                self.itemconfigure(items[key], state=shown)
            room = max(8, int((items["x1"] - items["x0"] - 18) / 7))  # characters that fit the card's width
            self.itemconfigure(items["name"], text=name[:room] + ("…" if len(name) > room else ""))
            self.itemconfigure(items["tag"], text=f"{cpu:.0f}% CPU")
            x0, x1, top, h = items["x0"], items["x1"], items["top"], items["h"]
            share = max(0.02, min(1.0, cpu / 100))
            self.coords(items["fill"], x0 + 9, top + h / 2, x0 + 9 + (x1 - x0 - 18) * share, top + h / 2 + 4)
            items["state"] = state
        self._paint_targets()

    def _paint_targets(self):
        """Card borders and status words for the card being looked at (SCANNING / LOCKED)."""
        a = self.accent
        for i, items in enumerate(self.card_items):
            state = items.get("state", "monitored")
            targeted = i == self.target and not self.locked
            word = state
            if targeted and state == "monitored" and not self.on:
                word = "scanning"
            text, colour = STATUS[word]
            if self.on and word == "monitored":
                colour = "#E8A0A0"  # hunt mode: no cyan left
            self.itemconfigure(items["status"], text=text, fill=colour)
            if self.on:
                outline = RED if targeted else "#7a2026"
                fill = "#2a0a0d" if targeted else ("#120507" if state == "paused" else "#1a0608")
            else:
                outline = CYAN if targeted else "#1d5a66"
                fill = "#0b1820" if targeted else "#080d12"
            self.itemconfigure(items["box"], outline=outline, fill=fill, width=2 if targeted else 1)
            self.itemconfigure(items["fill"], fill="#5C2626" if state == "paused" else a)
            hunt_target = self.on and targeted and i < len(self.cards_data)
            for corner in items["corners"]:
                self.itemconfigure(corner, state="normal" if hunt_target else "hidden")
            self.itemconfigure(items["lock"], state="normal" if hunt_target else "hidden")
            self.itemconfigure(items["lock_bg"], state="normal" if hunt_target else "hidden")
            if hunt_target:
                bx = self.bbox(items["lock"])
                if bx:
                    self.coords(items["lock_bg"], bx[0] - 2, bx[1], bx[2] + 2, bx[3])
                self.tag_raise(items["lock"])

    # --- the animation --------------------------------------------------------------------------------------------
    def tick(self):
        try:
            if self.winfo_viewable() and not self.locked:
                self.frame(time.time() - self.started)
            delay = 600 if self.locked else theme.pace(self, self.FPS_MS, background=400)
            self.after(delay, self.tick)
        except tk.TclError:
            return

    def _aim(self, target):
        """Start moving the eyes and beams to card `target` (or 'down')."""
        if target == getattr(self, "aim_at", None):
            return
        self.aim_at = target
        self.look_from = getattr(self, "look_now", (0.0, 0.0))
        self.look_to = (0.0, 3.0) if target == "down" else LOOK[target]
        self.beam_from = getattr(self, "beam_now", None)
        self.look_since = time.time()
        if target != "down":
            self.target = target
        self._paint_targets()

    def frame(self, t: float, force: bool = False):
        s, a, now = self.s, self.accent, time.time()
        cards = max(1, len(self.cards_data))
        # where to look: monitor mode walks the cards every 2.5 s; hunt mode shakes, targets each card, then locks
        if self.on and self.hunt_since is not None:
            since = now - self.hunt_since
            if since < 1.0:
                self._aim(0)
            elif since < 1.0 + 0.5 * cards:
                self._aim(int((since - 1.0) / 0.5))
            else:
                self._aim("down")
                if since > 2.0 + 0.5 * cards and not self.locked:
                    self.locked = True  # the design's phase-locked state: everything stops, red, staring down
                    self.move("all", -getattr(self, "shook", (0, 0))[0], -getattr(self, "shook", (0, 0))[1])
                    self.shook = (0, 0)
                    self._paint_targets()
            if since < 1.2:  # the shake when it engages
                dx, dy = random.choice([(1.5, -1), (-1.5, 1), (1, 1.5), (0, 0)])
                last = getattr(self, "shook", (0, 0))
                self.move("all", dx - last[0], dy - last[1])
                self.shook = (dx, dy)
        else:
            self._aim(int(t / 2.5) % cards)
        # ease the gaze from where it was to where it goes (0.55 s)
        k = min(1.0, (now - self.look_since) / 0.55) if self.look_since else 1.0
        k = 1 - (1 - k) ** 3
        lx = self.look_from[0] + (self.look_to[0] - self.look_from[0]) * k
        ly = self.look_from[1] + (self.look_to[1] - self.look_from[1]) * k
        self.look_now = (lx, ly)
        # eyes: glow pulse (2.6 s, or 0.5 s hunting), pupils, lids
        speed = 0.5 if self.on else 2.6
        pulse = 0.5 + 0.5 * math.sin(t * 2 * math.pi / speed) if not self.locked else 1.0
        strength = (0.9 if self.on else 0.45) * (0.55 + 0.45 * pulse)
        lid_k = 1.0 if self.on else 0.0
        for eye in self.eyes:
            x, y = eye["x"], eye["y"]
            for ring, share in zip(eye["glows"], (0.25, 0.45, 0.75)):
                self.itemconfigure(ring, fill=theme.mix(INK, a, share * strength))
            px, py = x + lx * s * 3, y + ly * s * 3
            r = 5 * s + 1.5
            self.coords(eye["pupil"], px - r, py - r, px + r, py + r)
            self.coords(eye["lid"], x - 34 * s, y - 22 * s, x + 34 * s, y - 22 * s, x + 34 * s, y - 22 * s + 14 * s * lid_k,
                        x, y - 22 * s + 19 * s * lid_k, x - 34 * s, y - 22 * s + 14 * s * lid_k)
            self.coords(eye["low"], x - 34 * s, y + 22 * s, x + 34 * s, y + 22 * s, x + 34 * s, y + 22 * s - 9 * s * lid_k,
                        x - 34 * s, y + 22 * s - 9 * s * lid_k)
        # beams: from each eye to the card looked at (or straight down when locked on)
        if self.card_items:
            if self.look_to == (0.0, 3.0):
                tx0, tx1, ty = None, None, self.height
            else:
                items = self.card_items[min(self.target, len(self.card_items) - 1)]
                tx0, tx1, ty = items["x0"], items["x1"], items["top"]
            if k < 1 or force or not getattr(self, "beams_set", False) or self.on and not self.locked:
                for beam, laser, eye in zip(self.beams, self.lasers, self.eyes):
                    ex, ey = eye["x"] + lx * s * 3, eye["y"] + ly * s * 3
                    if tx0 is None:
                        a0, a1 = ex - 60 * s, ex + 60 * s
                    else:
                        goal0, goal1 = tx0 + 6, tx1 - 6
                        prev = self.beam_from or (goal0, goal1)
                        a0 = prev[0] + (goal0 - prev[0]) * k
                        a1 = prev[1] + (goal1 - prev[1]) * k
                    self.coords(beam, ex, ey, a0, ty, a1, ty)
                    self.coords(laser, ex, ey, (a0 + a1) / 2, ty)
                    self.beam_now = (a0, a1)
                    flicker = self.on and not self.locked and int(t * 16) % 2
                    self.itemconfigure(beam, stipple="gray50" if self.on else "gray25",
                                       state="hidden" if flicker else "normal")
                self.beams_set = k >= 1
        # motes drifting up (monitor mode only: hunt mode is still)
        for item, x0, y0, phase in self.motes:
            if self.on:
                self.itemconfigure(item, state="hidden")
                continue
            p = ((t + phase) % 10) / 10
            x, y = x0 + 18 * p * s * 3, y0 - 70 * p * s * 3
            r = 1.6
            self.coords(item, x - r, y - r, x + r, y + r)
            fade = min(p / 0.2, 1, (1 - p) / 0.2)
            self.itemconfigure(item, state="normal", fill=theme.mix(INK, a, 0.55 * max(0, fade)))
        # the banner blinks while hunting (and stops once locked)
        if self.on:
            blink = self.locked or int(t * 2) % 2 == 0
            self.itemconfigure(self.banner, fill="#FF6B6B" if blink else "#7a2a2a")
