import json
import threading
from pathlib import Path

import numpy as np
import pytest
from PIL import Image, ImageDraw

from src.offline.batch import BatchRunner, create_batch, discover, parse_glossary
from src.offline.layout import find_regions, render_region
from src.offline.models import ModelError


class FakePipeline:
    fingerprint = {"test": 1}

    def __init__(self):
        self.calls = []
        self.behavior = "success"

    def process(self, source, glossary, progress):
        self.calls.append((source, glossary.copy()))
        if source.name.startswith("bad"):
            raise ValueError("bad image")
        if self.behavior == "model-error":
            raise ModelError("missing model")
        image = Image.new("RGB", (30, 40), "white")
        return image, {"status": self.behavior, "translated": 1, "preserved": int(self.behavior == "partial")}, image.convert("L")


def sources(tmp_path, names=("page10.jpg", "page2.png")):
    folder = tmp_path / "input"
    folder.mkdir()
    for name in names:
        Image.new("RGB", (30, 40), "white").save(folder / name)
    return folder


def batch(tmp_path, pipeline, names=("page10.jpg", "page2.png")):
    folder = sources(tmp_path, names)
    journal = create_batch([folder], pipeline.fingerprint, {"両津": "兩津"}, state_root=tmp_path / "state")
    return folder, journal


def load(path):
    return json.loads(path.read_text())


def test_glossary():
    assert parse_glossary("# comment\n両津=兩津\n麗子=麗子") == {"両津": "兩津", "麗子": "麗子"}
    for bad in ("no equals", "=name", "name=", "a=b\na=c"):
        with pytest.raises(ValueError):
            parse_glossary(bad)


def test_discovery_sort_dedup_and_exclusions(tmp_path):
    folder = sources(tmp_path)
    (folder / "translated").mkdir()
    Image.new("RGB", (1, 1)).save(folder / "translated" / "old.png")
    (folder / "link.png").symlink_to(folder / "page2.png")
    (folder / "cycle").symlink_to(folder, target_is_directory=True)
    found = discover([folder, folder / "page2.png"])
    assert [p.name for p, root in found] == ["page2.png", "page10.jpg"]


@pytest.mark.parametrize("location", ["same", "parent", "child"])
def test_custom_output_discovery_keeps_sources_and_excludes_results(tmp_path, location):
    folder = sources(tmp_path)
    output = folder if location == "same" else tmp_path if location == "parent" else folder / "export"
    for kind in ("final", "work"):
        generated = output / "part1" / kind / "old.png"
        generated.parent.mkdir(parents=True, exist_ok=True)
        Image.new("RGB", (1, 1)).save(generated)
    found = discover([folder], output)
    assert [path.name for path, _ in found] == ["page2.png", "page10.jpg"]
    assert len(discover([folder / "page2.png"], output)) == 1


def test_batch_resume_hash_and_preserve_old(tmp_path):
    pipe = FakePipeline()
    folder, journal = batch(tmp_path, pipe)
    result = BatchRunner(pipe).run(journal)
    assert result["counts"] == {"success": 2}
    old = Path(load(journal)["pages"][0]["output"])
    result = BatchRunner(pipe).run(journal)
    assert result["skipped"] == 2
    assert len(pipe.calls) == 2
    Image.new("RGB", (30, 40), "black").save(folder / "page2.png")
    BatchRunner(pipe).run(journal)
    assert len(pipe.calls) == 3
    assert Path(load(journal)["pages"][0]["output"]) != old
    assert old.is_file()


def test_corrupt_output_recomputed(tmp_path):
    pipe = FakePipeline()
    _, journal = batch(tmp_path, pipe)
    BatchRunner(pipe).run(journal)
    output = Path(load(journal)["pages"][0]["output"])
    output.write_bytes(b"corrupt")
    BatchRunner(pipe).run(journal)
    assert len(pipe.calls) == 3
    assert output.read_bytes() == b"corrupt"


def test_bad_page_does_not_stop_batch(tmp_path):
    pipe = FakePipeline()
    _, journal = batch(tmp_path, pipe, ("bad.png", "good.png"))
    result = BatchRunner(pipe).run(journal)
    assert result["counts"] == {"failed": 1, "success": 1}
    BatchRunner(pipe).run(journal)
    assert len(pipe.calls) == 2
    BatchRunner(pipe).run(journal, retry_failed=True)
    assert len(pipe.calls) == 3


def test_model_error_stops_batch(tmp_path):
    pipe = FakePipeline()
    pipe.behavior = "model-error"
    _, journal = batch(tmp_path, pipe)
    assert BatchRunner(pipe).run(journal)["status"] == "stopped"
    assert len(pipe.calls) == 1
    assert load(journal)["pages"][1]["state"] == "waiting"


def test_partial_requires_explicit_retry(tmp_path):
    pipe = FakePipeline()
    pipe.behavior = "partial"
    _, journal = batch(tmp_path, pipe)
    BatchRunner(pipe).run(journal)
    BatchRunner(pipe).run(journal)
    assert len(pipe.calls) == 2
    BatchRunner(pipe).run(journal, retry_partial=True)
    assert len(pipe.calls) == 4


def test_stop_and_resume(tmp_path):
    pipe = FakePipeline()
    _, journal = batch(tmp_path, pipe)
    runner = BatchRunner(pipe)
    runner.on_event = lambda event: runner.stop.set() if "state" in event else None
    assert runner.run(journal)["status"] == "stopped"
    assert len(pipe.calls) == 1
    assert BatchRunner(pipe).run(journal)["counts"] == {"success": 2}
    assert len(pipe.calls) == 2


def test_snapshot_collision_and_effective_config(tmp_path):
    pipe = FakePipeline()
    folder, journal = batch(tmp_path, pipe, ("same.png", "same.jpg"))
    data = load(journal)
    assert len({p["output"] for p in data["pages"]}) == 2
    Image.new("RGB", (5, 5)).save(folder / "late.png")
    BatchRunner(pipe).run(journal)
    assert len(pipe.calls) == 2
    pipe.fingerprint = {"test": 2}
    with pytest.raises(ValueError, match="版本"):
        BatchRunner(pipe).run(journal)


def test_separate_batches_reserve_distinct_outputs(tmp_path):
    pipe = FakePipeline()
    folder, first = batch(tmp_path, pipe)
    second = create_batch([folder], pipe.fingerprint, {}, state_root=tmp_path / "state")
    assert {p["output"] for p in load(first)["pages"]}.isdisjoint({p["output"] for p in load(second)["pages"]})


def test_final_folder_contains_only_composites_and_reports_link_back(tmp_path):
    pipe = FakePipeline()
    folder, journal = batch(tmp_path, pipe)
    BatchRunner(pipe).run(journal)
    final = folder / 'translated' / 'final'
    assert len(list(final.iterdir())) == 2
    assert all(p.suffix == '.png' and not p.name.endswith('.mask.png') for p in final.iterdir())
    for page in load(journal)['pages']:
        assert Path(page['report']).parent.name == 'work'
        assert Path(page['mask']).is_file()
        assert load(Path(page['report']))['output_path'] == page['output']
    assert len(discover([folder])) == 2


def test_progress_counts_completed_and_skipped_pages_without_fake_completion(tmp_path):
    pipe = FakePipeline()
    _, journal = batch(tmp_path, pipe)
    events = []
    runner = BatchRunner(pipe)
    def stop_after_one(event):
        events.append(event)
        if 'state' in event:
            runner.stop.set()
    runner.on_event = stop_after_one
    runner.run(journal)
    assert [e['progress'] for e in events if 'progress' in e] == [0, 1]
    events.clear()
    BatchRunner(pipe, events.append).run(journal)
    assert [e['progress'] for e in events if 'progress' in e] == [0, 1, 2]
    events.clear()
    BatchRunner(pipe, events.append).run(journal)
    assert [e['progress'] for e in events if 'progress' in e] == [0, 1, 2]


def test_closed_balloon_grouping():
    image = Image.new("RGB", (200, 200), "gray")
    ImageDraw.Draw(image).rectangle((40, 40, 100, 100), fill="white", outline="black", width=3)
    polys = [(np.array([[55, 50], [65, 50], [65, 90], [55, 90]]), 0.9),
             (np.array([[75, 50], [85, 50], [85, 90], [75, 90]]), 0.9)]
    regions, labels = find_regions(image, polys)
    assert len(regions) == 1
    assert len(regions[0]["polygons"]) == 2
    assert regions[0]["status"] == "pending"


def test_open_background_is_preserved():
    image = Image.new("RGB", (200, 200), "white")
    regions, _ = find_regions(image, [(np.array([[50, 50], [70, 50], [70, 90], [50, 90]]), .9)])
    assert regions[0]["status"] == "preserved"


def test_pixel_preservation_and_safe_glyphs():
    font = Path(__file__).resolve().parents[1] / "assets/fonts/NotoSansCJKtc-Bold.otf"
    if not font.exists():
        pytest.skip("Bundled font missing")
    image = Image.new("RGB", (400, 400), "gray")
    draw = ImageDraw.Draw(image)
    draw.rectangle((100, 100, 200, 220), fill="white", outline="black", width=3)
    draw.rectangle((125, 125, 145, 170), fill="black")
    regions, labels = find_regions(image, [(np.array([[123, 123], [147, 123], [147, 172], [123, 172]]), .9)])
    regions[0]["translation"] = "你好！"
    output, mask = render_region(image, regions[0], labels, font)
    assert mask.any()
    assert np.array_equal(np.array(image)[~mask], np.array(output)[~mask])
    assert not np.any(mask[labels != regions[0]["label"]])


def test_expanded_folder_subset_retains_original_output_layout(tmp_path):
    folder = tmp_path / "chapter"
    source = folder / "part1" / "page.png"
    source.parent.mkdir(parents=True)
    Image.new("RGB", (20, 20), "white").save(source)
    journal = create_batch([source], {}, {}, state_root=tmp_path / "state", source_roots={source: folder})
    page = json.loads(journal.read_text())["pages"][0]
    assert Path(page["output"]).parent == folder / "translated" / "part1" / "final"
    assert Path(page["report"]).parent == folder / "translated" / "part1" / "work"
