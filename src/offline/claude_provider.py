"""Official Claude Code subscription CLI adapter."""
from __future__ import annotations

import json
from pathlib import Path

from .cli_common import MODEL_NAME, check_model_name, find_cli, run_cli
from .models import ModelError
from .model_catalog import ModelCatalog, catalog_session, model_choices
from .generation_options import EFFORT_LABELS, fingerprint_options, validate_options
from .storage import sha256
from .translation_common import (PROMPT_VERSION, check_records, request_payload,
                                 translation_schema, validate_translations)

DEFAULT_MODEL = "sonnet"


def list_models():
    """Read the model picker from Claude Code's SDK initialization response."""
    executable = find_cli("claude", "Claude Code")
    arguments = ["--input-format", "stream-json", "--output-format", "stream-json", "--verbose",
                 "--tools", "", "--permission-mode", "plan", "--no-session-persistence",
                 "--setting-sources", "", "--strict-mcp-config", "--mcp-config", '{"mcpServers":{}}']
    with catalog_session(executable, arguments, "Claude") as (send, receive):
        request_id = "comic-models"
        send({"type": "control_request", "request_id": request_id,
              "request": {"subtype": "initialize", "hooks": {}}})
        message = receive(lambda message: message.get("type") == "control_response" and
                          isinstance(message.get("response"), dict) and
                          message["response"].get("request_id") == request_id)
        response = message["response"]
        data = response.get("response")
        if response.get("subtype") != "success" or not isinstance(data, dict):
            raise ModelError("Claude 模型查詢失敗；請更新 CLI 並確認登入。")
        # Newer CLIs resolve aliases to a concrete version. Older ones still
        # supply their real picker options; never invent a static catalog.
        rows = data.get("models")
        resolved = rows
        if isinstance(rows, list):
            resolved = [{**row, "value": row.get("resolvedModel") or row.get("value")}
                        for row in rows if isinstance(row, dict)]
        choices = model_choices(resolved, "value", "displayName")
        names = {name for name, _ in choices}
        capabilities = {}
        for row in rows:
            if not isinstance(row, dict) or row.get("hidden"):
                continue
            name = row.get("resolvedModel") or row.get("value")
            if not isinstance(name, str) or name not in names:
                continue
            caps = {"efforts": [level for level in (row.get("supportedEffortLevels") or [])
                                if level in EFFORT_LABELS],
                    "fast": row.get("supportsFastMode") is True}
            capabilities.setdefault(name, caps)
            # Keep the CLI's alias too: existing preferences can still select
            # "sonnet" even though the picker lists its resolved model ID.
            alias = row.get("value")
            if isinstance(alias, str) and MODEL_NAME.fullmatch(alias):
                capabilities.setdefault(alias, caps)
        return ModelCatalog(choices, capabilities)


class ClaudeTranslator:
    provider = "claude"

    def __init__(self, timeout=180, model=DEFAULT_MODEL, effort=None, fast=None):
        self.executable = find_cli("claude", "Claude Code")
        self.timeout = timeout
        self.model = check_model_name(model)
        self.options = validate_options(self.provider, effort, fast)
        self.last_metadata = {}
        self.fingerprint = {"provider": "claude-cli", "model": self.model, "prompt": PROMPT_VERSION,
                            "normalization": "s2t-protected-names-1", "cli_sha256": sha256(Path(self.executable))}
        self.fingerprint.update(fingerprint_options(self.options))

    def _run(self, arguments, timeout, input_text=None):
        effort = getattr(self, "options", {}).get("effort")
        overrides = {"CLAUDE_CODE_EFFORT_LEVEL": effort} if effort else None
        return run_cli(self.executable, arguments, timeout, "Claude", input_text=input_text,
                       env_overrides=overrides)

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
        options = getattr(self, "options", {})
        flags = ["--effort", options["effort"]] if options.get("effort") else []
        if options.get("fast"):
            flags += ["--settings", json.dumps({"fastMode": True})]
        try:
            stdout = self._run(["-p", "--model", self.model,
                                "--output-format", "json", "--json-schema", json.dumps(translation_schema(records)),
                                "--tools", "", "--permission-mode", "plan", "--no-session-persistence",
                                "--setting-sources", "", *flags], self.timeout + 20,
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
            self.last_metadata.update(options)
            return result
        except OSError as exc:
            raise ModelError("無法啟動 Claude；批次暫停，請確認 CLI 安裝。") from exc
