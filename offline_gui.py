"""Entry point for the comic translation GUI; the implementation lives in src/gui."""
from __future__ import annotations

import tkinter as tk

from src.gui.app import OfflineGUI

__all__ = ["OfflineGUI", "main"]


def main():
    try:
        from tkinterdnd2 import TkinterDnD
        root = TkinterDnD.Tk()
    except (ImportError, RuntimeError, tk.TclError):
        root = tk.Tk()
    OfflineGUI(root)
    root.mainloop()


if __name__ == "__main__":
    main()
