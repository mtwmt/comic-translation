"""Fault injection for inherited pipes and failed process cleanup."""
import os
import io
from pathlib import Path
import queue
import signal
import subprocess
import sys
import threading
import time
from types import SimpleNamespace

import pytest

from src.gui.worker import WorkerMixin
from src.offline import cli_common, model_catalog
from src.offline.models import ModelError
from src.platforms import windows


@pytest.mark.skipif(sys.platform != "win32", reason="Windows inherited pipe handling")
@pytest.mark.parametrize("catalog", [False, True])
def test_cleanup_returns_when_taskkill_fails_and_descendant_holds_stdout(tmp_path, monkeypatch, catalog):
    marker = tmp_path / "descendant.txt"
    script = tmp_path / "stalled.py"
    script.write_text("import subprocess, sys, time\nfrom pathlib import Path\n"
        "child = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(30)'], "
        "stdout=sys.stdout, stderr=sys.stderr)\n"
        "Path(sys.argv[1]).write_text(str(child.pid))\ntime.sleep(30)\n", encoding="utf-8")
    monkeypatch.setattr(windows, "kill_process_tree", lambda pid: None)
    monkeypatch.setattr(cli_common, "platform_support", windows)
    monkeypatch.setattr(model_catalog, "platform_support", windows)
    result = queue.Queue()
    def run():
        try:
            if catalog:
                with model_catalog.catalog_session(sys.executable, [str(script), str(marker)],
                                                   "Test", timeout=.7) as (_, receive):
                    receive(lambda message: True)
            else:
                cli_common.run_cli(sys.executable, [str(script), str(marker)], .7, "Test")
        except BaseException as error:
            result.put(error)
    worker = threading.Thread(target=run, daemon=True)
    started = time.monotonic()
    worker.start()
    try:
        worker.join(timeout=5)
        assert not worker.is_alive(), "cleanup blocked on a pipe still owned by a descendant"
        assert marker.exists(), "the test must create the inherited-pipe descendant"
        assert isinstance(result.get_nowait(), ModelError)
        assert time.monotonic() - started < 5
    finally:
        if marker.exists():
            try:
                os.kill(int(marker.read_text(encoding="utf-8")), signal.SIGTERM)
            except ProcessLookupError:
                pass
        worker.join(timeout=3)


def test_catalog_cleanup_never_waits_without_a_deadline(monkeypatch):
    class Process:
        pid = 123
        stdin = SimpleNamespace(close=lambda: None)
        stdout = io.StringIO()
        def wait(self, timeout=None):
            assert timeout is not None, "cleanup must not use an unbounded wait"
            raise subprocess.TimeoutExpired("fake", timeout)
        def kill(self):
            pass
    monkeypatch.setattr(model_catalog, "popen_cli", lambda *a, **k: Process())
    monkeypatch.setattr(model_catalog.platform_support, "kill_process_tree", lambda pid: None)
    with pytest.raises(ModelError, match="query failed"):
        with model_catalog.catalog_session("fake", [], "Test"):
            raise ModelError("query failed")


def test_worker_emits_done_and_restages_even_when_pipeline_close_fails(monkeypatch):
    from src.gui import worker
    stop = threading.Event()
    stop.set()
    gui = SimpleNamespace(pipeline=object(), stop_requested=stop, pending=queue.Queue(),
                          events=queue.Queue(), runner=object())
    gui.pending.put(("new", [Path("page.png")], {}))
    def fail(pipeline):
        raise OSError("cleanup failed")
    monkeypatch.setattr(worker.platform_support, "finish_pipeline", fail)
    WorkerMixin.work(gui)
    events = list(gui.events.queue)
    assert {"done": True} in events
    assert {"restage": [("new", Path("page.png"), False)]} in events
    assert any("cleanup failed" in event.get("error", "") for event in events)
    assert gui.pipeline is None and gui.runner is None
