"""Regression: a text mask must not join a balloon to a neighboring sign."""
import numpy as np
from PIL import Image, ImageDraw

from src.offline.layout import prepare_masked_regions
from src.offline.restoration import decode_mask
from src.platforms import macos, windows, windows_layout


def box(x1, y1, x2, y2):
    return np.array([[x1, y1], [x2, y1], [x2, y2], [x1, y2]])


def divided_page():
    image = Image.new("RGB", (500, 600), "gray")
    draw = ImageDraw.Draw(image)
    draw.rectangle((30, 40, 180, 300), fill="white", outline="black", width=3)
    draw.line((30, 170, 180, 170), fill="black", width=3)
    draw.rectangle((112, 85, 120, 125), fill="black")
    draw.rectangle((117, 205, 125, 235), fill="black")
    detections = [(box(100, 70, 140, 140), .97), (box(105, 190, 145, 250), .53)]
    mask = np.zeros((600, 500), bool)
    mask[85:126, 112:121] = True
    mask[205:236, 117:126] = True
    mask[166:175, 113:135] = True  # learned mask mistakenly bridges the outline
    return image, detections, mask


def test_windows_keeps_balloon_and_sign_separate_and_protects_outline():
    image, detections, mask = divided_page()
    original = mask.copy()
    old, _ = prepare_masked_regions(image, detections, mask)
    regions, _ = prepare_masked_regions(image, detections, mask, refine=windows_layout.refine_mask)
    assert len(old) == 1  # reproduces the previous/macOS grouping behavior
    assert len(regions) == 2
    assert sorted(region["bbox"] for region in regions) == [[100, 70, 141, 141], [105, 190, 146, 251]]
    assert all(len(region["polygons"]) == 1 for region in regions)
    assert all(not decode_mask(region["erase_mask"], mask.shape)[169:172, 30:181].any()
               for region in regions)
    assert np.array_equal(mask, original)


def test_multiple_columns_in_one_balloon_still_group_together():
    image, _, mask = divided_page()
    detections = [(box(100, 70, 125, 140), .97), (box(65, 70, 90, 140), .9)]
    draw = ImageDraw.Draw(image)
    draw.rectangle((72, 85, 80, 125), fill="black")
    mask[85:126, 72:81] = True
    regions, _ = prepare_masked_regions(image, detections, mask, refine=windows_layout.refine_mask)
    assert len(regions) == 1
    assert len(regions[0]["polygons"]) == 2


def test_large_ink_contained_in_text_footprint_is_not_removed():
    image = Image.new("RGB", (300, 400), "white")
    ImageDraw.Draw(image).rectangle((100, 80, 120, 210), fill="black")
    mask = np.zeros((400, 300), bool)
    mask[80:211, 100:121] = True
    cleaned = windows_layout.preserve_boundaries(image, [(box(95, 75, 125, 215), .9)], mask)
    assert np.array_equal(cleaned, mask)


def test_windows_factory_enables_correction_and_macos_keeps_default(monkeypatch):
    from src.offline import pipeline
    calls = []
    monkeypatch.setattr(pipeline, "TranslationPipeline", lambda *args, **kwargs: calls.append(kwargs))
    windows.create_local_pipeline("models")
    macos.create_local_pipeline("models")
    assert calls[0]["region_layout"] is windows_layout
    assert calls[1] == {"translator": None}


def test_windows_gui_worker_uses_windows_local_factory(monkeypatch):
    from src.platforms import windows_worker
    from src.offline import translators
    sentinel = object()
    monkeypatch.setattr(translators, "create_translator", lambda *choice: sentinel)
    monkeypatch.setattr(windows, "create_local_pipeline", lambda models, **kw: (models, kw))
    assert windows_worker._create_pipeline("models", ("agy", "model")) == (
        "models", {"translator": sentinel})


def test_windows_worker_forwards_generation_settings(monkeypatch):
    from src.platforms import windows_worker
    from src.offline import translators
    calls = []
    monkeypatch.setattr(translators, "create_translator", lambda *choice: calls.append(choice))
    monkeypatch.setattr(windows, "create_local_pipeline", lambda *args, **kwargs: None)
    choice = ("codex", "gpt-6.1-sol", 180, {"effort": "high", "fast": True})
    windows_worker._create_pipeline("models", choice)
    assert calls == [choice]


def test_duplicate_artwork_guess_excluded_but_nearby_dialogue_kept():
    large = dict(id='r011', bbox=[765,1185,1282,1607], label=None, status='pending', original='なんなんだよーっ！！')
    small = dict(id='r012', bbox=[1149,1162,1235,1354], label=None, status='pending', original='なんなんだよーーっ！！')
    dialogue = dict(id='r013', bbox=[572,1182,779,1399], label=547, status='pending', original='ぼく、まい子でち。')
    regions = [large, small, dialogue]
    windows_layout.resolve_duplicate_regions(regions)
    assert large['enabled'] is False and large['duplicate_of'] == 'r012'
    assert small['status'] == dialogue['status'] == 'pending'
    assert not any('enabled' in r for r in [small,dialogue])


def test_repeated_separate_dialogue_and_explicit_review_choices_not_excluded():
    from copy import deepcopy
    large = dict(id='large', bbox=[100,100,300,300], label=None, original='なんなんだよっ', status='pending')
    small = dict(id='small', bbox=[250,100,280,250], label=None, original='なんなんだよっ', status='pending')
    for edits in ({'manual': True}, {'font_size_override': 20}, {'mask_edited': True}, {'enabled': True}):
        candidate = {**deepcopy(large), **edits}
        windows_layout.resolve_duplicate_regions([candidate, deepcopy(small)], revision=True)
        assert 'duplicate_of' not in candidate
    separate = {**small, 'bbox': [350,100,380,250]}
    windows_layout.resolve_duplicate_regions([large, separate])
    assert 'duplicate_of' not in large
