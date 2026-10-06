"""Real metadata transports with local fake CLIs; no inference or cloud usage."""
import json
import subprocess
import sys
from contextlib import contextmanager

import pytest

from src.offline import claude_provider, codex_provider, model_catalog
from src.offline.cli_common import CliNotInstalled
from src.offline.models import ModelError


@pytest.fixture
def fake_catalog(tmp_path, monkeypatch):
    script = tmp_path / "catalog.py"
    script.write_text('''import json, sys
provider, *args = sys.argv[1:]
assert '--model' not in args
assert sys.stdin.isatty() is False
sys.stderr.write('PRIVATE' * 20000)
if provider == 'codex':
    assert args == ['app-server']
    init = json.loads(sys.stdin.readline())
    assert init['method'] == 'initialize'
    print(json.dumps({'id': init['id'], 'result': {}}), flush=True)
    assert json.loads(sys.stdin.readline())['method'] == 'initialized'
    for cursor, rows, next_cursor in [
        (None, [{'model': 'current-model', 'displayName': 'Current',
                 'supportedReasoningEfforts': [{'reasoningEffort': 'low'}, {'reasoningEffort': 'xhigh'}],
                 'additionalSpeedTiers': ['fast']},
                {'model': 'hidden-model', 'hidden': True}], 'next'),
        ('next', [{'model': 'new-model', 'displayName': 'New'},
                  {'model': 'current-model'}, {'model': 'invalid model'}], None)]:
        request = json.loads(sys.stdin.readline())
        assert request['method'] == 'model/list'
        assert request['params']['cursor'] == cursor
        assert request['params']['includeHidden'] is False
        print(json.dumps({'method': 'notification'}), flush=True)
        print(json.dumps({'id': request['id'], 'result': {'data': rows, 'nextCursor': next_cursor}}), flush=True)
else:
    assert '--input-format' in args and '--tools' in args
    assert args[args.index('--tools') + 1] == ''
    init = json.loads(sys.stdin.readline())
    assert init['type'] == 'control_request' and init['request']['subtype'] == 'initialize'
    response = {'subtype': 'success', 'request_id': init['request_id'], 'response': {'models': [
        {'value': 'sonnet', 'resolvedModel': 'claude-sonnet-current', 'displayName': 'Sonnet current',
         'supportsEffort': True, 'supportedEffortLevels': ['low', 'medium', 'high', 'max']},
        {'value': 'haiku', 'displayName': 'Haiku'},
    ]}}
    print(json.dumps({'type': 'control_response', 'response': {**response, 'request_id': 'other'}}), flush=True)
    print(json.dumps({'type': 'control_response', 'response': response}), flush=True)
# No user message, turn/start, exec, or prompt is permitted, even after the response.
assert sys.stdin.read() == ''
''', encoding="utf-8")
    real_session = model_catalog.catalog_session

    def install(module, provider):
        monkeypatch.setattr(module, "find_cli", lambda *args: sys.executable)

        @contextmanager
        def session(executable, arguments, label):
            with real_session(executable, [str(script), provider, *arguments], label, timeout=5) as value:
                yield value

        monkeypatch.setattr(module, "catalog_session", session)
    return install


def test_codex_queries_documented_picker_and_all_pages(fake_catalog):
    fake_catalog(codex_provider, "codex")
    catalog = codex_provider.list_models()
    assert catalog == [("current-model", "Current"), ("new-model", "New")]
    assert catalog.capabilities['current-model'] == {'efforts': ['low', 'xhigh'], 'fast': True}


def test_claude_reads_actual_picker_and_resolves_versions(fake_catalog):
    fake_catalog(claude_provider, "claude")
    catalog = claude_provider.list_models()
    assert catalog == [("claude-sonnet-current", "Sonnet current"), ("haiku", "Haiku")]
    assert catalog.capabilities['claude-sonnet-current'] == {'efforts': ['low', 'medium', 'high', 'max'], 'fast': False}
    assert catalog.capabilities['sonnet'] == catalog.capabilities['claude-sonnet-current']
    assert catalog.capabilities['haiku'] == {'efforts': [], 'fast': False}


def test_missing_claude_never_returns_a_fabricated_catalog(monkeypatch):
    def missing(*args):
        raise CliNotInstalled("找不到 Claude Code CLI")
    monkeypatch.setattr(claude_provider, "find_cli", missing)
    with pytest.raises(CliNotInstalled):
        claude_provider.list_models()


@pytest.mark.parametrize("rows", [None, {}, [], [{"value": "invalid model"}]])
def test_empty_or_invalid_catalog_is_an_error(rows):
    with pytest.raises(ModelError, match="模型清單"):
        model_catalog.model_choices(rows, "value", "displayName")


def test_metadata_timeout_reaps_the_process(monkeypatch):
    started = []
    popen = subprocess.Popen
    def launch(*args, **kwargs):
        process = popen(*args, **kwargs)
        started.append(process)
        return process
    monkeypatch.setattr(model_catalog.subprocess, "Popen", launch)
    with pytest.raises(ModelError, match="逾時"):
        with model_catalog.catalog_session(sys.executable,
                ["-c", "import time; time.sleep(30)"], "Test", timeout=0.2) as (send, receive):
            receive(lambda message: True)
    assert started[0].poll() is not None


def test_codex_null_capabilities_and_invalid_or_hidden_rows(monkeypatch):
    rows = [{"model": "valid", "hidden": True, "additionalSpeedTiers": ["fast"]},
            {"model": "valid", "supportedReasoningEfforts": None,
             "additionalSpeedTiers": None, "serviceTiers": None},
            {"model": "hidden", "hidden": True, "additionalSpeedTiers": ["fast"]},
            {"model": ["not-a-name"], "additionalSpeedTiers": ["fast"]},
            {"model": "invalid name", "additionalSpeedTiers": ["fast"]}]
    responses = iter([{"id": 1, "result": {}}, {"id": 2, "result": {"data": rows}}])
    @contextmanager
    def session(*args):
        yield lambda message: None, lambda matches: next(responses)
    monkeypatch.setattr(codex_provider, "find_cli", lambda *args: "unused")
    monkeypatch.setattr(codex_provider, "catalog_session", session)
    catalog = codex_provider.list_models()
    assert catalog == [("valid", "valid")]
    assert catalog.capabilities == {"valid": {"efforts": [], "fast": False}}
