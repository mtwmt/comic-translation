"""Source checkout paths, or writable paths beside the Windows portable exe."""
from pathlib import Path
import sys


def app_root():
    if sys.platform == "win32" and getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parents[1]


def offline_command(*arguments):
    if sys.platform == "win32" and getattr(sys, "frozen", False):
        return [sys.executable, "--cli", *arguments]
    return [sys.executable, str(app_root() / "offline.py"), *arguments]
