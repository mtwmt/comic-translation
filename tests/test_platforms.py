"""Adapter isolation checks that do not require physical macOS hardware."""
from types import SimpleNamespace

from src.platforms import macos, select_platform, windows
from src.offline import cli_common


def test_platform_selection_does_not_mix_adapters():
    assert select_platform("win32") is windows
    assert select_platform("darwin") is macos
    assert select_platform("linux") is macos


def test_macos_display_setup_does_not_query_windows_dpi():
    macos.enable_dpi_awareness()
    # This object has no Windows/Tk DPI APIs; macOS must not try to use them.
    assert macos.window_scale(object()) == 1.0


def test_macos_cli_keeps_original_input_and_process_session(monkeypatch):
    monkeypatch.setattr(cli_common, "platform_support", macos)
    calls = []
    pipe = object()

    class Process:
        returncode = 0
        stdin = pipe

        def communicate(self, input=None, timeout=None):
            calls.append((input, timeout))
            return input, ""

    process = Process()
    launches = []

    def launch(*args, **kwargs):
        launches.append(kwargs)
        return process

    monkeypatch.setattr(cli_common.subprocess, "Popen", launch)
    prompt = "日文\n繁中🙂"
    assert cli_common.run_cli("native-cli", [], 12, "Test", input_text=prompt) == prompt
    assert calls == [(prompt, 12)]
    assert process.stdin is pipe  # Windows must not detach this pipe on macOS.
    assert launches[0]["start_new_session"] is True




def test_windows_checks_follow_images_and_macos_keeps_original_row_behavior():
    old_rows = {"0": ("image", "first"), "1": ("image", "second")}
    new_rows = {"0": ("image", "second"), "history-0": ("image", "first")}
    win_selected = windows.capture_selection(["1"], old_rows)
    mac_selected = macos.capture_selection(["1"], old_rows)
    assert windows.restore_selection(win_selected, new_rows) == ["0"]
    assert macos.restore_selection(mac_selected, new_rows) == []
    changes = []
    source_list = SimpleNamespace(selection=lambda: ("1",), selection_remove=lambda rows: changes.append(rows))
    windows.after_submit(source_list)
    assert changes == []
    macos.after_submit(source_list)
    assert changes == [("1",)]


def test_unicode_detector_context_restores_cwd_on_failure_and_mac_does_not_change_it(tmp_path):
    from pathlib import Path
    import pytest
    folder = tmp_path / "辨識模型"
    folder.mkdir()
    previous = Path.cwd()
    with pytest.raises(RuntimeError):
        with windows.detector_context(folder) as directory:
            assert directory == "."
            assert Path.cwd() == folder
            raise RuntimeError("test failure")
    assert Path.cwd() == previous
    with macos.detector_context(folder) as directory:
        assert directory == str(folder)
        assert Path.cwd() == previous
