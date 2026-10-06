"""Exercise the real review widgets with local fakes; never sends user data."""
import json
import gc
import os
import tkinter as tk
from copy import deepcopy
from types import SimpleNamespace

import pytest
from PIL import Image, ImageDraw

from src.offline.manual_review import manual_region
from src.offline.models import sha256
from src.offline.review_gui import ReviewWindow

pytestmark = pytest.mark.skipif(os.environ.get('COMIC_GUI_TESTS') != '1', reason='requires a desktop Tk session')


@pytest.fixture
def window(tmp_path, monkeypatch):
    gc.collect()  # Tk variables from earlier windows must be finalized on the UI thread.
    image = Image.new('RGB', (500,600), 'white')
    ImageDraw.Draw(image).rectangle([120,120,150,150], fill='black')
    source = tmp_path/'source.png'
    image.save(source)
    old = manual_region(image, [300,300,380,400], [], {})
    old.update(manual=False, original='既有原文', translation='原有譯文')
    report = {'source': str(source), 'source_hash': sha256(source), 'image_size': list(image.size),
              'regions': [old], 'glossary': {'クリボン':'栗邦邦'}, 'fingerprint': {}}
    path = tmp_path/'report.json'
    path.write_text(json.dumps(report))
    root = tk.Tk()
    # Review windows inherit the main application's taller native buttons.
    from tkinter import ttk
    ttk.Style(root).configure('TButton', width=0, padding=(8,10))
    app = ReviewWindow(root, path, tmp_path)
    app.preview_delay = 100000  # Most tests drive workers explicitly.
    app.recognizer = SimpleNamespace(recognize=lambda crop: 'おまたせ！')
    errors = []
    monkeypatch.setattr('src.offline.review_gui.messagebox.showerror', lambda *a, **k: errors.append(a))
    app.test_errors = errors
    root.update()
    yield app
    root.destroy()


def point(app, x, y):
    scale, ox, oy, crop = app.mapping
    return SimpleNamespace(x=ox+(x-crop[0])*scale, y=oy+(y-crop[1])*scale)


def finish(app):
    app.worker.join(timeout=5)
    assert not app.worker.is_alive()
    app.poll()
    app.root.update()
    assert not app.busy


def add_box(app):
    app.start_box()
    app.pointer_down(point(app, 100,100))
    app.pointer_move(point(app, 210,230))
    app.pointer_up(point(app, 210,230))
    finish(app)


def test_box_ocr_edit_translate_only_selected_and_delete(window, monkeypatch):
    app = window
    before = deepcopy(app.report['regions'][0])
    add_box(app)
    assert len(app.report['regions']) == 2
    assert app.source.get('1.0','end-1c') == 'おまたせ！'
    assert app.display.get() == 'mask'
    assert app.delete_button.instate(['!disabled'])
    app.source.delete('1.0','end')
    app.source.insert('1.0','おまたせ〜っ♡')
    calls = []
    def translate(records, glossary):
        calls.append((records, glossary))
        return {records[0]['id']: '久等了～♡'}
    monkeypatch.setattr('src.offline.translators.translator_from_settings', lambda: SimpleNamespace(translate=translate, fingerprint={'model':'fake'}))
    app.translate_selected()
    assert app.box_button.instate(['disabled'])
    finish(app)
    assert calls == [([{'id':'r002','text':'おまたせ〜っ♡'}], {'クリボン':'栗邦邦'})]
    assert app.translation.get('1.0','end-1c') == '久等了～♡'
    assert app.report['regions'][0]['translation'] == before['translation']
    app.delete_region()
    assert len(app.report['regions']) == 1
    assert app.report['regions'][0]['translation'] == before['translation']
    from src.platforms import current
    assert app.delete_button.instate(['!disabled'] if current.DELETE_DETECTED_REGIONS else ['disabled'])
    assert not app.test_errors


def test_cancel_tiny_and_failed_translation_keep_draft(window, monkeypatch):
    app = window
    app.start_box()
    app.pointer_down(point(app,100,100))
    app.cancel_box()
    app.pointer_up(point(app,210,230))
    assert len(app.report['regions']) == 1
    app.start_box()
    app.pointer_down(point(app,100,100))
    app.pointer_up(point(app,102,103))
    assert '太小' in app.status.get()
    assert not app.busy
    add_box(app)
    app.translation.insert('1.0','自己的譯文')
    def fail(*args):
        raise RuntimeError('AGY unavailable')
    monkeypatch.setattr('src.offline.translators.translator_from_settings', fail)
    app.translate_selected()
    finish(app)
    assert app.translation.get('1.0','end-1c') == '自己的譯文'
    assert app.report['regions'][1]['translation'] == '自己的譯文'
    assert app.box_button.instate(['!disabled'])
    assert app.test_errors


def test_manual_region_applies_and_reopens_saved_report(window, monkeypatch):
    from pathlib import Path
    app = window
    add_box(app)
    app.pointer_down(point(app,210,230))
    app.pointer_up(point(app,225,245))
    app.translation.insert('1.0', '久等了！')
    app.font_size.set('30')
    app.clean_button.invoke()
    app.report['regions'][0]['enabled'] = False
    app.report['fingerprint']['restoration'] = 'test'
    app.restorer = SimpleNamespace(fingerprint='test', inpaint=lambda im, mask: Image.new('RGB', im.size, 'white'))
    font = Path(__file__).resolve().parents[1] / 'assets/fonts/NotoSansCJKtc-Bold.otf'
    monkeypatch.setattr('src.offline.review.resolve_font', lambda: (font, {}))
    original_report = app.report_path.read_bytes()
    app.apply()
    finish(app)
    assert not app.test_errors
    assert app.report['translated'] == 1
    assert app.report['regions'][1]['manual']
    assert app.report['regions'][1]['translation'] == '久等了！'
    assert app.report_path.read_bytes() == original_report
    output = Path(app.report['output_path'])
    assert output.exists()
    saved_path = output.with_suffix('.json')
    other = tk.Toplevel(app.root)
    try:
        reopened = ReviewWindow(other, saved_path, app.models)
        assert reopened.report['regions'][1]['translation'] == '久等了！'
        assert reopened.report['regions'][1]['manual']
        assert reopened.report['regions'][1]['bbox'] == [100,100,225,245]
        assert reopened.report['regions'][1]['font_size_override'] == 30
        assert reopened.report['regions'][1]['font_size'] == 30
        assert reopened.report['regions'][1]['cleaning_mode'] == 'white'
    finally:
        other.destroy()


@pytest.mark.parametrize('handle,end,expected', [
    ('nw',(90,90),[90,90,210,230]), ('n',(155,90),[100,90,210,230]),
    ('ne',(220,90),[100,90,220,230]), ('e',(220,165),[100,100,220,230]),
    ('se',(220,240),[100,100,220,240]), ('s',(155,240),[100,100,210,240]),
    ('sw',(90,240),[90,100,210,240]), ('w',(90,165),[90,100,210,230]),
])
def test_drag_resize_handles_preserve_text_without_ocr(window, handle, end, expected):
    app = window
    add_box(app)
    app.translation.insert('1.0','自己的譯文')
    def no_ocr(*args):
        pytest.fail('Resizing must not overwrite OCR or trigger translation')
    app.recognizer = SimpleNamespace(recognize=no_ocr)
    x,y = app.frame_points([100,100,210,230])[handle]
    app.pointer_down(SimpleNamespace(x=x,y=y))
    app.pointer_move(point(app,*end))
    assert app.report['regions'][1]['bbox'] == [100,100,210,230]
    app.pointer_up(point(app,*end))
    assert app.report['regions'][1]['bbox'] == expected
    assert app.translation.get('1.0','end-1c') == '自己的譯文'
    assert app.source.get('1.0','end-1c') == 'おまたせ！'
    assert len(app.report['regions']) == 2
    assert app.display.get() == 'mask'


def test_resize_zoom_cancel_overlap_and_brush_mode(window):
    app = window
    add_box(app)
    app.zoom.set(True)
    app.draw()
    app.pointer_down(point(app,210,230))
    app.pointer_move(point(app,220,240))
    app.cancel_box()
    app.pointer_up(point(app,220,240))
    assert app.report['regions'][1]['bbox'] == [100,100,210,230]
    app.pointer_down(point(app,210,230))
    app.pointer_up(point(app,220,240))
    assert app.report['regions'][1]['bbox'] == [100,100,220,240]
    app.zoom.set(False)
    app.draw()
    app.pointer_down(point(app,220,240))
    app.pointer_up(point(app,310,310))
    assert '重疊' in app.status.get()
    assert app.report['regions'][1]['bbox'] == [100,100,220,240]
    app.brush.set('remove')
    app.show_mask()
    app.pointer_down(point(app,220,240))
    assert app.resize_drag is None


def test_white_cleaning_and_font_controls_keep_text_and_persist(window):
    app = window
    add_box(app)
    app.translation.insert('1.0','久等了！')
    app.font_size.set('48')
    app.clean_button.invoke()
    assert app.report['regions'][1]['cleaning_mode'] == 'white'
    assert app.report['regions'][1]['font_size_override'] == 48
    assert app.translation.get('1.0','end-1c') == '久等了！'
    app.regions.selection_clear(0,'end')
    app.regions.selection_set(0)
    app.select()
    assert app.clean_button.instate(['disabled'])
    app.regions.selection_clear(0,'end')
    app.regions.selection_set(1)
    app.select()
    assert app.font_size.get() == '48'
    app.set_busy(True)
    assert app.font_control.instate(['disabled']) and app.clean_button.instate(['disabled'])
    app.set_busy(False)
    app.font_size.set('0')
    app.commit()
    assert app.report['regions'][1]['font_size_override'] == 0
    app.root.update()
    for widget in (app.font_control,app.clean_button,app.apply_button):
        assert widget.winfo_ismapped()
        assert widget.winfo_rooty()+widget.winfo_height() <= app.root.winfo_rooty()+app.root.winfo_height()


def wait_until(app, predicate):
    import time
    deadline = time.monotonic()+4
    while not predicate() and time.monotonic() < deadline:
        app.root.update()
        time.sleep(.01)
    assert predicate(), app.status.get()


def fake_preview_renderer(snapshot, models, restorer):
    updated = deepcopy(snapshot)
    for region in updated['regions']:
        region['status'] = 'translated'
    updated.update(translated=1,preserved=len(updated['regions'])-1)
    return Image.new('RGB',(500,600),'white'), updated, Image.new('L',(500,600),0)


def test_live_preview_never_writes_and_export_is_explicit(window, monkeypatch):
    from pathlib import Path
    app = window
    app.preview_delay = 10
    app.preview_restorer = object()
    app.restorer = object()
    calls = []
    def render(snapshot, models, restorer):
        calls.append(deepcopy(snapshot))
        return fake_preview_renderer(snapshot,models,restorer)
    monkeypatch.setattr('src.offline.review_gui.rerender',render)
    before = set(app.report_path.parent.iterdir())
    original_report = app.report_path.read_bytes()
    app.translation.delete('1.0','end')
    app.translation.insert('1.0','預覽內容~')
    cursor = app.translation.index('insert')
    wait_until(app,lambda: '預覽已更新' in app.status.get())
    assert calls[-1]['regions'][0]['translation'] == '預覽內容~'
    assert app.translation.index('insert') == cursor
    assert app.report_path.read_bytes() == original_report
    assert set(app.report_path.parent.iterdir()) == before
    assert app.dirty and app.translation['state'] == 'normal'
    app.font_size.set('36')
    wait_until(app,lambda: app.report['regions'][0].get('font_size_override') == 36 and '預覽已更新' in app.status.get())
    assert set(app.report_path.parent.iterdir()) == before
    app.apply_button.invoke()
    finish(app)
    assert not app.dirty
    assert Path(app.report['output_path']).exists()
    saved_files = set(app.report_path.parent.iterdir())
    assert len(saved_files-before) == 4  # PNG, mask, JSON, exclusive reservation.
    app.preview_button.invoke()
    wait_until(app,lambda: '預覽已更新' in app.status.get())
    assert set(app.report_path.parent.iterdir()) == saved_files


def test_slow_preview_cannot_replace_newer_edits(window, monkeypatch):
    import threading
    app = window
    app.preview_restorer = object()
    entered, release = threading.Event(), threading.Event()
    calls = []
    def render(snapshot, models, restorer):
        calls.append(snapshot['regions'][0]['translation'])
        if len(calls) == 1:
            entered.set()
            assert release.wait(3)
        return fake_preview_renderer(snapshot,models,restorer)
    monkeypatch.setattr('src.offline.review_gui.rerender',render)
    app.translation.delete('1.0','end')
    app.translation.insert('1.0','舊草稿')
    app.root.update()
    app.preview_now()
    assert entered.wait(1)
    try:
        app.translation.delete('1.0','end')
        app.translation.insert('1.0','最新草稿')
        app.root.update()
        assert app.translation['state'] == 'normal' and not app.busy
    finally:
        release.set()
    app.preview_worker.join(3)
    app.poll()
    assert app.translation.get('1.0','end-1c') == '最新草稿'
    assert app.report['regions'][0]['translation'] != '舊草稿' or app.preview_pending
    app.preview_now()
    wait_until(app,lambda: '預覽已更新' in app.status.get())
    assert app.report['regions'][0]['translation'] == '最新草稿'
    assert calls == ['舊草稿','最新草稿']
    assert not list(app.report_path.parent.glob('*revised*'))


def test_failed_lettering_keeps_last_preview_and_cannot_export_source(window, monkeypatch):
    app = window
    app.preview_restorer = app.restorer = object()
    previous = Image.new('RGB', (500,600), 'gray')
    app.result = previous
    def fail(snapshot, models, restorer):
        updated = deepcopy(snapshot)
        updated['regions'][0].update(status='preserved', reason='換行及縮小後仍放不下')
        return app.original.copy(), updated, Image.new('L',(500,600),0)
    monkeypatch.setattr('src.offline.review_gui.rerender', fail)
    exported = []
    monkeypatch.setattr('src.offline.review_gui.save_revision', lambda *args: exported.append(args))
    before = set(app.report_path.parent.iterdir())
    app.translation.delete('1.0','end')
    app.translation.insert('1.0','保留這次草稿')
    app.root.update()
    app.preview_now()
    wait_until(app, lambda: '預覽失敗' in app.status.get())
    assert app.result is previous
    assert '保留上次預覽' in app.reason['text']
    assert app.translation.get('1.0','end-1c') == '保留這次草稿'
    app.apply()
    finish(app)
    assert app.result is previous and app.dirty
    assert not exported and app.test_errors
    assert set(app.report_path.parent.iterdir()) == before


def test_explicit_keep_original_is_allowed():
    from src.offline.review_gui import require_rendered_translations
    require_rendered_translations({'regions': [
        dict(id='r001', status='preserved', enabled=False, translation='不套用'),
        dict(id='r002', status='preserved', enabled=True, translation=''),
    ]})


def test_start_box_clears_old_selection_but_keeps_its_draft(window):
    app = window
    app.translation.delete('1.0','end')
    app.translation.insert('1.0','修改中的譯文')
    app.root.update()
    assert app.canvas.find_withtag('region-frame')
    app.start_box()
    app.root.update()
    assert app.index is None and app.mask is None
    assert not app.regions.curselection()
    assert not app.canvas.find_withtag('region-frame')
    assert app.source.get('1.0','end-1c') == ''
    assert app.translation.get('1.0','end-1c') == ''
    assert app.translate_button.instate(['disabled'])
    assert app.translation['state'] == 'disabled'
    assert app.report['regions'][0]['translation'] == '修改中的譯文'
    app.pointer_down(point(app,100,100))
    app.pointer_move(point(app,210,230))
    assert app.canvas.find_withtag('selection')
    assert not app.canvas.find_withtag('region-frame')
    app.cancel_box()
    app.regions.selection_set(0)
    app.select()
    assert app.translation['state'] == 'normal'
    assert app.translation.get('1.0','end-1c') == '修改中的譯文'
    assert app.canvas.find_withtag('region-frame')


def test_brush_cursor_shows_paint_area_and_size_controls_it(window):
    app = window
    add_box(app)
    event = point(app, 150, 150)
    assert not app.draw_brush_cursor(event) and not app.canvas.find_withtag('brush-cursor')
    app.brush.set('remove')
    app.show_mask()
    app.brush_size.set(20)
    app.pointer_hover(event)
    ids = app.canvas.find_withtag('brush-cursor')
    assert ids and app.canvas.cget('cursor') == 'none'
    left, _, right, _ = app.canvas.coords(ids[-1])
    assert round(right - left) == 40  # diameter equals twice the radius setting
    # The painted source-pixel radius follows the setting at the current zoom.
    app.mask[:] = True
    app.pointer_down(event)
    cleared = (~app.mask).sum()
    app.brush_size.set(5)
    app.mask[:] = True
    app.pointer_down(event)
    assert cleared > (~app.mask).sum() > 0
    app.brush.set('inspect')
    app.show_mask()
    app.pointer_hover(event)
    assert not app.canvas.find_withtag('brush-cursor')


def test_detected_region_box_can_be_resized_and_keeps_its_text(window):
    app = window
    detected = app.report['regions'][0]
    assert not detected.get('manual')
    old_box = detected['bbox']
    x, y = app.frame_points(old_box)['se']
    app.pointer_down(SimpleNamespace(x=x, y=y))
    assert app.resize_drag is not None  # handles are offered for detected regions too
    end = (old_box[2] + 12, old_box[3] + 10)
    app.pointer_move(point(app, *end))
    app.pointer_up(point(app, *end))
    resized = app.report['regions'][0]
    assert resized['bbox'][2:] == list(end)
    assert resized['original'] == '既有原文' and resized['translation'] == '原有譯文'
    assert resized['manual'] and resized['label'] is None and resized['polygons'] == []
    assert len(app.report['regions']) == 1


def test_delete_automatic_region_restores_original_and_saves_empty_revision(window, monkeypatch):
    import numpy as np
    from pathlib import Path
    from src.platforms import windows
    monkeypatch.setattr('src.offline.review_gui.platform_support', windows)
    monkeypatch.setattr('src.offline.review.platform_support', windows)
    app = window
    app.report['fingerprint']['restoration'] = 'fixture'
    app.restorer = app.preview_restorer = SimpleNamespace(fingerprint='fixture')
    font = Path(__file__).resolve().parents[1]/'assets/fonts/NotoSansCJKtc-Bold.otf'
    monkeypatch.setattr('src.offline.review.resolve_font', lambda: (font, {}))
    app.result = Image.new('RGB', app.original.size, 'gray')
    before = app.report_path.read_bytes()
    app.delete_region()
    assert app.report['regions'] == [] and app.index is None
    assert app.delete_button.instate(['disabled'])
    app.preview_now()
    wait_until(app, lambda: '預覽已更新' in app.status.get())
    assert np.array_equal(np.asarray(app.result), np.asarray(app.original))
    app.apply()
    finish(app)
    assert not app.test_errors
    assert app.report_path.read_bytes() == before
    output = Path(app.report['output_path'])
    with Image.open(output) as saved:
        assert np.array_equal(np.asarray(saved), np.asarray(app.original))
    assert json.loads(output.with_suffix('.json').read_text(encoding='utf-8'))['regions'] == []


def test_auto_font_adjustment_is_not_blocked_by_unchanged_preserved_region(window, monkeypatch):
    from src.platforms import windows
    monkeypatch.setattr('src.offline.review_gui.platform_support', windows)
    app = window
    blocked = deepcopy(app.report['regions'][0])
    blocked.update(id='blocked', status='preserved', reason='遮罩碰到框線')
    app.report['regions'].append(blocked)
    app.rendered_report = deepcopy(app.report)
    app.preview_restorer = object()
    def render(snapshot, models, restorer):
        revised = deepcopy(snapshot)
        revised['regions'][0].update(status='translated', font_size=revised['regions'][0]['font_size_override'])
        return Image.new('RGB', app.original.size, 'gray'), revised, Image.new('L', app.original.size, 0)
    monkeypatch.setattr('src.offline.review_gui.rerender', render)
    app.font_size.set('20')
    app.preview_now()
    wait_until(app, lambda: '預覽已更新' in app.status.get())
    assert not app.report['regions'][0].get('manual')
    assert app.report['regions'][0]['font_size'] == 20
    assert app.report['regions'][1]['status'] == 'preserved'
    assert app.result.getpixel((0,0)) == (128,128,128)


def test_macos_keeps_manual_deletion_and_strict_preview_policy(window, monkeypatch):
    from src.platforms import macos
    from src.offline.review_gui import require_rendered_translations
    monkeypatch.setattr('src.offline.review_gui.platform_support', macos)
    app = window
    app.set_busy(False)
    assert app.delete_button.instate(['disabled'])
    app.delete_region()
    assert len(app.report['regions']) == 1
    failed = {'regions': [dict(id='failed', status='preserved', translation='已翻譯')]}
    with pytest.raises(ValueError):
        require_rendered_translations(failed, deepcopy(failed))


def test_windows_edited_failures_and_previously_rendered_regressions_still_block(monkeypatch):
    from src.platforms import windows
    from src.offline.review_gui import require_rendered_translations
    monkeypatch.setattr('src.offline.review_gui.platform_support', windows)
    prior = {'regions': [dict(id='region', status='preserved', translation='已翻譯', font_size_override=0)]}
    require_rendered_translations(deepcopy(prior), prior)
    edited = deepcopy(prior)
    edited['regions'][0]['font_size_override'] = 20
    with pytest.raises(ValueError, match='region'):
        require_rendered_translations(edited, prior)
    prior['regions'][0]['status'] = 'translated'
    with pytest.raises(ValueError, match='region'):
        require_rendered_translations(edited, prior)


def test_side_controls_scroll_when_short_and_reset_when_restored(window):
    from tkinter import ttk
    app = window
    side = app.apply_button.master.master.master
    assert isinstance(side, tk.Canvas)
    scrollbar = next(widget for widget in side.master.winfo_children()
                     if isinstance(widget, ttk.Scrollbar))
    app.root.geometry("1200x500")
    app.root.update()
    assert scrollbar.winfo_ismapped()
    side.yview_moveto(1)
    app.root.update()
    assert side.yview()[1] == pytest.approx(1)
    controls = app.apply_button.master.master
    assert controls.winfo_y() + app.apply_button.winfo_rooty() - controls.winfo_rooty() \
        + app.apply_button.winfo_height() <= side.winfo_height()
    app.root.geometry("1200x1600")
    app.root.update()
    assert not scrollbar.winfo_ismapped()
    assert side.yview()[0] == 0


@pytest.mark.parametrize("platform_name, scale, desired_height", [("windows", 1.75, 920), ("macos", 1, 850)])
def test_review_geometry_scales_and_is_clamped_to_screen(window, monkeypatch, platform_name, scale, desired_height):
    from src.platforms import macos, windows
    platform = windows if platform_name == "windows" else macos
    monkeypatch.setattr("src.offline.review_gui.platform_support", platform)
    monkeypatch.setattr(platform, "window_scale", lambda root: scale)
    root = tk.Toplevel(window.root)
    monkeypatch.setattr(root, "winfo_screenwidth", lambda: 1600)
    monkeypatch.setattr(root, "winfo_screenheight", lambda: 900)
    try:
        app = ReviewWindow(root, window.report_path, window.models)
        root.update()
        assert root.winfo_width() == min(round(1200 * scale), 1560)
        assert root.winfo_height() == min(round(desired_height * scale), 820)
        assert isinstance(app.apply_button.master.master.master, tk.Canvas)
    finally:
        root.destroy()
