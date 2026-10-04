from copy import deepcopy
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest
from PIL import Image, ImageDraw

from src.offline import pipeline as pipeline_module
from src.offline.layout import find_regions, prepare_masked_regions, render_region, render_masked_region
from src.offline.models import ModelError, sha256
from src.offline.restoration import RestorationModels, decode_mask, encode_mask, verify_restoration_models
from src.offline.review import rerender, save_revision


@pytest.fixture
def font():
    path = Path(__file__).resolve().parents[1] / "assets/fonts/NotoSansCJKtc-Bold.otf"
    if not path.exists():
        pytest.skip("Bundled font missing")
    return path


def test_mask_roundtrip_and_reject_out_of_bounds():
    rng = np.random.default_rng(42)
    for mask in [rng.random((71, 93)) > .8, np.zeros((71, 93), bool), np.ones((71, 93), bool)]:
        assert np.array_equal(decode_mask(encode_mask(mask), mask.shape), mask)
    with pytest.raises(ValueError):
        decode_mask({"box": [0, 0, 2, 2], "runs": [[3, 10]]}, (10, 10))
    with pytest.raises(ValueError):
        decode_mask({"box": [-1, 0, 2, 2], "runs": []}, (10, 10))


def test_high_resolution_balloon_has_readable_font(font):
    image = Image.new("RGB", (3200, 3200), "gray")
    draw = ImageDraw.Draw(image)
    draw.rectangle((800, 800, 1200, 1400), fill="white", outline="black", width=8)
    draw.rectangle((930, 950, 980, 1000), fill="black")
    regions, labels = find_regions(image, [(np.array([[925, 945], [985, 945], [985, 1005], [925, 1005]]), .9)])
    regions[0]["translation"] = "你好！"
    output, mask = render_region(image, regions[0], labels, font)
    assert regions[0]["font_size"] >= 38
    assert mask.any()
    assert np.array_equal(np.asarray(output)[~mask], np.asarray(image)[~mask])


@pytest.mark.parametrize("text", ["アリガトウ！", "オレ？", "ハイ！"])
def test_katakana_dialogue_and_unsafe_text_are_translated(tmp_path, monkeypatch, text):
    calls = []
    monkeypatch.setattr(pipeline_module, "verify_models", lambda *args, **kwargs: "test")
    monkeypatch.setattr(pipeline_module, "version", lambda name: "test")
    monkeypatch.setattr(pipeline_module, "resolve_font", lambda root: (Path(__file__).resolve().parents[1] / "assets/fonts/NotoSansCJKtc-Bold.otf", {"family": "fixture"}))
    monkeypatch.setattr(pipeline_module, "LocalModels", lambda root: SimpleNamespace(
        detect=lambda image: [], recognize=lambda crop: text))
    monkeypatch.setattr(pipeline_module, "find_regions", lambda *args: ([
        {"id": "r1", "bbox": [0, 0, 20, 20], "status": "preserved", "reason": "unsafe artwork"}], None))
    def translate(records, glossary):
        calls.append(records)
        return {"r1": "謝謝！"}
    pipe = pipeline_module.TranslationPipeline(tmp_path, translator=SimpleNamespace(fingerprint={}, translate=translate))
    source = tmp_path / "source.png"
    Image.new("RGB", (20, 20), "white").save(source)
    image, report, mask = pipe.process(source, {})
    assert calls == [[{"id": "r1", "text": text}]]
    assert report["text_translated"] == 1
    assert report["regions"][0]["translation"] == "謝謝！"
    assert report["translated"] == 0 and image is None
    assert not np.asarray(mask).any()
    calls.clear()
    pipe.process(source, {}, analyze_only=True)
    assert not calls


class FakeRestorer:
    fingerprint = {"test": "local-repair"}
    def __init__(self):
        self.calls = 0
    def inpaint(self, image, mask):
        self.calls += 1
        # Deliberately changes all pixels; the compositor must restore them.
        return Image.new("RGB", image.size, (200, 190, 180))


def complex_region():
    rgb = np.full((300, 300, 3), 245, np.uint8)
    rgb[50:250:3, 50:250] = 110
    rgb[100:130, 100:130] = 0
    image = Image.fromarray(rgb)
    mask = np.zeros((300, 300), bool)
    mask[99:131, 99:131] = True
    safe = np.zeros_like(mask)
    safe[85:170, 85:170] = True
    region = {"id": "r1", "bbox": [85, 85, 170, 170], "label": None, "direction": "vertical",
              "erase_mask": encode_mask(mask), "layout_mask": encode_mask(safe),
              "translation": "你好！", "requires_review": True, "status": "pending"}
    return image, region


def test_complex_repair_is_local_and_requires_review(font):
    image, region = complex_region()
    model = FakeRestorer()
    result, changed = render_masked_region(image, region, font, model)
    assert model.calls == 1
    assert region["cleaning"] == "lama" and region["requires_review"]
    assert np.array_equal(np.asarray(image)[~changed], np.asarray(result)[~changed])
    assert changed.sum() < image.width * image.height * .1


def test_shared_size_uses_balloon_space_before_shrinking(font):
    image, region = complex_region()
    region['bbox'] = [98, 98, 132, 155]
    region['font_target'] = 24
    output, changed = render_masked_region(image, region, font, FakeRestorer())
    assert region['font_size'] == 24
    assert np.array_equal(np.asarray(image)[~changed], np.asarray(output)[~changed])


def test_cramped_dialogue_is_flagged_when_below_page_size(font):
    image, region = complex_region()
    image = Image.new('RGB', image.size, 'white')
    region.update(translation='你好！你好！', font_target=36, requires_review=False)
    render_masked_region(image, region, font, FakeRestorer())
    assert region['font_size'] < round(36 * .85)
    assert region['font_size_warning'] and region['requires_review']
    assert region['cleaning'] == 'solid-fill'


def test_short_shouts_do_not_inflate_page_dialogue_size(monkeypatch):
    from src.offline import layout
    image, example = complex_region()
    regions = []
    for text, fitted in [('這是一段普通的對話內容。', 18), ('另外一段普通的對話內容。', 20),
                         ('啊！', 35), ('混蛋！', 35), ('等等！', 35)]:
        region = deepcopy(example)
        region.update(translation=text, sample_size=fitted)
        regions.append(region)
    disabled = deepcopy(example)
    disabled.update(enabled=False, translation='這段停用的對話不應影響字級。', sample_size=80)
    regions.append(disabled)
    monkeypatch.setattr(layout, 'fit_region_lettering',
                        lambda size, region, font, safe: (None, region['sample_size'], []))
    plan = layout.plan_page_lettering(image, regions, None)
    assert plan['dialogue_size'] == 19
    assert [r['font_target'] for r in regions[:2]] == [19, 19]
    assert [r['font_target'] for r in regions[2:5]] == [23, 23, 23]
    assert 'font_target' not in disabled


def test_unfittable_text_never_calls_inpainting(font):
    image, region = complex_region()
    region["translation"] = "很長的譯文" * 150
    model = FakeRestorer()
    original = np.asarray(image).copy()
    with pytest.raises(ValueError, match="字級"):
        render_masked_region(image, region, font, model)
    assert model.calls == 0
    assert np.array_equal(np.asarray(image), original)


def test_oversized_mask_cannot_authorize_erasing_art(font):
    image, region = complex_region()
    region["erase_mask"] = encode_mask(np.ones((300, 300), bool))
    model = FakeRestorer()
    with pytest.raises(ValueError, match="超出"):
        render_masked_region(image, region, font, model)
    assert model.calls == 0


def test_solid_background_does_not_need_lama(font):
    image = Image.new("RGB", (400, 400), "gray")
    draw = ImageDraw.Draw(image)
    draw.rectangle((100, 100, 230, 250), fill="white", outline="black", width=3)
    draw.rectangle((145, 140, 165, 180), fill="black")
    mask = np.zeros((400, 400), bool)
    mask[139:182, 144:167] = True
    detections = [(np.array([[140, 135], [170, 135], [170, 185], [140, 185]]), .9)]
    regions, _ = prepare_masked_regions(image, detections, mask)
    regions[0]["translation"] = "你好！"
    model = FakeRestorer()
    result, changed = render_masked_region(image, regions[0], font, model)
    assert model.calls == 0 and regions[0]["cleaning"] == "solid-fill"
    assert np.array_equal(np.asarray(result)[~changed], np.asarray(image)[~changed])


def test_revision_starts_from_original_and_preserves_old_files(tmp_path, font, monkeypatch):
    monkeypatch.setattr("src.offline.review.resolve_font", lambda root: (font, {"family": "fixture"}))
    image, region = complex_region()
    source = tmp_path / "source.png"
    image.save(source)
    report = {"source": str(source), "source_hash": sha256(source), "image_size": list(image.size),
              "fingerprint": {"restoration": FakeRestorer.fingerprint}, "regions": [region]}
    model = FakeRestorer()
    models = font.parents[1]
    output, revised, mask = rerender(report, models, model)
    assert revised["translated"] == 1 and revised["status"] == "partial"
    assert report["regions"][0]["status"] == "pending"
    path = save_revision(tmp_path / "report.json", output, revised, mask)
    saved = path.with_suffix(".png").read_bytes()
    revised["regions"][0]["enabled"] = False
    restored, disabled, _ = rerender(revised, models, model)
    assert np.array_equal(np.asarray(restored), np.asarray(image))
    assert disabled["translated"] == 0
    assert path.with_suffix(".png").read_bytes() == saved
    source.write_bytes(b"changed")
    with pytest.raises(ValueError, match="改變"):
        rerender(report, models, model)


@pytest.mark.parametrize('folders', [('final', 'work'), ('成品', '工作資料')])
def test_revision_keeps_png_separate_from_work_files(tmp_path, font, monkeypatch, folders):
    import json
    monkeypatch.setattr("src.offline.review.resolve_font", lambda root: (font, {"family": "fixture"}))
    image, region = complex_region()
    source = tmp_path / 'source.png'
    image.save(source)
    final, metadata = (tmp_path / name for name in folders)
    final.mkdir()
    metadata.mkdir()
    report = {'source': str(source), 'source_hash': sha256(source), 'image_size': list(image.size),
              'fingerprint': {'restoration': FakeRestorer.fingerprint}, 'regions': [region],
              'output_path': str(final / 'page.png'), 'metadata_dir': str(metadata)}
    output, revised, mask = rerender(report, font.parents[1], FakeRestorer())
    path = save_revision(metadata / 'page.json', output, revised, mask)
    saved = json.loads(path.read_text())
    assert path.parent == metadata
    assert Path(saved['output_path']).parent == final
    assert Path(saved['output_path']).name == 'source_zh-TW_revised.png'
    assert [p.suffix for p in final.iterdir()] == ['.png']
    assert path.with_name(path.stem + '.mask.png').is_file()


def test_missing_repair_models_fail_without_downloading(tmp_path, monkeypatch):
    import urllib.request
    monkeypatch.setattr(urllib.request, "urlopen", lambda *args: pytest.fail("Inference must not download"))
    with pytest.raises(ModelError, match="prepare-restoration"):
        verify_restoration_models(tmp_path)


def test_detector_recovers_missed_lines_and_protects_panel_rule():
    image = Image.new("RGB", (100, 100), "white")
    ImageDraw.Draw(image).line((0, 10, 99, 10), fill="black", width=2)
    block = np.array([[[300, 300, 500, 500, .99, 0, .99]]], dtype=np.float32)
    seg = np.zeros((1, 1, 1024, 1024), np.float32)
    seg[0, 0, 90:300, 180:250] = 1
    seg[0, 0, 300:700, 700:760] = 1
    lines = np.zeros((1, 2, 1024, 1024), np.float32)
    lines[0, 0, 290:710, 690:770] = 1
    model = RestorationModels.__new__(RestorationModels)
    model.detector = SimpleNamespace(setInput=lambda value: None, getUnconnectedOutLayersNames=lambda: [],
                                     forward=lambda names: [lines, block, seg])
    detections, mask, line_boxes = model.detect(image)
    assert len(detections) == 2
    assert mask[35:65, 70:75].any()
    assert not mask[10:12].any()


def test_wide_block_of_vertical_lines_keeps_vertical_layout():
    image = Image.new("RGB", (400, 400), "gray")
    ImageDraw.Draw(image).rectangle((100, 100, 260, 180), fill="white", outline="black", width=3)
    mask = np.zeros((400, 400), bool)
    mask[120:160, 140:145] = True
    detections = [(np.array([[120, 115], [240, 115], [240, 165], [120, 165]]), .9)]
    regions, _ = prepare_masked_regions(image, detections, mask, [(130, 120, 10, 40), (160, 120, 10, 40)])
    assert regions[0]["direction"] == "vertical"


def test_enhanced_pipeline_retains_pixel_invariant(tmp_path, monkeypatch, font):
    import src.offline.restoration as restoration_module
    image = Image.new("RGB", (400, 400), "gray")
    draw = ImageDraw.Draw(image)
    draw.rectangle((100, 100, 230, 250), fill="white", outline="black", width=3)
    draw.rectangle((145, 140, 165, 180), fill="black")
    mask = np.zeros((400, 400), bool)
    mask[139:182, 144:167] = True
    detections = [(np.array([[140, 135], [170, 135], [170, 185], [140, 185]]), .9)]
    restorer = FakeRestorer()
    restorer.detect = lambda im: (detections, mask, [(145, 140, 20, 40)])
    monkeypatch.setattr(restoration_module, "RestorationModels", lambda root: restorer)
    monkeypatch.setattr(pipeline_module, "verify_models", lambda *args, **kwargs: "test")
    monkeypatch.setattr(pipeline_module, "version", lambda name: "test")
    monkeypatch.setattr(pipeline_module, "resolve_font", lambda root: (Path(__file__).resolve().parents[1] / "assets/fonts/NotoSansCJKtc-Bold.otf", {"family": "fixture"}))
    monkeypatch.setattr(pipeline_module, "LocalModels", lambda root: SimpleNamespace(recognize=lambda crop: "ハイ！", detect=lambda im, **options: []))
    translator = SimpleNamespace(fingerprint={"provider": "fixture"}, translate=lambda records, glossary: {"r001": "你好！"})
    pipe = pipeline_module.TranslationPipeline(font.parents[1], translator, restoration="enhanced")
    source = tmp_path / "source.png"
    image.save(source)
    result, report, changed = pipe.process(source, {})
    assert report["translated"] == 1
    assert report["regions"][0]["original"] == "ハイ！"
    assert report["regions"][0]["cleaning"] == "solid-fill"
    assert np.array_equal(np.asarray(result)[np.asarray(changed) == 0], np.asarray(image)[np.asarray(changed) == 0])


def test_gap_filling_guess_that_reads_as_nothing_is_dropped(tmp_path, monkeypatch, font):
    import src.offline.restoration as restoration_module
    image = Image.new("RGB", (400, 400), "gray")
    draw = ImageDraw.Draw(image)
    draw.rectangle((100, 100, 230, 250), fill="white", outline="black", width=3)
    draw.rectangle((145, 140, 165, 180), fill="black")
    draw.rectangle((300, 300, 345, 380), fill="black")  # a lone glyph the main detector missed
    mask = np.zeros((400, 400), bool)
    mask[139:182, 144:167] = True
    detections = [(np.array([[140, 135], [170, 135], [170, 185], [140, 185]]), .9)]
    restorer = FakeRestorer()
    restorer.detect = lambda im: (detections, mask, [(145, 140, 20, 40)])
    monkeypatch.setattr(restoration_module, "RestorationModels", lambda root: restorer)
    monkeypatch.setattr(pipeline_module, "verify_models", lambda *args, **kwargs: "test")
    monkeypatch.setattr(pipeline_module, "version", lambda name: "test")
    monkeypatch.setattr(pipeline_module, "resolve_font", lambda root: (Path(__file__).resolve().parents[1] / "assets/fonts/NotoSansCJKtc-Bold.otf", {"family": "fixture"}))
    extra = [(np.array([[295, 295], [350, 295], [350, 385], [295, 385]]), .8)]
    monkeypatch.setattr(pipeline_module, "LocalModels", lambda root: SimpleNamespace(
        recognize=lambda crop: "ハイ！" if crop.width < 60 and crop.height < 70 and crop.width > 30 and crop.height > 40 and crop.getpixel((15, 15)) != (0, 0, 0) and crop.size[0] != 49 else "．．．",
        detect=lambda im, **options: extra))
    translator = SimpleNamespace(fingerprint={"provider": "fixture"}, translate=lambda records, glossary: {r["id"]: "你好！" for r in records})
    pipe = pipeline_module.TranslationPipeline(font.parents[1], translator, restoration="enhanced")
    source = tmp_path / "source.png"
    image.save(source)
    _, report, _ = pipe.process(source, {}, analyze_only=True)
    assert [r["id"] for r in report["regions"]] == ["r001"]
    assert not any(r.get("recovered") for r in report["regions"])
