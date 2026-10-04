"""Image list: staged jobs, history rows, checkbox selection."""
from __future__ import annotations

import json
from pathlib import Path
from tkinter import filedialog

from src.offline.batch import discover

STATE_LABELS = {"waiting": "等待處理", "running": "等待繼續", "success": "已輸出", "partial": "已輸出 · 待確認",
                "failed": "失敗", "stopped": "已暫停 · 可繼續"}


class StagingMixin:
    def pick_files(self):
        paths = filedialog.askopenfilenames(filetypes=[("圖片", "*.png *.jpg *.jpeg *.webp")])
        if paths:
            self.add([Path(p) for p in paths])

    def pick_folder(self):
        path = filedialog.askdirectory()
        if path:
            self.add([Path(path)])

    def add(self, paths):
        try:
            sources = discover(paths, getattr(self, "output_directory", None))
            if not sources:
                self.status.set("沒有找到 PNG、JPEG 或 WebP 圖片。")
                return
        except OSError as error:
            self.status.set(str(error))
            return
        if not hasattr(self, "source_roots"):
            self.source_roots = {}
        for path, source_root in sources:
            self.source_roots.setdefault(path, source_root)
            item = ("new", path, False)
            if item not in self.staged:
                self.staged.append(item)
        self.refresh_staged()
        self.status.set("已加入清單，尚未開始翻譯。確認後按「開始翻譯」。")

    # -- selection -------------------------------------------------------
    def select_all(self):
        if not self.busy:
            self.source_list.selection_set(self.source_list.get_children())
            self.update_selection()

    def select_none(self):
        if not self.busy:
            self.source_list.selection_remove(self.source_list.selection())
            self.update_selection()

    def click_checkbox(self, event):
        if self.busy:
            return "break"
        row = self.source_list.identify_row(event.y)
        if row and self.source_list.identify_column(event.x) == "#1":
            self.source_list.focus(row)
            self.source_list.selection_toggle(row)
            self.update_selection()
            return "break"

    def toggle_focused(self, event):
        row = self.source_list.focus()
        if row and not self.busy:
            self.source_list.selection_toggle(row)
            self.update_selection()
        return "break"

    def update_selection(self):
        selected = set(self.source_list.selection())
        rows = self.source_list.get_children()
        for row in rows:
            self.source_list.set(row, "check", "☑" if row in selected else "☐")
        unit = "項" if any(kind == "resume" for kind, _, _ in self.staged) else "張"
        self.staging_title.configure(text=f"已選 {len(selected)}／{len(rows)} {unit}")
        self.select_all_button.configure(state="normal" if rows and len(selected) < len(rows) and not self.busy else "disabled")
        self.select_none_button.configure(state="normal" if selected and not self.busy else "disabled")
        self.remove_button.configure(state="normal" if selected and not self.busy else "disabled")
        self.clear_button.configure(state="normal" if rows and not self.busy else "disabled")
        self.review_button.configure(state="normal" if len(self.selected_image_sources()) == 1 and not self.busy else "disabled")
        self.update_primary_button()

    def selected_image_sources(self):
        sources = []
        for iid in self.source_list.selection():
            source = self.history_ids.get(iid)
            if source is None and iid.isdigit() and int(iid) < len(self.staged):
                kind, path, _ = self.staged[int(iid)]
                if kind == "new":
                    source = path
            if source is not None:
                sources.append(Path(source).resolve())
        return sources

    def selected_retry_sources(self):
        """Restrict retries to checked problem pages, never successful pages."""
        sources = []
        for iid in self.source_list.selection():
            source = self.history_ids.get(iid)
            if source and self.history.get(source, ("", ""))[1] in ("failed", "partial", "stopped"):
                sources.append(Path(source))
        return sources

    # -- history ---------------------------------------------------------
    def remember_report(self, source, path):
        self.source_reports.setdefault(str(Path(source).resolve()), set()).add(Path(path))

    def record_page(self, source, label, state="waiting"):
        if not hasattr(self, "history"):
            return
        self.history[str(Path(source).resolve())] = (label, state)
        self.refresh_staged()

    def load_journal_rows(self, path):
        try:
            data = json.loads(Path(path).read_text(encoding="utf-8"))
            for page in data["pages"]:
                state = "stopped" if page["state"] == "running" else page["state"]
                self.history[str(Path(page["source"]).resolve())] = (STATE_LABELS.get(state, "等待處理"), state)
                self.remember_report(page["source"], page.get("report", Path(page["output"]).with_suffix(".json")))
            self.refresh_staged()
        except (OSError, ValueError, KeyError):
            pass

    def mark_unfinished_stopped(self):
        for source, (label, state) in self.history.copy().items():
            if state in ("running", "waiting"):
                self.history[source] = (STATE_LABELS["stopped"], "stopped")

    def refresh_staged(self):
        selected = self.source_list.selection()
        position = self.source_list.yview()[0]
        self.source_list.delete(*self.source_list.get_children())
        pending_sources = set()
        for index, (kind, path, retry) in enumerate(self.staged):
            label = "等待重試批次" if retry else "等待繼續批次" if kind == "resume" else "等待處理"
            self.source_list.insert("", "end", iid=str(index), values=("☐", path.name, label))
            if kind == "new":
                pending_sources.add(str(path))
        self.history_ids = {}
        for index, (source, (label, state)) in enumerate(self.history.items()):
            if source in pending_sources:
                continue
            iid = f"history-{index}"
            self.history_ids[iid] = source
            self.source_list.insert("", "end", iid=iid, values=("☐", Path(source).name, label), tags=(state,))
        self.source_list.selection_set([item for item in selected if self.source_list.exists(item)])
        self.source_list.yview_moveto(position)
        if self.source_list.get_children():
            self.drop.place_forget()
        else:
            self.drop.place(relx=.5, rely=.5, anchor="center")
        self.update_selection()
        if not self.busy and self.staged:
            unit = "項" if any(kind == "resume" for kind, _, _ in self.staged) else "張圖片"
            self.progress_text.set(f"{len(self.staged)} {unit}待處理")
        elif not self.busy and not self.history:
            self.progress_text.set("尚未加入圖片")
            self.progress_bar.grid_remove()
        self.output_button.configure(state="normal" if self.latest_output else "disabled")

    def remove_staged(self):
        if self.busy:
            return
        selected = set(self.source_list.selection())
        for index, (kind, path, _) in enumerate(self.staged):
            if str(index) in selected and kind == "new" and hasattr(self, "history"):
                self.history.pop(str(path), None)
        self.staged = [item for index, item in enumerate(self.staged) if str(index) not in selected]
        for iid in selected:
            source = getattr(self, "history_ids", {}).get(iid)
            if source:
                self.history.pop(source, None)
        if hasattr(self.source_list, "selection_remove"):
            self.source_list.selection_remove(self.source_list.selection())
        self.refresh_staged()

    def clear_staged(self):
        if self.busy:
            return
        self.staged.clear()
        if hasattr(self, "history"):
            self.history.clear()
        self.refresh_staged()
