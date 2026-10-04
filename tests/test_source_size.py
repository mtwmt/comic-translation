from copy import deepcopy
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw

from src.offline.layout import fit_region_lettering, plan_page_lettering, render_masked_region
from src.offline.manual_review import manual_region
from src.offline.restoration import decode_mask
from src.offline.source_size import estimate_source_font_size

FONT = Path(__file__).resolve().parents[1]/'assets/fonts/NotoSansCJKtc-Bold.otf'


def source_page():
    im = Image.new('RGB',(1000,1000),'white')
    draw = ImageDraw.Draw(im)
    for y in (95,140,185):
        draw.rectangle((100,y,123,y+23),fill='black')
        draw.rectangle((500,y*2-100,571,y*2-29),fill='black')
    for y in range(100,200,8):
        draw.rectangle((133,y,138,y+5),fill='black')
    # Outline and neighbouring artwork must not affect the type estimate.
    draw.line((60,50,60,430),fill='black',width=4)
    normal = manual_region(im,[60,60,220,390],[],{})
    large = manual_region(im,[400,60,720,450],[normal],{})
    normal.update(original='あいう',translation='你好！')
    large.update(original='あいう',translation='你好！')
    return im,normal,large


def test_estimate_excludes_furigana_and_respects_source_scale():
    im,normal,large = source_page()
    assert estimate_source_font_size(im,normal) == 27
    assert estimate_source_font_size(im,large) == 80
    enlarged = im.resize((2000,2000),Image.Resampling.NEAREST)
    scaled = manual_region(enlarged,[120,120,440,780],[],{})
    assert abs(estimate_source_font_size(enlarged,scaled)-54) <= 1


def test_auto_matches_source_and_does_not_force_page_uniformity():
    im,normal,large = source_page()
    plan = plan_page_lettering(im,[normal,large],FONT)
    assert plan['policy'] == 'source-size-first-1'
    assert normal['font_target'] == 27 and large['font_target'] == 80
    for r in (normal,large):
        out,mask = render_masked_region(im,r,FONT,None)
        assert r['font_size'] == r['source_font_size']
        assert np.array_equal(np.asarray(im)[~mask],np.asarray(out)[~mask])


def test_only_overflow_shrinks_and_manual_override_wins():
    im,normal,large = source_page()
    large['translation'] = '這是一段需要完整保留內容的很長對話。'*3
    plan_page_lettering(im,[normal,large],FONT)
    safe = decode_mask(large['layout_mask'],(1000,1000))
    _,size,_ = fit_region_lettering(im.size,large,FONT,safe,large['font_target'])
    assert size < large['source_font_size'] == 80
    fixed = deepcopy(normal)
    fixed['font_size_override'] = 42
    plan_page_lettering(im,[fixed,large],FONT)
    assert fixed['font_size_override'] == 42 and 'font_target' not in fixed
    render_masked_region(im,fixed,FONT,None)
    assert fixed['font_size'] == 42


def test_empty_source_falls_back_without_using_old_output_size():
    im,normal,_ = source_page()
    normal.update(font_size=200,font_target=200,source_font_size=200)
    blank = Image.new('RGB',im.size,'white')
    assert estimate_source_font_size(blank,normal) is None
    plan_page_lettering(blank,[normal],FONT)
    assert 'source_font_size' not in normal and 'font_target' not in normal
