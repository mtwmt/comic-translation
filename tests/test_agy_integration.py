"""Offline-only integration checks; fake translations are not quality evidence."""
import json
import queue
import sys
import threading
import tkinter.filedialog
import tkinter.messagebox
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest
from PIL import Image

from src.offline import pipeline as pipeline_module
from src.offline import models as model_module
from src.offline.batch import BatchRunner, create_batch
from src.offline.models import ModelError


class FakeTranslator:
    def __init__(self, level="medium"):
        self.fingerprint = {"provider": "agy", "model": "test-flash", "thinking": level}
        self.calls = []
        self.preflights = 0
        self.failure = None

    def preflight(self):
        self.preflights += 1
        if self.failure:
            raise ModelError(self.failure)

    def translate(self, records, glossary):
        self.calls.append((records, dict(glossary)))
        return {record["id"]: "你好！" for record in records}


@pytest.fixture
def fake_vision(monkeypatch):
    calls = {"verify": [], "detect": 0, "recognize": 0, "local_translate": 0}

    def verify(root):
        calls["verify"].append(False)
        return "vision-model-hash"

    class Vision:
        def __init__(self, root):
            pass

        def detect(self, image):
            calls["detect"] += 1
            return []

        def recognize(self, image):
            calls["recognize"] += 1
            return "こんにちは。"

        def translate(self, records, glossary):
            calls["local_translate"] += 1
            return {record["id"]: "本機譯文" for record in records}

    def regions(image, detections):
        return [{"id": "r1", "status": "pending", "bbox": [2, 2, 8, 8]}], np.zeros((image.height, image.width))

    def render(image, region, labels, font):
        output = image.copy()
        output.putpixel((3, 3), (0, 0, 0))
        mask = np.zeros((image.height, image.width), dtype=bool)
        mask[3, 3] = True
        return output, mask

    monkeypatch.setattr(pipeline_module, "verify_models", verify)
    monkeypatch.setattr(pipeline_module, "version", lambda name: "fake-1.0")
    monkeypatch.setattr(pipeline_module, "resolve_font", lambda root: (Path("fixture.ttf"), {"family": "fixture"}))
    monkeypatch.setattr(pipeline_module, "LocalModels", Vision)
    monkeypatch.setattr(pipeline_module, "find_regions", regions)
    monkeypatch.setattr(pipeline_module, "render_region", render)
    return calls


def make_source(tmp_path, name="page.png"):
    source = tmp_path / name
    Image.new("RGB", (12, 12), "white").save(source)
    return source


def test_agy_pipeline_uses_only_vision_models_and_cloud_translator(tmp_path, fake_vision):
    translator = FakeTranslator()
    pipeline = pipeline_module.TranslationPipeline(tmp_path / "models", translator=translator)
    source = make_source(tmp_path)
    stages = []
    image, report, mask = pipeline.process(source, {"太郎": "太郎"}, stages.append)

    assert fake_vision["verify"] == [False]
    assert "llama-cpp-python" not in pipeline.fingerprint["dependencies"]
    assert pipeline.fingerprint["translator"] == translator.fingerprint
    assert translator.preflights >= 1
    assert translator.calls == [([{"id": "r1", "text": "こんにちは。"}], {"太郎": "太郎"})]
    assert fake_vision["local_translate"] == 0
    assert report["status"] == "success"
    assert report["regions"][0]["translation"] == "你好！"
    assert report["glossary"] == {"太郎": "太郎"}
    assert report["regions"][0]["protected_terms"] == ["太郎"]
    assert report["fingerprint"]["translator"] == translator.fingerprint
    assert image.size == (12, 12)
    assert mask.getbbox() == (3, 3, 4, 4)
    assert "本機翻譯" not in stages


def test_pipeline_without_translator_only_allows_local_analysis(tmp_path, fake_vision):
    pipeline = pipeline_module.TranslationPipeline(tmp_path / "models")
    source = make_source(tmp_path)
    with pytest.raises(ValueError, match="需要設定翻譯引擎"):
        pipeline.process(source, {})
    image, report, mask = pipeline.process(source, {}, analyze_only=True)
    assert fake_vision["verify"] == [False]
    assert "llama-cpp-python" not in pipeline.fingerprint["dependencies"]
    assert fake_vision["local_translate"] == 0
    assert pipeline.font is None
    assert image is None and not mask.getbbox()
    assert report["mode"] == "analysis" and report["text_translated"] == 0
    assert report["regions"][0]["original"] == "こんにちは。"


def test_agy_preflight_failure_does_not_run_ocr_or_fallback(tmp_path, fake_vision):
    translator = FakeTranslator()
    pipeline = pipeline_module.TranslationPipeline(tmp_path / "models", translator=translator)
    translator.failure = "AGY quota exhausted"
    with pytest.raises(ModelError, match="quota"):
        pipeline.process(make_source(tmp_path), {})
    assert fake_vision["detect"] == 0
    assert fake_vision["recognize"] == 0
    assert fake_vision["local_translate"] == 0
    assert translator.calls == []


def test_agy_translation_failure_propagates_instead_of_returning_original(tmp_path, fake_vision):
    class QuotaTranslator(FakeTranslator):
        def translate(self, records, glossary):
            raise ModelError("AGY quota exhausted")

    pipeline = pipeline_module.TranslationPipeline(tmp_path / "models", translator=QuotaTranslator())
    with pytest.raises(ModelError, match="quota"):
        pipeline.process(make_source(tmp_path), {})
    assert fake_vision["local_translate"] == 0


def test_agy_model_and_thinking_change_batch_fingerprint(tmp_path, fake_vision):
    medium = pipeline_module.TranslationPipeline(tmp_path / "models", translator=FakeTranslator("medium"))
    high = pipeline_module.TranslationPipeline(tmp_path / "models", translator=FakeTranslator("high"))
    journal = create_batch([make_source(tmp_path)], medium.fingerprint, {}, state_root=tmp_path / "state")
    with pytest.raises(ValueError, match="版本"):
        BatchRunner(high).run(journal)
    assert fake_vision["detect"] == 0


def test_agy_batch_pause_and_resume_preserves_completed_pages(tmp_path, fake_vision):
    class IntermittentTranslator(FakeTranslator):
        paused = False

        def translate(self, records, glossary):
            if len(self.calls) == 1 and not self.paused:
                self.paused = True
                raise ModelError("AGY quota exhausted; retry after reset")
            return super().translate(records, glossary)

    translator = IntermittentTranslator()
    pipeline = pipeline_module.TranslationPipeline(tmp_path / "models", translator=translator)
    inputs = [make_source(tmp_path, f"page{i}.png") for i in range(1, 4)]
    journal = create_batch(inputs, pipeline.fingerprint, {}, state_root=tmp_path / "state")
    events = []
    stopped = BatchRunner(pipeline, events.append).run(journal)
    saved = json.loads(journal.read_text())
    completed = Path(saved["pages"][0]["output"])
    original_bytes = completed.read_bytes()

    assert stopped["status"] == "stopped"
    assert [page["state"] for page in saved["pages"]] == ["success", "stopped", "waiting"]
    assert not Path(saved["pages"][1]["output"]).exists()
    assert any(event.get("systemic") for event in events)
    assert fake_vision["local_translate"] == 0

    resumed = BatchRunner(pipeline).run(journal)
    assert resumed == {"status": "completed", "counts": {"success": 3}, "skipped": 1}
    assert len(translator.calls) == 3
    assert completed.read_bytes() == original_bytes
    assert fake_vision["local_translate"] == 0


def vision_manifest(tmp_path):
    files = {}
    required = ["detector/inference.pdiparams", "detector/inference.json", "detector/inference.yml",
                "ocr/pytorch_model.bin", "font/NotoSerifCJKtc-Regular.otf", "font/OFL.txt"]
    for name in required:
        path = tmp_path / name
        path.parent.mkdir(exist_ok=True)
        path.write_bytes(b"synthetic-test-model")
        files[name] = model_module.sha256(path)
    manifest = {"schema": 1, "specs": model_module.MODEL_SPECS,
                "font_revision": "Serif2.003", "files": files}
    model_module.atomic_json(tmp_path / "manifest.json", manifest)
    return manifest


def test_cloud_verification_accepts_no_local_llm_but_rejects_bad_vision(tmp_path):
    vision_manifest(tmp_path)
    assert model_module.verify_models(tmp_path)
    (tmp_path / "ocr/pytorch_model.bin").write_bytes(b"corrupt")
    with pytest.raises(ModelError):
        model_module.verify_models(tmp_path)


def test_cloud_model_hash_does_not_depend_on_unused_local_llm(tmp_path):
    manifest = vision_manifest(tmp_path)
    initial = model_module.verify_models(tmp_path)
    manifest["specs"] = {**manifest["specs"], "translator": ["retired-model", "old-revision", []]}
    manifest["files"]["translator/Qwen3-4B-Q4_K_M.gguf"] = "missing-unused-file"
    model_module.atomic_json(tmp_path / "manifest.json", manifest)
    assert model_module.verify_models(tmp_path) == initial


def make_headless_gui(tmp_path):
    import offline_gui

    gui = offline_gui.OfflineGUI.__new__(offline_gui.OfflineGUI)
    gui.settings = tmp_path / "settings.json"
    gui.preferences = {}
    gui.output_directory = None
    gui.glossary = SimpleNamespace(get=lambda *args: "太郎=太郎")
    gui.pending = queue.Queue()
    gui.staged = []
    gui.history = {}
    gui.history_ids = {}
    gui.update_name_count = lambda: None
    gui.busy = False
    gui.status = SimpleNamespace(set=lambda text: None)
    gui.refresh_staged = lambda: None
    gui.append = lambda text: None
    gui.starts = []
    gui.start_worker = lambda: gui.starts.append(True)
    return offline_gui, gui


def test_save_character_names_without_starting_translation(tmp_path):
    _, gui = make_headless_gui(tmp_path)
    gui.glossary = SimpleNamespace(get=lambda *args: "マリオ=瑪利歐\nピーチ=碧姬公主")
    gui.save_glossary()
    assert json.loads(gui.settings.read_text())["glossary"] == "マリオ=瑪利歐\nピーチ=碧姬公主"
    assert gui.pending.empty() and not gui.starts


def test_invalid_character_names_leave_saved_mapping_intact(tmp_path):
    _, gui = make_headless_gui(tmp_path)
    gui.save_glossary()
    original = gui.settings.read_bytes()
    messages = []
    gui.status = SimpleNamespace(set=messages.append)
    gui.glossary = SimpleNamespace(get=lambda *args: "マリオ")
    gui.save_glossary()
    assert gui.settings.read_bytes() == original
    assert messages and not gui.starts


def test_gui_progress_keeps_page_count_during_slow_translation(tmp_path):
    _, gui = make_headless_gui(tmp_path)
    values, labels, statuses = {}, [], []
    gui.progress_bar = SimpleNamespace(configure=lambda **kw: values.update(kw))
    gui.progress_text = SimpleNamespace(set=labels.append)
    gui.status = SimpleNamespace(set=statuses.append)
    gui.update_progress({'progress': 3, 'total': 6})
    gui.update_progress({'index': 4, 'total': 6, 'source': 'page4.jpg', 'stage': 'AGY 3.8 Medium 翻譯（僅傳文字）'})
    assert values['value'] == 50
    assert labels[-1] == '已處理 3／6 張（50%）'
    assert statuses[-1] == '第 4 張：page4.jpg｜翻譯對白'


def test_gui_stages_without_popup_or_processing_until_start(tmp_path, monkeypatch):
    module, gui = make_headless_gui(tmp_path)
    monkeypatch.setattr(tkinter.messagebox, "askyesno", lambda *args, **kwargs: pytest.fail("No modal consent prompt"))
    monkeypatch.setattr(tkinter.filedialog, "askopenfilename", lambda **kwargs: str(tmp_path / "batch.json"))
    source = make_source(tmp_path)
    gui.add([source])
    gui.add([source])
    assert len(gui.staged) == 1  # duplicate source is not added again
    assert gui.pending.empty()
    assert gui.starts == []
    assert len(gui.staged) == 1
    gui.start_translation()
    assert gui.starts == [True]
    assert gui.staged == []


def test_gui_only_start_button_submits_confirmed_sources(tmp_path, monkeypatch):
    module, gui = make_headless_gui(tmp_path)
    monkeypatch.setattr(tkinter.messagebox, "askyesno", lambda *args, **kwargs: pytest.fail("No modal consent prompt"))
    monkeypatch.setattr(tkinter.filedialog, "askopenfilename", lambda **kwargs: str(tmp_path / "batch.json"))
    one, two = make_source(tmp_path, "one.png"), make_source(tmp_path, "two.png")
    gui.add([one])
    gui.add([two])
    assert gui.pending.empty() and gui.starts == []
    gui.start_translation()
    assert gui.pending.get() == ("new", [one, two], {"太郎": "太郎"})
    assert gui.pending.empty()
    assert gui.starts == [True] and gui.staged == []
    gui.start_translation()  # double click cannot submit twice
    assert gui.starts == [True]


def test_gui_removing_staged_sources_does_not_process_them(tmp_path):
    _, gui = make_headless_gui(tmp_path)
    one, two = make_source(tmp_path, "one.png"), make_source(tmp_path, "two.png")
    gui.add([one, two])
    gui.source_list = SimpleNamespace(selection=lambda: ['0'])
    gui.remove_staged()
    assert gui.staged == [("new", two, False)]
    gui.clear_staged()
    gui.start_translation()
    assert gui.pending.empty() and gui.starts == []


def test_gui_validation_failure_retains_staged_sources(tmp_path):
    _, gui = make_headless_gui(tmp_path)
    source = make_source(tmp_path)
    gui.add([source])
    gui.glossary = SimpleNamespace(get=lambda *args: "invalid glossary")
    gui.start_translation()
    assert len(gui.staged) == 1 and gui.pending.empty() and gui.starts == []


@pytest.mark.parametrize("destination", ["default", "custom", "source"])
def test_gui_output_submission_writes_to_selected_location(tmp_path, monkeypatch, destination):
    module, gui = make_headless_gui(tmp_path)
    folder = tmp_path / "chapter"
    source = folder / "part1" / "page.png"
    source.parent.mkdir(parents=True)
    Image.new("RGB", (30, 30), "white").save(source)
    chosen = None if destination == "default" else folder if destination == "source" else tmp_path / "匯出 資料夾"
    gui.output_directory = chosen
    gui.add([folder])
    gui.start_translation()
    # Work uses the submitted destination, independent of later preferences.
    gui.output_directory = tmp_path / "later"
    gui.pipeline = SimpleNamespace(fingerprint={"test": 1}, process=lambda *args, **kwargs: (
        Image.new("RGB", (30, 30), "white"), {"status": "success", "translated": 1}, Image.new("L", (30, 30))))
    gui.events = queue.Queue()
    gui.stop_requested = threading.Event()
    monkeypatch.setattr("src.gui.worker.create_batch", lambda *args, **kwargs: create_batch(
        *args, **kwargs, state_root=tmp_path / "state"))
    gui.work()
    events = list(gui.events.queue)
    assert not any("error" in event for event in events)
    journal = Path(next(event["journal"] for event in events if "journal" in event))
    page = json.loads(journal.read_text())["pages"][0]
    base = chosen or folder / "translated"
    assert Path(page["output"]).parent == base / "part1" / "final"
    assert Path(page["output"]).is_file()
    assert Path(page["report"]).parent == base / "part1" / "work"
    assert Path(page["report"]).is_file()
    assert not (tmp_path / "later").exists()


def test_gui_resume_keeps_original_output_after_preference_change(tmp_path, monkeypatch):
    module, gui = make_headless_gui(tmp_path)
    source = make_source(tmp_path)
    gui.pipeline = SimpleNamespace(fingerprint={"test": 1}, process=lambda *args, **kwargs: (
        Image.new("RGB", (30, 30), "white"), {"status": "success", "translated": 1}, Image.new("L", (30, 30))))
    journal = create_batch([source], gui.pipeline.fingerprint, {"old": "舊名"},
                           output=tmp_path / "old", state_root=tmp_path / "state")
    original_output = json.loads(journal.read_text())["pages"][0]["output"]
    gui.output_directory = tmp_path / "new"
    gui.batch_output = gui.output_directory
    gui.pending.put(("resume", journal, False))
    gui.events = queue.Queue()
    gui.stop_requested = threading.Event()
    monkeypatch.setattr("src.gui.worker.create_batch", lambda *args, **kwargs: pytest.fail("Resume must keep its journal"))
    gui.work()
    assert not any("error" in event for event in list(gui.events.queue))
    data = json.loads(journal.read_text())
    assert data["status"] == "completed" and data["glossary"] == {"old": "舊名"}
    assert data["pages"][0]["output"] == original_output
    assert Path(original_output).is_file()
    assert not gui.output_directory.exists()


def test_adding_during_processing_waits_for_another_start(tmp_path):
    _, gui = make_headless_gui(tmp_path)
    gui.busy = True
    gui.add([make_source(tmp_path)])
    gui.start_translation()
    assert gui.starts == [] and gui.pending.empty()
    gui.busy = False
    gui.check_idle = lambda: None
    assert len(gui.staged) == 1


@pytest.mark.parametrize("command", ["translate", "resume"])
def test_cli_agy_without_explicit_cloud_consent_rejects_before_pipeline(monkeypatch, capsys, command):
    import offline

    def forbidden_pipeline(*args, **kwargs):
        pytest.fail("Cloud consent must be checked before any pipeline setup")

    monkeypatch.setattr(pipeline_module, "TranslationPipeline", forbidden_pipeline)
    monkeypatch.setattr(sys, "argv", ["offline.py", command, "unused-input"])
    with pytest.raises(SystemExit) as error:
        offline.main()
    assert error.value.code == 2
    assert "需要 --allow-cloud-text" in capsys.readouterr().err


def test_gui_worker_builds_agy_pipeline_by_default(tmp_path, monkeypatch):
    from src.offline import translators

    _, gui = make_headless_gui(tmp_path)
    gui.pipeline = None
    gui.events = queue.Queue()
    gui.stop_requested = threading.Event()
    translator = FakeTranslator()
    created = []
    monkeypatch.setattr(translators, "create_translator", lambda provider, model: translator)
    monkeypatch.setattr(pipeline_module, "TranslationPipeline",
                        lambda models, translator=None: created.append(translator) or SimpleNamespace())
    gui.work()
    assert created == [translator]
    assert not any("error" in event for event in list(gui.events.queue))


@pytest.mark.parametrize("command", ["translate", "resume"])
def test_cli_explicit_cloud_consent_routes_to_agy(monkeypatch, tmp_path, command):
    import offline
    from src.offline import batch, translators

    translator = FakeTranslator()
    created = []
    ran = []
    journal = tmp_path / "batch.json"
    monkeypatch.setattr(translators, "translator_from_settings", lambda: translator)
    monkeypatch.setattr(pipeline_module, "TranslationPipeline",
                        lambda models, translator=None: created.append(translator) or SimpleNamespace(fingerprint={}))
    monkeypatch.setattr(batch, "create_batch", lambda *args, **kwargs: journal)
    monkeypatch.setattr(batch, "BatchRunner", lambda *args, **kwargs: SimpleNamespace(
        run=lambda journal, **options: ran.append(journal) or {"status": "completed"}))
    monkeypatch.setattr(sys, "argv", ["offline.py", command, str(journal), "--allow-cloud-text"])
    offline.main()
    assert created == [translator]
    assert ran == [journal]


def test_prepare_preserves_existing_full_model_manifest_and_agy_hash(tmp_path, monkeypatch):
    import huggingface_hub

    manifest = vision_manifest(tmp_path)
    translator = tmp_path / "translator/Qwen3-4B-Q4_K_M.gguf"
    translator.parent.mkdir()
    translator.write_bytes(b"existing-local-translator")
    manifest["files"]["translator/Qwen3-4B-Q4_K_M.gguf"] = model_module.sha256(translator)
    model_module.atomic_json(tmp_path / "manifest.json", manifest)
    original_manifest = (tmp_path / "manifest.json").read_bytes()
    original_hash = model_module.verify_models(tmp_path)
    downloads = []
    monkeypatch.setattr(huggingface_hub, "snapshot_download", lambda repo, **kwargs: downloads.append(repo))

    model_module.prepare_models(tmp_path)

    assert downloads == [model_module.MODEL_SPECS[name][0] for name in ("detector", "ocr")]
    assert model_module.verify_models(tmp_path) == original_hash
    assert (tmp_path / "manifest.json").read_bytes() == original_manifest


def test_fresh_prepare_only_downloads_vision_and_needs_no_external_font(tmp_path, monkeypatch):
    import huggingface_hub
    import urllib.request

    downloads = []

    def download(repo, *, local_dir, **kwargs):
        downloads.append(repo)
        local_dir.mkdir()
        names = ["inference.pdiparams", "inference.json", "inference.yml"] if local_dir.name == "detector" else ["pytorch_model.bin"]
        for name in names:
            (local_dir / name).write_bytes(b"synthetic-test-model")

    monkeypatch.setattr(huggingface_hub, "snapshot_download", download)
    monkeypatch.setattr(urllib.request, "urlretrieve", lambda *a: pytest.fail("Fonts must be bundled"))
    model_module.prepare_models(tmp_path)
    assert downloads == [model_module.MODEL_SPECS[name][0] for name in ("detector", "ocr")]
    assert model_module.verify_models(tmp_path)
    assert not (tmp_path / "font").exists() and not (tmp_path / "translator").exists()


@pytest.mark.parametrize("contents", ["null", "{}", '{"schema":1,"specs":{},"files":{}}', "invalid JSON"])
def test_unreadable_or_incomplete_vision_manifest_stops_batch(tmp_path, contents):
    (tmp_path / "manifest-vision.json").write_text(contents)
    with pytest.raises(ModelError):
        model_module.verify_models(tmp_path)


def test_agy_failure_without_init_is_systemic_not_bad_translation():
    from src.offline.agy_provider import parse_translation

    stdout = json.dumps({"event": "result", "result": {"status": "ERROR", "response": "quota exhausted"}})
    with pytest.raises(ModelError):
        parse_translation(stdout, [{"id": "r1", "text": "こんにちは。"}], {})


@pytest.mark.parametrize("stopped_by_user", [False, True])
def test_gui_stopped_batch_does_not_automatically_launch_pending_queue(tmp_path, stopped_by_user):
    _, gui = make_headless_gui(tmp_path)
    gui.worker = None
    gui.stop_requested = threading.Event()
    if stopped_by_user:
        gui.stop_requested.set()
    gui.events = queue.Queue()
    gui.events.put({"summary": {"status": "stopped", "counts": {"stopped": 1}}})
    gui.events.put({"done": True})
    gui.pending.put(("new", [tmp_path / "later.png"], {}))
    gui.had_error = False
    gui.root = SimpleNamespace(after=lambda *args: None)
    gui.status = SimpleNamespace(set=lambda text: None)
    gui.set_busy = lambda busy: None
    gui.poll()
    gui.check_idle()
    assert gui.had_error
    assert gui.starts == []
    assert gui.pending.qsize() == 1


@pytest.mark.skipif(sys.platform == "win32", reason="POSIX process-group cancellation")
@pytest.mark.parametrize("interruption", [KeyboardInterrupt, SystemExit])
def test_cli_keyboard_interrupt_cleans_up_agy_process_group(monkeypatch, interruption):
    from src.offline import agy_provider, cli_common

    class Process:
        pid = 1234567
        returncode = None
        calls = 0

        def communicate(self, input=None, timeout=None):
            self.calls += 1
            if self.calls == 1:
                raise interruption
            return "", ""

    process = Process()
    killed = []
    monkeypatch.setattr(cli_common.subprocess, "Popen", lambda *args, **kwargs: process)
    monkeypatch.setattr(cli_common.os, "killpg", lambda pid, signal: killed.append((pid, signal)))
    translator = agy_provider.AgyTranslator.__new__(agy_provider.AgyTranslator)
    translator.executable = "/unused/fake-agy"
    with pytest.raises(interruption):
        translator._run(["-p", "synthetic"], 10)
    assert killed and killed[0][0] == process.pid
    assert process.calls == 2


def test_gui_setup_failure_returns_sources_to_visible_staging(tmp_path, monkeypatch):
    from src.offline import translators
    _, gui = make_headless_gui(tmp_path)
    source = make_source(tmp_path)
    gui.pipeline = None
    gui.events = queue.Queue()
    gui.stop_requested = threading.Event()
    gui.pending.put(('new', [source], {}))
    monkeypatch.setattr(translators, 'create_translator', lambda provider, model: FakeTranslator())
    def fail_setup(*args, **kwargs):
        raise ModelError('models unavailable')
    monkeypatch.setattr(pipeline_module, 'TranslationPipeline', fail_setup)
    gui.work()
    events = list(gui.events.queue)
    assert {'restage': [('new', source, False)]} in events
    assert {'error': 'models unavailable'} in events
    assert gui.pending.empty()
