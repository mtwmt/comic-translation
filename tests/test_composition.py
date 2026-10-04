import numpy as np
from PIL import Image

from src.offline.composition import render_page


def test_failed_and_overlapping_regions_preserve_source_and_first_result():
    original = Image.new("RGB", (10, 10), "white")
    regions = [{"id": name, "status": "pending", "translation": "譯文"}
               for name in ("first", "overlap", "error")]

    def render(region):
        if region["id"] == "error":
            raise ValueError("cannot fit")
        mask = np.zeros((10, 10), bool)
        mask[2:5, 2:5] = True
        # Deliberately changes the whole page, beyond its authorized mask.
        return Image.new("RGB", original.size, "black" if region["id"] == "first" else "red"), mask

    result, summary, mask = render_page(original, regions, render)
    changed = np.asarray(mask) != 0
    assert np.array_equal(np.asarray(result)[~changed], np.asarray(original)[~changed])
    assert (np.asarray(result)[changed] == 0).all()
    assert regions[1]["status"] == regions[2]["status"] == "preserved"
    assert "重疊" in regions[1]["reason"] and regions[2]["reason"] == "cannot fit"
    assert summary["status"] == "partial" and summary["translated"] == 1


def test_revision_retries_preserved_regions_but_honors_disabled_and_missing_text():
    original = Image.new("RGB", (10, 10), "white")
    regions = [{"id": "edited", "status": "preserved", "translation": "譯文", "requires_review": True},
               {"id": "disabled", "status": "translated", "translation": "不要套用", "enabled": False},
               {"id": "empty", "status": "translated", "translation": ""}]
    calls = []

    def render(region):
        calls.append(region["id"])
        mask = np.zeros((10, 10), bool)
        mask[2, 2] = True
        return Image.new("RGB", original.size, "black"), mask

    _, summary, _ = render_page(original, regions, render, retry_preserved=True,
                                missing_reason="尚未填寫譯文", text_status="edited")
    assert calls == ["edited"]
    assert regions[0]["text_status"] == "edited"
    assert regions[1]["reason"] == "使用者保留原文"
    assert regions[2]["reason"] == "尚未填寫譯文"
    assert summary["review_required"] == 1 and summary["status"] == "partial"


def test_analysis_without_translations_does_not_invoke_renderer():
    def render(region):
        raise AssertionError("analysis must not render")

    region = {"status": "pending"}
    result, summary, mask = render_page(Image.new("RGB", (10, 10), "white"), [region], render)
    assert summary["status"] == "failed" and summary["translated"] == 0
    assert not np.asarray(mask).any() and result.getpixel((0, 0)) == (255, 255, 255)
