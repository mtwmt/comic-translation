from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest
from PIL import Image, ImageDraw

from src.offline import fonts
from src.offline.layout import complete_character_mask, lettering_tokens, wrap_tokens, prepare_masked_regions
from src.offline.models import ModelError


def test_punctuation_stays_with_dialogue_and_roundtrips():
    for text in ['誰都看得出來好嗎！！', '你把碧姬公主弄到哪裡去了！？', '「等等！」你這傢伙～～！', '……不對，現在哪是表演雜耍的時候啊！！']:
        tokens = lettering_tokens(text)
        lines = wrap_tokens(tokens, 7, 8)
        assert lines and ''.join(''.join(line) for line in lines) == text
        assert all(line[0][0] not in '。，、！？!?,：；）］」』】…～' for line in lines[1:])
        assert all(line[-1][-1] not in '（［「『【' for line in lines[:-1])
    assert lettering_tokens('好！！') == ['好', '！！']
    assert lettering_tokens('誰！？') == ['誰', '！？']


def test_complete_strokes_without_growing_through_panel_border():
    image = Image.new('RGB', (300, 300), 'white')
    d = ImageDraw.Draw(image)
    d.rectangle((100, 110, 119, 139), fill='black')
    d.line((0, 100, 299, 100), fill='black', width=3)
    seed = np.zeros((300, 300), bool)
    seed[115:130, 105:115] = True
    poly = np.array([[95, 95], [130, 95], [130, 145], [95, 145]])
    mask = complete_character_mask(image, seed, [poly])
    assert mask[110:140, 100:120].all()
    assert not mask[100:103].any()


def test_furigana_between_columns_in_shared_balloon():
    image = Image.new('RGB', (400, 400), 'gray')
    d = ImageDraw.Draw(image)
    d.rectangle((80, 80, 240, 200), fill='white', outline='black', width=3)
    d.rectangle((100, 100, 120, 150), fill='black')
    d.rectangle((190, 100, 210, 150), fill='black')
    d.rectangle((150, 120, 153, 126), fill='black')
    seed = np.zeros((400, 400), bool)
    seed[98:153, 98:123] = True
    seed[98:153, 188:213] = True
    detections = [(np.array([[95, 95], [125, 95], [125, 155], [95, 155]]), .9),
                  (np.array([[185, 95], [215, 95], [215, 155], [185, 155]]), .9)]
    from src.offline.restoration import decode_mask
    regions, _ = prepare_masked_regions(image, detections, seed)
    assert len(regions) == 1
    mask = decode_mask(regions[0]['erase_mask'], (400, 400))
    assert mask[120:127, 150:154].all()
    assert not mask[80:83].any()


def test_missing_system_and_bundled_fonts_fail_clearly(tmp_path, monkeypatch):
    monkeypatch.setattr(fonts, 'system_font_candidates', lambda: [])
    monkeypatch.setattr(fonts.Path, 'is_file', lambda path: False)
    with pytest.raises(ModelError, match='Noto 繁中粗體缺失'):
        fonts.resolve_font()


def test_font_collection_uses_traditional_chinese_semibold_face(tmp_path, monkeypatch):
    path = tmp_path / 'PingFang.ttc'
    path.write_bytes(b'collection fixture')
    faces = [('PingFang HK', 'Semibold'), ('PingFang TC', 'Regular'), ('PingFang TC', 'Semibold')]
    def fake_font(path, size, index=0):
        if index >= len(faces):
            raise OSError('end of collection')
        return SimpleNamespace(getname=lambda: faces[index])
    monkeypatch.setattr(fonts.ImageFont, 'truetype', fake_font)
    monkeypatch.setattr(fonts, 'system_font_candidates', lambda: [(path, 'PingFang TC', 'Semibold')])
    selected, details = fonts.resolve_font()
    assert details['index'] == 2
    assert fonts.load_font(fonts.FontFace(selected, details['index']), 36).getname() == ('PingFang TC', 'Semibold')


def test_windows_uses_jhenghei_bold(tmp_path, monkeypatch):
    monkeypatch.setattr(fonts.sys, 'platform', 'win32')
    monkeypatch.setenv('WINDIR', str(tmp_path / 'Windows'))
    font = tmp_path / 'Windows/Fonts/msjhbd.ttc'
    font.parent.mkdir(parents=True)
    font.write_bytes(b'Windows font fixture')
    monkeypatch.setattr(fonts.ImageFont, 'truetype', lambda *args, **kwargs: SimpleNamespace(getname=lambda: ('Microsoft JhengHei', 'Bold')))
    selected, details = fonts.resolve_font()
    assert selected == font
    assert details['family'] == 'Microsoft JhengHei' and details['style'] == 'Bold'


def test_bundled_fallback_is_real_traditional_chinese_bold(tmp_path, monkeypatch):
    monkeypatch.setattr(fonts, 'system_font_candidates', lambda: [])
    path, details = fonts.resolve_font()
    assert path.parent == fonts.BUNDLED_FONTS
    assert details['family'] == 'Noto Sans CJK TC' and details['style'] == 'Bold'
    assert fonts.load_font(fonts.FontFace(path, details['index']), 40).getmask('繁體漫畫！？').getbbox()


def test_word_aware_wrap_preserves_coins_and_phrase_boundaries():
    text = '你打算拿金幣做什麼？'
    lines = wrap_tokens(lettering_tokens(text), 5, 4)
    assert [''.join(line) for line in lines] == ['你打算', '拿金幣', '做什麼？']
    assert ''.join(''.join(line) for line in lines) == text


def test_name_title_and_glossary_are_never_split():
    text = '你把碧姬公主弄到哪裡去了！？'
    lines = [''.join(line) for line in wrap_tokens(lettering_tokens(text), 5, 4)]
    assert any('碧姬公主' in line for line in lines)
    assert all(len(line) > 1 for line in lines)
    name = '阿里山勇者'
    text = '請讓阿里山勇者先過來！'
    lines = [''.join(line) for line in wrap_tokens(lettering_tokens(text), 7, 4, (name,))]
    assert any(name in line for line in lines)
    assert ''.join(lines) == text


def test_manual_newlines_are_kept_and_all_characters_survive():
    from src.offline.layout import glyph_layer
    font, details = fonts.resolve_font()
    info = {}
    text = '你打算\n拿金幣\n做什麼？'
    layer = glyph_layer((300, 300), text, (10, 10, 290, 290),
                        fonts.FontFace(font, details.get('index', 0)), 30, True, layout_info=info)
    assert layer is not None
    assert info['lines'] == ['你打算', '拿金幣', '做什麼？']


def test_clause_breaks_can_use_an_extra_column_for_readability():
    text = '幸好槍戰有了回報，保住了一隻，就先忍耐一下吧。'
    lines = [''.join(line) for line in wrap_tokens(lettering_tokens(text), 7, 6)]
    assert ''.join(lines) == text
    assert '有了回報，' in lines and '保住了一隻，' in lines
    assert all(len(line) > 1 for line in lines)


def test_negation_and_aspect_particle_stay_with_word():
    for text, phrase in [('……不對，現在哪是表演雜耍的時候啊！！', '不對'),
                         ('雖然覺得身上掛著空手槍，根本派不上用場。', '掛著')]:
        lines = [''.join(line) for line in wrap_tokens(lettering_tokens(text), 6, 10)]
        assert ''.join(lines) == text
        assert any(phrase in line for line in lines)
        assert '……' not in lines


def test_tilde_variants_are_vertical_only_in_vertical_text():
    from pathlib import Path
    import numpy as np
    from src.offline.layout import glyph_layer
    font = Path(__file__).resolve().parents[1]/'assets/fonts/NotoSansCJKtc-Bold.otf'
    layers = [glyph_layer((120,120), text, (10,10,110,110), font, 48, True) for text in ('~','～','〜')]
    assert all(np.array_equal(layers[0], layer) for layer in layers[1:])
    y,x = np.where(layers[0] > 0)
    assert y.max()-y.min() > x.max()-x.min()
    horizontal = glyph_layer((120,120),'~',(10,10,110,110),font,48,False)
    y,x = np.where(horizontal > 0)
    assert x.max()-x.min() > y.max()-y.min()


@pytest.mark.parametrize('symbol', ['♡', '♥'])
@pytest.mark.parametrize('vertical', [False, True])
@pytest.mark.parametrize('missing_style', ['blank', 'box'])
def test_missing_hearts_use_bundled_glyph_without_changing_chinese(monkeypatch, symbol, vertical, missing_style):
    from src.offline import layout
    real = fonts.load_font(fonts.BUNDLED_FONTS / 'NotoSansCJKtc-Bold.otf', 48)

    class MissingHeartFont:
        size = 48

        def getmask(self, text):
            if text in ('♡', '♥', '\uffff'):
                return real.getmask(' ' if missing_style == 'blank' else '\uffff')
            return real.getmask(text)

    primary = MissingHeartFont()
    assert fonts.lettering_font(primary, '讓') is primary
    assert fonts.lettering_font(real, symbol) is real
    expected = layout.glyph_layer((120, 120), symbol, (10, 10, 110, 110),
                                  fonts.BUNDLED_FONTS / 'NotoSansCJKtc-Bold.otf', 48, vertical)
    monkeypatch.setattr(layout, 'load_font', lambda *_: primary)
    actual = layout.glyph_layer((120, 120), symbol, (10, 10, 110, 110), 'unused', 48, vertical)
    assert np.count_nonzero(actual) > 100
    assert np.array_equal(actual, expected)


@pytest.mark.parametrize('vertical', [False, True])
def test_platform_font_renders_heart_at_end_of_dialogue(vertical):
    from src.offline.layout import glyph_layer
    path, details = fonts.resolve_font()
    face = fonts.FontFace(path, details.get('index', 0))
    info = {}
    # One row/column, with the heart in the last cell.
    box = (10, 10, 70, 350) if vertical else (10, 10, 350, 70)
    layer = glyph_layer((360, 360), '讓您久等了~♡', box, face, 40, vertical, layout_info=info)
    assert info['lines'] == ['讓您久等了~♡']
    heart_cell = layer[292:338, 10:70] if vertical else layer[10:70, 292:338]
    assert np.count_nonzero(heart_cell) > 100


def test_expressive_ending_can_wrap_when_dialogue_outgrows_one_column():
    tokens = lettering_tokens('久等了~♡')
    assert [''.join(line) for line in wrap_tokens(tokens, 4, 3)] == ['久等了', '~♡']
    assert [''.join(line) for line in wrap_tokens(tokens, 5, 3)] == ['久等了~♡']


@pytest.mark.parametrize('vertical', [True, False])
def test_requested_size_wraps_before_shrinking(vertical):
    from src.offline.layout import fit_region_lettering
    safe = np.zeros((500, 500), dtype=bool)
    box = (80, 60, 300, 350) if vertical else (60, 80, 350, 300)
    x1,y1,x2,y2 = box
    safe[y1:y2,x1:x2] = True
    region = dict(bbox=box, translation='久等了~♡', direction='vertical' if vertical else 'horizontal',
                  font_size_override=65)
    font = fonts.BUNDLED_FONTS / 'NotoSansCJKtc-Bold.otf'
    glyphs, size, lines = fit_region_lettering((500,500), region, font, safe)
    assert size == 65 and lines == ['久等了', '~♡']
    assert not np.any((glyphs > 0) & ~safe)


def test_font_download_verifies_hash_and_keeps_intact_copy(tmp_path):
    source = tmp_path / "source.otf"
    source.write_bytes(b"fake font bytes")
    digest = fonts.sha256(source)
    target = tmp_path / "fonts" / "font.otf"
    assert fonts.ensure_bundled_font(target, source.as_uri(), digest) == target
    assert target.read_bytes() == b"fake font bytes"
    source.write_bytes(b"changed")  # an intact copy is not downloaded again
    assert fonts.ensure_bundled_font(target, source.as_uri(), digest).read_bytes() == b"fake font bytes"
    corrupt = tmp_path / "other" / "font.otf"
    with pytest.raises(fonts.ModelError, match="校驗碼"):
        fonts.ensure_bundled_font(corrupt, source.as_uri(), "0" * 64)
    assert not corrupt.exists() and not list(corrupt.parent.glob("*.part"))
