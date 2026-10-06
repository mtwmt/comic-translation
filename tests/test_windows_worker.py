"""Native Windows stop tests with long local work and a fake CLI descendant."""
import ctypes
import json
import queue
import subprocess
import sys
import threading
import time
from pathlib import Path

import pytest
from PIL import Image

from src.offline.batch import BatchRunner, create_batch
from src.offline.cancellation import OperationCancelled
from src.platforms.windows_worker import WindowsPipeline

pytestmark = pytest.mark.skipif(sys.platform != "win32", reason="Windows worker isolation")


class FakePipeline:
    fingerprint = {"test": "isolated-windows"}

    def __init__(self, models, choice):
        if choice == "slow-start":
            Path(models).write_text("started", encoding="utf-8")
            time.sleep(30)

    def process(self, source, glossary, progress):
        if Path(source).stem == "page2":
            child = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(30)"],
                                     creationflags=subprocess.CREATE_NO_WINDOW)
            progress(f"blocking:{child.pid}")
            time.sleep(30)  # simulate OCR or an unresponsive CLI
        image = Image.new("RGB", (12, 12), "white")
        return image, {"status": "success", "translated": 1, "preserved": 0}, image.convert("L")


def test_stop_kills_current_page_and_cli_keeps_completed_output_and_resumes(tmp_path):
    stop = threading.Event()
    pipeline = WindowsPipeline(tmp_path, "normal", stop, factory=FakePipeline)
    paths = []
    for index in range(1, 4):
        path = tmp_path / f"page{index}.png"
        Image.new("RGB", (12, 12), "white").save(path)
        paths.append(path)
    journal = create_batch(paths, pipeline.fingerprint, {}, state_root=tmp_path / "state")
    child_handle, stopped_at = None, None
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.OpenProcess.restype = ctypes.c_void_p
    kernel32.WaitForSingleObject.argtypes = [ctypes.c_void_p, ctypes.c_ulong]
    kernel32.CloseHandle.argtypes = [ctypes.c_void_p]

    def event(message):
        nonlocal child_handle, stopped_at
        if message.get("stage", "").startswith("blocking:"):
            child_handle = kernel32.OpenProcess(0x100000, False, int(message["stage"].split(":")[1]))
            assert child_handle
            stopped_at = time.monotonic()
            stop.set()

    try:
        summary = BatchRunner(pipeline, event).run(journal)
        elapsed = time.monotonic() - stopped_at
        assert elapsed < 3, elapsed
        assert summary["status"] == "stopped"
        assert summary["counts"] == {"success": 1, "stopped": 1, "waiting": 1}
        assert not pipeline.process_handle.is_alive()
        assert kernel32.WaitForSingleObject(child_handle, 0) == 0  # CLI child exited too
        data = json.loads(journal.read_text(encoding="utf-8"))
        old = Path(data["pages"][0]["output"])
        old_bytes = old.read_bytes()
        assert not Path(data["pages"][1]["output"]).exists()
        assert not Path(data["pages"][1]["report"]).exists()

        class ResumePipeline:
            fingerprint = FakePipeline.fingerprint
            def process(self, source, glossary, progress):
                assert Path(source) != paths[0]  # don't redo the completed page
                image = Image.new("RGB", (12, 12), "black")
                return image, {"status": "success", "translated": 1, "preserved": 0}, image.convert("L")
        assert BatchRunner(ResumePipeline()).run(journal)["counts"] == {"success": 3}
        assert old.read_bytes() == old_bytes
    finally:
        pipeline.close()
        if child_handle:
            kernel32.CloseHandle(child_handle)


def test_stop_during_model_initialization_does_not_wait_for_load(tmp_path):
    marker = tmp_path / "starting.txt"
    stop = threading.Event()
    result = queue.Queue()
    def initialize():
        try:
            WindowsPipeline(marker, "slow-start", stop, factory=FakePipeline)
        except BaseException as error:
            result.put(error)
    worker = threading.Thread(target=initialize)
    worker.start()
    deadline = time.monotonic() + 10
    while not marker.exists() and time.monotonic() < deadline:
        time.sleep(0.02)
    assert marker.exists()
    started = time.monotonic()
    stop.set()
    worker.join(timeout=3)
    assert not worker.is_alive()
    assert time.monotonic() - started < 3
    assert isinstance(result.get_nowait(), OperationCancelled)
