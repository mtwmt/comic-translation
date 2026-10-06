"""Real local subprocess checks; no subscription CLI or cloud requests."""
import json
import os
from pathlib import Path
import subprocess
import sys

import pytest

from src.offline import cli_common
from src.offline.models import ModelError


def test_large_unicode_stdin_and_output_do_not_block_or_use_arguments(tmp_path, monkeypatch):
    script = tmp_path / "echo.py"
    script.write_text(
        "import json, os, sys\n"
        "sys.stdout.write('x' * 100000)\n"
        "sys.stderr.write('y' * 100000)\n"
        "text = sys.stdin.buffer.read().decode('utf-8')\n"
        "print(json.dumps({'text': text, 'args': sys.argv[1:], 'cwd': os.getcwd(), "
        "'key': os.environ.get('OPENAI_API_KEY')}))\n", encoding="utf-8")
    prompt = '日文「こんにちは」繁中🙂 " & | < > %PATH% ! ^ \\ \n' * 3000
    monkeypatch.setenv("OPENAI_API_KEY", "must-not-reach-child")
    result = cli_common.run_cli(sys.executable, [str(script), "fixed"], 10, "Test", input_text=prompt)
    data = json.loads(result[100000:])
    assert data["text"] == prompt
    assert data["args"] == ["fixed"]
    assert data["key"] is None
    assert not Path(data["cwd"]).exists()  # temporary workspace is removed


def test_preflight_without_input_gets_eof_and_can_merge_stderr():
    result = cli_common.run_cli(sys.executable, ["-c",
        "import sys; assert sys.stdin.read() == ''; sys.stderr.write('status')"],
        10, "Test", merge_stderr=True)
    assert result == "status"


def test_error_does_not_expose_cli_output():
    with pytest.raises(ModelError, match="結束碼 7") as error:
        cli_common.run_cli(sys.executable, ["-c",
            "import sys; print('PRIVATE'); sys.stderr.write('SECRET'); sys.exit(7)"], 10, "Test")
    assert "PRIVATE" not in str(error.value) and "SECRET" not in str(error.value)


@pytest.mark.skipif(os.name != "nt", reason="Windows working directory locks")
@pytest.mark.parametrize("exit_code", [0, 7])
def test_windows_workspace_lock_preserves_cli_result_or_error(tmp_path, monkeypatch, exit_code):
    import ctypes
    from ctypes import wintypes

    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.CreateFileW.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD,
                                    ctypes.c_void_p, wintypes.DWORD, wintypes.DWORD, wintypes.HANDLE]
    kernel32.CreateFileW.restype = wintypes.HANDLE
    kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
    kernel32.CloseHandle.restype = wintypes.BOOL
    # Keep test-created workspaces under pytest's own temporary directory.
    monkeypatch.setattr(cli_common.tempfile, "tempdir", str(tmp_path))
    popen = subprocess.Popen
    locks = []

    def start(*args, **kwargs):
        workspace = Path(kwargs["cwd"])
        # An open CLI-created file must reproduce a real sharing violation.
        locked_file = workspace / "busy.txt"
        locked_file.write_text("test fixture", encoding="utf-8")
        handle = kernel32.CreateFileW(str(locked_file), 0x80000000, 1, None, 3, 0, None)
        assert handle != ctypes.c_void_p(-1).value
        locks.append((handle, workspace))
        with pytest.raises(PermissionError) as locked:
            locked_file.unlink()
        assert locked.value.winerror == 32
        return popen(*args, **kwargs)

    monkeypatch.setattr(cli_common.subprocess, "Popen", start)
    try:
        def query():
            return cli_common.run_cli(sys.executable, ["-c",
                f"import sys; print('model-id\\tModel label'); sys.exit({exit_code})"], 10, "Test")

        if exit_code:
            with pytest.raises(ModelError, match="結束碼 7"):
                query()
        else:
            assert query().strip() == "model-id\tModel label"
        assert locks and locks[0][1].exists()
    finally:
        for handle, workspace in locks:
            kernel32.CloseHandle(handle)
            # Only delete the exact directory created inside this test's root.
            assert workspace.resolve().parent == tmp_path.resolve()
            cli_common.shutil.rmtree(workspace)


def test_timeout_while_child_does_not_read_stdin_reaps_process(monkeypatch):
    started = []
    popen = subprocess.Popen

    def start(*args, **kwargs):
        process = popen(*args, **kwargs)
        if "cwd" in kwargs:  # Windows cleanup also launches taskkill.
            started.append((process, kwargs["cwd"]))
        return process

    monkeypatch.setattr(cli_common.subprocess, "Popen", start)
    with pytest.raises(ModelError, match="逾時"):
        cli_common.run_cli(sys.executable, ["-c", "import time; time.sleep(30)"],
                           0.2, "Test", input_text="文" * 1000000)
    process, workspace = started[0]
    assert process.poll() is not None
    assert not Path(workspace).exists()


@pytest.mark.parametrize("name,entry", [
    ("codex", "@openai/codex/bin/codex.js"),
    ("claude", "@anthropic-ai/claude-code/cli.js"),
])
@pytest.mark.parametrize("local", [False, True])
def test_npm_batch_shims_are_bypassed(tmp_path, monkeypatch, name, entry, local):
    root = tmp_path / "CLI 含空白 & symbols"
    modules = root / "node_modules"
    shim = (modules / ".bin" if local else root) / f"{name}.cmd"
    shim.parent.mkdir(parents=True, exist_ok=True)
    shim.write_text("@echo off\nexit /b 99\n")
    script = modules / entry
    script.parent.mkdir(parents=True)
    script.touch()
    node = root / "node.exe"
    node.touch()
    monkeypatch.setattr(cli_common.shutil, "which", lambda name: str(node) if name == "node.exe" else None)
    args = ["--json-schema", '{"a": "引號 & %PATH%"}', "--tools", ""]
    assert cli_common.cli_command(str(shim), args) == [str(node), str(script), *args]


def test_native_cli_is_preferred_to_batch_shim(tmp_path):
    shim = tmp_path / "agy.cmd"
    native = tmp_path / "agy.exe"
    native.touch()
    assert cli_common.cli_command(str(shim), ["models"]) == [str(native), "models"]
    assert cli_common.cli_command(str(native), ["models"]) == [str(native), "models"]


def test_unknown_or_incomplete_batch_wrapper_is_rejected(tmp_path, monkeypatch):
    monkeypatch.setattr(cli_common.shutil, "which", lambda _: None)
    for name in ("custom.bat", "codex.cmd", "claude.cmd"):
        with pytest.raises(ModelError, match="Windows 包裝檔"):
            cli_common.cli_command(str(tmp_path / name), ["--help"])


@pytest.mark.skipif(os.name != "nt", reason="real Windows process launch")
def test_windows_node_launch_preserves_quotes_and_stdin(tmp_path):
    node = cli_common.shutil.which("node.exe")
    if not node:
        pytest.skip("Node.js is not installed")
    shim = tmp_path / "工具 & path" / "codex.cmd"
    script = shim.parent / "node_modules/@openai/codex/bin/codex.js"
    script.parent.mkdir(parents=True)
    shim.write_text("@echo off\nexit /b 99\n")
    script.write_text("let text = ''; process.stdin.setEncoding('utf8'); "
                      "process.stdin.on('data', chunk => text += chunk); "
                      "process.stdin.on('end', () => console.log(JSON.stringify({"
                      "args: process.argv.slice(2), text})));", encoding="utf-8")
    args = ["--schema", '{"a": "含空白 & %PATH% \\\""}', "", "backslash\\"]
    prompt = "日文\n繁中🙂 & ! %PATH% " * 2000
    result = cli_common.run_cli(str(shim), args, 10, "Test", input_text=prompt)
    assert json.loads(result) == {"args": args, "text": prompt}


@pytest.mark.parametrize("provider", ["agy", "claude", "codex"])
def test_translator_maximum_page_round_trip_through_stdin(tmp_path, monkeypatch, provider):
    from src.offline import agy_provider, claude_provider, codex_provider
    from src.offline.translation_common import request_payload

    records = [{"id": f"r{i:03}", "text": "あ" * 120} for i in range(100)]
    records[0]["alternatives"] = ['日文 " & %PATH%\n別的辨識']
    glossary = {"星野": "星野"}
    expected = request_payload(records, glossary)
    script = tmp_path / "fake_cli.py"
    script.write_text('''import json, sys
from pathlib import Path
provider, expected_file, *args = sys.argv[1:]
raw = sys.stdin.buffer.read().decode('utf-8')
if args[:2] == ['auth', 'status']:
    assert raw == ''
    print(json.dumps({'loggedIn': True, 'authMethod': 'claude.ai', 'apiProvider': 'firstParty'}))
elif args[:2] == ['login', 'status']:
    assert raw == ''
    print('Logged in using ChatGPT', file=sys.stderr)
elif args[:2] == ['-p', '/config']:
    assert raw == ''
    print(json.dumps({'status': 'SUCCESS', 'command': {'data': {'config': {'useG1Credits': False}}}}))
else:
    expected = Path(expected_file).read_text(encoding='utf-8')
    assert expected not in args
    if provider == 'agy':
        assert len(raw.splitlines()) == 1
        message = json.loads(raw)
        assert message['event'] == 'user'
        raw = message['message']['content']
    assert raw == expected
    result = {f'r{i:03}': '好。' for i in range(100)}
    if provider == 'agy':
        print(json.dumps({'event': 'init', 'init': {'model': args[args.index('--model') + 1]}}))
        print(json.dumps({'event': 'result', 'result': {'status': 'SUCCESS', 'structured_output': result}}))
    elif provider == 'claude':
        print(json.dumps({'subtype': 'success', 'structured_output': result}))
    else:
        Path(args[args.index('-o') + 1]).write_text(json.dumps(result), encoding='utf-8')
        print(json.dumps({'type': 'turn.completed'}))
''', encoding="utf-8")
    expected_file = tmp_path / "expected.txt"
    expected_file.write_text(expected, encoding="utf-8")
    real_run = cli_common.run_cli

    def run(executable, arguments, timeout, label, **kwargs):
        return real_run(sys.executable, [str(script), provider, str(expected_file), *arguments],
                        timeout, label, **kwargs)

    module = {"agy": agy_provider, "claude": claude_provider, "codex": codex_provider}[provider]
    monkeypatch.setattr(module, "run_cli", run)
    cls = {"agy": agy_provider.AgyTranslator, "claude": claude_provider.ClaudeTranslator,
           "codex": codex_provider.CodexTranslator}[provider]
    translator = cls.__new__(cls)
    translator.executable, translator.timeout, translator.model = "unused", 10, "test-model"
    assert translator.translate(records, glossary) == {row["id"]: "好。" for row in records}
