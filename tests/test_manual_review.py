from copy import deepcopy
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest
from PIL import Image, ImageDraw

from src.offline.manual_review import manual_region, recognize_manual_region, translate_region
from src.offline.restoration import decode_mask
from src.offline.review import load_source, rerender, save_revision
from src.offline.models import sha256


def sample():
    image = Image.new('RGB', (500, 600), 'white')
    draw = ImageDraw.Draw(image)
    draw.rectangle((125, 130, 150, 155), fill='black')
    draw.rectangle((125, 170, 150, 195), fill='black')
    # An illustration stroke extends across the selection edge.
    draw.line((180, 50, 180, 160), fill='black', width=3)
    return image


def test_manual_mask_preserves_boundary_art_and_handles_reverse_drag():
    image = sample()
    region = manual_region(image, (210, 230, 100, 100), [{'id': 'r002', 'bbox': [0, 0, 30, 30]}], {'クリボン': '栗邦邦'})
    assert region['bbox'] == [100, 100, 210, 230]
    assert region['id'] == 'r001'
    assert region['protected_terms'] == ['栗邦邦']
    mask = decode_mask(region['erase_mask'], (600, 500))
    safe = decode_mask(region['layout_mask'], mask.shape)
    assert mask[140, 140] and mask[180, 140]
    assert not mask[100:160, 180].any()
    assert not safe[100:160, 180].any()
    assert not mask[:100].any() and not mask[:, :100].any()


@pytest.mark.parametrize('box, message', [((100,100,104,120),'太小'), ((0,0,500,600),'15%'), ((110,110,180,200),'重疊')])
def test_invalid_box_leaves_existing_regions_unchanged(box, message):
    regions = [{'id': 'r009', 'bbox': [100,100,200,220], 'translation': '已完成'}]
    before = deepcopy(regions)
    with pytest.raises(ValueError, match=message):
        manual_region(sample(), box, regions, {})
    assert regions == before


def test_ocr_failure_keeps_editable_region_and_only_crops_selected_area():
    image = sample()
    region = manual_region(image, [100,100,210,230], [], {})
    def fail(crop):
        assert crop.size == (110,130)
        raise RuntimeError('OCR unavailable')
    result = recognize_manual_region(image, region, SimpleNamespace(recognize=fail))
    assert result['original'] == '' and result['manual']
    assert '手動填寫' in result['reason']
    result = recognize_manual_region(image, region, SimpleNamespace(recognize=lambda _: 'おまたせ！'))
    calls = []
    def translate(records, glossary):
        calls.append((records, glossary))
        return {region['id']: '久等了！'}
    assert translate_region(result, {'クリボン':'栗邦邦'}, SimpleNamespace(translate=translate)) == '久等了！'
    assert calls == [([{'id': region['id'], 'text': 'おまたせ！'}], {'クリボン':'栗邦邦'})]
    result['original'] = ''
    with pytest.raises(ValueError, match='原文'):
        translate_region(result, {}, SimpleNamespace(translate=translate))
    assert len(calls) == 1


def test_manual_region_render_save_reload_preserves_pixels_outside_box(tmp_path, monkeypatch):
    image = sample()
    source = tmp_path / 'source.png'
    image.save(source)
    region = manual_region(image, [100,100,210,230], [], {})
    region.update(original='おまたせ！', translation='久等了！')
    font = Path(__file__).resolve().parents[1] / 'assets/fonts/NotoSansCJKtc-Bold.otf'
    monkeypatch.setattr('src.offline.review.resolve_font', lambda: (font, {'family': 'test'}))
    report = {'source': str(source), 'source_hash': sha256(source), 'image_size': list(image.size),
              'fingerprint': {'restoration': 'test'}, 'regions': [region], 'glossary': {}}
    restorer = SimpleNamespace(fingerprint='test', inpaint=lambda im, mask: Image.new('RGB', im.size, 'white'))
    rendered, updated, changed = rerender(report, tmp_path, restorer)
    assert updated['translated'] == 1
    assert updated['review_required'] == 1
    mask = np.asarray(changed) > 0
    assert not mask[:100].any() and not mask[230:].any()
    assert not mask[:, :100].any() and not mask[:,210:].any()
    assert not mask[100:160,180].any()
    assert np.array_equal(np.asarray(image)[~mask], np.asarray(rendered)[~mask])
    path = save_revision(tmp_path/'report.json', rendered, updated, changed)
    import json
    saved = json.loads(path.read_text(encoding="utf-8"))
    assert saved['regions'][0]['manual']
    assert load_source(saved).size == image.size
    assert Path(saved['output_path']).exists()
    assert np.array_equal(np.asarray(Image.open(source)), np.asarray(image))


def test_resize_rebuilds_masks_but_preserves_text_identity_and_other_regions():
    from src.offline.manual_review import resize_manual_region
    image = sample()
    region = manual_region(image, [100,100,210,230], [], {})
    region.update(original='手動更正', translation='久等了', direction='horizontal', enabled=False,
                  mask_edited=True, font_size=30, layout_lines=['舊排版'])
    before = deepcopy(region)
    resized = resize_manual_region(image, region, [110,110,165,210], [region], {})
    assert region == before
    for key in ('id','original','translation','direction','enabled'):
        assert resized[key] == before[key]
    assert resized['bbox'] == [110,110,165,210]
    assert 'layout_lines' not in resized and 'font_size' not in resized
    mask = decode_mask(resized['erase_mask'], (600,500))
    assert mask[140,140]
    assert not mask[:110].any() and not mask[:,165:].any()
    assert resized['requires_review'] and not resized['mask_edited']
    other = {'id':'r999', 'bbox':[215,100,260,240]}
    with pytest.raises(ValueError, match='重疊'):
        resize_manual_region(image, region, [100,100,240,230], [region,other], {})
    assert region == before


def test_white_cleanup_removes_faint_ink_but_preserves_border_and_brush_exclusions():
    from src.offline.manual_review import strengthen_white_cleaning
    from src.offline.layout import render_masked_region
    from src.offline.restoration import encode_mask
    image = sample()
    draw = ImageDraw.Draw(image)
    draw.rectangle((110,200,160,210), fill=(240,240,240))
    # Faint scan noise joins the dark character to an outline: it must not
    # make the whole character a protected border component.
    draw.line((150,140,180,140), fill=(250,250,250))
    old = manual_region(image,[100,100,210,230],[],{})
    assert not decode_mask(old['erase_mask'],(600,500))[205,120]
    region = strengthen_white_cleaning(image,old,[old],{})
    mask = decode_mask(region['erase_mask'],(600,500))
    assert mask[205,120] and mask[135,135]
    assert not mask[120,180]
    # Deliberately protect one speck with the removal brush.
    mask[205,120] = False
    region.update(translation='你好', font_size_override=30, erase_mask=encode_mask(mask), mask_edited=True)
    font = Path(__file__).resolve().parents[1]/'assets/fonts/NotoSansCJKtc-Bold.otf'
    out,changed = render_masked_region(image,region,font,None)
    assert out.getpixel((120,205)) == (240,240,240)
    assert out.getpixel((125,205)) == (255,255,255)
    assert out.getpixel((180,120)) == image.getpixel((180,120))
    assert np.array_equal(np.asarray(out)[~changed],np.asarray(image)[~changed])
    assert region['font_size'] == 30 and region['cleaning'] == 'white-fill'


def test_exact_font_override_survives_page_planning_and_rejects_oversize():
    from src.offline.layout import plan_page_lettering, render_masked_region
    image = Image.new('RGB',(800,800),'white')
    ImageDraw.Draw(image).rectangle((100,100,130,130),fill='black')
    region = manual_region(image,[80,80,300,410],[],{})
    region.update(translation='久等了！', font_size_override=64)
    font = Path(__file__).resolve().parents[1]/'assets/fonts/NotoSansCJKtc-Bold.otf'
    normal = deepcopy(region)
    normal.update(id='r002', font_size_override=0)
    plan_page_lettering(image,[region,normal],font)
    assert region['font_size_override'] == 64 and 'font_target' not in region
    render_masked_region(image,region,font,None)
    assert region['font_size'] == 64
    region['font_size_override'] = 512
    render_masked_region(image,region,font,None)
    assert 12 <= region['font_size'] < 512
    assert region['font_size_override'] == 512
    assert '已縮小至' in region['font_size_warning']


def test_ocr_candidates_try_plain_cleaned_and_column_reads():
    from src.offline.manual_review import ocr_candidates
    from src.offline.restoration import encode_mask
    pixels = np.full((200, 200, 3), 255, np.uint8)
    pixels[40:160, 40:70] = 0     # left column
    pixels[40:160, 120:150] = 0   # right column
    mask = np.zeros((200, 200), bool)
    mask[40:160, 40:70] = mask[40:160, 120:150] = True
    region = {"bbox": [30, 30, 160, 170], "direction": "vertical", "erase_mask": encode_mask(mask)}
    seen = []

    class Recognizer:
        def recognize(self, crop):
            seen.append(crop.size)
            return {1: "あ", 2: "い"}.get(len(seen), "うえ") if crop.width < 100 else "全体"

    found = ocr_candidates(Image.fromarray(pixels), region, Recognizer())
    assert found[0] == "全体" and len(found) >= 2 and len(set(found)) == len(found)
    assert len(seen) == 4  # plain, cleaned, and two columns
