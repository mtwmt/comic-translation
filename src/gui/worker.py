"""Translation worker thread, event polling and the primary Start/Stop button."""
from __future__ import annotations

import json
import queue
import threading
import time
from pathlib import Path

from src.offline.cli_common import CliNotInstalled
from src.offline.batch import BatchRunner, create_batch, discover, parse_glossary
from src.gui.staging import STATE_LABELS

ROOT = Path(__file__).resolve().parents[2]

STAGE_NAMES = {"偵測文字": "尋找對話文字", "日文辨識": "讀取日文對白",
               "清字與排版": "替換文字並排版", "開始": "準備圖片"}
STATE_SUMMARY = {"success": "已處理偵測區域", "partial": "部分完成／待確認", "failed": "失敗"}


class WorkerMixin:
    # -- primary button --------------------------------------------------
    def primary_action(self):
        if self.busy:
            self.stop()
        else:
            _, jobs, retries, journal = self.primary_plan()
            if journal:
                self.pending.put(("resume", journal, False))
                self.load_journal_rows(journal)
                self.append("繼續上次翻譯：" + str(journal))
                self.start_worker()
            elif jobs or retries:
                self.start_translation(jobs=jobs, retry_sources=retries)

    def resumable_journal(self):
        candidates = ([self.latest_journal] if self.latest_journal else []) + self.unfinished_batches
        for path in dict.fromkeys(candidates):
            try:
                data = json.loads(Path(path).read_text(encoding="utf-8"))
                if data.get("schema") == 1 and data.get("status") != "completed" and any(
                        page.get("state") in ("waiting", "running", "stopped") for page in data.get("pages", [])):
                    return Path(path)
            except (OSError, ValueError, TypeError, AttributeError):
                continue
        return None

    def primary_plan(self):
        selected = set(self.source_list.selection())
        jobs = [job for index, job in enumerate(self.staged) if not selected or str(index) in selected]
        for iid in selected:
            source = self.history_ids.get(iid)
            if source and self.history.get(source, ("", ""))[1] == "waiting":
                jobs.append(("new", Path(source), False))
        retries = self.selected_retry_sources()
        if jobs and retries:
            return f"翻譯勾選（{len(jobs) + len(retries)}）", jobs, retries, None
        if retries:
            return f"重轉勾選（{len(retries)}）", [], retries, None
        if jobs:
            continuing = all(kind == "resume" for kind, _, _ in jobs)
            label = "繼續翻譯" if continuing else "開始翻譯"
            return f"{label}（{len(jobs)}）", jobs, [], None
        journal = self.resumable_journal() if not selected else None
        return "繼續上次翻譯" if journal else "開始翻譯", [], [], journal

    def update_primary_button(self):
        stopping = self.busy and self.stop_requested.is_set()
        label, jobs, retries, journal = self.primary_plan() if not self.busy else ("", [], [], None)
        text = "準備中…" if self.preparing else "停止中…" if stopping else "停止" if self.busy else label
        enabled = (self.busy or jobs or retries or journal) and not stopping and not self.preparing
        self.start_button.configure(text=text, state="normal" if enabled else "disabled")

    # -- starting / stopping ---------------------------------------------
    def start_translation(self, jobs=None, retry_sources=()):
        jobs = list(self.staged if jobs is None else jobs)
        if self.busy or not (jobs or retry_sources):
            return
        if not self.pending.empty():
            self.status.set("尚有已提交的工作，請等目前工作結束。")
            return
        paths = list(dict.fromkeys([path for kind, path, _ in jobs if kind == "new"] + list(retry_sources)))
        try:
            if retry_sources and len(discover(paths)) != len(paths):
                raise ValueError("部分勾選圖片已不存在或無法讀取，請重新加入原圖。")
            if paths:
                text = self.glossary.get("1.0", "end").strip()
                glossary = parse_glossary(text)
                self.write_settings(glossary=text)
        except (ValueError, OSError) as error:
            self.status.set(str(error))
            return
        self.batch_source_roots = {path: root for path, root in getattr(self, "source_roots", {}).items() if path in paths}
        self.batch_output = getattr(self, "output_directory", None)
        if paths:
            self.pending.put(("new", paths, glossary))
        for kind, path, retry in jobs:
            if kind == "resume":
                self.pending.put((kind, path, retry))
        self.append(f"開始處理：{len(jobs) + len(retry_sources)} 個來源")
        if hasattr(self, "history"):
            for path in retry_sources:
                self.history[str(path)] = ("等待重轉", "waiting")
            for kind, path, _ in jobs:
                if kind == "new":
                    self.history[str(path)] = ("等待處理", "waiting")
                else:
                    self.load_journal_rows(path)
            self.update_name_count()
        self.staged = [job for job in self.staged if job not in jobs]
        if hasattr(self, "source_list"):
            self.source_list.selection_remove(self.source_list.selection())
        self.refresh_staged()
        self.start_worker()

    def start_worker(self):
        if self.worker and self.worker.is_alive():
            return
        self.stop_requested.clear()
        self.had_error = False
        self.set_busy(True)
        self.worker = threading.Thread(target=self.work, daemon=False)
        self.worker.start()

    def set_busy(self, busy):
        self.busy = busy
        self.refresh_staged()
        if busy:
            self.progress_bar.grid()
            self.activity_frame.grid()
            self.progress_bar.configure(value=0)
            self.progress_text.set("準備中…")
            self.stage_started = time.monotonic()
            self.activity_bar.start(15)
        else:
            self.activity_bar.stop()
            self.activity_frame.grid_remove()
            self.elapsed_text.set("")
        self.prepare_button.configure(state="disabled" if busy else "normal")
        self.provider_box.configure(state="disabled" if busy else "readonly")
        self.model_box.configure(state="disabled" if busy else "normal")
        self.model_refresh_button.configure(state="disabled" if busy else "normal")
        self.choose_output_button.configure(state="disabled" if busy else "normal")
        self.reset_output_button.configure(state="disabled" if busy or not self.output_directory else "normal")

    def stop(self):
        self.stop_requested.set()
        if self.runner:
            self.runner.stop.set()
        self.status.set("停止中：等待目前頁面安全保存，不會開始下一頁。")
        self.start_button.configure(text="停止中…")
        self.start_button.configure(state="disabled")

    # -- worker thread (never touches Tk) --------------------------------
    def work(self):
        current = None
        journal = None
        try:
            if self.pipeline is None:
                self.events.put({"stage": "檢查翻譯所需檔案（首次啟動可能需要一點時間）"})
                from src.offline.pipeline import TranslationPipeline
                from src.offline.translators import create_translator
                self.pipeline = TranslationPipeline(ROOT / "models", translator=create_translator(*self.translator_choice()))
            while not self.stop_requested.is_set():
                try:
                    kind, value, options = self.pending.get_nowait()
                except queue.Empty:
                    break
                current = (kind, value, options)
                journal = None
                journal = create_batch(value, self.pipeline.fingerprint, options,
                                       output=getattr(self, "batch_output", None),
                                       source_roots=getattr(self, "batch_source_roots", {})) if kind == "new" else value
                self.events.put({"journal": str(journal)})
                runner = BatchRunner(self.pipeline, self.events.put)
                self.runner = runner
                if self.stop_requested.is_set():
                    runner.stop.set()
                result = runner.run(journal, retry_failed=bool(options) if kind == "resume" else False,
                                    retry_partial=bool(options) if kind == "resume" else False)
                self.events.put({"summary": result})
                self.runner = None
                if result["status"] == "stopped":
                    break
                current = None
        except CliNotInstalled as error:
            self.events.put({"error": str(error), "cli_missing": True, "install_url": error.install_url})
        except Exception as error:
            self.events.put({"error": str(error)})
        finally:
            # A failed setup or stopped batch goes back to the visible list;
            # the user can review it and press Start again, without re-adding.
            remaining = []
            if current is not None:
                remaining.append(("resume", journal, False) if journal is not None else current)
            while not self.pending.empty():
                remaining.append(self.pending.get_nowait())
            if remaining:
                restored = []
                for kind, value, options in remaining:
                    if kind == "new":
                        restored.extend(("new", path, False) for path in value)
                    else:
                        restored.append((kind, value, options))
                self.events.put({"restage": restored})
            self.runner = None
            self.events.put({"done": True})

    # -- main-thread event handling --------------------------------------
    def poll(self):
        while True:
            try:
                event = self.events.get_nowait()
            except queue.Empty:
                break
            self.handle_event(event)
        if self.busy and hasattr(self, "elapsed_text"):
            seconds = int(time.monotonic() - self.stage_started)
            self.elapsed_text.set(f"處理中・目前階段已用 {seconds} 秒")
        self.root.after(100, self.poll)

    def handle_event(self, event):
        if "models" in event:
            self.show_model_list(event)
        if "journal" in event:
            self.latest_journal = Path(event["journal"])
            self.append("批次紀錄：" + str(self.latest_journal))
            self.load_journal_rows(self.latest_journal)
        if hasattr(self, "progress_bar"):
            self.update_progress(event)
        if "state" in event:
            self.handle_page_state(event)
        if "summary" in event:
            self.handle_summary(event["summary"])
        if "error" in event:
            self.had_error = True
            self.append("錯誤：" + event["error"])
            self.status.set(event["error"])
            self.mark_unfinished_stopped()
            self.refresh_staged()
            if event.get("cli_missing"):
                self.offer_cli_install(event.get("install_url"))
        if "done" in event:
            # The thread may still be returning; controls are enabled only after exit.
            self.root.after(50, self.check_idle)
        if "models_ready" in event:
            self.pipeline = None
            if hasattr(self, "progress_bar"):
                self.progress_bar.configure(value=100)
                self.progress_text.set("翻譯所需檔案已就緒")
        if "restage" in event:
            for item in event["restage"]:
                if item not in self.staged:
                    self.staged.append(item)
            self.refresh_staged()

    def handle_page_state(self, event):
        state = event["state"]
        self.append(f"{STATE_SUMMARY.get(state, state)}：{Path(event['source']).name} {event.get('reason', '')}")
        self.append(f"  貼字 {event.get('translated', 0)} 區／保留 {event.get('preserved', 0)} 區／待目視確認 {event.get('review_required', 0)} 區")
        if state in ("success", "partial"):
            self.latest_output = Path(event["output"])
        self.record_page(event["source"], STATE_LABELS.get(state, state), state)
        candidate = Path(event.get("report", Path(event["output"]).with_suffix(".json")))
        self.remember_report(event["source"], candidate)
        if candidate.exists():
            self.latest_report = candidate

    def handle_summary(self, summary):
        self.append("批次結果：" + json.dumps(summary, ensure_ascii=False))
        if summary["status"] == "stopped":
            self.had_error = True
        else:
            counts = summary.get("counts", {})
            self.status.set(f"處理結束：完成 {counts.get('success', 0)} 張，待確認 {counts.get('partial', 0)} 張，失敗 {counts.get('failed', 0)} 張。")

    def update_progress(self, event):
        if "progress" in event:
            done, total = event["progress"], event["total"]
            percent = round(done / total * 100) if total else 0
            self.progress_bar.configure(value=percent)
            self.progress_text.set(f"已處理 {done}／{total} 張（{percent}%）")
        if "stage" in event:
            stage = event["stage"]
            if "翻譯" in stage and ("AGY" in stage or "（僅傳文字）" in stage):
                stage = "翻譯對白"
            stage = STAGE_NAMES.get(stage, stage)
            prefix = f"第 {event['index']} 張：{Path(event['source']).name}｜" if "index" in event else ""
            self.status.set(prefix + stage)
            self.stage_started = time.monotonic()
            if "source" in event:
                self.record_page(event["source"], stage + "…", "running")

    def check_idle(self):
        if self.worker and self.worker.is_alive():
            self.root.after(50, self.check_idle)
            return
        self.mark_unfinished_stopped()
        self.preparing = False
        self.set_busy(False)
        if self.stop_requested.is_set():
            self.status.set("已停止。已完成結果保留，可繼續批次或加入新圖片。")
        elif not self.pending.empty() and not self.had_error:
            self.start_worker()
