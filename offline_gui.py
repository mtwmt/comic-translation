"""Entry point for the comic translation GUI; the implementation lives in src/gui."""
from __future__ import annotations

import multiprocessing
import sys

# PyInstaller reuses this executable for OCR workers. Divert before GUI imports.
if __name__ == "__main__":
    multiprocessing.freeze_support()

import tkinter as tk

from src.gui.app import OfflineGUI
from src.platforms import current as platform_support

__all__ = ["OfflineGUI", "main"]


def main():
    platform_support.enable_dpi_awareness()
    try:
        from tkinterdnd2 import TkinterDnD
        root = TkinterDnD.Tk()
    except (ImportError, RuntimeError, tk.TclError):
        root = tk.Tk()
    OfflineGUI(root)
    root.mainloop()


if __name__ == "__main__":
    if getattr(sys, "frozen", False) and sys.argv[1:2] == ["--cli"]:
        del sys.argv[1]
        from offline import main as cli_main
        cli_main()
    elif getattr(sys, "frozen", False) and sys.argv[1:2] == ["--self-test"]:
        from src.platforms.windows_smoke import main as check_main
        check_main(sys.argv[2:])
    else:
        main()
