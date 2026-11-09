"""The About page: who made Khaltron 9000 and why, in the owner's words (2026-11-09)."""

import tkinter as tk
import webbrowser

from PIL import ImageTk

from . import theme

AUTHOR = "Khaldoun Alnaierat"
REPO = "https://github.com/KhaldounN/khaltron"
STORY = [
    "I like to analyze things, and I run large, complex analyses on my PC. Many of them run in the background "
    "for hours, often started with Claude, doing a lot of work while I do something else.",
    "But when I play games, I want my PC back, so I need to stop all of that first.",
    "I created Khaltron to give me visibility and control over all these background processes: what is running "
    "now, what comes next, what it costs my PC, and one click to freeze it all for a game and bring it back after.",
    "Have fun with it. I'm happy for other people to use it: it's free and open source (MIT licence).",
]


class AboutPage(tk.Frame):
    def __init__(self, parent):
        super().__init__(parent, bg=theme.BG)
        card = tk.Frame(self, bg=theme.PANEL, highlightthickness=1, highlightbackground=theme.LINE)
        card.pack(fill="x", padx=2, pady=(6, 0))
        inner = tk.Frame(card, bg=theme.PANEL)
        inner.pack(fill="x", padx=24, pady=22)
        self.logo = ImageTk.PhotoImage(theme.logo(112))
        tk.Label(inner, image=self.logo, bg=theme.PANEL).pack(side="left", anchor="n", padx=(0, 24))
        words = tk.Frame(inner, bg=theme.PANEL)
        words.pack(side="left", fill="x", expand=True)
        tk.Label(words, text="ABOUT KHALTRON 9000", font=(theme.DISPLAY, 16), fg=theme.TEXT,
                 bg=theme.PANEL, anchor="w").pack(fill="x")
        tk.Label(words, text=f"●  MADE BY {AUTHOR.upper()}", font=(theme.MONO, 9, "bold"), fg=theme.LASER,
                 bg=theme.PANEL, anchor="w").pack(fill="x", pady=(6, 14))
        self.paragraphs = []
        for text in STORY:
            label = tk.Label(words, text=text, font=(theme.FONT, 10), fg=theme.TEXT, bg=theme.PANEL, anchor="w",
                             justify="left")
            label.pack(fill="x", pady=(0, 10))
            self.paragraphs.append(label)
        link = tk.Label(words, text=f"▸  {REPO}", font=(theme.MONO, 9, "bold"), fg=theme.LASER, bg=theme.PANEL,
                        anchor="w", cursor="hand2")
        link.pack(fill="x", pady=(4, 0))
        link.bind("<Button-1>", lambda e: webbrowser.open(REPO))
        words.bind("<Configure>", self._wrap)

    def _wrap(self, event):
        """Paragraphs wrap to the page's width (at most ~95 characters a line, so they stay easy to read)."""
        width = min(event.width - 8, 760)
        for label in self.paragraphs:
            label.configure(wraplength=max(260, width))
