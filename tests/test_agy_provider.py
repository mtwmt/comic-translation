import json

import pytest

from src.offline.agy_provider import AgyTranslator, MODEL, parse_translation
from src.offline.translation_common import request_payload
from src.offline.models import ModelError


def response(values, model=MODEL, status="SUCCESS"):
    return "\n".join(json.dumps(e) for e in [
        {"event": "init", "init": {"model": model}},
        {"event": "result", "result": {"status": status, "structured_output": values, "usage": {"total_tokens": 1}}}])


def test_exact_model_names_and_id_validation():
    rows = [{"id": "a", "text": "星野一郎じゃない。"}]
    glossary = {"星野": "星野", "星野一郎": "星野一郎"}
    result, metadata = parse_translation(response({"a": "不是星野一郎。"}), rows, glossary)
    assert result["a"] == "不是星野一郎。" and metadata["model"] == MODEL
    for raw in [response({"a": "不是星野一郎。"}, model="other"), response({"b": "你好"}),
                response({"a": "星野。"}), response({"a": "こんにちは"}), response({"a": ""}),
                response({"a": "不是星野一郎。"}) + '\n{"event":"step_update","step_update":{"step_type":"tool"}}']:
        with pytest.raises(ValueError):
            parse_translation(raw, rows, glossary)


def test_cloud_error_is_batch_wide():
    with pytest.raises(ModelError):
        parse_translation(response({}, status="ERROR"), [{"id": "a", "text": "はい"}], {})


@pytest.mark.parametrize("credits", [True, None, "false", 0])
def test_credits_fail_closed(credits):
    translator = AgyTranslator.__new__(AgyTranslator)
    translator._run = lambda *a: json.dumps({"status": "SUCCESS", "command": {"data": {"config": {"useG1Credits": credits}}}})
    with pytest.raises(ModelError):
        translator.preflight()


def test_send_rechecks_settings_and_pins_model_without_shell():
    translator = AgyTranslator.__new__(AgyTranslator)
    translator.timeout = 30
    translator.model = MODEL
    calls = []
    translator.preflight = lambda: calls.append("preflight")
    def run(args, timeout, input_text=None):
        calls.append(args)
        assert "-p" not in args
        assert args[args.index("--input-format") + 1] == "stream-json"
        assert input_text.endswith("\n") and len(input_text.splitlines()) == 1
        assert json.loads(input_text) == {"event": "user", "message": {
            "content": request_payload([{"id": "a", "text": "こんにちは。"}], {})}}
        return response({"a": "你好。"})
    translator._run = run
    assert translator.translate([{"id": "a", "text": "こんにちは。"}], {}) == {"a": "你好。"}
    assert calls[0] == "preflight"
    assert calls[1][calls[1].index("--model") + 1] == MODEL
    assert "--dangerously-skip-permissions" not in calls[1]


def test_failed_preflight_does_not_send_source():
    translator = AgyTranslator.__new__(AgyTranslator)
    def fail():
        raise ModelError("quota setting")
    translator.preflight = fail
    translator._run = lambda *a: pytest.fail("must not transmit")
    with pytest.raises(ModelError):
        translator.translate([{"id": "a", "text": "PRIVATE_SOURCE"}], {})


def test_missing_agy_raises_install_hint(monkeypatch):
    import pytest
    from src.offline import agy_provider
    monkeypatch.setattr(agy_provider.shutil, "which", lambda name: None)
    with pytest.raises(agy_provider.AgyNotInstalled):
        agy_provider.AgyTranslator()
    assert agy_provider.INSTALL_URL.startswith("https://antigravity.google/")
