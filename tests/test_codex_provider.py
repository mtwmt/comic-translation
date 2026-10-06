import json

import pytest

from src.offline.codex_provider import CodexTranslator
from src.offline.models import ModelError
from src.offline.translation_common import request_payload

ROWS = [{"id": "a", "text": "お待たせ！"}]


def codex(run):
    t = CodexTranslator.__new__(CodexTranslator)
    t.timeout, t.model, t.last_metadata, t._run = 30, "gpt-5.5", {}, run
    return t


def codex_run(events, answer, status="Logged in using ChatGPT"):
    from pathlib import Path
    def run(args, timeout, cwd=None, merge_stderr=False, input_text=None):
        if args[0] == "login":
            assert input_text is None
            return status
        assert args[-1] == "-"
        assert input_text == request_payload(ROWS, {})
        assert input_text not in args
        Path(args[args.index("-o") + 1]).write_text(json.dumps(answer), encoding="utf-8")
        return "\n".join(json.dumps(e) for e in events)
    return run


def test_codex_translates_read_only_and_checks_events():
    ok = [{"type": "item.completed", "item": {"type": "agent_message", "text": "{}"}}, {"type": "turn.completed", "usage": {"output_tokens": 2}}]
    t = codex(codex_run(ok, {"a": "久等了！"}))
    assert t.translate(ROWS, {}) == {"a": "久等了！"}
    assert t.last_metadata["usage"] == {"output_tokens": 2}
    ran = [{"type": "item.completed", "item": {"type": "command_execution"}}, {"type": "turn.completed"}]
    with pytest.raises(ValueError, match="非翻譯"):
        codex(codex_run(ran, {"a": "好"})).translate(ROWS, {})
    failed = [{"type": "turn.failed", "error": {"message": "unsupported"}}]
    with pytest.raises(ModelError, match="未完成"):
        codex(codex_run(failed, {"a": "好"})).translate(ROWS, {})
    with pytest.raises(ModelError, match="安全檢查"):
        codex(codex_run(ok, {"a": "好"}, status="Logged in using an API key")).translate(ROWS, {})


@pytest.mark.parametrize('fast', [True, False])
def test_effort_and_fast_are_passed_to_exec_and_recorded(fast):
    calls = []
    fake = codex_run([{'type': 'turn.completed'}], {'a': '久等了！'})
    def run(args, timeout, **kwargs):
        calls.append(args)
        return fake(args, timeout, **kwargs)
    translator = codex(run)
    translator.options = {'effort': 'xhigh', 'fast': fast}
    assert translator.translate(ROWS, {}) == {'a': '久等了！'}
    config = [calls[-1][i + 1] for i, arg in enumerate(calls[-1]) if arg == '-c']
    assert 'model_reasoning_effort="xhigh"' in config
    # Off leaves the user's own Codex service tier untouched.
    speed = [value for value in config if value.startswith(('service_tier', 'features.fast_mode'))]
    assert speed == (['service_tier="fast"', 'features.fast_mode=true'] if fast else [])
    assert translator.last_metadata['effort'] == 'xhigh'
    assert translator.last_metadata['fast'] is fast
