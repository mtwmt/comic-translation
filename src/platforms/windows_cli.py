"""Find installed official Windows CLIs even in a GUI's stale PATH.

Only known CLI and official extension layouts are searched. Desktop launchers,
credentials and registry settings are not inspected or modified.
"""
from __future__ import annotations

import os
from pathlib import Path
import re


def installed_files(root, pattern):
    try:
        return [path for path in root.glob(pattern) if path.is_file()]
    except OSError:
        return []


def newest(paths):
    def modified(path):
        try:
            return path.stat().st_mtime_ns
        except OSError:
            return 0
    return sorted(paths, key=modified, reverse=True)


def find_installed_cli(name):
    if name not in {"claude", "codex"}:
        return None
    home = Path.home()
    local = Path(os.environ.get("LOCALAPPDATA") or home / "AppData/Local")
    roaming = Path(os.environ.get("APPDATA") or home / "AppData/Roaming")
    candidates = [home / ".local/bin" / f"{name}.exe",
                  local / "Microsoft/WinGet/Links" / f"{name}.exe",
                  roaming / "npm" / f"{name}.exe", roaming / "npm" / f"{name}.cmd"]
    if name == "codex":
        candidates += newest(installed_files(local / "OpenAI/Codex/bin", "*/codex.exe"))
    extensions = []
    publisher = "anthropic.claude-code" if name == "claude" else "openai.chatgpt"
    for editor in (".vscode", ".vscode-insiders", ".cursor", ".antigravity"):
        root = home / editor / "extensions"
        if name == "claude":
            extensions += installed_files(root, f"{publisher}-*/resources/native-binary/claude.exe")
        else:
            extensions += installed_files(root, f"{publisher}-*/bin/windows-*/codex.exe")
    def version(path):
        extension = next(part for part in path.parts if part.startswith(publisher + "-"))
        match = re.match(re.escape(publisher) + r"-(\d+(?:\.\d+)*)", extension)
        return tuple(map(int, match[1].split("."))) if match else ()
    candidates += sorted(extensions, key=version, reverse=True)
    for candidate in candidates:
        try:
            if candidate.is_file():
                return str(candidate.resolve())
        except OSError:
            continue
    return None
