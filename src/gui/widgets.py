"""Small custom Tk widgets."""
from __future__ import annotations

import tkinter as tk
from tkinter import ttk


class ProgressLine(tk.Canvas):
    """A thin, flat page-progress track independent of native theme geometry."""

    def __init__(self, parent):
        self.value = 0
        self.maximum = 100
        style = ttk.Style(parent)
        background = style.lookup("TFrame", "background") or parent.cget("background")
        super().__init__(parent, height=4, highlightthickness=0, borderwidth=0, background=background)
        self.fill = self.create_rectangle(0, 0, 0, 4, fill="#2463da", outline="")
        self.bind("<Configure>", lambda event: self.redraw())

    def configure(self, cnf=None, **kwargs):
        if isinstance(cnf, dict):
            kwargs = {**cnf, **kwargs}
            cnf = None
        self.value = kwargs.pop("value", self.value)
        self.maximum = kwargs.pop("maximum", self.maximum)
        result = super().configure(cnf, **kwargs) if cnf or kwargs else None
        if hasattr(self, "fill"):
            self.redraw()
        return result

    def __getitem__(self, key):
        if key in ("value", "maximum"):
            return getattr(self, key)
        return super().__getitem__(key)

    def redraw(self):
        fraction = min(1, max(0, self.value / max(1, self.maximum)))
        self.coords(self.fill, 0, 0, self.winfo_width() * fraction, 4)
