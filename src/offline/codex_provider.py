"""Official Codex subscription CLI adapter."""
from __future__ import annotations

import json
from pathlib import Path

from .cli_common import check_model_name, empty_workspace, find_cli, run_cli
from .models import ModelError
from .storage import sha256
from .translation_common import (PROMPT_VERSION, check_records, request_payload,
                                 translation_schema, validate_translations)

DEFAULT_MODEL = "gpt-5.5"


def list_models():
    """Return the visible model catalog reported by the Codex CLI."""
    executable = find_cli("codex", "Codex")
    catalog = json.loads(run_cli(executable, ["debug", "models"], 30, "Codex"))
    return [(m["slug"], m.get("display_name") or m["slug"]) for m in catalog.get("models", [])
            if m.get("visibility") == "list" and isinstance(m.get("slug"), str)]


class CodexTranslator:
    provider = "codex"
    allowed_items = {"agent_message", "reasoning"}

    def __init__(self, timeout=180, model=DEFAULT_MODEL):
        self.executable = find_cli("codex", "Codex")
        self.timeout = timeout
        self.model = check_model_name(model)
        self.last_metadata = {}
        self.fingerprint = {"provider": "codex-cli", "model": self.model, "prompt": PROMPT_VERSION,
                            "normalization": "s2t-protected-names-1", "cli_sha256": sha256(Path(self.executable))}

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
            try:
                stdout = self._run(["exec", "-m", self.model, "--skip-git-repo-check", "--ephemeral", "-s", "read-only",
                                    "--output-schema", str(schema), "-o", str(answer), "--json",
                                    "-"], self.timeout + 20, cwd=workspace,
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
        return result
