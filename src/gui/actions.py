"""Window-level actions: model download, review window, output folder, log, close."""
from __future__ import annotations

import os
import subprocess
import sys
import threading
import webbrowser
from pathlib import Path
from tkinter import messagebox

from src.gui.worker import ROOT


class ActionsMixin:
    def toggle_log(self):
        if self.show_log.get():
            self.log_window.deiconify()
            self.log_window.lift()
        else:
            self.log_window.withdraw()

    def hide_log(self):
        self.show_log.set(False)
        self.log_window.withdraw()

    def append(self, text):
        self.log.configure(state="normal")
        self.log.insert("end", text + "\n")
        # Keep the UI log bounded for long batches.
        if int(self.log.index("end-1c").split(".")[0]) > 1000:
            self.log.delete("1.0", "101.0")
        self.log.see("end")
        self.log.configure(state="disabled")

    def offer_cli_install(self, install_url):
        if not install_url:
            messagebox.showinfo("找不到翻譯 CLI", "這台電腦找不到所選翻譯引擎的 CLI。\n"
                                "請依官方指示安裝並在終端機完成訂閱登入，或改選其他翻譯引擎。", parent=self.root)
        elif messagebox.askyesno("找不到 CLI", "翻譯需要官方 CLI，但這台電腦找不到。\n"
                                 "要開啟官方安裝頁面嗎？安裝並完成登入後，重新按「繼續上次翻譯」即可。",
                                 parent=self.root):
            webbrowser.open(install_url)

    def prepare(self):
        if self.busy:
            return
        if not messagebox.askyesno("下載翻譯所需檔案", "首次使用需要下載讀取日文、清除原字及貼上中文所需的檔案。\n已有檔案會檢查完整性，通常不需再次下載。\n請預留至少 2.5 GB 空間。要開始嗎？"):
            return
        self.preparing = True
        self.stop_requested.clear()
        self.set_busy(True)
        self.had_error = False
        self.start_button.configure(state="disabled")
        self.status.set("下載並檢查所需檔案中；下載速度取決於網路，請稍候。")
        self.worker = threading.Thread(target=self.download_models, daemon=False)
        self.worker.start()

    def download_models(self):
        try:
            environment = dict(os.environ)
            environment.pop("HF_HUB_OFFLINE", None)
            environment.pop("TRANSFORMERS_OFFLINE", None)
            for command in ("prepare-models", "prepare-restoration"):
                subprocess.run([sys.executable, str(ROOT / "offline.py"), command],
                               env=environment, check=True)
            self.events.put({"models_ready": True})
            from src.offline.fonts import resolve_font
            try:
                resolve_font(ROOT / "models")
                ready = "翻譯所需檔案已就緒，可以加入圖片。"
            except RuntimeError as error:
                ready = "所需檔案下載完成；" + str(error)
            self.events.put({"stage": ready})
        except Exception as error:
            self.events.put({"error": str(error)})
        finally:
            self.events.put({"done": True})

    def review(self):
        if self.busy:
            return
        sources = self.selected_image_sources()
        if len(sources) != 1:
            self.status.set("請在圖片清單中只選取一張要修訂的圖片。")
            return
        source = sources[0]
        from src.offline.report_lookup import find_source_report
        path = find_source_report(source, self.source_reports.get(str(source), ()), self.source_roots.get(source))
        if path is None:
            self.status.set(f"{source.name} 尚無可修訂的辨識結果；請先翻譯，失敗時可勾選重轉。")
            return
        if path:
            try:
                for existing in self.review_windows:
                    if (existing.root.winfo_exists()
                            and path in (existing.report_path, getattr(existing, "saved_report_path", None))):
                        existing.root.deiconify()
                        existing.root.lift()
                        return
                from src.offline.review_gui import open_review
                window = open_review(Path(path), ROOT / "models", parent=self.root)
                self.review_windows.append(window)
                self.status.set(f"已開啟修訂：{source.name}")
            except Exception as error:
                messagebox.showerror("無法開啟預覽", str(error))

    def open_output(self):
        if not self.latest_output:
            messagebox.showinfo("輸出", "目前還沒有已輸出的譯圖。")
            return
        path = str(self.latest_output.parent)
        if sys.platform == "win32":
            os.startfile(path)
        elif sys.platform == "darwin":
            subprocess.Popen(["open", path])
        else:
            subprocess.Popen(["xdg-open", path])

    def close(self):
        if (self.worker and self.worker.is_alive()) or any(
                (window.worker and window.worker.is_alive()) or
                (window.preview_worker and window.preview_worker.is_alive()) for window in self.review_windows):
            messagebox.showinfo("工作尚未結束", "請先停止並等待目前工作結束，再關閉程式。")
            return
        if any(window.root.winfo_exists() and window.dirty for window in self.review_windows):
            if not messagebox.askyesno("尚未儲存", "修訂視窗還有未儲存的修改，要放棄修改並關閉程式嗎？", parent=self.root):
                return
        self.root.destroy()
