"""Native desktop checks; opt in with COMIC_GUI_TESTS=1 on a desktop session."""
import os
import json
import tkinter as tk
from tkinter import filedialog, font as tkfont

import pytest
from PIL import Image

import offline_gui

pytestmark = pytest.mark.skipif(os.environ.get("COMIC_GUI_TESTS") != "1", reason="requires a desktop Tk session")


@pytest.fixture
def gui(tmp_path, monkeypatch):
    monkeypatch.setattr("src.gui.app.STATE_ROOT", tmp_path / "state")
    monkeypatch.setattr("src.offline.fonts.resolve_font", lambda _: None)
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
    assert "栗邦邦" in gui.settings.read_text()
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
    saved = json.loads(gui.settings.read_text())
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
    assert json.loads(gui.settings.read_text())["output_directory"] == str(chosen)
    gui.reset_output_button.invoke()
    saved = json.loads(gui.settings.read_text())
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
    for index in range(8):
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
    saved = review_report(tmp_path/'translated'/'工作資料'/'page1_繁中.json', paths[0])
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
    saved = review_report(tmp_path/'custom-output'/'工作資料'/'first.json', paths[0])
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
