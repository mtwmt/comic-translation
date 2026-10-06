"""Read-only initialization retries must never resubmit translation text."""
import json
import pickle
import pytest

from src.offline import agy_provider
from src.offline.cli_common import CliTimeout
from src.offline.models import ModelError
from src.platforms import macos, windows
from src.platforms.windows_agy import CONFIG_TIMEOUTS

CONFIG_ARGS = ["-p", "/config", "--output-format", "json", "--print-timeout", "30s"]


def test_windows_restarts_only_stalled_config_checks():
    calls = []
    def run(arguments, timeout, input_text=None):
        assert input_text is None
        calls.append((arguments, timeout))
        if len(calls) < 3:
            raise CliTimeout("AGY config", timeout)
        return "config-result"
    assert windows.query_agy_configuration(run, CONFIG_ARGS) == "config-result"
    assert calls == [(CONFIG_ARGS, timeout) for timeout in CONFIG_TIMEOUTS[:3]]


def test_windows_config_stall_is_bounded_and_identifies_unsent_text():
    calls = []
    def run(arguments, timeout):
        calls.append(timeout)
        raise CliTimeout("AGY config", timeout)
    with pytest.raises(ModelError, match="尚未送出本頁翻譯文字"):
        windows.query_agy_configuration(run, CONFIG_ARGS)
    assert calls == list(CONFIG_TIMEOUTS)
    assert CONFIG_TIMEOUTS[-1] >= 45  # a slow but working CLI keeps the single-call budget


def test_auth_or_cli_failure_is_not_retried():
    calls = []
    def run(arguments, timeout):
        calls.append(arguments)
        raise ModelError("authentication failed")
    with pytest.raises(ModelError, match="authentication failed"):
        windows.query_agy_configuration(run, CONFIG_ARGS)
    assert len(calls) == 1


def test_macos_keeps_single_45_second_config_call():
    calls = []
    def run(arguments, timeout):
        calls.append((arguments, timeout))
        raise CliTimeout("AGY", timeout)
    with pytest.raises(CliTimeout):
        macos.query_agy_configuration(run, CONFIG_ARGS)
    assert calls == [(CONFIG_ARGS, 45)]
    assert macos.agy_call_label(CONFIG_ARGS, 45) == "AGY"


def test_translation_timeout_is_not_retried(monkeypatch):
    monkeypatch.setattr(agy_provider, "platform_support", windows)
    translator = agy_provider.AgyTranslator.__new__(agy_provider.AgyTranslator)
    translator.timeout, translator.model = 180, "selected-model"
    calls = []
    def run(arguments, timeout, input_text=None):
        calls.append((arguments, input_text))
        if arguments[:2] == ["-p", "/config"]:
            return json.dumps({"status": "SUCCESS", "command": {"data": {"config": {"useG1Credits": False}}}})
        raise CliTimeout("AGY translation", timeout)
    translator._run = run
    with pytest.raises(CliTimeout):
        translator.translate([{"id": "r1", "text": "こんにちは。"}], {})
    assert len(calls) == 2
    assert calls[0][1] is None
    assert "こんにちは。" in calls[1][1]


def test_translation_cannot_enter_initialization_retry_path():
    with pytest.raises(ValueError, match="只適用"):
        windows.query_agy_configuration(lambda *a: pytest.fail("must not run"), ["--input-format", "stream-json"])


def test_windows_timeout_labels_distinguish_config_and_translation():
    assert "設定檢查" in windows.agy_call_label(CONFIG_ARGS, 8)
    assert windows.agy_call_label(["--input-format", "stream-json"], 200) == "AGY 翻譯（200 秒）"


def test_timeout_can_cross_windows_worker_pipe():
    error = CliTimeout("AGY 翻譯（200 秒）", 200)
    restored = pickle.loads(pickle.dumps(error))
    assert isinstance(restored, CliTimeout)
    assert restored.timeout == 200 and restored.label == error.label
    assert str(restored) == str(error)
