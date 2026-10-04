"""Official Claude Code subscription CLI adapter."""
from __future__ import annotations

import json
from pathlib import Path

from .cli_common import check_model_name, find_cli, run_cli
from .models import ModelError
from .storage import sha256
from .translation_common import (PROMPT_VERSION, check_records, request_payload,
                                 translation_schema, validate_translations)

DEFAULT_MODEL = "sonnet"
# Claude Code has no model-list command; these aliases always resolve to the latest.
MODELS = [("opus", "Claude Opus（最新）"), ("sonnet", "Claude Sonnet（最新）"), ("haiku", "Claude Haiku（最新）")]


def list_models():
    """Return supported model aliases without requiring a CLI installation."""
    return list(MODELS)


class ClaudeTranslator:
    provider = "claude"

    def __init__(self, timeout=180, model=DEFAULT_MODEL):
        self.executable = find_cli("claude", "Claude Code")
        self.timeout = timeout
        self.model = check_model_name(model)
        self.last_metadata = {}
        self.fingerprint = {"provider": "claude-cli", "model": self.model, "prompt": PROMPT_VERSION,
                            "normalization": "s2t-protected-names-1", "cli_sha256": sha256(Path(self.executable))}

    def _run(self, arguments, timeout, input_text=None):
        return run_cli(self.executable, arguments, timeout, "Claude", input_text=input_text)

    def preflight(self):
        try:
            status = json.loads(self._run(["auth", "status"], 30))
            if status.get("loggedIn") is not True or status.get("authMethod") != "claude.ai" \
                    or status.get("apiProvider") != "firstParty":
                raise ValueError("不是 claude.ai 訂閱登入")
        except (OSError, TypeError, ValueError, AttributeError) as exc:
            raise ModelError("Claude 安全檢查失敗：請在終端機執行 claude 並以 claude.ai 訂閱登入；"
                             "無法確認時不傳送文字。") from exc

    def translate(self, records, glossary):
        self.last_metadata = {}
        if not records:
            return {}
        check_records(records)
        self.preflight()
        try:
            stdout = self._run(["-p", "--model", self.model,
                                "--output-format", "json", "--json-schema", json.dumps(translation_schema(records)),
                                "--tools", "", "--permission-mode", "plan", "--no-session-persistence",
                                "--setting-sources", ""], self.timeout + 20,
                               input_text=request_payload(records, glossary))
            data = json.loads(stdout)
            if not isinstance(data, dict) or data.get("is_error") or data.get("subtype") != "success":
                raise ModelError("Claude 未完成翻譯：可能未登入、額度不足或連線失敗。請確認後續跑。")
            if data.get("permission_denials"):
                raise ValueError("Claude 嘗試使用工具，結果拒絕使用")
            values = data.get("structured_output")
            if values is None:
                values = json.loads(data.get("result", ""))
            result = validate_translations(values, records, glossary)
            self.last_metadata = {"model": self.model, "prompt_version": PROMPT_VERSION,
                                  "usage": data.get("usage"), "duration_seconds": (data.get("duration_ms") or 0) / 1000,
                                  "cloud_text": True}
            return result
        except OSError as exc:
            raise ModelError("無法啟動 Claude；批次暫停，請確認 CLI 安裝。") from exc
