"""Local OCR/layout + selectable subscription translation. Tk stays on main thread."""
from __future__ import annotations

import json
import queue
import threading
from pathlib import Path
import tkinter as tk
from tkinter import ttk

from src.offline.batch import STATE_ROOT
from src.gui.actions import ActionsMixin
from src.platforms import current as platform_support
from src.gui.settings import SettingsMixin
from src.gui.staging import StagingMixin
from src.gui.theme import configure_style
from src.gui.view import ViewMixin
from src.gui.worker import ROOT, WorkerMixin


class OfflineGUI(ViewMixin, SettingsMixin, StagingMixin, WorkerMixin, ActionsMixin):
    def __init__(self, root):
        self.root = root
        root.title("漫畫翻譯器")
        platform_support.configure_app_icon(root)
        scale = platform_support.window_scale(root)
        root.geometry(f"{round(920 * scale)}x{round(700 * scale)}")
        root.minsize(round(780 * scale), round(700 * scale))
        self.init_state()
        self.heading_font = configure_style(root)
        self.build_menu()
        frame = ttk.Frame(root, padding=10, style="Card.TFrame")
        frame.pack(fill="both", expand=True)
        frame.columnconfigure(0, weight=1)
        frame.rowconfigure(1, weight=1)
        self.build_toolbar(frame)
        self.build_content_split(frame)
        names_area = self.build_names_panel()
        self.load_preferences(STATE_ROOT / "settings.json")
        self.glossary.insert("1.0", self.preferences.get("glossary", ""))
        output = self.preferences.get("output_directory")
        self.output_directory = Path(output).expanduser().resolve() if isinstance(output, str) and output.strip() else None
        self.output_path = tk.StringVar(value=self.output_description())
        self.update_name_count()
        self.build_list_panel(names_area)
        self.build_output_row(frame)
        self.build_progress(frame)
        self.build_activity_and_status(frame)
        self.build_maintenance_and_log(frame)
        self.refresh_staged()
        root.protocol("WM_DELETE_WINDOW", self.close)
        root.after(100, self.poll)
        self.restore_previous_session()
        self.check_font()
        if platform_support.CACHE_MODEL_CATALOG:
            root.after_idle(self.initialize_model_list)

    def init_state(self):
        self.events = queue.Queue()
        self.pending = queue.Queue()
        self.staged = []
        self.source_roots = {}
        self.batch_source_roots = {}
        self.batch_output = None
        self.history = {}
        self.history_ids = {}
        self.row_keys = {}
        self.source_reports = {}
        self.busy = False
        self.worker = None
        self.runner = None
        self.pipeline = None
        self.stop_requested = threading.Event()
        self.latest_journal = None
        self.latest_output = None
        self.latest_report = None
        self.unfinished_batches = []
        self.review_windows = []
        self.usage_window = None
        self.had_error = False
        self.preparing = False
        self.status = tk.StringVar(value="加入圖片或資料夾，確認後開始翻譯。")

    def restore_previous_session(self):
        """Reload batch journals so earlier results and unfinished work reappear."""
        unfinished = []
        recent_outputs = []
        recent_batches = []
        for path in (STATE_ROOT / "batches").glob("*.json"):
            try:
                saved = json.loads(path.read_text(encoding="utf-8"))
                if saved.get("schema") == 1 and isinstance(saved.get("pages"), list):
                    recent_batches.append((path.stat().st_mtime, path))
                if saved.get("status") != "completed":
                    unfinished.append(path)
                for page in saved.get("pages", []):
                    output = Path(page["output"])
                    report = Path(page.get("report", output.with_suffix(".json")))
                    self.remember_report(page["source"], report)
                    if output.is_file():
                        recent_outputs.append((output.stat().st_mtime, output, report))
            except (ValueError, OSError):
                pass
        if recent_batches:
            _, self.latest_journal = max(recent_batches)
            self.load_journal_rows(self.latest_journal)
            self.progress_text.set(f"已載入上次結果 · {len(self.history)} 張")
            self.status.set("勾選失敗或待確認的圖片，主按鈕會切換為「重轉勾選」。")
        if recent_outputs:
            _, self.latest_output, self.latest_report = max(recent_outputs)
        if unfinished:
            self.unfinished_batches = sorted(unfinished, key=lambda path: path.stat().st_mtime, reverse=True)
            self.status.set("有尚未完成的翻譯，可按「繼續上次翻譯」接續；或勾選圖片重轉。")
        self.refresh_staged()

    def check_font(self):
        from src.offline.fonts import resolve_font
        try:
            resolve_font()
        except RuntimeError as error:
            self.status.set(str(error))
