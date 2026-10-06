"""Installed CLI discovery without PATH changes or external CLI execution."""
from pathlib import Path

import pytest

from src.offline import cli_common
from src.platforms import macos, windows, windows_cli


@pytest.fixture
def installed_home(tmp_path, monkeypatch):
    home = tmp_path / "使用者 & home"
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: home))
    monkeypatch.setenv("LOCALAPPDATA", str(home / "AppData/Local"))
    monkeypatch.setenv("APPDATA", str(home / "AppData/Roaming"))
    monkeypatch.setattr(cli_common.shutil, "which", lambda _: None)
    monkeypatch.setattr(cli_common, "platform_support", windows)
    return home


def install(path):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.touch()
    return str(path.resolve())


def test_claude_official_extension_is_found_and_newer_version_preferred(installed_home):
    install(installed_home / '.antigravity/extensions/anthropic.claude-code-2.1.121-win32-x64/resources/native-binary/claude.exe')
    expected = install(installed_home / '.vscode/extensions/anthropic.claude-code-2.1.289-win32-x64/resources/native-binary/claude.exe')
    install(installed_home / '.vscode/extensions/unrelated.claude-code-9.0.0/resources/native-binary/claude.exe')
    assert cli_common.find_cli('claude', 'Claude Code') == expected


def test_codex_desktop_cli_found_without_path_and_incomplete_update_ignored(installed_home):
    expected = install(installed_home / 'AppData/Local/OpenAI/Codex/bin/current/codex.exe')
    (installed_home / 'AppData/Local/OpenAI/Codex/bin/incomplete').mkdir()
    assert cli_common.find_cli('codex', 'Codex') == expected


def test_codex_official_extension_found_without_desktop_install(installed_home):
    expected = install(installed_home / '.vscode/extensions/openai.chatgpt-26.5928.31416-win32-x64/bin/windows-x86_64/codex.exe')
    assert cli_common.find_cli('codex', 'Codex') == expected


@pytest.mark.parametrize('name', ['claude','codex'])
def test_native_cli_and_path_take_priority(installed_home, monkeypatch, name):
    native = install(installed_home / '.local/bin' / f'{name}.exe')
    assert cli_common.find_cli(name, name) == native
    on_path = install(installed_home / 'existing cli' / f'{name}.exe')
    monkeypatch.setattr(cli_common.shutil, 'which', lambda _: on_path)
    assert cli_common.find_cli(name, name) == on_path


def test_macos_does_not_search_windows_installs(installed_home, monkeypatch):
    install(installed_home / '.local/bin/claude.exe')
    monkeypatch.setattr(cli_common, 'platform_support', macos)
    with pytest.raises(cli_common.CliNotInstalled):
        cli_common.find_cli('claude', 'Claude Code')


def test_missing_cli_and_unrelated_names_do_not_pick_desktop_launchers(installed_home):
    install(installed_home / 'AppData/Local/Claude/Claude.exe')
    assert windows_cli.find_installed_cli('custom') is None
    with pytest.raises(cli_common.CliNotInstalled):
        cli_common.find_cli('claude', 'Claude Code')
