"""Portable state lives outside PyInstaller's internal resources, independent of cwd."""
from pathlib import Path
import sys

from src import runtime_paths


def test_windows_frozen_paths_and_helper_use_executable_directory(monkeypatch, tmp_path):
    executable = tmp_path / "可攜版" / "ComicTranslator.exe"
    monkeypatch.setattr(sys, "platform", "win32")
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "executable", str(executable))
    monkeypatch.setattr(sys, "_MEIPASS", str(tmp_path / "other/_internal"), raising=False)
    monkeypatch.chdir(tmp_path)
    assert runtime_paths.app_root() == executable.parent
    assert runtime_paths.offline_command("prepare-models") == [str(executable), "--cli", "prepare-models"]


def test_source_and_mac_keep_checkout_paths(monkeypatch, tmp_path):
    checkout = Path(runtime_paths.__file__).resolve().parents[1]
    for platform, frozen in (("win32", False), ("darwin", False), ("darwin", True)):
        monkeypatch.setattr(sys, "platform", platform)
        monkeypatch.setattr(sys, "frozen", frozen, raising=False)
        monkeypatch.chdir(tmp_path)
        assert runtime_paths.app_root() == checkout
        assert runtime_paths.offline_command("prepare-models") == [sys.executable, str(checkout / "offline.py"), "prepare-models"]
