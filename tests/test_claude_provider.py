import json

import pytest

from src.offline.claude_provider import ClaudeTranslator
from src.offline.models import ModelError
from src.offline.translation_common import request_payload

ROWS = [{"id": "a", "text": "お待たせ！"}]


def claude(run):
    t = ClaudeTranslator.__new__(ClaudeTranslator)
    t.timeout, t.model, t.last_metadata, t._run = 30, "haiku", {}, run
    return t


def test_claude_requires_subscription_login_before_sending_text():
    sent = []
    def run(args, timeout, input_text=None):
        sent.append(args)
        return json.dumps({"loggedIn": True, "authMethod": "api_key", "apiProvider": "firstParty"})
    with pytest.raises(ModelError, match="安全檢查"):
        claude(run).translate(ROWS, {})
    assert sent == [["auth", "status"]]  # the page text was never passed to a CLI


def test_claude_translates_with_tools_disabled_and_chosen_model():
    calls = []
    def run(args, timeout, input_text=None):
        calls.append(args)
        if args[0] == "auth":
            assert input_text is None
            return json.dumps({"loggedIn": True, "authMethod": "claude.ai", "apiProvider": "firstParty"})
        assert input_text == request_payload(ROWS, {})
        assert input_text not in args
        assert args[:2] == ["-p", "--model"]
        return json.dumps({"subtype": "success", "is_error": False, "structured_output": {"a": "久等了！"},
                           "usage": {"output_tokens": 3}, "duration_ms": 1500})
    t = claude(run)
    assert t.translate(ROWS, {}) == {"a": "久等了！"}
    send = calls[1]
    assert send[send.index("--model") + 1] == "haiku"
    assert send[send.index("--tools") + 1] == "" and send[send.index("--permission-mode") + 1] == "plan"
    assert t.last_metadata["usage"] == {"output_tokens": 3}


def test_claude_failure_or_tool_use_is_rejected():
    def run_with(payload):
        def run(args, timeout, input_text=None):
            if args[0] == "auth":
                return json.dumps({"loggedIn": True, "authMethod": "claude.ai", "apiProvider": "firstParty"})
            return json.dumps(payload)
        return run
    with pytest.raises(ModelError):
        claude(run_with({"subtype": "error_max_turns", "is_error": True})).translate(ROWS, {})
    with pytest.raises(ValueError, match="工具"):
        claude(run_with({"subtype": "success", "is_error": False, "structured_output": {"a": "好"},
                         "permission_denials": [{"tool": "Bash"}]})).translate(ROWS, {})
