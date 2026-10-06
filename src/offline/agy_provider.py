"""Official AGY subprocess adapter. Text only, subscription only, no fallback."""
from __future__ import annotations

import json
from pathlib import Path
import shutil

from .cli_common import MODEL_NAME, CliNotInstalled, check_model_name, run_cli
from .models import ModelError
from .model_catalog import ModelCatalog
from .generation_options import EFFORT_LABELS
from .storage import sha256
from src.platforms import current as platform_support
from .translation_common import (PROMPT_VERSION, check_records, request_payload,
                                 translation_schema, validate_translations)

INSTALL_URL = "https://antigravity.google/docs/cli/install/"
DEFAULT_MODEL = "gemini-3.8-flash-medium"


def parse_translation(stdout, records, glossary, model=DEFAULT_MODEL):
    events = [json.loads(line) for line in stdout.splitlines() if line.strip()]
    completed = [e["result"] for e in events if e.get("event") == "result"]
    if len(completed) != 1 or completed[0].get("status") != "SUCCESS":
        raise ModelError("AGY 未完成翻譯：可能未登入、額度不足或連線失敗。請在 AGY 中確認後續跑。")
    if any(e.get("event") == "step_update" and
           (e.get("step_update", {}).get("step_type") in {"tool", "subagent"}
            or e.get("step_update", {}).get("tool_info")
            or e.get("step_update", {}).get("subagent_info")) for e in events):
        raise ValueError("AGY 執行了非翻譯工具，結果拒絕使用")
    initial = [e["init"] for e in events if e.get("event") == "init"]
    if len(initial) != 1 or initial[0].get("model") != model:
        raise ValueError("AGY 未確認指定的翻譯模型")
    metadata = completed[0]
    values = metadata.get("structured_output")
    if values is None:
        values = json.loads(metadata.get("response", ""))
    result = validate_translations(values, records, glossary)
    return result, {"model": model, "prompt_version": PROMPT_VERSION,
                    "usage": metadata.get("usage"), "duration_seconds": metadata.get("duration_seconds"),
                    "cloud_text": True}


class AgyNotInstalled(CliNotInstalled):
    """The `agy` executable is not on PATH; the GUI offers the official install page."""


def list_models(executable=None):
    """Model ids from `agy models` (tab separated `id<TAB>label`)."""
    executable = executable or shutil.which("agy")
    if not executable:
        raise AgyNotInstalled("找不到 AGY CLI", INSTALL_URL)
    models = []
    for line in run_cli(executable, ["models"], 30, "AGY").splitlines():
        identifier, _, label = line.partition("\t")
        if label and MODEL_NAME.fullmatch(identifier.strip()):
            models.append((identifier.strip(), label.strip()))
    return ModelCatalog(models, model_capabilities(name for name, _ in models))


def model_capabilities(names):
    """Only expose effort variants actually returned by AGY's catalog."""
    families, selected = {}, {}
    for name in names:
        if not isinstance(name, str) or not MODEL_NAME.fullmatch(name):
            continue
        family, _, level = name.rpartition("-")
        if family and level in EFFORT_LABELS:
            families.setdefault(family, {})[level] = name
            selected[name] = (family, level)
    return {name: {"efforts": list(families[family]), "fast": False,
                   "effort_models": families[family], "selected_effort": level}
            for name, (family, level) in selected.items()}


class AgyTranslator:
    provider = "agy"

    def __init__(self, timeout=180, model=DEFAULT_MODEL):
        executable = shutil.which("agy")
        if not executable:
            raise AgyNotInstalled("找不到 AGY CLI；請安裝官方 AGY 並在終端機執行 agy 完成登入。", INSTALL_URL)
        self.executable = str(Path(executable).resolve())
        self.timeout = timeout
        self.model = check_model_name(model)
        self.last_metadata = {}
        self.fingerprint = {"provider": "agy-cli", "model": self.model, "prompt": PROMPT_VERSION,
                            "normalization": "s2t-protected-names-1", "cli_sha256": sha256(Path(self.executable))}

    def _run(self, arguments, timeout, input_text=None):
        label = platform_support.agy_call_label(arguments, timeout)
        return run_cli(self.executable, arguments, timeout, label, input_text=input_text)

    def preflight(self):
        try:
            arguments = ["-p", "/config", "--output-format", "json", "--print-timeout", "30s"]
            data = json.loads(platform_support.query_agy_configuration(self._run, arguments))
            config = data["command"]["data"]["config"]
            if data.get("status") != "SUCCESS" or config.get("useG1Credits") is not False:
                raise ValueError("額外 credits 未明確停用")
            if config.get("modelProvider") or config.get("gcp") or config.get("customModelsConfig"):
                raise ValueError("偵測到自訂 provider 設定；此入口僅支援官方訂閱登入")
        except (OSError, KeyError, TypeError, ValueError) as exc:
            raise ModelError("AGY 安全檢查失敗：請用官方訂閱登入並關閉 Use G1 Credits；無法確認時不傳送文字。") from exc

    def translate(self, records, glossary):
        self.last_metadata = {}
        if not records:
            return {}
        check_records(records)
        # Recheck at the point of transmission, including after local OCR.
        self.preflight()
        schema = translation_schema(records)
        try:
            message = json.dumps({"event": "user", "message": {"content": request_payload(records, glossary)}},
                                 ensure_ascii=False) + "\n"
            stdout = self._run(["--input-format", "stream-json", "--model", self.model,
                                "--output-format", "stream-json", "--json-schema", json.dumps(schema),
                                "--disable-slash-commands", "--sandbox", "--mode", "plan",
                                "--print-timeout", f"{self.timeout}s"], self.timeout + 20, input_text=message)
            result, self.last_metadata = parse_translation(stdout, records, glossary, self.model)
            return result
        except OSError as exc:
            raise ModelError("無法啟動 AGY；批次暫停，請確認 CLI 安裝。") from exc
