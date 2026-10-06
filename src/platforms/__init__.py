"""Select an isolated OS adapter; translation and image processing stay shared."""
from __future__ import annotations

import sys


def select_platform(name):
    if name == "win32":
        from . import windows
        return windows
    # The existing macOS implementation also supplies the portable POSIX path.
    from . import macos
    return macos


current = select_platform(sys.platform)
