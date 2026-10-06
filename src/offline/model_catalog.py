"""Metadata-only CLI protocols; never send a user prompt or start a turn."""
from __future__ import annotations

import json
import queue
import subprocess
import threading
import time
from contextlib import contextmanager

from .cli_common import cli_command, clean_environment, empty_workspace, popen_cli
from .models import ModelError
from src.platforms import current as platform_support


@contextmanager
def catalog_session(executable, arguments, label, timeout=30):
    with empty_workspace("comic-models-") as workspace:
        process = popen_cli(cli_command(executable, arguments), cwd=workspace,
            env=clean_environment(), stdin=subprocess.PIPE, stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL, text=True, encoding="utf-8", errors="replace",
            start_new_session=platform_support.START_NEW_SESSION)
        messages = queue.Queue()
        deadline = time.monotonic() + timeout

        def read():
            try:
                # The reader closes its own stream. Closing it from the query
                # thread can block on its read lock if a descendant holds stdout.
                with process.stdout:
                    for line in process.stdout:
                        try:
                            message = json.loads(line)
                        except ValueError:
                            continue
                        if isinstance(message, dict):
                            messages.put(message)
            except OSError:
                pass
            finally:
                messages.put(None)

        reader = threading.Thread(target=read, daemon=True)
        reader.start()

        def send(message):
            try:
                process.stdin.write(json.dumps(message, ensure_ascii=False) + "\n")
                process.stdin.flush()
            except OSError as error:
                raise ModelError(f"{label} 無法查詢模型；請確認 CLI 版本與登入。") from error

        def receive(matches):
            while True:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise ModelError(f"{label} 模型查詢逾時；請確認登入與連線。")
                try:
                    message = messages.get(timeout=remaining)
                except queue.Empty as error:
                    raise ModelError(f"{label} 模型查詢逾時；請確認登入與連線。") from error
                if message is None:
                    raise ModelError(f"{label} 模型查詢未完成；請更新官方 CLI 並確認登入。")
                if matches(message):
                    return message

        try:
            yield send, receive
        finally:
            try:
                process.stdin.close()
            except OSError:
                pass  # An exited CLI closed its pipe; keep the query's own error.
            try:
                process.wait(timeout=1)
            except subprocess.TimeoutExpired:
                platform_support.kill_process_tree(process.pid)
                try:
                    process.kill()
                except OSError:
                    pass
                try:
                    process.wait(timeout=1)
                except subprocess.TimeoutExpired:
                    pass
            reader.join(timeout=1)


class ModelCatalog(list):
    """Model choices plus the CLI's supported effort/speed metadata."""
    def __init__(self, choices, capabilities):
        super().__init__(choices)
        self.capabilities = capabilities


def model_choices(rows, id_key, label_key):
    """Only accept CLI-supplied names, preserving order and dropping duplicates."""
    from .cli_common import MODEL_NAME
    if not isinstance(rows, list):
        raise ModelError("CLI 未回傳模型清單；請更新官方 CLI 並確認登入。")
    choices = {}
    for row in rows:
        if not isinstance(row, dict):
            continue
        name = row.get(id_key)
        if isinstance(name, str) and MODEL_NAME.fullmatch(name) and not row.get("hidden", False):
            label = row.get(label_key)
            choices.setdefault(name, label if isinstance(label, str) and label else name)
    if not choices:
        raise ModelError("CLI 回傳空的模型清單；請確認登入、CLI 版本與帳號設定。")
    return list(choices.items())
