"""Native desktop checks; opt in with COMIC_GUI_TESTS=1 on a desktop session."""
import os
import json
import gc
import sys
import tkinter as tk
from tkinter import filedialog, font as tkfont

import pytest
from PIL import Image

import offline_gui

pytestmark = pytest.mark.skipif(os.environ.get("COMIC_GUI_TESTS") != "1", reason="requires a desktop Tk session")


@pytest.fixture
def gui(tmp_path, monkeypatch):
    gc.collect()
    monkeypatch.setattr("src.gui.app.STATE_ROOT", tmp_path / "state")
    monkeypatch.setattr("src.offline.fonts.resolve_font", lambda: None)
    monkeypatch.setattr("src.gui.settings.list_models", lambda _: [])
    root = tk.Tk()
    app = offline_gui.OfflineGUI(root)
    root.update()
    # Exercises submission and widgets, with no model, CLI or network calls.
    monkeypatch.setattr(app, "start_worker", lambda: app.set_busy(True))
    yield app
    root.destroy()


def add_pages(gui, tmp_path, count=3):
    paths = []
    for index in range(count):
        path = tmp_path / f"page{index + 1}.png"
        Image.new("RGB", (30, 30), "white").save(path)
        paths.append(path)
    gui.add([tmp_path])
    gui.root.update()
    return paths


def test_names_text_stays_visible_and_saves_without_starting(gui):
    assert gui.names_panel.winfo_ismapped()
    gui.glossary.insert("1.0", "クリボン=栗邦邦\nマリオ=瑪利歐\nピーチ=碧姬公主")
    gui.save_glossary()
    gui.root.update()
    assert gui.names_panel.winfo_ismapped()
    assert gui.glossary.get("1.0", "end-1c") == "クリボン=栗邦邦\nマリオ=瑪利歐\nピーチ=碧姬公主"
    assert "栗邦邦" in gui.settings.read_text(encoding="utf-8")
    assert gui.pending.empty()


def test_names_pane_is_taller_narrower_and_can_be_resized(gui, tmp_path):
    add_pages(gui, tmp_path)
    gui.glossary.insert("1.0", "マリオ=瑪利歐\nピーチ=碧姬公主")
    gui.root.geometry("780x700")
    gui.root.update()
    before = gui.glossary.winfo_height()
    assert before >= 8 * tkfont.nametofont("TkTextFont").metrics("linespace")
    assert gui.glossary.winfo_width() < gui.names_panel.winfo_width() * .65
    assert gui.save_names_button.winfo_rootx() > gui.glossary.winfo_rootx() + gui.glossary.winfo_width()
    _, y = gui.content_split.sash_coord(0)
    x = gui.content_split.winfo_width() // 2
    gui.content_split.event_generate("<ButtonPress-1>", x=x, y=y + 2)
    gui.root.update()
    gui.content_split.event_generate("<B1-Motion>", x=x, y=y - 70, state=0x100)
    gui.root.update()
    gui.content_split.event_generate("<ButtonRelease-1>", x=x, y=y - 70)
    gui.root.update()
    assert gui.glossary.winfo_height() > before + 50
    assert gui.glossary.get("1.0", "end-1c") == "マリオ=瑪利歐\nピーチ=碧姬公主"
    for iid in gui.source_list.get_children()[:3]:
        bounds = gui.source_list.bbox(iid)
        assert bounds and bounds[1] + bounds[3] <= gui.source_list.winfo_height()
    assert gui.save_names_button.winfo_ismapped() and gui.prepare_button.winfo_ismapped()


def test_output_picker_remembers_choice_and_preserves_saved_names(gui, tmp_path, monkeypatch):
    gui.glossary.insert("1.0", "マリオ=瑪利歐")
    gui.save_glossary()
    gui.glossary.insert("end", "\ninvalid unsaved draft")
    chosen = tmp_path / "匯出 資料夾"
    chosen.mkdir()
    monkeypatch.setattr(filedialog, "askdirectory", lambda **kwargs: str(chosen))
    gui.choose_output_button.invoke()
    saved = json.loads(gui.settings.read_text(encoding="utf-8"))
    assert saved == {"glossary": "マリオ=瑪利歐", "output_directory": str(chosen)}
    assert gui.output_path.get() == str(chosen / "final")
    assert gui.reset_output_button.instate(["!disabled"])
    reopened = offline_gui.OfflineGUI(tk.Toplevel(gui.root))
    assert reopened.output_directory == chosen
    assert reopened.output_path.get() == str(chosen / "final")
    assert reopened.glossary.get("1.0", "end-1c") == "マリオ=瑪利歐"
    reopened.root.destroy()
    gui.glossary.delete("1.0", "end")
    gui.glossary.insert("1.0", "ピーチ=碧姬公主")
    gui.save_glossary()
    assert json.loads(gui.settings.read_text(encoding="utf-8"))["output_directory"] == str(chosen)
    gui.reset_output_button.invoke()
    saved = json.loads(gui.settings.read_text(encoding="utf-8"))
    assert saved == {"glossary": "ピーチ=碧姬公主", "output_directory": None}
    assert gui.output_directory is None and "translated/final" in gui.output_path.get()
    assert gui.reset_output_button.instate(["disabled"])


def test_output_picker_cancel_failure_and_busy_keep_destination(gui, tmp_path, monkeypatch):
    chosen = tmp_path / "chosen"
    gui.set_output_directory(chosen)
    original = gui.settings.read_bytes()
    monkeypatch.setattr(filedialog, "askdirectory", lambda **kwargs: "")
    gui.choose_output_button.invoke()
    assert gui.settings.read_bytes() == original and gui.output_directory == chosen
    def fail_write(*args, **kwargs):
        raise OSError("cannot save settings")
    monkeypatch.setattr("src.gui.settings.atomic_json", fail_write)
    gui.set_output_directory(tmp_path / "other")
    assert "cannot save settings" in gui.status.get()
    assert gui.output_directory == chosen and gui.output_path.get() == str(chosen / "final")
    gui.set_busy(True)
    monkeypatch.setattr(filedialog, "askdirectory", lambda **kwargs: pytest.fail("Busy picker must stay closed"))
    assert gui.choose_output_button.instate(["disabled"])
    assert gui.reset_output_button.instate(["disabled"])
    gui.pick_output()
    gui.set_output_directory(None)
    assert gui.output_directory == chosen and gui.settings.read_bytes() == original


def test_all_none_remove_and_folder_expansion(gui, tmp_path):
    paths = add_pages(gui, tmp_path)
    assert [job[1] for job in gui.staged] == paths
    gui.select_all()
    assert len(gui.source_list.selection()) == 3
    gui.select_none()
    assert not gui.source_list.selection()
    assert len(gui.staged) == 3
    gui.source_list.selection_set("1")
    gui.remove_staged()
    assert [job[1] for job in gui.staged] == [paths[0], paths[2]]
    assert not gui.source_list.selection()
    assert all(path.exists() for path in paths)


def test_start_retains_rows_progress_and_results(gui, tmp_path):
    paths = add_pages(gui, tmp_path)
    gui.start_translation()
    assert not gui.staged and gui.pending.qsize() == 1
    assert len(gui.source_list.get_children()) == 3
    gui.events.put({"index": 1, "total": 3, "source": str(paths[0]), "stage": "AGY 文字翻譯"})
    gui.poll()
    assert "翻譯對白" in gui.source_list.set("history-0", "state")
    for index, state in enumerate(("success", "partial", "failed")):
        gui.events.put({"source": str(paths[index]), "state": state, "output": str(tmp_path / f"out{index}.png"), "progress": index + 1, "total": 3})
    gui.poll()
    gui.set_busy(False)
    assert [gui.source_list.set(row, "state") for row in gui.source_list.get_children()] == ["已輸出", "已輸出 · 待確認", "失敗"]
    assert gui.progress_bar["value"] == 100
    assert gui.output_button.instate(["!disabled"])


def test_stop_and_busy_selection_do_not_change_running_jobs(gui, tmp_path):
    add_pages(gui, tmp_path)
    gui.start_translation()
    gui.select_all()
    assert not gui.source_list.selection()
    for button in (gui.review_button, gui.prepare_button, gui.clear_button):
        assert button.instate(["disabled"])
    assert gui.log_toggle.instate(["!disabled"])
    gui.log_toggle.invoke()
    gui.root.update()
    assert gui.log_window.winfo_ismapped()
    gui.hide_log()
    assert not gui.show_log.get()
    gui.clear_staged()
    assert len(gui.history) == 3
    gui.stop()
    gui.refresh_staged()
    assert gui.start_button.instate(["disabled"])
    assert gui.start_button["text"] == "停止中…"
    assert gui.pending.qsize() == 1


def test_small_window_roles_and_details_keep_controls_visible(gui, tmp_path):
    add_pages(gui, tmp_path)
    # Enough entries to overflow on both Windows and macOS font metrics.
    for index in range(40):
        gui.glossary.insert("end", f"name{index}=譯名{index}\n")
    gui.root.geometry("780x700")
    gui.show_log.set(True)
    gui.toggle_log()
    gui.root.update()
    assert gui.glossary_scroll.winfo_ismapped()
    gui.glossary.see("end")
    gui.root.update()
    assert gui.glossary.yview()[0] > 0
    for widget in (gui.start_button, gui.output_button, gui.source_list, gui.review_button, gui.prepare_button, gui.log_toggle,
                   gui.clear_button, gui.staging_title, gui.choose_output_button, gui.reset_output_button):
        assert widget.winfo_ismapped()
        assert widget.winfo_rooty() + widget.winfo_height() <= gui.root.winfo_rooty() + gui.root.winfo_height()
        assert widget.winfo_rootx() + widget.winfo_width() <= gui.root.winfo_rootx() + gui.root.winfo_width()
        assert widget.winfo_width() >= widget.winfo_reqwidth() or widget is gui.source_list
    assert gui.log_window.winfo_ismapped()
    # The smallest supported window still exposes three actual file rows.
    for iid in gui.source_list.get_children()[:3]:
        bounds = gui.source_list.bbox(iid)
        assert bounds and bounds[1] + bounds[3] <= gui.source_list.winfo_height()


def test_checked_retry_only_processes_selected_problem_pages(gui, tmp_path, monkeypatch):
    from src.offline.batch import create_batch
    paths = add_pages(gui, tmp_path, count=5)
    gui.staged = [("new", paths[4], False)]
    gui.history = {str(path): (label, state) for path, label, state in zip(
        paths, ("失敗", "失敗", "已輸出", "已輸出 · 待確認"),
        ("failed", "failed", "success", "partial"))}
    gui.refresh_staged()
    monkeypatch.setattr(filedialog, "askopenfilename", lambda **kwargs: pytest.fail("Retry must not open a batch picker"))
    gui.source_list.selection_set("history-0", "history-2", "history-3")
    gui.update_selection()
    assert gui.start_button["text"] == "重轉勾選（2）"
    gui.glossary.insert("1.0", "マリオ=瑪利歐")
    gui.start_button.invoke()
    assert gui.pending.qsize() == 1
    assert gui.staged == [("new", paths[4], False)]
    assert gui.history[str(paths[1])][1] == "failed"
    assert gui.history[str(paths[2])][1] == "success"

    calls = []
    class Pipeline:
        fingerprint = {"test": "selected-retry"}
        def process(self, source, glossary, progress):
            calls.append((source, glossary))
            image = Image.new("RGB", (30, 30), "white")
            return image, {"status": "success", "translated": 1, "preserved": 0}, image.convert("L")

    gui.pipeline = Pipeline()
    monkeypatch.setattr("src.gui.worker.create_batch", lambda *args, **kwargs: create_batch(
        *args, **kwargs, state_root=tmp_path / "state"))
    gui.work()
    gui.poll()
    gui.check_idle()
    assert calls == [(paths[0], {"マリオ": "瑪利歐"}), (paths[3], {"マリオ": "瑪利歐"})]
    assert gui.history[str(paths[1])][1] == "failed"
    assert gui.history[str(paths[2])][1] == "success"
    if sys.platform == "win32":
        # Windows retains checks without submitting successful pages again.
        assert gui.selected_image_sources() == [paths[0], paths[2], paths[3]]
        assert gui.start_button.instate(["disabled"])
        gui.select_none()
    assert gui.start_button.instate(["!disabled"])
    assert gui.start_button["text"] == "開始翻譯（1）"
    assert gui.staged == [("new", paths[4], False)]


def test_retry_invalid_names_keeps_selection_and_does_not_submit(gui, tmp_path):
    paths = add_pages(gui, tmp_path, count=1)
    gui.staged.clear()
    gui.history[str(paths[0])] = ("失敗", "failed")
    gui.refresh_staged()
    gui.source_list.selection_set("history-0")
    gui.update_selection()
    gui.glossary.insert("1.0", "不完整的對照")
    gui.start_button.invoke()
    assert gui.pending.empty() and not gui.busy
    assert gui.history[str(paths[0])][1] == "failed"
    assert gui.source_list.selection() == ("history-0",)
    assert "日文=中文" in gui.status.get()


def test_reopen_loads_failed_pages_for_checkbox_retry_without_starting(gui, tmp_path):
    import json
    source = tmp_path / "failed.png"
    Image.new("RGB", (20, 20), "white").save(source)
    batches = tmp_path / "state" / "batches"
    batches.mkdir(parents=True)
    journal = batches / "last.json"
    journal.write_text(json.dumps({"schema": 1, "status": "completed", "pages": [
        {"source": str(source), "output": str(tmp_path / "missing-result.png"), "state": "failed"}
    ]}))
    window = tk.Toplevel(gui.root)
    try:
        reopened = offline_gui.OfflineGUI(window)
        window.update()
        assert reopened.history[str(source)][1] == "failed"
        assert not reopened.busy and reopened.pending.empty()
        reopened.source_list.selection_set("history-0")
        reopened.update_selection()
        assert reopened.start_button.instate(["!disabled"])
        assert reopened.selected_retry_sources() == [source]
    finally:
        window.destroy()


def review_report(path, source):
    import json
    from src.offline.models import sha256
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({'source':str(source), 'source_hash':sha256(source), 'image_size':[30,30], 'regions':[]}))
    return path


def capture_review(monkeypatch):
    from types import SimpleNamespace
    calls = []
    def open_review(path, models, parent):
        calls.append(path)
        return SimpleNamespace(root=SimpleNamespace(winfo_exists=lambda: False), worker=None)
    monkeypatch.setattr('src.offline.review_gui.open_review', open_review)
    monkeypatch.setattr(filedialog, 'askopenfilename', lambda **kw: pytest.fail('Review must not ask for JSON'))
    return calls


def test_review_opens_checked_picture_not_last_batch_output(gui, tmp_path, monkeypatch):
    paths = add_pages(gui, tmp_path, 2)
    calls = capture_review(monkeypatch)
    reports = [review_report(tmp_path/'work'/f'page{i}.json', path) for i,path in enumerate(paths)]
    gui.staged.clear()
    for source, path in zip(paths, reports):
        # A failed page may have OCR data but no output PNG.
        gui.events.put({'source':str(source),'report':str(path),'output':str(path.with_suffix('.png')), 'state':'failed'})
    gui.poll()
    assert gui.latest_report == reports[1]
    gui.source_list.selection_set('history-0')
    gui.update_selection()
    gui.review_button.invoke()
    assert calls == [reports[0]]
    gui.source_list.selection_set('history-0', 'history-1')
    gui.update_selection()
    assert gui.review_button.instate(['disabled'])
    gui.review()
    assert calls == [reports[0]]
    assert '一張' in gui.status.get()


def test_review_readded_source_and_unprocessed_source(gui, tmp_path, monkeypatch):
    paths = add_pages(gui, tmp_path, 2)
    calls = capture_review(monkeypatch)
    saved = review_report(tmp_path/'translated'/'work'/'page1_繁中.json', paths[0])
    gui.source_list.selection_set('0')
    gui.update_selection()
    gui.review_button.invoke()
    assert calls == [saved]
    gui.source_list.selection_set('1')
    gui.update_selection()
    gui.review_button.invoke()
    assert calls == [saved]
    assert '尚無可修訂' in gui.status.get()


def test_review_reopen_uses_latest_saved_revision(gui, tmp_path, monkeypatch):
    import json
    from pathlib import Path
    paths = add_pages(gui, tmp_path, 1)
    calls = capture_review(monkeypatch)
    saved = review_report(tmp_path/'custom-output'/'work'/'first.json', paths[0])
    revised = review_report(saved.parent/'first_修訂.json', paths[0])
    os.utime(saved,(100,100))
    os.utime(revised,(200,200))
    batches = tmp_path/'state'/'batches'
    batches.mkdir(parents=True)
    (batches/'last.json').write_text(json.dumps({'schema':1,'status':'completed','pages':[
        {'source':str(paths[0]),'output':str(tmp_path/'no-png.png'),'report':str(saved),'state':'failed'}]}))
    root = tk.Toplevel(gui.root)
    try:
        reopened = offline_gui.OfflineGUI(root)
        reopened.source_list.selection_set('history-0')
        reopened.update_selection()
        reopened.review_button.invoke()
        assert calls == [revised]
    finally:
        root.destroy()


def test_primary_submits_checked_new_pages_and_keeps_unchecked_pages(gui, tmp_path):
    paths = add_pages(gui, tmp_path)
    gui.source_list.selection_set('1')
    gui.update_selection()
    assert gui.start_button['text'] == '開始翻譯（1）'
    gui.start_button.invoke()
    kind, submitted, glossary = gui.pending.get_nowait()
    assert kind == 'new' and submitted == [paths[1]]
    assert [job[1] for job in gui.staged] == [paths[0], paths[2]]
    assert gui.start_button['text'] == '停止'
    actions = gui.start_button.master.winfo_children()
    assert actions == [gui.start_button, gui.review_button]


@pytest.mark.skipif(sys.platform != "win32", reason="Windows checkbox retention")
def test_checked_image_survives_submission_progress_and_setup_failure(gui, tmp_path):
    paths = add_pages(gui, tmp_path)
    gui.source_list.selection_set("1")
    gui.update_selection()
    gui.primary_action()
    assert gui.selected_image_sources() == [paths[1]]
    assert gui.source_list.set(gui.source_list.selection()[0], "check") == "☑"
    gui.record_page(paths[1], "讀取日文對白", "running")
    assert gui.selected_image_sources() == [paths[1]]
    gui.handle_event({"error": "synthetic setup failure"})
    gui.handle_event({"restage": [("new", paths[1], False)]})
    gui.set_busy(False)
    assert gui.selected_image_sources() == [paths[1]]
    assert gui.source_list.set(gui.source_list.selection()[0], "check") == "☑"
    assert gui.start_button["text"] == "開始翻譯（1）"


@pytest.mark.skipif(sys.platform != "win32", reason="Windows checkbox retention")
def test_checked_image_does_not_jump_when_staged_rows_are_renumbered(gui, tmp_path):
    paths = add_pages(gui, tmp_path)
    gui.source_list.selection_set("1")
    gui.update_selection()
    gui.staged.pop(0)
    gui.refresh_staged()
    assert gui.source_list.selection() == ("0",)
    assert gui.selected_image_sources() == [paths[1]]
    gui.record_page(paths[2], "已輸出", "success")
    assert gui.selected_image_sources() == [paths[1]]


def test_macos_adapter_preserves_original_submit_selection_behavior(gui, tmp_path, monkeypatch):
    from src.platforms import macos

    monkeypatch.setattr("src.gui.staging.platform_support", macos)
    monkeypatch.setattr("src.gui.worker.platform_support", macos)
    paths = add_pages(gui, tmp_path)
    gui.source_list.selection_set("1")
    gui.update_selection()
    gui.primary_action()
    assert gui.pending.get_nowait() == ("new", [paths[1]], {})
    assert [job[1] for job in gui.staged] == [paths[0], paths[2]]
    assert not gui.source_list.selection()


def test_primary_combines_checked_new_and_problem_pages_without_repeating_success(gui, tmp_path):
    paths = add_pages(gui, tmp_path)
    gui.staged = [('new', paths[0], False)]
    gui.history = {str(paths[1]): ('失敗', 'failed'), str(paths[2]): ('已輸出', 'success')}
    gui.refresh_staged()
    gui.select_all()
    assert gui.start_button['text'] == '翻譯勾選（2）'
    gui.start_button.invoke()
    assert gui.pending.get_nowait() == ('new', [paths[0], paths[1]], {})
    assert not gui.staged
    assert gui.history[str(paths[2])][1] == 'success'


def test_primary_continues_latest_unfinished_batch_without_picker_or_new_names(gui, tmp_path, monkeypatch):
    import json
    paths = add_pages(gui, tmp_path, 2)
    gui.staged.clear()
    journal = tmp_path/'unfinished.json'
    journal.write_text(json.dumps({'schema': 1, 'status': 'stopped', 'glossary': {'old': '舊名'}, 'pages': [
        {'source': str(paths[0]), 'output': str(tmp_path/'out0.png'), 'state': 'success'},
        {'source': str(paths[1]), 'output': str(tmp_path/'out1.png'), 'state': 'waiting'},
    ]}))
    gui.latest_journal = journal
    gui.load_journal_rows(journal)
    gui.glossary.insert('1.0', 'invalid names draft')
    monkeypatch.setattr(filedialog, 'askopenfilename', lambda **kw: pytest.fail('No JSON picker'))
    gui.update_selection()
    assert gui.start_button['text'] == '繼續上次翻譯'
    gui.start_button.invoke()
    assert gui.pending.get_nowait() == ('resume', journal, False)
    assert not gui.settings.exists()
    assert gui.history[str(paths[0])][1] == 'success'


def test_primary_only_completed_selection_is_disabled(gui, tmp_path):
    paths = add_pages(gui, tmp_path, 1)
    gui.staged.clear()
    gui.history[str(paths[0])] = ('已輸出', 'success')
    gui.refresh_staged()
    gui.select_all()
    assert gui.start_button.instate(['disabled'])
    assert gui.review_button.instate(['!disabled'])
    gui.start_button.invoke()
    assert gui.pending.empty()


def test_translator_engine_and_model_are_selectable_and_saved(gui, monkeypatch):
    assert gui.provider_label.get().startswith("AGY")
    refreshed = []
    monkeypatch.setattr(gui, "refresh_model_list", lambda: refreshed.append(gui.provider_from_label()))
    gui.pipeline = object()
    gui.provider_label.set("Codex（ChatGPT）")
    gui.on_provider_selected()
    assert gui.pipeline is None and refreshed == ["codex"]
    gui.model_name.set("gpt-6-sol")
    gui.on_model_committed()
    assert gui.translator_choice() == ("codex", "gpt-6-sol")
    saved = json.loads(gui.settings.read_text(encoding="utf-8"))
    assert saved["translator_provider"] == "codex" and saved["translator_models"]["codex"] == "gpt-6-sol"
    gui.model_name.set("bad name;rm")
    gui.on_model_committed()
    assert gui.translator_choice() == ("codex", "gpt-6-sol") and "無法儲存" in gui.status.get()
    gui.set_busy(True)
    assert gui.provider_box.instate(["disabled"])


def test_model_queries_ignore_stale_responses_and_clear_previous_provider(gui, monkeypatch):
    gui.provider_label.set("Codex（ChatGPT）")
    gui.model_request_id = 2
    gui.show_model_list({"models": "codex", "request_id": 2, "items": [("new-model", "New")]})
    assert gui.model_box["values"] == ("new-model",)
    gui.show_model_list({"models": "codex", "request_id": 1, "items": [("old-model", "Old")]})
    assert gui.model_box["values"] == ("new-model",)
    monkeypatch.setattr(gui, "refresh_model_list", lambda: None)
    gui.provider_label.set("Claude Code")
    gui.on_provider_selected()
    assert not gui.model_box["values"]


def test_macos_catalog_refresh_failure_keeps_existing_choices(gui, monkeypatch):
    from src.platforms import macos
    monkeypatch.setattr("src.gui.settings.platform_support", macos)
    provider = gui.provider_from_label()
    model = gui.model_name.get()
    gui.show_model_list({"models": provider, "items": [("known-model", "Known")]})
    gui.show_model_list({"models": provider, "items": [], "error_text": "offline"})
    assert gui.model_box["values"] == ("known-model",)
    assert gui.model_name.get() == model
    assert "offline" in gui.status.get()


def test_windows_catalog_is_saved_reopened_and_retained_on_query_failure(gui, monkeypatch):
    from src.platforms import windows
    monkeypatch.setattr('src.gui.settings.platform_support', windows)
    provider = gui.provider_from_label()
    selected = gui.model_name.get()
    gui.show_model_list({'models': provider, 'items': [('model-one', 'One'), ('model-two', 'Two')]})
    saved = json.loads(gui.settings.read_text(encoding='utf-8'))
    assert saved['translator_model_catalogs'][provider] == ['model-one', 'model-two']
    assert gui.model_name.get() == selected
    gui.show_model_list({'models': provider, 'items': [], 'error_text': 'offline'})
    assert gui.model_box['values'] == ('model-one', 'model-two')
    other = tk.Toplevel(gui.root)
    try:
        reopened = offline_gui.OfflineGUI(other)
        queried = []
        monkeypatch.setattr(reopened, '_request_model_list', lambda **kw: queried.append(kw))
        other.update()
        assert reopened.model_box['values'] == ('model-one', 'model-two')
        assert not queried
        reopened.preferences['translator_model_catalogs']['codex'] = ['codex-test']
        monkeypatch.setattr(reopened, 'refresh_model_list', lambda: None)
        reopened.provider_label.set('Codex（ChatGPT）')
        reopened.on_provider_selected()
        assert reopened.model_box['values'] == ('codex-test',)
    finally:
        other.destroy()


def test_windows_queries_missing_catalog_automatically_and_ignores_corrupt_cache(gui, monkeypatch):
    from src.platforms import windows, macos
    monkeypatch.setattr('src.gui.settings.platform_support', windows)
    calls = []
    monkeypatch.setattr(gui, '_request_model_list', lambda **kw: calls.append(kw))
    gui.preferences['translator_model_catalogs'] = {gui.provider_from_label(): ['bad name', None]}
    gui.initialize_model_list()
    assert calls == [{'quiet': True}]
    gui.preferences['translator_model_catalogs'][gui.provider_from_label()] = ['safe-model', 'safe-model']
    assert gui.cached_model_names(gui.provider_from_label()) == ['safe-model']
    monkeypatch.setattr('src.gui.settings.platform_support', macos)
    assert not gui.cached_model_names(gui.provider_from_label())
    gui.initialize_model_list()
    assert calls == [{'quiet': True}]


@pytest.mark.skipif(sys.platform != 'win32', reason='Windows control behavior')
def test_blank_model_area_opens_picker_and_selection_is_saved(gui):
    box = gui.model_box
    box.configure(values=('pick-one', 'pick-two'))
    gui.model_name.set('pick-one')
    gui.root.update()
    heights = [control.winfo_height() for control in (gui.provider_box, box, gui.model_refresh_button)]
    assert max(heights) == min(heights)
    y = box.winfo_height() // 2
    x = box.winfo_width() - 35
    assert box.identify(x, y) == 'textarea'
    box.event_generate('<Button-1>', x=x, y=y)
    gui.root.update()
    popup = str(box.tk.call('ttk::combobox::PopdownWindow', str(box)))
    assert int(box.tk.call('winfo', 'ismapped', popup))
    listing = popup + '.f.l'
    option_bounds = box.tk.call(listing, 'bbox', 0)
    option_left = int(box.tk.call('winfo', 'rootx', listing)) + option_bounds[0]
    entry_left = box.winfo_rootx() + box.bbox(0)[0]
    assert option_left == entry_left, (option_left, entry_left, box.tk.call('grid', 'info', listing))
    # Posting an already mapped picker must not let Tk reset its left inset.
    box.tk.call('ttk::combobox::Post', str(box))
    gui.root.update()
    option_bounds = box.tk.call(listing, 'bbox', 0)
    assert int(box.tk.call('winfo', 'rootx', listing)) + option_bounds[0] == entry_left
    box.tk.call(listing, 'selection', 'clear', 0, 'end')
    box.tk.call(listing, 'selection', 'set', 1)
    box.tk.call('event', 'generate', listing, '<ButtonRelease-1>')
    gui.root.update()
    assert gui.model_name.get() == 'pick-two'
    assert gui.translator_choice()[1] == 'pick-two'
    assert not int(box.tk.call('winfo', 'ismapped', popup))
    # Clicking actual text keeps entry editing, rather than reopening the list.
    first = box.bbox(0)
    box.event_generate('<Button-1>', x=first[0] + 1, y=y)
    gui.root.update()
    assert not int(box.tk.call('winfo', 'ismapped', popup))
    box.insert('end', '-typed')
    assert gui.model_name.get() == 'pick-two-typed'
    # Native arrow posting resets list geometry; it must remain aligned too.
    # A longer catalog also exercises the native scrollbar layout.
    box.configure(values=('pick-two-typed',) + tuple(f'pick-{i}' for i in range(30)))
    box.event_generate('<Button-1>', x=box.winfo_width()-8, y=y)
    gui.root.update()
    assert int(box.tk.call('winfo', 'ismapped', popup + '.f.sb'))
    option_bounds = box.tk.call(listing, 'bbox', 0)
    assert int(box.tk.call('winfo', 'rootx', listing)) + option_bounds[0] == box.winfo_rootx() + box.bbox(0)[0]
    box.tk.call('ttk::combobox::Unpost', str(box))
    gui.set_busy(True)
    box.event_generate('<Button-1>', x=x, y=y)
    gui.root.update()
    assert not int(box.tk.call('winfo', 'ismapped', popup))


@pytest.mark.skipif(sys.platform != 'win32', reason='Windows native application icons')
def test_native_icons_use_separate_system_small_and_large_sizes(gui):
    import ctypes as c
    from ctypes import wintypes as w
    class IconInfo(c.Structure):
        _fields_ = [('is_icon', w.BOOL), ('x', w.DWORD), ('y', w.DWORD),
                    ('mask', w.HBITMAP), ('color', w.HBITMAP)]
    class Bitmap(c.Structure):
        _fields_ = [('kind', w.LONG), ('width', w.LONG), ('height', w.LONG),
                    ('stride', w.LONG), ('planes', w.WORD), ('depth', w.WORD), ('bits', c.c_void_p)]
    user32, gdi32 = c.windll.user32, c.windll.gdi32
    user32.GetAncestor.argtypes = [w.HWND, w.UINT]
    user32.GetAncestor.restype = w.HWND
    user32.SendMessageW.argtypes = [w.HWND, w.UINT, w.WPARAM, w.LPARAM]
    user32.SendMessageW.restype = c.c_ssize_t
    user32.GetIconInfo.argtypes = [w.HICON, c.POINTER(IconInfo)]
    gdi32.GetObjectW.argtypes = [w.HANDLE, c.c_int, c.c_void_p]
    gdi32.DeleteObject.argtypes = [w.HANDLE]
    window = user32.GetAncestor(gui.root.winfo_id(), 2)
    icons = []
    for kind, metric in ((0, 49), (1, 11)):
        icon = user32.SendMessageW(window, 0x7F, kind, 0)
        icons.append(icon)
        info, bitmap = IconInfo(), Bitmap()
        assert user32.GetIconInfo(icon, c.byref(info))
        try:
            assert gdi32.GetObjectW(info.color, c.sizeof(bitmap), c.byref(bitmap))
            size = user32.GetSystemMetrics(metric)
            assert (bitmap.width, bitmap.height, bitmap.depth) == (size, size, 32)
        finally:
            gdi32.DeleteObject(info.color)
            gdi32.DeleteObject(info.mask)
    assert icons[0] != icons[1]


@pytest.mark.skipif(sys.platform != 'win32', reason='Windows control behavior')
def test_blank_model_area_without_catalog_starts_query(gui, monkeypatch):
    queried = []
    monkeypatch.setattr(gui, 'refresh_model_list', lambda: queried.append(True))
    box = gui.model_box
    box.configure(values=())
    box.event_generate('<Button-1>', x=box.winfo_width()-35, y=box.winfo_height()//2)
    gui.root.update()
    assert queried == [True]


@pytest.mark.skipif(sys.platform != 'win32', reason='Windows generation controls')
def test_reasoning_and_fast_follow_model_capabilities_and_persist(gui):
    from src.offline.translators import PROVIDERS
    gui.provider_label.set(PROVIDERS['codex'])
    gui.model_name.set('gpt-6.1-sol')
    gui.apply_translator_choice('codex', 'gpt-6.1-sol')
    gui.show_model_list({'models': 'codex', 'items': [('gpt-6.1-sol', 'Sol'), ('gpt-5.5', 'Other')],
        'capabilities': {'gpt-6.1-sol': {'efforts': ['low', 'medium', 'high', 'xhigh', 'max'], 'fast': True},
                         'gpt-5.5': {'efforts': ['low', 'medium', 'high', 'xhigh'], 'fast': False}}})
    controls = gui.translation_controls
    gui.root.update()
    assert controls.frame.winfo_ismapped()
    assert controls.frame.master == gui.model_box.master
    assert controls.fast_button.winfo_ismapped()
    # Even at the minimum window width, the single row reserves room for
    # supported options and the query button; the model entry can shrink.
    width, height = gui.root.minsize()
    gui.root.geometry(f'{width}x{height}')
    gui.root.update()
    row_controls = (gui.provider_box, gui.model_box, controls.effort_box, gui.model_refresh_button)
    assert len({control.winfo_rooty() for control in row_controls}) == 1
    assert len({control.winfo_height() for control in row_controls}) == 1
    for left, right in zip(row_controls, row_controls[1:]):
        assert left.winfo_rootx() + left.winfo_width() <= right.winfo_rootx()
    assert gui.model_box.winfo_width() > 50
    for control in (controls.effort_box, controls.fast_button, gui.model_refresh_button):
        assert control.winfo_ismapped()
        assert control.winfo_width() == control.winfo_reqwidth()
    assert tuple(controls.effort_box.cget('values')) == ('CLI 預設', '輕', '中', '高', '極高', '最高')
    assert controls.fast.get() is False
    controls.effort.set('極高')
    controls.fast.set(True)
    controls.commit()
    assert gui.pipeline_choice() == ('codex', 'gpt-6.1-sol', 180, {'effort': 'xhigh', 'fast': True})
    saved = json.loads(gui.settings.read_text(encoding="utf-8"))
    assert saved['translator_options']['codex']['gpt-6.1-sol'] == {'effort': 'xhigh', 'fast': True}
    # Worker configuration must be readable without touching Tk from its thread.
    import threading
    choices = []
    worker = threading.Thread(target=lambda: choices.append(gui.pipeline_choice()))
    worker.start(); worker.join(timeout=1)
    assert choices == [('codex', 'gpt-6.1-sol', 180, {'effort': 'xhigh', 'fast': True})]
    gui.set_busy(True)
    assert controls.effort_box.instate(['disabled']) and controls.fast_button.instate(['disabled'])
    gui.set_busy(False)
    gui.model_name.set('gpt-5.5')
    gui.on_model_committed()
    gui.root.update()
    assert not controls.fast_button.winfo_ismapped()
    assert '最高' not in controls.effort_box.cget('values')
    assert controls.effort.get() == 'CLI 預設' and controls.fast.get() is False
    gui.model_name.set('gpt-6.1-sol')
    gui.on_model_committed()
    gui.root.update()
    assert controls.fast_button.winfo_ismapped()
    assert controls.effort.get() == '極高' and controls.fast.get() is True
    # Reloading preferences also restores the saved capabilities and choice.
    gui.load_preferences(gui.settings)
    controls.refresh()
    assert controls.effort.get() == '極高' and controls.fast.get() is True


@pytest.mark.skipif(sys.platform != 'win32', reason='Windows generation controls')
def test_claude_unsupported_settings_are_disabled_and_agy_keeps_model_picker(gui):
    from src.offline.translators import PROVIDERS
    controls = gui.translation_controls
    gui.provider_label.set(PROVIDERS['claude'])
    gui.model_name.set('claude-sonnet-5-5')
    gui.apply_translator_choice('claude', 'claude-sonnet-5-5')
    gui.show_model_list({'models': 'claude', 'items': [('claude-sonnet-5-5', 'Sonnet'), ('haiku', 'Haiku')],
        'capabilities': {'claude-sonnet-5-5': {'efforts': ['low', 'medium', 'high', 'xhigh', 'max'], 'fast': False},
                         'haiku': {'efforts': [], 'fast': False}}})
    assert controls.effort_box.instate(['readonly']) and controls.fast_button.instate(['disabled'])
    gui.root.update()
    assert not controls.fast_button.winfo_ismapped()
    assert controls.fast_button.cget('text') == 'Fast（額外計費）'
    gui.model_name.set('haiku'); gui.on_model_committed()
    assert controls.effort_box.instate(['disabled']) and controls.fast_button.instate(['disabled'])
    gui.provider_label.set(PROVIDERS['agy'])
    gui.on_provider_selected(); gui.root.update()
    assert controls.frame.winfo_ismapped()
    assert controls.fast_button.instate(['disabled'])
    assert not controls.fast_button.winfo_ismapped()
    assert len(gui.pipeline_choice()) == 2


@pytest.mark.skipif(sys.platform != 'win32', reason='Windows generation controls')
def test_reasoning_save_failure_keeps_previous_settings(gui, monkeypatch):
    from src.offline.translators import PROVIDERS
    gui.provider_label.set(PROVIDERS['codex']); gui.model_name.set('test-model')
    gui.apply_translator_choice('codex', 'test-model')
    gui.show_model_list({'models': 'codex', 'items': [('test-model', 'Test')],
                         'capabilities': {'test-model': {'efforts': ['low', 'high'], 'fast': True}}})
    def fail(**kwargs):
        raise OSError('read-only')
    monkeypatch.setattr(gui, 'write_settings', fail)
    controls = gui.translation_controls
    controls.effort.set('高'); controls.fast.set(True); controls.commit()
    assert controls.effort.get() == 'CLI 預設' and controls.fast.get() is False
    assert gui.pipeline_choice()[-1] == {'effort': None, 'fast': False}
    assert '無法儲存' in gui.status.get()


@pytest.mark.skipif(sys.platform != 'win32', reason='Windows generation controls')
def test_old_model_cache_automatically_loads_missing_capabilities_once(gui, monkeypatch):
    from src.offline.translators import PROVIDERS
    gui.provider_label.set(PROVIDERS['codex'])
    gui.preferences['translator_model_catalogs'] = {'codex': ['test-model']}
    gui.preferences['translator_model_capabilities'] = {}
    calls = []
    monkeypatch.setattr(gui, '_request_model_list', lambda **kwargs: calls.append(kwargs))
    gui.initialize_model_list()
    assert calls == [{'quiet': True}]
    gui.preferences['translator_model_capabilities']['codex'] = {'test-model': {'efforts': ['low'], 'fast': True}}
    gui.initialize_model_list()
    assert len(calls) == 1


@pytest.mark.skipif(sys.platform != 'win32', reason='Windows Claude alias controls')
def test_claude_alias_loads_effort_from_metadata_and_migrates_old_cache(gui, monkeypatch):
    from src.offline.translators import PROVIDERS
    gui.provider_label.set(PROVIDERS['claude'])
    gui.model_name.set('sonnet')
    gui.apply_translator_choice('claude', 'sonnet')
    caps = {'efforts': ['low', 'medium', 'high', 'xhigh', 'max'], 'fast': False}
    gui.preferences['translator_model_catalogs'] = {'claude': ['claude-sonnet-current']}
    gui.preferences['translator_model_capabilities'] = {'claude': {'claude-sonnet-current': caps}}
    calls = []
    monkeypatch.setattr(gui, '_request_model_list', lambda **kwargs: calls.append(kwargs))
    gui.initialize_model_list()
    assert calls == [{'quiet': True}]
    gui.show_model_list({'models': 'claude', 'items': [('claude-sonnet-current', 'Sonnet')],
                         'capabilities': {'claude-sonnet-current': caps, 'sonnet': caps}})
    controls = gui.translation_controls
    assert controls.effort_box.instate(['readonly'])
    assert tuple(controls.effort_box.cget('values')) == ('CLI 預設', '輕', '中', '高', '極高', '最高')
    controls.effort.set('極高'); controls.commit()
    assert gui.model_name.get() == 'sonnet'
    assert gui.pipeline_choice() == ('claude', 'sonnet', 180, {'effort': 'xhigh', 'fast': False})
    gui.load_preferences(gui.settings)
    controls.refresh()
    assert controls.effort.get() == '極高'
    gui.initialize_model_list()
    assert len(calls) == 1
    # An unrelated custom model must not borrow Sonnet's capabilities.
    gui.model_name.set('sonnet-custom'); gui.on_model_committed()
    assert controls.effort_box.instate(['disabled'])
    assert gui.pipeline_choice()[-1] == {'effort': None, 'fast': False}


@pytest.mark.skipif(sys.platform != 'win32', reason='Windows AGY effort controls')
def test_agy_effort_switches_real_model_and_restores_saved_choice(gui):
    from src.offline.agy_provider import model_capabilities
    names = ['gemini-3.8-flash-high', 'gemini-3.8-flash-medium', 'gemini-3.8-flash-low',
             'gemini-3.1-pro-high', 'gemini-3.1-pro-low']
    gui.apply_translator_choice('agy', 'gemini-3.8-flash-medium')
    gui.model_name.set('gemini-3.8-flash-medium')
    gui.show_model_list({'models': 'agy', 'items': [(name, name) for name in names],
                         'capabilities': model_capabilities(names)})
    controls = gui.translation_controls
    assert controls.effort.get() == '中'
    assert tuple(controls.effort_box.cget('values')) == ('輕', '中', '高')
    assert controls.fast_button.instate(['disabled']) and controls.fast.get() is False
    controls.effort.set('輕'); controls.commit()
    assert gui.model_name.get() == 'gemini-3.8-flash-low'
    assert gui.pipeline_choice() == ('agy', 'gemini-3.8-flash-low')
    assert json.loads(gui.settings.read_text(encoding="utf-8"))['translator_models']['agy'] == 'gemini-3.8-flash-low'
    # Selecting a complete model id updates the separate effort picker too.
    gui.model_name.set('gemini-3.1-pro-high'); gui.on_model_committed()
    assert controls.effort.get() == '高'
    assert tuple(controls.effort_box.cget('values')) == ('輕', '高')
    controls.effort.set('中'); controls.commit()
    assert gui.model_name.get() == 'gemini-3.1-pro-high'
    gui.load_preferences(gui.settings); controls.refresh()
    assert controls.effort.get() == '高'
    gui.set_busy(True)
    controls.effort.set('輕'); controls.commit()
    assert gui.pipeline_choice() == ('agy', 'gemini-3.1-pro-high')
    gui.set_busy(False)
    assert controls.effort.get() == '高'


@pytest.mark.skipif(sys.platform != 'win32', reason='Windows AGY effort controls')
def test_agy_old_cache_supports_effort_and_save_failure_keeps_selected_model(gui, monkeypatch):
    gui.preferences['translator_model_catalogs'] = {'agy': ['gemini-3.8-flash-low', 'gemini-3.8-flash-high']}
    gui.preferences['translator_model_capabilities'] = {}
    gui.model_name.set('gemini-3.8-flash-high')
    gui.apply_translator_choice('agy', 'gemini-3.8-flash-high')
    controls = gui.translation_controls
    assert tuple(controls.effort_box.cget('values')) == ('輕', '高')
    def fail(**kwargs):
        raise OSError('read-only')
    monkeypatch.setattr(gui, 'write_settings', fail)
    controls.effort.set('輕'); controls.commit()
    assert gui.model_name.get() == 'gemini-3.8-flash-high'
    assert controls.effort.get() == '高'
    assert gui.pipeline_choice() == ('agy', 'gemini-3.8-flash-high')
    assert '無法儲存 AGY' in gui.status.get()
