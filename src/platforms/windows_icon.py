"""Load the actual Windows icon sizes instead of enlarging Tk's 16/32 px icons."""
from __future__ import annotations

import ctypes
from ctypes import wintypes


def apply_dpi_icons(root, path):
    user32 = ctypes.WinDLL("user32", use_last_error=True)
    user32.GetAncestor.argtypes = [wintypes.HWND, wintypes.UINT]
    user32.GetAncestor.restype = wintypes.HWND
    user32.LoadImageW.argtypes = [wintypes.HINSTANCE, wintypes.LPCWSTR, wintypes.UINT,
                                 ctypes.c_int, ctypes.c_int, wintypes.UINT]
    user32.LoadImageW.restype = wintypes.HANDLE
    user32.SendMessageW.argtypes = [wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM]
    user32.SendMessageW.restype = ctypes.c_ssize_t
    user32.DestroyIcon.argtypes = [wintypes.HICON]
    user32.DestroyIcon.restype = wintypes.BOOL
    window = user32.GetAncestor(root.winfo_id(), 2)  # GA_ROOT: Tk's decorated window.
    if not window:
        return
    icons = []
    for kind, metric in ((0, 49), (1, 11)):  # ICON_SMALL/SM_CXSMICON; ICON_BIG/SM_CXICON.
        size = user32.GetSystemMetrics(metric)
        icon = user32.LoadImageW(None, str(path), 1, size, size, 0x10)  # IMAGE_ICON/LR_LOADFROMFILE.
        if icon:
            icons.append(icon)
            user32.SendMessageW(window, 0x80, kind, icon)  # WM_SETICON.

    def release(event):
        if event.widget is root:
            for icon in icons:
                user32.DestroyIcon(icon)

    root.bind("<Destroy>", release, add="+")
