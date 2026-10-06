"""Official Codex subscription CLI adapter."""
from __future__ import annotations

import json
from pathlib import Path

from .cli_common import check_model_name, empty_workspace, find_cli, run_cli
from .models import ModelError
from .model_catalog import ModelCatalog, catalog_session, model_choices
from .generation_options import EFFORT_LABELS, fingerprint_options, validate_options
from .storage import sha256
from .translation_common import (PROMPT_VERSION, check_records, request_payload,
                                 translation_schema, validate_translations)

DEFAULT_MODEL = "gpt-5.5"


def list_models():
    """Return the visible model catalog reported by the Codex CLI."""
    executable = find_cli("codex", "Codex")
    # The documented picker protocol works on CLI versions without debug models.
    with catalog_session(executable, ["app-server"], "Codex") as (send, receive):
        send({"id": 1, "method": "initialize", "params": {"clientInfo": {
            "name": "comic_translation", "title": "Comic Translation", "version": "1.0"}}})
        if "error" in receive(lambda message: message.get("id") == 1):
            raise ModelError("Codex 初始化失敗；請更新 CLI 並確認設定。")
        send({"method": "initialized", "params": {}})
        rows, cursor, seen = [], None, set()
        for request_id in range(2, 102):
            send({"id": request_id, "method": "model/list",
                  "params": {"limit": 100, "includeHidden": False, "cursor": cursor}})
            message = receive(lambda message: message.get("id") == request_id)
            result = message.get("result")
            if not isinstance(result, dict) or not isinstance(result.get("data"), list):
                raise ModelError("Codex 模型查詢失敗；請更新 CLI 並確認登入。")
            rows.extend(result["data"])
            cursor = result.get("nextCursor")
            if not cursor:
                choices = model_choices(rows, "model", "displayName")
                names = {name for name, _ in choices}
                capabilities = {}
                for row in rows:
                    if not isinstance(row, dict) or row.get("hidden") or not isinstance(row.get("model"), str) \
                            or row["model"] not in names:
                        continue
                    efforts = [item.get("reasoningEffort") for item in row.get("supportedReasoningEfforts") or []
                               if isinstance(item, dict) and item.get("reasoningEffort") in EFFORT_LABELS]
                    fast = "fast" in (row.get("additionalSpeedTiers") or []) or any(
                        isinstance(tier, dict) and tier.get("id") == "priority"
                        for tier in row.get("serviceTiers") or [])
                    capabilities.setdefault(row["model"], {"efforts": efforts, "fast": fast})
                return ModelCatalog(choices, capabilities)
            if not isinstance(cursor, str) or cursor in seen:
                break
            seen.add(cursor)
        raise ModelError("Codex 模型清單分頁異常；請更新 CLI 後重試。")


class CodexTranslator:
    provider = "codex"
    allowed_items = {"agent_message", "reasoning"}

    def __init__(self, timeout=180, model=DEFAULT_MODEL, effort=None, fast=None):
        self.executable = find_cli("codex", "Codex")
        self.timeout = timeout
        self.model = check_model_name(model)
        self.options = validate_options(self.provider, effort, fast)
        self.last_metadata = {}
        self.fingerprint = {"provider": "codex-cli", "model": self.model, "prompt": PROMPT_VERSION,
                            "normalization": "s2t-protected-names-1", "cli_sha256": sha256(Path(self.executable))}
        self.fingerprint.update(fingerprint_options(self.options))

    def _run(self, arguments, timeout, cwd=None, merge_stderr=False, input_text=None):
        return run_cli(self.executable, arguments, timeout, "Codex", cwd=cwd,
                       merge_stderr=merge_stderr, input_text=input_text)

    def preflight(self):
        try:
            if "ChatGPT" not in self._run(["login", "status"], 30, merge_stderr=True):
                raise ValueError("不是 ChatGPT 訂閱登入")
        except (OSError, ValueError) as exc:
            raise ModelError("Codex 安全檢查失敗：請在終端機執行 codex login 並以 ChatGPT 訂閱登入；"
                             "無法確認時不傳送文字。") from exc

    def translate(self, records, glossary):
        self.last_metadata = {}
        if not records:
            return {}
        check_records(records)
        self.preflight()
        with empty_workspace("comic-codex-") as workspace:
            schema, answer = Path(workspace, "schema.json"), Path(workspace, "answer.json")
            schema.write_text(json.dumps(translation_schema(records)), encoding="utf-8")
            options = getattr(self, "options", {})
            flags = []
            if options.get("effort"):
                flags += ["-c", f'model_reasoning_effort="{options["effort"]}"']
            if options.get("fast"):
                flags += ["-c", 'service_tier="fast"', "-c", "features.fast_mode=true"]
            try:
                stdout = self._run(["exec", "-m", self.model, "--skip-git-repo-check", "--ephemeral", "-s", "read-only",
                                    "--output-schema", str(schema), "-o", str(answer), "--json",
                                    *flags, "-"], self.timeout + 20, cwd=workspace,
                                   input_text=request_payload(records, glossary))
                events = [json.loads(line) for line in stdout.splitlines() if line.startswith("{")]
                if any(e.get("type") in {"error", "turn.failed"} for e in events) \
                        or not any(e.get("type") == "turn.completed" for e in events):
                    raise ModelError("Codex 未完成翻譯：可能未登入、額度不足、模型不支援此帳號或連線失敗。請確認後續跑。")
                if any(e.get("type", "").startswith("item.") and
                       e.get("item", {}).get("type") not in self.allowed_items | {"error"} for e in events):
                    raise ValueError("Codex 執行了非翻譯動作，結果拒絕使用")
                result = validate_translations(json.loads(answer.read_text(encoding="utf-8")), records, glossary)
            except OSError as exc:
                raise ModelError("無法啟動 Codex；批次暫停，請確認 CLI 安裝。") from exc
        usage = next((e.get("usage") for e in events if e.get("type") == "turn.completed"), None)
        self.last_metadata = {"model": self.model, "prompt_version": PROMPT_VERSION, "usage": usage,
                              "duration_seconds": None, "cloud_text": True}
        self.last_metadata.update(options)
        return result
