"""Compare cached layout against the frozen, uncached pre-refactor algorithm."""
from pathlib import Path
import runpy

import cv2
import numpy as np
from PIL import Image, ImageDraw
import pytest

from src.offline import layout
from src.offline.restoration import decode_mask

OLD = runpy.run_path(str(Path(__file__).parent / "fixtures/layout_before_cache.py"))


def current_metadata(regions):
    # erase_boxes belonged only to the deleted white-balloon renderer.
    return [{key: value for key, value in region.items() if key != "erase_boxes"}
            for region in regions]


def old_windows_prepare(image, detections, seed, line_boxes):
    # The former Windows wrapper completed/refined before invoking the shared
    # routine, which completed again. Keep this separate from the new hook.
    completed = OLD["complete_character_mask"](image, seed, [p for p, _ in detections])
    groups, _ = OLD["find_regions"](image, detections, completed)
    merged = np.zeros(completed.shape, bool)
    for group in groups:
        if len(group["polygons"]) > 1:
            x1, y1, x2, y2 = group["bbox"]
            merged[y1:y2, x1:x2] = True
    gray = np.asarray(image.convert("L"))
    support = np.zeros(gray.shape, np.uint8)
    for polygon, _ in detections:
        cv2.fillPoly(support, [np.asarray(polygon, np.int32)], 1)
    _, labels, stats, _ = cv2.connectedComponentsWithStats(
        (gray < 215).astype(np.uint8), connectivity=8)
    inside = np.bincount(labels[support > 0], minlength=len(stats))
    protected = np.zeros(len(stats), bool)
    limit = max(48, min(image.size) * .09)
    for label, (_, _, width, height, area) in enumerate(stats[1:], 1):
        protected[label] = max(width, height) > limit and inside[label] < area * .92
    preserved = completed & ~protected[labels]
    refined = completed & (~merged | preserved)
    return OLD["prepare_masked_regions"](image, detections, refined, line_boxes)


def page(seed):
    rng = np.random.default_rng(seed)
    width, height = ((180, 240), (500, 600), (720, 960))[seed % 3]
    image = Image.new("RGB", (width, height), "gray")
    draw = ImageDraw.Draw(image)
    draw.rectangle((10, 10, width - 11, height - 11), fill="white", outline="black", width=3)
    draw.line((10, height // 2, width - 11, height // 2), fill="black", width=3)
    detections, lines = [], []
    for index in range(8):
        x = int(rng.integers(15, width - 35))
        y = int(rng.integers(15, height - 65))
        w, h = int(rng.integers(8, 28)), int(rng.integers(12, 55))
        # Include components around both thresholds and disconnected annotation.
        color = (0, 214, 215, 224, 225, 240)[index % 6]
        draw.rectangle((x + 3, y + 3, x + w - 3, y + h - 3), fill=(color,) * 3)
        poly = np.array([[x, y], [x+w, y], [x+w, y+h], [x, y+h]])
        detections.append((poly, float(rng.random())))
        lines.append((x, y, w, h))
    mask = (np.asarray(image.convert("L")) < 225) & (rng.random((height, width)) < .3)
    # Reproduce a learned mask connecting balloons across artwork.
    mask[height//2-4:height//2+5, 20:width-20] = True
    if seed % 5 == 0:
        detections, lines = [], []
    return image, detections, mask, lines


@pytest.mark.parametrize("seed", range(12))
@pytest.mark.parametrize("windows", [False, True])
def test_layout_masks_labels_and_metadata_match_before_refactor(seed, windows):
    from src.platforms.windows_layout import refine_mask
    image, detections, mask, lines = page(seed)
    original = mask.copy()
    expected, old_labels = (old_windows_prepare(image, detections, mask, lines) if windows
                            else OLD["prepare_masked_regions"](image, detections, mask, lines))
    actual, labels = layout.prepare_masked_regions(
        image, detections, mask, lines, refine=refine_mask if windows else None)
    assert np.array_equal(labels, old_labels)
    assert actual == current_metadata(expected)
    for before, after in zip(expected, actual):
        for name in ("erase_mask", "layout_mask", "interior_mask"):
            if name in before:
                assert np.array_equal(decode_mask(before[name], mask.shape),
                                      decode_mask(after[name], mask.shape))
    assert np.array_equal(mask, original)


def test_character_components_are_computed_once_per_page(monkeypatch):
    from src.platforms.windows_layout import refine_mask
    image, detections, mask, lines = page(1)
    calls = []
    original = layout.ink_components
    def components(image):
        calls.append(image)
        return original(image)
    monkeypatch.setattr(layout, "ink_components", components)
    layout.prepare_masked_regions(image, detections, mask, lines, refine=refine_mask)
    assert len(calls) == 1


@pytest.mark.parametrize("windows", [False, True])
@pytest.mark.parametrize("divided", [False, True])
def test_closed_balloon_joint_completion_and_outline_bridge_match(windows, divided):
    from src.platforms.windows_layout import refine_mask
    image = Image.new("RGB", (500, 600), "gray")
    draw = ImageDraw.Draw(image)
    draw.rectangle((30, 40, 180, 300), fill="white", outline="black", width=3)
    if divided:
        draw.line((30, 170, 180, 170), fill="black", width=3)
    draw.rectangle((112, 85, 120, 125), fill="black")
    draw.rectangle((72, 205, 80, 235), fill="black")
    draw.rectangle((92, 155, 95, 160), fill="black")  # annotation between columns
    detections = [(np.array([[100,70],[140,70],[140,140],[100,140]]), .97),
                  (np.array([[65,190],[90,190],[90,250],[65,250]]), .9)]
    mask = np.zeros((600, 500), bool)
    mask[85:126,112:121] = True
    mask[205:236,72:81] = True
    mask[166:175,30:181] = True
    lines = [(112, 85, 9, 41), (72, 205, 9, 31)]
    before, old_labels = (old_windows_prepare(image, detections, mask, lines) if windows
                         else OLD["prepare_masked_regions"](image, detections, mask, lines))
    after, labels = layout.prepare_masked_regions(image, detections, mask, lines,
                                                  refine=refine_mask if windows else None)
    assert any("interior_mask" in region for region in after)
    assert after == current_metadata(before)
    assert np.array_equal(labels, old_labels)
    for old, new in zip(before, after):
        for name in ("erase_mask", "layout_mask", "interior_mask"):
            if name in old:
                assert np.array_equal(decode_mask(old[name], mask.shape),
                                      decode_mask(new[name], mask.shape))
