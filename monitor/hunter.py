"""The Khaltron 9000 header, built to the owner's design package (design/khaltron-header/: README.md is the spec,
khaltron-header.js the behaviour, khaltron-header.css the looks): the thin top bar (1920 x 180, the owner's
shorter version of 2026-11-09). A mechanical raccoon robot in the middle, cropped at the chest, whose glowing eyes
watch up to six apps shown as cards, three on each side, with the gaming-mode button top right.

The design is a web page; this is the same thing on a tkinter Canvas, in the design's own 1600 x 320 coordinates
scaled to the window's width (5:1, like the design):
- Still parts, painted once per mode with Pillow (a Canvas has no blending or blur): the dark radial background,
  the steel ledge band, the artwork (960 x 320 at x 320, its outer 14% faded into the dark), the film grain; for
  gaming mode also the 6% push-in toward the eyes, the red colour grade, darkening by 30% and the red vignette.
- Live parts on top, as in the design's SVG: eye glow, pupils that follow the gaze, the red eyes and angry lids of
  gaming mode, a scan beam from each eye (and a laser in gaming mode), drifting dust, the cards, the brand and the
  button.

Behaviour (the design's state machine and timings, KhaltronHeader.TIMING in the JS):
- Monitor mode (phase "watch"): cyan. Every 1.8 s the robot looks at another card; that card gets a cyan
  highlight. Every card says MONITORED.
- Gaming mode, played once: "sweep" (it glares at each card: look 380 ms, the card flashes WARNED, 260 ms, the next;
  the card looked at lifts, gets red corner brackets and a blinking TERMINATE? badge; cards not reached yet say
  SCANNING...), then "pausing" (800 ms after the last warning: it looks straight down, the beams flood every card,
  all cards flash PAUSED), then "locked" (1.3 s later): everything stops, red, staring down. on_locked fires there:
  the app freezes the jobs at that moment, as the design's README asks.
- Exit gaming mode at any time with the button.

Honest cards: in gaming mode the cards are what gaming mode really pauses (your background jobs, OneDrive...) first,
then your other apps. The robot warns them all, as in the design, but only the paused ones say PAUSED; the others
(your browser, Claude...) say SPARED. Once the jobs are frozen, the cards follow what was really frozen."""

import math
import random
import threading
import time
import tkinter as tk
import tkinter.font as tkfont
from dataclasses import dataclass

from PIL import Image, ImageChops, ImageDraw, ImageEnhance, ImageFilter, ImageTk

from . import sound, theme
from .config import HOME

NATIVE_W, NATIVE_H = 1920, 180   # the design's thin top bar (10.7:1): ~110 px tall in a 1180 px window
VIEW_W = NATIVE_W
OFFSET = 0
CYAN, RED = "#35E0FF", "#FF3B3B"
YELLOW = "#FFC83D"        # development mode (the owner's choice, 2026-11-13): the raccoon, its eyes and beams go yellow
EYES = [(933.3, 82.2), (985.6, 82.7)]   # measured on the banner art (its glowing eyes at 1044,348 / 1138,349)
CAM = (959, 82)           # the push-in's origin
ART_BOX = (357, 0, 1199, 180)  # the artwork's left, top, width, height: the whole banner, its ledge on the bar's edge
SLOTS = [28, 188, 348, 1422, 1582, 1742]                     # three cards left of the robot, three right
CARD_TOP, CARD_W, CARD_H = 112, 150, 50
ANGLES = [87, 86.3, 85.2, -85.2, -86.3, -87]                 # beam rotation per card (degrees, CSS rotate)
PUPIL = [(-2.5, .6), (-2.2, .6), (-2, .6), (2, .6), (2.2, .6), (2.5, .6)]
DOWN = "c"                # "look-c": each eye floods its own side (left beam the left cards, right beam the right)
DOWN_ANGLES, DOWN_SCALE = (86, -86), 7.0
LIDS = [[(919.3, 68.2), (948.7, 68.2), (948.7, 80.8), (919.3, 73.4)],
        [(971.3, 69.9), (1000.5, 69.9), (1000.5, 75.1), (971.3, 82.3)]]
EYE = {"glow": 10.5, "dark": 5.7, "ring": 4.5, "ring_w": 1.4, "pupil": 2.6, "spark": 1.2}
BEAM = {"start": 4, "length": 1000, "half": 20, "laser_from": 8, "laser_to": 966}
TIMING = {"idleStep": 3600,  # the design said 1.8 s; halved for a lighter header (2026-11-13)
          "firstIdle": 1200, "sweepStart": 450, "lookToWarn": 380, "warnToNext": 260,
          "afterLastWarn": 800, "pausingToLocked": 1300}
STATUS = {"monitored": ("● MONITORED", "#7FE9FF"), "scanning": ("SCANNING…", "#C2AEAE"),
          "warned": ("⚠ WARNED", "#FF7A7A"), "paused": ("❚❚ PAUSED", "#FFB3B3"),
          "spared": ("○ SPARED", "#9AA6B2")}
ART = HOME / "assets" / "khaltron-banner.jpg"  # the owner's banner (2026-11-10), its black bars cut off;
# khaltron-raccoon.jpg (the first artwork) still makes the logo and icon (theme.logo)
CATEGORIES = [("chrome", "BROWSER"), ("edge", "BROWSER"), ("firefox", "BROWSER"), ("brave", "BROWSER"),
              ("opera", "BROWSER"), ("python", "JOBS"), ("claude", "AI"), ("discord", "CHAT"), ("slack", "CHAT"),
              ("teams", "MEETINGS"), ("zoom", "MEETINGS"), ("outlook", "MAIL"), ("spotify", "MUSIC"),
              ("onedrive", "SYNC"), ("steam", "GAMES"), ("epic", "GAMES"), ("code", "CODE"), ("terminal", "SHELL"),
              ("powershell", "SHELL"), ("explorer", "FILES"), ("defender", "SECURITY"), ("windows", "SYSTEM"),
              ("node", "RUNTIME"), ("obs", "STREAM"), ("word", "DOCS"), ("excel", "SHEETS"), ("task manager", "SYSTEM")]


@dataclass
class Card:
    name: str
    tag: str
    load: float            # 0..1 (its share of the CPU)
    pids: tuple = ()
    pausable: bool = False  # gaming mode pauses it (your background jobs, OneDrive...); the others are spared


def card_for(program) -> Card:
    """A Programs-on-this-PC row as a card: short name, a category tag, the CPU share as the load bar."""
    name = program.name.replace(" (incl. your background jobs)", " jobs")
    lower = name.lower()
    tag = next((t for key, t in CATEGORIES if key in lower), "APP")
    return Card(name, tag, max(0.03, min(1.0, program.cpu / 100)), tuple(program.pids))


# --- the still picture -------------------------------------------------------------------------------------------
_native: dict[str, Image.Image] = {}  # by look: "watch", "hunt", "dev"
_scaled: dict[tuple, Image.Image] = {}
_lock = threading.Lock()


def _look(look) -> str:
    """The picture's look: "watch" (monitor mode), "hunt" (gaming mode) or "dev" (development mode)."""
    return "hunt" if look is True else "watch" if look is False else look


def _native_scene(look) -> Image.Image:
    """The still picture at the design's 1600 x 320, for monitor, gaming or development mode (cached)."""
    look = _look(look)
    hunt = look == "hunt"
    with _lock:
        if look in _native:
            return _native[look]
        # the dark background: radial-gradient(ellipse at 50% 40%, #15181D 0%, #07080A 60%)
        radial = Image.radial_gradient("L").resize((int(VIEW_W * 1.2), int(NATIVE_H * 2.4)))
        left, top = int(VIEW_W * .5 - radial.width / 2), int(NATIVE_H * .4 - radial.height / 2)
        mask = Image.new("L", (VIEW_W, NATIVE_H), 255)
        mask.paste(radial.point(lambda v: min(255, int(v / .60))), (left, top))
        img = Image.composite(Image.new("RGB", mask.size, "#07080A"), Image.new("RGB", mask.size, "#15181D"), mask)
        # the artwork: 1199 x 180 at (357, 0), the robot on its ledge, outer 14% faded into the dark
        if ART.exists():
            ax, ay, aw, ah = ART_BOX
            art = Image.open(ART).convert("RGB").resize((aw, ah), Image.LANCZOS)
            fade = Image.new("L", (aw, 1))
            for x in range(aw):
                t = x / (aw - 1)
                fade.putpixel((x, 0), int(255 * min(1, t / .14, (1 - t) / .14)))
            img.paste(art, (ax, ay), fade.resize((aw, ah)))
        if hunt:
            # the camera pushes in 6% toward the eyes (the cards and brand stay put; they are drawn live)
            z, (cx, cy) = 1.06, (CAM[0] + OFFSET, CAM[1])
            box = (cx - cx / z, cy - cy / z, cx + (VIEW_W - cx) / z, cy + (NATIVE_H - cy) / z)
            img = img.resize((VIEW_W, NATIVE_H), Image.LANCZOS, box=box)
            # colour grade #FF2A2A at .38 (CSS mix-blend-mode: color keeps the brightness, takes the hue)
            grey = img.convert("L")
            red = Image.merge("RGB", (grey.point(lambda v: min(255, int(v * 1.55))), grey.point(lambda v: int(v * .32)),
                                      grey.point(lambda v: int(v * .32))))
            img = Image.blend(img, red, .38)
            img = ImageEnhance.Brightness(img).enhance(.7)  # the 30% darkening
            # the red vignette: inset 0 0 130px rgba(255,30,30,.45)
            edge = Image.new("L", img.size, 0)
            ImageDraw.Draw(edge).rectangle((0, 0, VIEW_W - 1, NATIVE_H - 1), outline=255, width=34)
            edge = edge.filter(ImageFilter.GaussianBlur(30)).point(lambda v: int(v * .45))  # inset 70px
            img = Image.composite(Image.new("RGB", img.size, (255, 30, 30)), img, edge)
        elif look == "dev":
            # the yellow grade: like gaming mode's red one, but warmer, lighter and without the push-in
            grey = img.convert("L")
            amber = Image.merge("RGB", (grey.point(lambda v: min(255, int(v * 1.5))),
                                        grey.point(lambda v: min(255, int(v * 1.12))), grey.point(lambda v: int(v * .25))))
            img = Image.blend(img, amber, .42)
            edge = Image.new("L", img.size, 0)
            ImageDraw.Draw(edge).rectangle((0, 0, VIEW_W - 1, NATIVE_H - 1), outline=255, width=34)
            edge = edge.filter(ImageFilter.GaussianBlur(30)).point(lambda v: int(v * .3))
            img = Image.composite(Image.new("RGB", img.size, (255, 190, 40)), img, edge)
        # film grain (.12, overlay)
        noise = Image.effect_noise(img.size, 45).convert("RGB")
        img = Image.blend(img, ImageChops.overlay(img, noise), .12)
        _native[look] = img
        return img


def scene(width: int, look) -> Image.Image:
    key = (width, _look(look))
    if key not in _scaled:
        height = round(width * NATIVE_H / VIEW_W)
        _scaled[key] = _native_scene(look).resize((width, height), Image.LANCZOS)
        if len(_scaled) > 9:
            _scaled.pop(next(iter(_scaled)))
    return _scaled[key]


def _round_rect(x0, y0, x1, y1, r):
    return [x0 + r, y0, x1 - r, y0, x1, y0, x1, y0 + r, x1, y1 - r, x1, y1, x1 - r, y1, x0 + r, y1, x0, y1,
            x0, y1 - r, x0, y0 + r, x0, y0]


def _ease(k: float) -> float:
    """cubic-bezier(.3,.9,.3,1), close enough: a quick start that settles softly."""
    k = max(0.0, min(1.0, k))
    return 1 - (1 - k) ** 3


# --- the live header --------------------------------------------------------------------------------------------------
class KhaltronHeader(tk.Canvas):
    """The window gives it: set_programs() (the monitor-mode cards), set_state() (gaming mode as the app sees it,
    maybe switched elsewhere: hotkey, tray, Claude), mark_frozen() (which cards really got paused). It calls back:
    on_locked(cards) when the gaming sequence locks (time to freeze the jobs), on_exit() when the user leaves gaming
    mode, and targets() for the cards gaming mode will pause. Development mode has its own pill left of the gaming
    one: on_dev() when clicked, set_dev() for its state (hidden while gaming mode runs: never both)."""

    FRAME_MS = 90    # while something moves: the gaming sequence, the eyes turning, a card flashing
    CALM_MS = 220    # calm (monitor / dev mode, eyes still): the glow and the dust don't need more (2026-11-13: lighter)

    def __init__(self, parent, on_locked, on_exit, targets, on_dev=None):
        super().__init__(parent, height=200, bg=theme.BG, highlightthickness=0)
        self.on_locked_cb, self.on_exit_cb, self.targets_cb = on_locked, on_exit, targets
        self.on_dev_cb = on_dev
        self.dev_on, self.dev_busy, self.dev_hover, self.dev_items = False, False, False, []
        self.button_x0 = 0.0  # the gaming pill's left edge (the dev pill sits left of it)
        self.width = 0
        self.hunt, self.phase, self.look, self.warned = False, "watch", 2, -1
        self.user_engaged = False          # the user clicked: the real freeze waits for "locked"
        self.busy = False                  # the app is switching gaming mode in the background
        self.cards: list[Card] = []        # monitor-mode cards (live data)
        self.hunt_cards: list[Card] = []   # gaming-mode cards (fixed for the sequence)
        self.frozen_names: set[str] | None = None
        self.flash: dict[int, tuple[float, str]] = {}
        self.timer = None
        self.gaze = {"angle": (ANGLES[2], ANGLES[2]), "scale": 1.0, "pupil": PUPIL[2], "from": None, "since": 0.0}
        self.hover = False
        self.mode_line, self.banner, self.button_items = [], [], []
        self.started = time.time()
        self.bind("<Configure>", self._resized)
        self._schedule(self._idle_step, TIMING["firstIdle"])
        self.after(self.FRAME_MS, self._tick)

    # --- geometry: the design's coordinates, scaled to the width ---------------------------------------------------
    @property
    def S(self) -> float:
        return self.width / VIEW_W

    def P(self, x, y):
        """A point of the stage (edges: the brand, the button) on screen."""
        return x * self.S, y * self.S

    def D(self, x, y):
        """A point of the design's scene (the robot, its eyes, the cards) on screen: centred on the stage."""
        return self.P(x + OFFSET, y)

    def cam(self, x, y):
        """Where a point of the robot shows: in gaming mode the camera is pushed in 6% around CAM."""
        if self.hunt:
            x, y = CAM[0] + (x - CAM[0]) * 1.06, CAM[1] + (y - CAM[1]) * 1.06
        return self.D(x, y)

    @property
    def accent(self) -> str:
        return RED if self.hunt else YELLOW if self.dev_on else CYAN

    @property
    def scene_look(self) -> str:
        return "hunt" if self.hunt else "dev" if self.dev_on else "watch"

    def _resized(self, event):
        if event.width != self.width and event.width > 50:
            self.width = event.width
            self.configure(height=round(event.width * NATIVE_H / VIEW_W))
            self.build()
            others = [look for look in ("watch", "hunt", "dev") if look != self.scene_look]
            threading.Thread(target=lambda w=event.width: [scene(w, look) for look in others],
                             daemon=True).start()  # the other modes, ready to switch

    # --- building ------------------------------------------------------------------------------------------------
    def build(self):
        if not self.width:
            return
        self.delete("all")
        S, a = self.S, self.accent
        self.photo = ImageTk.PhotoImage(scene(self.width, self.scene_look))
        self.scene_item = self.create_image(0, 0, image=self.photo, anchor="nw")
        self.shaken = (0.0, 0.0)
        # eye overlays (in the camera layer: they move with the push-in and the shake)
        self.eyes = []
        self.glow_colours, self.pupils_ready = {}, False  # new items: paint them once in full
        for i, (ex, ey) in enumerate(EYES):
            x, y = self.cam(ex, ey)
            g, d, r_ = EYE["glow"], EYE["dark"], EYE["ring"]
            glow = [self.create_oval(x - r * S, y - r * S, x + r * S, y + r * S, outline=a, width=max(1, 2 * S))
                    for r in (g, g * .72)]
            red = [self.create_oval(x - d * S, y - d * S, x + d * S, y + d * S, fill="#0A0204", outline=""),
                   self.create_oval(x - r_ * S, y - r_ * S, x + r_ * S, y + r_ * S, outline=RED,
                                    width=max(1, EYE["ring_w"] * S))]
            for item in red:
                self.itemconfigure(item, state="normal" if self.hunt else "hidden")
            pupil = [self.create_oval(0, 0, 0, 0, fill=a, outline=""), self.create_oval(0, 0, 0, 0, fill="#ffffff",
                                                                                      outline="")]
            lid = self.create_polygon(*[c for p in LIDS[i] for c in self.cam(*p)], fill="#08090B", outline="",
                                      state="normal" if self.hunt else "hidden")
            self.eyes.append({"x": x, "y": y, "glow": glow, "pupil": pupil, "lid": lid, "red": red})
        self.camera_items = [self.scene_item] + [i for e in self.eyes for i in e["glow"] + e["red"] + e["pupil"] +
                                                 [e["lid"]]]
        # beams and lasers (their own layer, over the camera)
        self.beams = [self.create_polygon(0, 0, 0, 0, 0, 0, fill=a, outline="", stipple="gray12") for _ in EYES]
        self.lasers = [self.create_line(0, 0, 0, 0, fill="#FF6A6A", width=max(1, 2 * S), state="hidden")
                       for _ in EYES]
        self.beams_ready = False
        # dust motes drifting up
        rng = random.Random(11)
        self.motes = [(self.create_oval(0, 0, 0, 0, fill=a, outline=""), rng.uniform(40, VIEW_W - 40), rng.uniform(80, 165),
                       rng.uniform(0, 10), rng.uniform(8, 13)) for _ in range(8)]
        # the cards
        self.card_items = []
        name_font = tkfont.Font(family=theme.MONO + (" SemiBold" if theme.MONO == "JetBrains Mono" else ""),
                                size=-max(9, round(12 * S)))
        tag_font = tkfont.Font(family=theme.MONO, size=-max(8, round(9 * S)))
        status_font = tkfont.Font(family=theme.MONO, size=-max(8, round(9 * S)), weight="bold")
        badge_font = tkfont.Font(family=theme.MONO, size=-max(7, round(9 * S)), weight="bold")
        self.fonts = {"name": name_font, "tag": tag_font, "badge": badge_font}
        for slot in SLOTS:
            x0, y0 = self.D(slot, CARD_TOP)
            w, h = CARD_W * S, CARD_H * S
            pad = 10 * S
            items = {"x0": x0, "y0": y0, "w": w, "h": h, "dy": 0.0}
            items["ring"] = self.create_polygon(*_round_rect(x0 - 2, y0 - 2, x0 + w + 2, y0 + h + 2, 9 * S),
                                                smooth=True, fill="", outline="", width=2, state="hidden")
            items["box"] = self.create_polygon(*_round_rect(x0, y0, x0 + w, y0 + h, 8 * S), smooth=True,
                                               fill="#080C12", outline=a, width=1)
            items["name"] = self.create_text(x0 + pad, y0 + 13 * S, anchor="w", fill="#F2F7FB", font=name_font)
            items["tag"] = self.create_text(x0 + w - pad, y0 + 13 * S, anchor="e", fill="#93A5B6", font=tag_font)
            items["track"] = self.create_rectangle(x0 + pad, y0 + 24 * S, x0 + w - pad, y0 + 28 * S,
                                                   fill="#1A2129", width=0)
            items["fill"] = self.create_rectangle(x0 + pad, y0 + 24 * S, x0 + pad, y0 + 28 * S, fill=a, width=0)
            items["status"] = self.create_text(x0 + pad, y0 + 38 * S, anchor="w", font=status_font)
            k, o = 10 * S, 5 * S
            items["corners"] = [self.create_line(x0 - o, y0 - o + k, x0 - o, y0 - o, x0 - o + k, y0 - o,
                                                 fill=RED, width=2, state="hidden"),
                                self.create_line(x0 + w + o, y0 + h + o - k, x0 + w + o, y0 + h + o,
                                                 x0 + w + o - k, y0 + h + o, fill=RED, width=2, state="hidden")]
            items["badge_bg"] = self.create_polygon(0, 0, 0, 0, 0, 0, smooth=True, fill=RED, outline="",
                                                    state="hidden")
            items["badge"] = self.create_text(0, 0, text="TERMINATE?", fill="#1A0404", state="hidden", font=badge_font)
            self.card_items.append(items)
        # brand: wordmark, mode line, banner
        bx, by = self.P(28, 16)
        word = tkfont.Font(family=theme.DISPLAY, size=-max(13, round(22 * S)))
        self._spaced(bx, by, "KHALTRON 9000", word, "#F2F7FB", .08, anchor="nw")
        self.line_font = tkfont.Font(family=theme.MONO, size=-max(8, round(11 * S)))
        self.banner_font = tkfont.Font(family=theme.MONO, size=-max(7, round(10 * S)), weight="bold")
        line_y = by + word.metrics("linespace") + 5 * S + self.line_font.metrics("linespace") / 2
        dot = max(3, 3.5 * S)
        self.dot = self.create_oval(bx, line_y - dot, bx + 2 * dot, line_y + dot, fill=a, outline="")
        self.mode_line_at = (bx + 2 * dot + 9 * S, line_y)
        self.banner_at = (bx, line_y + self.line_font.metrics("linespace") + 4 * S)
        self.mode_line, self.banner, self.button_items = [], [], []
        self.button_font = tkfont.Font(family=theme.DISPLAY_SEMI, size=-max(10, round(13 * S)))
        self._paint_text()
        self._paint_button()
        self._paint_cards()
        self._frame(time.time() - self.started, force=True)

    def _spaced(self, x, y, text, font, colour, spacing_em, anchor="w"):
        """Text with letter-spacing (the design's .08-.18em), one canvas item per letter. Returns the items."""
        items, step = [], font.metrics("ascent") * spacing_em
        for ch in text:
            items.append(self.create_text(x, y, text=ch, font=font, fill=colour, anchor=anchor))
            x += font.measure(ch) + step
        return items

    # --- the state machine (the design's JS) -------------------------------------------------------------------
    def _schedule(self, fn, ms):
        if self.timer is not None:
            try:
                self.after_cancel(self.timer)
            except tk.TclError:
                pass
        self.timer = self.after(ms, fn)

    def _set(self, **changes):
        before = (self.hunt, self.phase)
        for key, value in changes.items():
            setattr(self, key, value)
        if "look" in changes:
            self._aim(changes["look"])
        if (self.hunt, self.phase) != before:
            self._paint_text()
            self._paint_button()
        self._paint_cards()
        if self.phase == "locked" and before[1] != "locked":
            self.beams_ready = False
            self._frame(time.time() - self.started, force=True)  # one last, steady frame: then it stays still
            if self.user_engaged:
                self.on_locked_cb(self.hunt_cards)

    def _idle_step(self):
        if self.phase != "watch":
            return
        count = max(1, len(self.cards))
        n = self.look if isinstance(self.look, int) else 0
        if count > 1:
            while n == self.look:
                n = random.randrange(count)
        self._set(look=n)
        self._schedule(self._idle_step, TIMING["idleStep"])

    def engage(self, user: bool):
        """Start gaming mode's sequence. user=True: the real freeze happens when it locks (on_locked)."""
        if self.hunt:
            return
        self.user_engaged = user
        from . import sound
        sound.play_gaming()  # the design's activation sound (2.4 s): its drop lands as the bar turns red
        # all six cards, as in the design: what gaming mode really pauses first, then the other apps (spared)
        targets = list(self.targets_cb() or [])
        names = {c.name for c in targets}
        self.hunt_cards = (targets + [c for c in self.cards if c.name not in names])[:len(SLOTS)]
        self.frozen_names = None
        self.hunt, self.phase, self.warned = True, "sweep", -1
        self.build()                      # the red picture, pushed in
        self._paint_text()
        self._paint_button()
        self._set(look=0)
        self._schedule(lambda: self._sweep(0), TIMING["sweepStart"])

    def _sweep(self, k):
        if not self.hunt:
            return
        last = max(0, len(self.hunt_cards) - 1)
        self._set(look=k)

        def warn():
            if not self.hunt:
                return
            self.flash[k] = (time.time(), "warn")
            self._set(warned=k)
            if k < last:
                self._schedule(lambda: self._sweep(k + 1), TIMING["warnToNext"])
            else:
                self._schedule(self._pausing, TIMING["afterLastWarn"])
        self._schedule(warn, TIMING["lookToWarn"])

    def _pausing(self):
        if not self.hunt:
            return
        for i in range(len(self.hunt_cards)):
            self.flash[i] = (time.time(), "pause")
        self._set(phase="pausing", look=DOWN)
        self._schedule(lambda: self.hunt and self._set(phase="locked"), TIMING["pausingToLocked"])

    def disengage(self, user: bool):
        if not self.hunt:
            return
        self.hunt, self.phase, self.warned, self.user_engaged = False, "watch", -1, False
        self.frozen_names = None
        self.flash.clear()
        self.build()
        self._set(look=2)
        self._schedule(self._idle_step, TIMING["firstIdle"])
        if user:
            self.on_exit_cb()

    # --- what the window tells it ---------------------------------------------------------------------------------
    def set_programs(self, cards: list[Card]):
        cards = cards[:len(SLOTS)]
        if [(c.name, c.tag, round(c.load, 2)) for c in cards] != [(c.name, c.tag, round(c.load, 2)) for c in self.cards]:
            self.cards = cards
            if not self.hunt:
                self._paint_cards()

    def mark_frozen(self, frozen_pids: set[int]):
        """Once the jobs are really frozen: the cards that got paused say PAUSED, the others SPARED."""
        if not self.hunt or self.phase != "locked" or not frozen_pids:
            return
        names = {c.name for c in self.hunt_cards if set(c.pids) & frozen_pids}
        if names != self.frozen_names:
            self.frozen_names = names
            self._paint_cards()

    def set_state(self, on: bool, busy: bool | None = None):
        """Gaming mode as the app sees it (it may have been switched by the hotkey, the tray or Claude)."""
        if busy is not None and busy != self.busy:
            self.busy = busy
            self._paint_button()
        if self.busy:
            return
        if on and not self.hunt:
            self.engage(user=False)       # switched elsewhere: play the sequence, nothing more to do
        elif not on and self.hunt and not (self.user_engaged and self.phase != "locked"):
            self.disengage(user=False)

    def _click(self, _event=None):
        if self.busy:
            return
        if self.hunt:
            self.disengage(user=True)
        else:
            self.engage(user=True)

    # --- painting what changes rarely -----------------------------------------------------------------------------
    def _paint_text(self):
        if not self.width:
            return
        for item in self.mode_line + self.banner:
            self.delete(item)
        if not self.hunt:
            line, banner = ("DEV MODE // YOUR WORK FIRST" if self.dev_on else "MONITOR MODE // WATCHING"), ""
        elif self.phase == "sweep":
            line, banner = "GAMING MODE // ISSUING WARNINGS", "⚠ GAMING MODE ENGAGED — ISSUING WARNINGS"
        else:
            line, banner = "GAMING MODE // ALL PROCESSES PAUSED", "⚠ ALL NON-ESSENTIAL PROCESSES PAUSED"
        self.mode_line = self._spaced(*self.mode_line_at, line, self.line_font, "#B4C3D1", .18)
        self.banner = self._spaced(*self.banner_at, banner, self.banner_font, "#FF6B6B", .16) if banner else []
        self.itemconfigure(self.dot, fill=self.accent)

    def _paint_button(self):
        if not self.width:
            return
        for item in self.button_items:
            self.delete(item)
        S = self.S
        text = "SWITCHING…" if self.busy else ("EXIT GAMING MODE" if self.hunt else "GAMING MODE")
        tw = self.button_font.measure(text) + len(text) * self.button_font.metrics("ascent") * .12
        icon_w, pad, gap = 18 * S, 22 * S, 10 * S
        w, h = tw + icon_w + gap + 2 * pad, 44 * S
        x1, y0 = self.width - 28 * S, 16 * S
        x0 = x1 - w
        if self.hunt:
            fill = theme.mix(theme.BG, RED, .3 if self.hover else .18)
            edge, colour = RED, "#FFD9D9"
        else:
            fill = theme.mix("#060C12", CYAN, .16) if self.hover else "#081018"
            edge, colour = CYAN, "#CFF7FF"
        items = [self.create_polygon(*_round_rect(x0, y0, x1, y0 + h, h / 2), smooth=True, fill=fill, outline=edge)]
        # the gamepad icon
        ix, iy = x0 + pad, y0 + h / 2
        items.append(self.create_polygon(*_round_rect(ix, iy - 5.5 * S, ix + icon_w, iy + 5.5 * S, 5 * S),
                                         smooth=True, fill="", outline=colour, width=max(1, 2 * S)))
        items.append(self.create_line(ix + 5 * S, iy - 2.5 * S, ix + 5 * S, iy + 1.5 * S, fill=colour,
                                      width=max(1, 1.6 * S)))
        items.append(self.create_line(ix + 3 * S, iy - .5 * S, ix + 7 * S, iy - .5 * S, fill=colour,
                                      width=max(1, 1.6 * S)))
        for dx, dy in ((12, -1.5), (14, .5)):
            items.append(self.create_oval(ix + dx * S - 1.3 * S, iy + dy * S - 1.3 * S, ix + dx * S + 1.3 * S,
                                          iy + dy * S + 1.3 * S, fill=colour, outline=""))
        items += self._spaced(ix + icon_w + gap, iy, text, self.button_font, colour, .12)
        for item in items:
            self.tag_bind(item, "<Button-1>", self._click)
            self.tag_bind(item, "<Enter>", lambda e: self._hover(True))
            self.tag_bind(item, "<Leave>", lambda e: self._hover(False))
        self.button_items = items
        self.button_x0 = x0
        self._paint_dev_button()

    # --- the development mode pill ----------------------------------------------------------------------------------
    def set_dev(self, on: bool, busy: bool | None = None):
        """Development mode as the app sees it (it may have been switched by the hotkey, the tray or Claude)."""
        switched = on != self.dev_on
        busy_changed = busy is not None and busy != self.dev_busy
        if switched and on:
            self._dev_sound()  # switched elsewhere (hotkey, tray, Claude): the sound plays now
        self.dev_on = on
        if busy is not None:
            self.dev_busy = busy
        if switched:
            self.build()  # a new look: the yellow (or the usual cyan) picture, eyes, beams, cards and text
        elif busy_changed:
            self._paint_dev_button()

    def _dev_sound(self):
        if time.time() - getattr(self, "dev_sound_at", 0) > 10:  # once per switch, not again when it lands
            self.dev_sound_at = time.time()
            sound.play_dev()

    def _dev_click(self, _event=None):
        if not self.dev_busy and not self.hunt and self.on_dev_cb:
            if not self.dev_on:
                self._dev_sound()  # at the click: the switch itself takes a few seconds
            self.on_dev_cb()

    def _dev_hover(self, inside: bool):
        if inside != self.dev_hover:
            self.dev_hover = inside
            self.configure(cursor="hand2" if inside else "")
            self._paint_dev_button()

    def _paint_dev_button(self):
        if not self.width:
            return
        for item in self.dev_items:
            self.delete(item)
        self.dev_items = []
        if self.hunt or not self.on_dev_cb:  # gaming mode's show: one mode at a time
            return
        S = self.S
        text = "SWITCHING…" if self.dev_busy else ("DEV MODE: ON" if self.dev_on else "DEV MODE")
        icon = "</>"
        icon_w = self.button_font.measure(icon)
        tw = self.button_font.measure(text) + len(text) * self.button_font.metrics("ascent") * .12
        pad, gap = 22 * S, 10 * S
        w, h = tw + icon_w + gap + 2 * pad, 44 * S
        x1, y0 = self.button_x0 - 12 * S, 16 * S
        x0 = x1 - w
        if self.dev_on:  # on: filled yellow, dark letters
            fill = theme.mix(YELLOW, "#FFFFFF", .25) if self.dev_hover else YELLOW
            edge, colour = YELLOW, "#1A1204"
        else:
            fill = theme.mix("#060C12", CYAN, .16) if self.dev_hover else "#081018"
            edge, colour = CYAN, "#CFF7FF"
        items = [self.create_polygon(*_round_rect(x0, y0, x1, y0 + h, h / 2), smooth=True, fill=fill, outline=edge)]
        ix, iy = x0 + pad, y0 + h / 2
        items.append(self.create_text(ix, iy, text=icon, font=self.button_font, fill=colour, anchor="w"))
        items += self._spaced(ix + icon_w + gap, iy, text, self.button_font, colour, .12)
        for item in items:
            self.tag_bind(item, "<Button-1>", self._dev_click)
            self.tag_bind(item, "<Enter>", lambda e: self._dev_hover(True))
            self.tag_bind(item, "<Leave>", lambda e: self._dev_hover(False))
        self.dev_items = items

    def _hover(self, inside: bool):
        if inside != self.hover:
            self.hover = inside
            self.configure(cursor="hand2" if inside else "")
            self._paint_button()

    def _status_of(self, i: int) -> str:
        if self.phase == "watch":
            return "monitored"
        if self.phase == "sweep":
            return "warned" if i <= self.warned else "scanning"
        card = self.hunt_cards[i]
        if self.phase == "locked" and self.frozen_names is not None:  # the truth, once the jobs are frozen
            return "paused" if card.name in self.frozen_names else "spared"
        return "paused" if card.pausable else "spared"

    def _paint_cards(self):
        if not getattr(self, "card_items", None):
            return
        cards = self.hunt_cards if self.hunt else self.cards
        S = self.S
        for i, items in enumerate(self.card_items):
            show = i < len(cards)
            for key in ("box", "name", "tag", "track", "fill", "status"):
                self.itemconfigure(items[key], state="normal" if show else "hidden")
            targeted = show and self.phase in ("watch", "sweep") and self.look == i
            hunt_target = targeted and self.hunt
            for corner in items["corners"]:
                self.itemconfigure(corner, state="normal" if hunt_target else "hidden")
            badge = "normal" if hunt_target and self.phase == "sweep" else "hidden"
            self.itemconfigure(items["badge"], state=badge)
            self.itemconfigure(items["badge_bg"], state=badge)
            if not show:
                self.itemconfigure(items["ring"], state="hidden")
                self._lift(items, 0)
                continue
            card = cards[i]
            room_px = items["w"] - 20 * S - self.fonts["tag"].measure(card.tag) - 6 * S
            name = card.name
            while name and self.fonts["name"].measure(name + "…") > room_px:
                name = name[:-1]
            self.itemconfigure(items["name"], text=card.name if name == card.name else name.rstrip() + "…")
            self.itemconfigure(items["tag"], text=card.tag)
            status = self._status_of(i)
            text, colour = STATUS[status]
            if status == "monitored" and self.dev_on:
                colour = theme.mix(YELLOW, "#FFFFFF", .35)
            self.itemconfigure(items["status"], text=text, fill=colour)
            x0, y0, w = items["x0"], items["y0"] + items["dy"], items["w"]
            self.coords(items["fill"], x0 + 10 * S, y0 + 24 * S, x0 + 10 * S + (w - 20 * S) * card.load, y0 + 28 * S)
            self.itemconfigure(items["fill"], fill="#5C2626" if status == "paused" else self.accent)
            if self.hunt:
                edge = RED if hunt_target else theme.mix("#1A0608", RED, .5)
                surface = "#120507" if status == "paused" else "#170709"
            else:
                edge = theme.mix("#080C12", self.accent, .85 if targeted else .35)
                surface = "#080C12"
            self.itemconfigure(items["box"], outline=edge, fill=surface, width=1)
            ring = theme.mix(theme.BG, RED if hunt_target else self.accent, .35 if hunt_target else .25)
            self.itemconfigure(items["ring"], outline=ring, state="normal" if targeted else "hidden")
            if hunt_target:
                bh = self.fonts["badge"].metrics("linespace") + 2
                bx1, by = x0 + w - 10 * S, items["y0"] - bh + 3  # mostly above the card's top edge
                bw = self.fonts["badge"].measure("TERMINATE?") + 16 * S
                self.coords(items["badge"], bx1 - bw / 2, by + bh / 2)
                self.coords(items["badge_bg"], *_round_rect(bx1 - bw, by, bx1, by + bh, bh / 2))
            self._lift(items, -4 * S if hunt_target else 0)

    def _lift(self, items, dy):
        """The targeted card rises 6px in gaming mode."""
        move = dy - items["dy"]
        if move:
            for key in ("ring", "box", "name", "tag", "track", "fill", "status", "badge", "badge_bg"):
                self.move(items[key], 0, move)
            for corner in items["corners"]:
                self.move(corner, 0, move)
            items["dy"] = dy

    # --- the gaze: pupils and beams ease to their target in .55 s ----------------------------------------------------
    def _aim(self, look):
        g = self.gaze
        g["from"] = (g["angle"], g["scale"], g["pupil"])
        if look == DOWN:
            g["to"] = (DOWN_ANGLES, DOWN_SCALE, (0, 1))
        else:
            look = min(look, len(SLOTS) - 1)
            g["to"] = ((ANGLES[look], ANGLES[look]), 1.0, PUPIL[look])
        g["since"] = time.time()
        self.beams_ready = False

    # --- the animation --------------------------------------------------------------------------------------------
    def _tick(self):
        try:
            if self.winfo_viewable() and self.width and self.phase != "locked":
                self._frame(time.time() - self.started)
            busy = (self.hunt and self.phase != "locked") or self.flash or self.gaze.get("to") and                 time.time() - self.gaze["since"] < .6
            fast = self.FRAME_MS if busy else self.CALM_MS
            # another window has the focus: calm frames once a second (the gaming sequence keeps its pace)
            delay = 700 if self.phase == "locked" else theme.pace(self, fast, background=fast if busy else 1000)
            self.after(delay, self._tick)
        except tk.TclError:
            return

    def _frame(self, t: float, force: bool = False):
        S, a, g = self.S, self.accent, self.gaze
        locked = self.phase == "locked"
        # the gaze
        moving = False
        if g.get("to"):
            k = _ease((time.time() - g["since"]) / .55)
            (a0, s0, p0), (a1, s1, p1) = g["from"], g["to"]
            g["angle"] = tuple(x0 + (x1 - x0) * k for x0, x1 in zip(a0, a1))
            g["scale"] = s0 + (s1 - s0) * k
            g["pupil"] = (p0[0] + (p1[0] - p0[0]) * k, p0[1] + (p1[1] - p0[1]) * k)
            moving = k < 1
        # the shake (gaming mode, until it locks): the camera layer jumps by 1.5px
        if self.hunt and not locked:
            dx, dy = random.choice([(1.5, -1), (-1.5, 1), (1, 1.5), (0, 0)])
            dx, dy = dx * S, dy * S
        else:
            dx, dy = 0.0, 0.0
        if (dx, dy) != self.shaken:
            for item in self.camera_items:
                self.move(item, dx - self.shaken[0], dy - self.shaken[1])
            self.shaken = (dx, dy)
        # eyes: glow pulse (2.6 s; .5 s gaming), pupils
        period = .5 if self.hunt else 2.6
        pulse = 1.0 if locked else .775 + .225 * math.cos(t * 2 * math.pi / period)
        strength = (.9 if self.hunt else .45) * pulse
        # calm: the slow glow pulse and the dust only every second frame (~2 a second; they move slowly anyway)
        self.frames = getattr(self, "frames", 0) + 1
        busy = moving or force or (self.hunt and not locked) or bool(self.flash)
        slow_parts = busy or self.frames % 2 == 0
        pupils_moved = moving or force or (dx, dy) != (0.0, 0.0) or not getattr(self, "pupils_ready", False)
        glows = getattr(self, "glow_colours", {})
        for eye in self.eyes:
            for ring, share in zip(eye["glow"], (.55, .9)):
                colour = theme.mix("#05070A", a, share * strength)
                if slow_parts and (glows.get(ring) != colour or force):  # only when changed: each change repaints
                    self.itemconfigure(ring, outline=colour)
                    glows[ring] = colour
            if pupils_moved:
                ex, ey = eye["x"] + self.shaken[0], eye["y"] + self.shaken[1]
                px, py = ex + g["pupil"][0] * S, ey + g["pupil"][1] * S  # (design px, scaled)
                for item, r in zip(eye["pupil"], (EYE["pupil"], EYE["spark"])):
                    self.coords(item, px - r * S, py - r * S, px + r * S, py + r * S)
        self.glow_colours = glows
        self.pupils_ready = not moving
        # beams: a cone from each eye, rotated toward the card (scaled wide when looking down); lasers in gaming
        if moving or force or (self.hunt and not locked) or not self.beams_ready:
            flicker = self.hunt and not locked and int(t * 1000 / 120) % 2
            for beam, laser, (bx, by), angle in zip(self.beams, self.lasers, EYES, g["angle"]):
                ox, oy = self.D(bx, by)
                theta = math.radians(angle)

                def rot(px, py, ox=ox, oy=oy, bx=bx, by=by, theta=theta):
                    vx, vy = px - bx, py - by
                    rx = vx * math.cos(theta) - vy * math.sin(theta)
                    ry = vx * math.sin(theta) + vy * math.cos(theta)
                    return ox + rx * S, oy + ry * S
                half, length = BEAM["half"] * g["scale"], BEAM["length"]
                self.coords(beam, *rot(bx, by + BEAM["start"]), *rot(bx - half, by + length),
                            *rot(bx + half, by + length))
                wide = g["scale"] > 2  # flooding every card: fainter, so the cards stay readable
                self.itemconfigure(beam, fill=a, stipple="gray25" if self.hunt and not wide else "gray12",
                                   state="hidden" if flicker or locked else "normal")  # gone once locked
                self.coords(laser, *rot(bx, by + BEAM["laser_from"]), *rot(bx, by + BEAM["laser_to"]))
                self.itemconfigure(laser, state="normal" if self.hunt and g["scale"] < 2 else "hidden")
            self.beams_ready = not moving
        # dust drifting up (frozen in mid-air once locked)
        if not locked and slow_parts:
            for item, x0, y0, phase, dur in self.motes:
                p = ((t + phase) % dur) / dur
                x, y = self.P(x0 + 14 * p, y0 - 50 * p)
                fade = .55 if .2 <= p <= .8 else (p / .2 * .55 if p < .2 else (1 - p) / .2 * .45)
                r = max(1, 1.2 * S)
                self.coords(item, x - r, y - r, x + r, y + r)
                self.itemconfigure(item, fill=theme.mix("#05070A", a, fade))
        # card flashes: WARNED (a red glow, .6 s) and PAUSED (red fading to dark, .7 s)
        for i, (since, kind) in list(self.flash.items()):
            k = (time.time() - since) / (.6 if kind == "warn" else .7)
            if k >= 1 or i >= len(self.card_items):
                del self.flash[i]
                self._paint_cards()
                continue
            items = self.card_items[i]
            if kind == "warn":
                self.itemconfigure(items["ring"], state="normal", outline=theme.mix(RED, theme.BG, k))
            else:
                self.itemconfigure(items["box"], fill=theme.mix(theme.mix(theme.BG, RED, .45), "#120507", k))
        # blinking: the TERMINATE? badge (.5 s) and the banner (1 s) while the sequence plays; steady once locked
        if self.hunt and not locked:
            on = int(t * 2) % 2 == 0
            for items in self.card_items:
                self.itemconfigure(items["badge_bg"], fill=RED if int(t * 4) % 2 == 0 else "#8a1f1f")
            for item in self.banner:
                self.itemconfigure(item, fill="#FF6B6B" if on else "#6b2a2a")
        elif locked:
            for item in self.banner:
                self.itemconfigure(item, fill="#FF6B6B")
