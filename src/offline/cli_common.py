"""Shared plumbing for subscription CLI translators (agy, claude, codex).

Text only, no shell, empty temporary workspace, API-key variables removed so a
CLI can never silently fall back to a paid API.
"""
from __future__ import annotations

import os
from pathlib import Path
import re
import shutil
import signal
import subprocess
import tempfile
from contextlib import contextmanager

from .models import ModelError

MODEL_NAME = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:/\[\]-]{0,79}")

# Credentials and endpoint overrides that switch a CLI from the user's
# subscription login to pay-per-token access.
PAID_ENVIRONMENT = (
    "ANTHROPIC_API_KEY", "ANTHROPIC_AUTH_TOKEN", "ANTHROPIC_BASE_URL", "CLAUDE_CODE_USE_BEDROCK",
    "CLAUDE_CODE_USE_VERTEX", "OPENAI_API_KEY", "CODEX_API_KEY", "OPENAI_BASE_URL",
    "GEMINI_API_KEY", "GOOGLE_API_KEY",
)


class CliNotInstalled(ModelError):
    """A translator CLI is not on PATH."""

    def __init__(self, message, install_url=None):
        super().__init__(message)
        self.install_url = install_url


def find_cli(name, label):
    executable = shutil.which(name)
    if not executable:
        raise CliNotInstalled(f"找不到 {label} CLI；請安裝官方 {label} 並在終端機完成訂閱登入。")
    return str(Path(executable).resolve())


def check_model_name(model):
    if not isinstance(model, str) or not MODEL_NAME.fullmatch(model):
        raise ValueError("模型名稱只能包含英數字與 . _ : / [ ] -")
    return model


def clean_environment():
    return {key: value for key, value in os.environ.items() if key not in PAID_ENVIRONMENT}


@contextmanager
def empty_workspace(prefix="comic-translate-"):
    """No repository files, images or path names are visible to the agent."""
    with tempfile.TemporaryDirectory(prefix=prefix) as workspace:
        yield workspace


def terminate(process):
    if os.name == "nt":
        subprocess.run(["taskkill", "/PID", str(process.pid), "/T", "/F"], capture_output=True)
    else:
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
    process.communicate()


def cli_command(executable, arguments):
    """Bypass npm's Windows batch shims without routing arguments through cmd.exe."""
    path = Path(executable)
    if path.suffix.lower() not in {".cmd", ".bat"}:
        return [executable, *arguments]
    native = path.with_suffix(".exe")
    if native.is_file():
        return [str(native), *arguments]
    # Only the known official npm layouts are supported. Do not parse or
    # execute arbitrary batch wrappers: JSON quotes and shell metacharacters
    # must reach the CLI unchanged. Both global and local npm installs work.
    entries = {"codex": "@openai/codex/bin/codex.js",
               "claude": "@anthropic-ai/claude-code/cli.js"}
    entry = entries.get(path.stem.lower())
    if entry:
        modules = path.parent.parent if path.parent.name == ".bin" else path.parent / "node_modules"
        script = modules / entry
        node = path.parent / "node.exe"
        runtime = str(node) if node.is_file() else shutil.which("node.exe")
        if script.is_file() and runtime:
            return [runtime, str(script), *arguments]
    raise ModelError("無法直接啟動此 CLI 的 Windows 包裝檔；請安裝官方原生執行檔，"
                     "或確認官方 npm 套件與 node.exe 已安裝。未傳送文字。")


def run_cli(executable, arguments, timeout, label, cwd=None, merge_stderr=False, input_text=None):
    """Run a CLI and return stdout. Raises ModelError without echoing stderr."""
    def start(workspace):
        return subprocess.Popen(cli_command(executable, arguments), cwd=workspace, env=clean_environment(),
                                stdin=subprocess.PIPE if input_text is not None else subprocess.DEVNULL,
                                stdout=subprocess.PIPE,
                                stderr=subprocess.STDOUT if merge_stderr else subprocess.PIPE,
                                text=True, encoding="utf-8", errors="replace", start_new_session=os.name != "nt")
    def finish(process):
        try:
            stdout, _ = process.communicate(input=input_text, timeout=timeout)
        except subprocess.TimeoutExpired:
            terminate(process)
            raise ModelError(f"{label} 逾時，已停止本次呼叫；批次暫停，不自動重試或切換付費 API。")
        except (KeyboardInterrupt, SystemExit):
            terminate(process)
            raise
        if process.returncode:
            # Never put arbitrary CLI stderr (potential credentials) in UI.
            raise ModelError(f"{label} 結束碼 {process.returncode}；請確認登入、額度與連線後續跑。沒有切換付費 API。")
        return stdout
    if cwd is not None:
        return finish(start(cwd))
    with empty_workspace() as workspace:
        return finish(start(workspace))
