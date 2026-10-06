"""Synthetic orchestration checks, not translation-quality or model stress tests."""
import json

from PIL import Image

from src.offline.batch import BatchRunner, create_batch


def test_100_synthetic_pages_and_resume(tmp_path):
    source = tmp_path / "input"
    source.mkdir()
    for index in range(1, 101):
        Image.new("RGB", (8, 8), (index, index, index)).save(source / f"page{index}.png")

    class Pipeline:
        fingerprint = {"synthetic": 1}
        calls = 0

        def process(self, path, glossary, progress):
            self.calls += 1
            with Image.open(path) as decoded:
                image = decoded.copy()
            return image, {"status": "success", "translated": 1, "preserved": 0}, image.convert("L")

    pipeline = Pipeline()
    journal = create_batch([source], pipeline.fingerprint, {}, state_root=tmp_path / "state")
    runner = BatchRunner(pipeline)
    result = runner.run(journal)
    assert result["counts"] == {"success": 100}
    assert pipeline.calls == 100
    assert BatchRunner(pipeline).run(journal)["skipped"] == 100
    assert pipeline.calls == 100
    data = json.loads(journal.read_text(encoding="utf-8"))
    assert [p["source"].split("page")[-1] for p in data["pages"]] == [f"{i}.png" for i in range(1, 101)]
