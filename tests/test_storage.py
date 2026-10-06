"""Output failure/concurrency checks shared by reports, jobs and revision."""
from concurrent.futures import ThreadPoolExecutor
import json
import threading

import pytest
from PIL import Image, UnidentifiedImageError

from src.offline import storage


@pytest.mark.parametrize("kind", ["json", "png"])
def test_replace_failure_preserves_previous_output_and_cleans_temp(tmp_path, monkeypatch, kind):
    path = tmp_path / f"output.{kind}"
    previous = b"previous result"
    path.write_bytes(previous)

    def fail_replace(*args):
        raise OSError("disk failure")

    monkeypatch.setattr(storage.os, "replace", fail_replace)
    with pytest.raises(OSError, match="disk failure"):
        if kind == "json":
            storage.atomic_json(path, {"message": "繁體中文"})
        else:
            storage.save_png(path, Image.new("RGB", (10, 10)))
    assert path.read_bytes() == previous
    assert list(tmp_path.iterdir()) == [path]


def test_concurrent_json_writers_publish_complete_independent_files(tmp_path, monkeypatch):
    path = tmp_path / "settings.json"
    barrier = threading.Barrier(2)
    replace = storage.os.replace
    temporaries = []

    def simultaneous_replace(source, target):
        if source not in temporaries:  # a retried replace must not wait again
            temporaries.append(source)
            barrier.wait(timeout=5)
        replace(source, target)

    monkeypatch.setattr(storage.os, "replace", simultaneous_replace)
    payloads = [{"name": "繁體中文", "data": "a" * 10000}, {"name": "另一次保存", "data": "b" * 10000}]
    with ThreadPoolExecutor(max_workers=2) as workers:
        list(workers.map(lambda payload: storage.atomic_json(path, payload), payloads))
    assert len(set(temporaries)) == 2
    assert json.loads(path.read_text(encoding="utf-8")) in payloads
    assert list(tmp_path.iterdir()) == [path]


def test_invalid_png_is_not_published(tmp_path):
    path = tmp_path / "output.png"
    Image.new("RGB", (10, 10), "white").save(path)
    previous = path.read_bytes()

    class InvalidImage:
        def save(self, stream, format):
            stream.write(b"invalid PNG")

    with pytest.raises(UnidentifiedImageError):
        storage.save_png(path, InvalidImage())
    assert path.read_bytes() == previous
    assert list(tmp_path.iterdir()) == [path]


def test_permission_retry_publishes_once_and_uses_bounded_backoff(tmp_path, monkeypatch):
    path = tmp_path / "settings.json"
    replace = storage.os.replace
    calls, delays = [], []
    def transient(source, target):
        calls.append((source, target))
        if len(calls) < 3:
            raise PermissionError("sharing violation")
        return replace(source, target)
    monkeypatch.setattr(storage.os, "replace", transient)
    monkeypatch.setattr(storage.time, "sleep", delays.append)
    storage.atomic_json(path, {"message": "繁體中文"})
    assert len(calls) == 3 and delays == [.01, .02]
    assert json.loads(path.read_text(encoding="utf-8")) == {"message": "繁體中文"}
    assert list(tmp_path.iterdir()) == [path]


def test_permanent_permission_failure_is_bounded_and_keeps_old_file(tmp_path, monkeypatch):
    path = tmp_path / "settings.json"
    path.write_bytes(b"previous")
    calls, delays = [], []
    def denied(source, target):
        calls.append((source, target))
        raise PermissionError("permission denied")
    monkeypatch.setattr(storage.os, "replace", denied)
    monkeypatch.setattr(storage.time, "sleep", delays.append)
    with pytest.raises(PermissionError, match="permission denied"):
        storage.atomic_json(path, {"new": True})
    assert len(calls) == 6 and sum(delays) == pytest.approx(.38)
    assert path.read_bytes() == b"previous"
    assert list(tmp_path.iterdir()) == [path]
