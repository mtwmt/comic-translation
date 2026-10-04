"""ttk style setup."""
from __future__ import annotations

from tkinter import ttk
from tkinter import font as tkfont


def configure_style(root):
    """Keep the OS theme (including macOS dark mode) instead of emulating
    the web mockup with a different Tk theme and fixed white surfaces.

    Returns the bold heading font so the caller can keep a reference.
    """
    style = ttk.Style(root)
    background = style.lookup("TFrame", "background")
    foreground = style.lookup("TLabel", "foreground")
    default_font = tkfont.nametofont("TkDefaultFont")
    heading_font = default_font.copy()
    heading_font.configure(weight="bold")
    style.configure("Card.TFrame", background=background)
    style.configure("Border.TFrame", background=background, borderwidth=0)
    style.configure("Muted.TLabel", background=background, foreground=foreground)
    style.configure("Heading.TLabel", font=heading_font, background=background)
    style.configure("TButton", width=0, padding=(8, 3))
    style.configure("Compact.TButton", width=0, padding=(6, 3))
    style.configure("Log.TCheckbutton", padding=(6, 3))
    style.configure("Quiet.TButton", width=0, padding=(6, 2))
    style.configure("Link.TButton", width=0, padding=(6, 2))
    style.configure("Primary.TButton", padding=(12, 4))
    style.configure("Treeview", rowheight=default_font.metrics("linespace") + 8)
    return heading_font
