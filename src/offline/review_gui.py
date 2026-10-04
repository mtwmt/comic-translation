"""Small local review window: source/result/mask, text edits and mask brush."""
from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path
import queue
import threading
import tkinter as tk
from tkinter import ttk, messagebox

import cv2
import numpy as np
from PIL import Image, ImageTk

from .restoration import decode_mask, encode_mask
from .review import load_source, rerender, save_revision
from .manual_review import manual_region, ocr_candidates, recognize_manual_region, resize_manual_region, strengthen_white_cleaning, translate_region


def require_rendered_translations(report):
    """Never replace an edited preview/export with a silent source fallback."""
    failed = [r for r in report["regions"] if r.get("enabled", True)
              and r.get("translation", "").strip() and r.get("status") == "preserved"]
    if failed:
        details = "；".join(f"{r['id']}：{r.get('reason', '無法完成排版')}" for r in failed)
        raise ValueError("保留上次預覽，尚未套用此次調整。" + details)


class ReviewWindow:
    def __init__(self, root, report_path, models):
        self.root, self.report_path, self.models = root, Path(report_path), Path(models)
        self.report = json.loads(self.report_path.read_text(encoding="utf-8"))
        self.original = load_source(self.report)
        self.result = self.original.copy()
        result_path = Path(self.report.get("output_path", self.report_path.with_suffix(".png")))
        if result_path.exists():
            with Image.open(result_path) as im:
                if im.size == self.original.size:
                    self.result = im.convert("RGB")
        self.index = None
        self.mask = None
        self.worker = None
        self.events = queue.Queue()
        self.restorer = None
        self.recognizer = None
        self.busy = False
        self.drag_start = None
        self.resize_drag = None
        self.preview_worker = None
        self.preview_restorer = None
        self.preview_timer = None
        self.preview_delay = 450
        self.edit_version = 0
        self.preview_pending = False
        self.loading_fields = False
        self.dirty = False
        self.display = tk.StringVar(value="result")
        self.brush = tk.StringVar(value="inspect")
        self.brush_size = tk.IntVar(value=10)  # radius in screen pixels
        self.zoom = tk.BooleanVar(value=False)
        self.enabled = tk.BooleanVar(value=True)
        self.direction = tk.StringVar(value="直排")
        self.font_size = tk.StringVar(value="0")
        self.status = tk.StringVar(value="修改後自動更新本機預覽；按「儲存成品」才會輸出檔案。")
        root.title(f"漫畫翻譯｜{Path(self.report['source']).name}｜修訂")
        root.geometry("1200x850")
        body = ttk.Frame(root, padding=10)
        body.pack(fill="both", expand=True)
        left, right = ttk.Frame(body), ttk.Frame(body, width=340)
        left.pack(side="left", fill="both", expand=True)
        right.pack(side="right", fill="y", padx=(12, 0))
        modes = ttk.Frame(left)
        modes.pack(fill="x")
        for text, value in [("原圖", "original"), ("譯圖", "result"), ("清字遮罩", "mask")]:
            ttk.Radiobutton(modes, text=text, variable=self.display, value=value, command=self.draw).pack(side="left")
        ttk.Checkbutton(modes, text="放大選取區", variable=self.zoom, command=self.draw).pack(side="left", padx=10)
        self.box_button = ttk.Button(modes, text="框選漏字", command=self.start_box)
        self.box_button.pack(side="left")
        self.canvas = tk.Canvas(left, bg="#d9d9d9", highlightthickness=0)
        self.canvas.pack(fill="both", expand=True, pady=8)
        self.canvas.bind("<Configure>", lambda event: self.draw())
        self.canvas.bind("<Button-1>", self.pointer_down)
        self.canvas.bind("<B1-Motion>", self.pointer_move)
        self.canvas.bind("<ButtonRelease-1>", self.pointer_up)
        self.canvas.bind("<Motion>", self.pointer_hover)
        self.canvas.bind("<Leave>", lambda event: self.canvas.delete("brush-cursor"))
        root.bind("<Escape>", lambda event: self.cancel_box())
        self.regions = tk.Listbox(right, height=6, width=42, exportselection=False)
        self.regions.pack(fill="x")
        self.regions.bind("<<ListboxSelect>>", self.select)
        self.delete_button = ttk.Button(right, text="刪除手動區域", command=self.delete_manual)
        self.delete_button.pack(anchor="e")
        ttk.Label(right, text="辨識原文（可更正）").pack(anchor="w", pady=(8, 0))
        self.source = tk.Text(right, height=3, width=38, wrap="word", undo=True)
        self.source.pack(fill="x")
        reread = ttk.Frame(right)
        reread.pack(fill="x", pady=(4, 0))
        self.reread_button = ttk.Button(reread, text="重新辨識", command=self.reread_selected)
        self.reread_button.pack(side="left")
        self.candidates = tk.StringVar()
        self.candidate_box = ttk.Combobox(reread, textvariable=self.candidates, state="disabled", width=24)
        self.candidate_box.pack(side="left", fill="x", expand=True, padx=(6, 0))
        self.candidate_box.bind("<<ComboboxSelected>>", self.pick_candidate)
        self.translate_button = ttk.Button(right, text="翻譯此區（雲端文字）", command=self.translate_selected)
        self.translate_button.pack(fill="x", pady=4)
        ttk.Label(right, text="繁中譯文（修改後自動預覽）").pack(anchor="w", pady=(8, 0))
        self.translation = tk.Text(right, height=3, width=38, wrap="word", undo=True)
        self.translation.pack(fill="x")
        self.enable_button = ttk.Checkbutton(right, text="套用此區譯文（取消則保留原圖）", variable=self.enabled)
        self.enable_button.pack(anchor="w", pady=8)
        lettering = ttk.Frame(right)
        lettering.pack(fill="x")
        self.direction_control = ttk.Combobox(lettering, textvariable=self.direction, values=["直排", "橫排"], state="readonly", width=5)
        self.direction_control.pack(side="left")
        ttk.Label(lettering, text="字級 px").pack(side="left", padx=(8, 3))
        validate_size = (root.register(lambda value: value == "" or value.isascii() and value.isdigit() and int(value) <= 512), "%P")
        self.font_control = ttk.Spinbox(lettering, from_=0, to=512, increment=2, width=5,
                                       textvariable=self.font_size, validate="key", validatecommand=validate_size)
        self.font_control.pack(side="left")
        self.font_hint = ttk.Label(right, text="0＝依原文字級，放不下才縮小。", wraplength=340)
        self.font_hint.pack(anchor="w")
        self.clean_button = ttk.Button(right, text="加強白底清字", command=self.strengthen_cleaning)
        self.clean_button.pack(fill="x", pady=4)
        self.reason = ttk.Label(right, wraplength=310)
        self.reason.pack(fill="x", pady=5)
        ttk.Label(right, text="檢視模式：拖曳框的四角或邊緣調整大小（偵測到的區域也可以）\n遮罩筆刷：僅在文字框附近生效", wraplength=310).pack(anchor="w", pady=(10, 0))
        self.brush_buttons = []
        for text, value in [("檢視", "inspect"), ("加入清字範圍", "add"), ("排除清字範圍", "remove")]:
            button = ttk.Radiobutton(right, text=text, variable=self.brush, value=value,
                                    command=self.show_mask)
            button.pack(anchor="w")
            self.brush_buttons.append(button)
        size_row = ttk.Frame(right)
        size_row.pack(fill="x", pady=(4, 0))
        ttk.Label(size_row, text="筆刷大小").pack(side="left")
        self.brush_scale = ttk.Scale(size_row, from_=3, to=60, variable=self.brush_size, orient="horizontal",
                                     command=lambda value: self.brush_size.set(round(float(value))))
        self.brush_scale.pack(side="left", fill="x", expand=True, padx=6)
        self.brush_buttons.append(self.brush_scale)
        actions = ttk.Frame(right)
        actions.pack(fill="x", pady=10)
        self.preview_button = ttk.Button(actions, text="更新預覽", command=self.preview_now)
        self.preview_button.pack(side="left", fill="x", expand=True)
        self.apply_button = ttk.Button(actions, text="儲存成品", command=self.apply)
        self.apply_button.pack(side="left", fill="x", expand=True, padx=(8, 0))
        ttk.Label(right, text="局部補畫可能推測錯誤，請放大確認畫線。\n空白譯文或取消套用的區域會保留原圖。", wraplength=310).pack(anchor="w")
        ttk.Label(root, textvariable=self.status, wraplength=1150, padding=10).pack(fill="x")
        self.refresh_list()
        if self.report["regions"]:
            self.regions.selection_set(0)
            self.select()
        self.set_busy(False)
        for widget in (self.source, self.translation):
            widget.edit_modified(False)
            widget.bind("<<Modified>>", self.text_changed)
        for variable in (self.font_size, self.direction, self.enabled):
            variable.trace_add("write", lambda *args: self.changed(show_result=True))
        root.protocol("WM_DELETE_WINDOW", self.close)
        root.after(100, self.poll)

    def refresh_list(self):
        self.regions.delete(0, "end")
        for r in self.report["regions"]:
            state = "已貼字" if r["status"] == "translated" else "保留原圖"
            if r.get("requires_review"):
                state += "／待目視確認"
            self.regions.insert("end", f"{r['id']}  {state}")

    def commit(self):
        if self.index is not None:
            r = self.report["regions"][self.index]
            r["original"] = self.source.get("1.0", "end").strip()
            r["translation"] = self.translation.get("1.0", "end").strip()
            r["enabled"] = self.enabled.get()
            r["direction"] = "vertical" if self.direction.get() == "直排" else "horizontal"
            size = self.font_size.get().strip()
            r["font_size_override"] = int(size) if size.isascii() and size.isdigit() and int(size) <= 512 else 0
            if self.mask is not None:
                r["erase_mask"] = encode_mask(self.mask)

    def select(self, event=None):
        selected = self.regions.curselection()
        if not selected or self.busy or selected[0] == self.index:
            return
        self.cancel_box()
        self.commit()
        self.loading_fields = True
        self.index = selected[0]
        r = self.report["regions"][self.index]
        self.candidates.set("")
        self.candidate_box.configure(values=[], state="disabled")
        self.source.configure(state="normal")
        self.source.delete("1.0", "end")
        self.source.insert("1.0", r.get("original", ""))
        self.translation.configure(state="normal")
        self.translation.delete("1.0", "end")
        self.translation.insert("1.0", r.get("translation", ""))
        self.enabled.set(r.get("enabled", True))
        self.direction.set("直排" if r.get("direction") == "vertical" else "橫排")
        self.font_size.set(str(r.get("font_size_override", 0)))
        from .source_size import estimate_source_font_size
        estimated = estimate_source_font_size(self.original, r)
        hint = f"原文估計 {estimated} px" if estimated else "原文字級無法可靠估計，使用自動排版"
        if r.get("font_size"):
            hint += f"；目前 {r['font_size']} px"
        self.font_hint.configure(text=hint + "。0＝自動，放不下才縮小。")
        self.clean_button.configure(state="normal" if r.get("manual") else "disabled")
        self.reason.configure(text=r.get("reason") or "已完成貼字；請核對內容與畫面。")
        self.mask = decode_mask(r["erase_mask"], (self.original.height, self.original.width)) if "erase_mask" in r else None
        self.apply_button.configure(state="normal" if self.mask is not None else "disabled")
        self.translate_button.configure(state="normal")
        self.delete_button.configure(state="normal" if r.get("manual") else "disabled")
        if self.mask is None:
            self.reason.configure(text="此舊報告沒有可編輯遮罩，請用新版清字模式重新處理。")
        self.source.edit_modified(False)
        self.translation.edit_modified(False)
        self.loading_fields = False
        self.set_busy(False)
        self.draw()

    def text_changed(self, event):
        if event.widget.edit_modified():
            event.widget.edit_modified(False)
            self.changed(show_result=event.widget is self.translation)

    def changed(self, show_result=False):
        if self.loading_fields:
            return
        self.edit_version += 1
        self.dirty = True
        self.preview_pending = True
        if show_result:
            self.display.set("result")
        if self.preview_timer is not None:
            self.root.after_cancel(self.preview_timer)
        self.preview_timer = self.root.after(self.preview_delay, self.start_preview)

    def preview_now(self):
        self.display.set("result")
        self.preview_pending = True
        if self.preview_timer is not None:
            self.root.after_cancel(self.preview_timer)
            self.preview_timer = None
        self.start_preview()

    def start_preview(self):
        self.preview_timer = None
        if self.busy or self.resize_drag is not None or self.drag_start is not None or self.preview_worker and self.preview_worker.is_alive():
            return
        if not self.preview_pending:
            return
        self.commit()
        snapshot, revision = deepcopy(self.report), self.edit_version
        self.preview_pending = False
        self.status.set("正在更新本機預覽…不輸出檔案，可繼續編輯。")
        def run():
            try:
                from .restoration import RestorationModels
                if self.preview_restorer is None:
                    self.preview_restorer = RestorationModels(self.models)
                im, report, mask = rerender(snapshot, self.models, self.preview_restorer)
                require_rendered_translations(report)
                self.events.put({"kind": "preview", "version": revision, "image": im, "report": report})
            except Exception as error:
                self.events.put({"kind": "preview", "version": revision, "error": str(error)})
        self.preview_worker = threading.Thread(target=run, daemon=False)
        self.preview_worker.start()

    def receive_preview(self, event):
        for widget in (self.source, self.translation):
            if widget.edit_modified():
                widget.edit_modified(False)
                self.changed(show_result=widget is self.translation)
        if event["version"] == self.edit_version and not self.busy:
            if "error" in event:
                self.status.set("預覽失敗（未輸出檔案）：" + event["error"])
                self.reason.configure(text=event["error"])
            else:
                self.result, self.report = event["image"], event["report"]
                # Update rendering metadata without replacing the editor text,
                # cursor or undo history while the user is typing.
                selected = self.regions.curselection()
                self.refresh_list()
                for index in selected:
                    self.regions.selection_set(index)
                if self.index is not None:
                    r = self.report["regions"][self.index]
                    self.mask = decode_mask(r["erase_mask"], (self.original.height, self.original.width)) if "erase_mask" in r else None
                    self.reason.configure(text=r.get("font_size_warning") or r.get("reason") or "預覽完成，尚未儲存。")
                    self.font_hint.configure(text=f"目前 {r.get('font_size', '—')} px；超出範圍會換行、必要時縮小。")
                self.draw()
                self.status.set("預覽已更新，尚未儲存；調整完成後按「儲存成品」。")
        if self.preview_pending and not self.busy:
            self.preview_timer = self.root.after(self.preview_delay, self.start_preview)

    def show_mask(self):
        self.cancel_box()
        self.display.set("mask")
        self.draw()

    def start_box(self):
        if self.busy:
            return
        self.commit()
        self.cancel_box()
        # Starting a new region leaves the old draft intact, but no longer
        # targets it with the frame, editor, or mask tools.
        self.edit_version += 1
        self.regions.selection_clear(0, "end")
        self.index, self.mask = None, None
        self.loading_fields = True
        for widget in (self.source, self.translation):
            widget.configure(state="normal")
            widget.delete("1.0", "end")
            widget.edit_modified(False)
        self.font_size.set("0")
        self.enabled.set(False)
        self.font_hint.configure(text="框選新區域後可調整字級。")
        self.reason.configure(text="請在左側拖曳框住漏掉的文字。")
        self.loading_fields = False
        self.set_busy(False)
        self.brush.set("box")
        self.zoom.set(False)
        self.display.set("original")
        self.canvas.configure(cursor="crosshair")
        self.draw()
        self.status.set("拖曳框住一段漏字，避開對話框邊線與插圖；放開後在本機辨識。Esc 取消。")

    def cancel_box(self):
        self.drag_start = None
        resizing = self.resize_drag is not None
        self.resize_drag = None
        if self.brush.get() == "box":
            self.brush.set("inspect")
        self.canvas.delete("selection")
        self.canvas.configure(cursor="")
        if resizing:
            self.draw()

    def frame_points(self, box):
        scale, ox, oy, crop = self.mapping
        x1, y1, x2, y2 = box
        x1, x2 = ox + (x1-crop[0])*scale, ox + (x2-crop[0])*scale
        y1, y2 = oy + (y1-crop[1])*scale, oy + (y2-crop[1])*scale
        return {"nw": (x1,y1), "n": ((x1+x2)/2,y1), "ne": (x2,y1),
                "e": (x2,(y1+y2)/2), "se": (x2,y2), "s": ((x1+x2)/2,y2),
                "sw": (x1,y2), "w": (x1,(y1+y2)/2)}

    def resize_handle(self, event):
        if self.busy or self.brush.get() != "inspect" or self.index is None:
            return None
        region = self.report["regions"][self.index]
        points = self.frame_points(region["bbox"])
        for key, (x, y) in points.items():
            if abs(event.x-x) <= 8 and abs(event.y-y) <= 8:
                return key
        x1, y1 = points["nw"]
        x2, y2 = points["se"]
        if x1 <= event.x <= x2:
            if abs(event.y-y1) <= 6:
                return "n"
            if abs(event.y-y2) <= 6:
                return "s"
        if y1 <= event.y <= y2:
            if abs(event.x-x1) <= 6:
                return "w"
            if abs(event.x-x2) <= 6:
                return "e"
        return None

    def draw_brush_cursor(self, event):
        """Show the exact area a click will paint instead of an arrow."""
        self.canvas.delete("brush-cursor")
        if self.brush.get() not in {"add", "remove"} or self.busy or self.mask is None:
            return False
        radius = self.brush_size.get()
        color = "#00c853" if self.brush.get() == "add" else "#ff3b30"
        self.canvas.create_oval(event.x - radius - 1, event.y - radius - 1, event.x + radius + 1, event.y + radius + 1,
                                outline="white", width=3, tags="brush-cursor")
        self.canvas.create_oval(event.x - radius, event.y - radius, event.x + radius, event.y + radius,
                                outline=color, width=2, tags="brush-cursor")
        return True

    def pointer_hover(self, event):
        if self.resize_drag is not None or self.brush.get() == "box":
            return
        if self.draw_brush_cursor(event):
            self.canvas.configure(cursor="none")
            return
        handle = self.resize_handle(event)
        cursor = "sb_h_double_arrow" if handle in ("e", "w") else "sb_v_double_arrow" if handle in ("n", "s") else "crosshair" if handle else ""
        self.canvas.configure(cursor=cursor)

    def draw_region_frame(self, box):
        self.canvas.delete("region-frame")
        points = self.frame_points(box)
        self.canvas.create_rectangle(*points["nw"], *points["se"], outline="#008cff", width=2, tags="region-frame")
        if self.brush.get() == "inspect" and not self.busy:
            for x, y in points.values():
                self.canvas.create_rectangle(x-4, y-4, x+4, y+4, fill="white", outline="#008cff", tags="region-frame")

    def resized_box(self, event):
        box = self.resize_drag["box"].copy()
        handle = self.resize_drag["handle"]
        x, y = self.source_point(event, clamp=True)
        if "w" in handle:
            box[0] = min(round(x), box[2]-8)
        if "e" in handle:
            box[2] = max(round(x), box[0]+8)
        if "n" in handle:
            box[1] = min(round(y), box[3]-8)
        if "s" in handle:
            box[3] = max(round(y), box[1]+8)
        return box

    def source_point(self, event, clamp=False):
        scale, ox, oy, crop = self.mapping
        x, y = (event.x - ox) / scale + crop[0], (event.y - oy) / scale + crop[1]
        if not clamp and not (crop[0] <= x < crop[2] and crop[1] <= y < crop[3]):
            return None
        return max(crop[0], min(crop[2], x)), max(crop[1], min(crop[3], y))

    def pointer_down(self, event):
        if self.busy:
            return
        handle = self.resize_handle(event)
        if handle:
            self.commit()
            self.edit_version += 1
            self.preview_pending = True
            self.resize_drag = {"handle": handle, "box": self.report["regions"][self.index]["bbox"].copy()}
            self.status.set("拖曳調整框選大小，放開更新清字範圍；Esc 取消。原文與譯文會保留。")
            return
        if self.brush.get() != "box":
            self.paint(event)
            return
        self.drag_start = self.source_point(event)
        if self.drag_start is not None:
            self.edit_version += 1
            self.preview_pending = True

    def pointer_move(self, event):
        if self.busy:
            return
        if self.resize_drag is not None:
            self.draw_region_frame(self.resized_box(event))
            return
        if self.brush.get() != "box":
            self.paint(event)
            return
        if self.drag_start is not None:
            end = self.source_point(event, clamp=True)
            scale, ox, oy, crop = self.mapping
            points = [(ox + (x-crop[0])*scale, oy + (y-crop[1])*scale) for x, y in (self.drag_start, end)]
            self.canvas.delete("selection")
            self.canvas.create_rectangle(*points[0], *points[1], outline="#008cff", width=2, tags="selection")

    def pointer_up(self, event):
        if not self.busy and self.resize_drag is not None:
            box = self.resized_box(event)
            original_box = self.resize_drag["box"]
            self.resize_drag = None
            if box == original_box:
                self.draw()
                return
            self.commit()
            try:
                region = resize_manual_region(self.original, self.report["regions"][self.index], box,
                                              self.report["regions"], self.report.get("glossary", {}))
            except ValueError as error:
                self.status.set(str(error))
                self.draw()
                return
            self.report["regions"][self.index] = region
            self.mask = decode_mask(region["erase_mask"], (self.original.height, self.original.width))
            index, self.index = self.index, None
            self.refresh_list()
            self.regions.selection_set(index)
            self.select()
            self.display.set("mask")
            self.draw()
            self.status.set(region["reason"])
            self.changed()
            return
        if self.busy or self.brush.get() != "box" or self.drag_start is None:
            return
        box = (*self.drag_start, *self.source_point(event, clamp=True))
        self.cancel_box()
        self.commit()
        try:
            region = manual_region(self.original, box, self.report["regions"], self.report.get("glossary", {}))
        except ValueError as error:
            self.status.set(str(error))
            return
        self.set_busy(True)
        self.status.set("正在本機辨識框選文字；圖片不會上傳。")
        def run():
            try:
                from .providers import LocalModels
                if self.recognizer is None:
                    self.recognizer = LocalModels(self.models)
                region_result = recognize_manual_region(self.original, region, self.recognizer)
                self.events.put({"kind": "region", "region": region_result})
            except Exception as error:
                self.events.put(error)
        self.worker = threading.Thread(target=run, daemon=False)
        self.worker.start()

    def delete_manual(self):
        if self.busy or self.index is None or not self.report["regions"][self.index].get("manual"):
            return
        self.report["regions"].pop(self.index)
        self.index, self.mask = None, None
        self.refresh_list()
        self.source.delete("1.0", "end")
        self.translation.delete("1.0", "end")
        if self.report["regions"]:
            self.regions.selection_set(0)
            self.select()
        self.set_busy(False)
        self.draw()
        self.status.set("已移除手動區域，正在更新預覽；按「儲存成品」才會輸出。")
        self.changed(show_result=True)

    def strengthen_cleaning(self):
        if self.busy or self.index is None or not self.report["regions"][self.index].get("manual"):
            return
        self.commit()
        self.cancel_box()
        try:
            region = strengthen_white_cleaning(self.original, self.report["regions"][self.index],
                                               self.report["regions"], self.report.get("glossary", {}))
        except ValueError as error:
            self.status.set(str(error))
            return
        self.report["regions"][self.index] = region
        index, self.index = self.index, None
        self.refresh_list()
        self.regions.selection_set(index)
        self.select()
        self.display.set("mask")
        self.draw()
        self.status.set(region["reason"])
        self.changed()

    def reread_selected(self):
        if self.busy or self.index is None:
            return
        self.commit()
        self.cancel_box()
        region = deepcopy(self.report["regions"][self.index])
        self.set_busy(True)
        self.status.set("正在本機重新辨識此區；圖片不會上傳。")
        def run():
            try:
                from .providers import LocalModels
                if self.recognizer is None:
                    self.recognizer = LocalModels(self.models)
                self.events.put({"kind": "candidates", "id": region["id"],
                                 "items": ocr_candidates(self.original, region, self.recognizer)})
            except Exception as error:
                self.events.put(error)
        self.worker = threading.Thread(target=run, daemon=False)
        self.worker.start()

    def pick_candidate(self, event=None):
        text = self.candidates.get().strip()
        if text and not self.busy:
            self.source.delete("1.0", "end")
            self.source.insert("1.0", text)
            self.status.set("已套用辨識候選；按「翻譯此區」重新翻譯。若都不對，仍可直接修改原文。")

    def translate_selected(self):
        if self.busy or self.index is None:
            return
        self.commit()
        region = deepcopy(self.report["regions"][self.index])
        if not region.get("original", "").strip():
            self.status.set("請先填寫或更正辨識原文。")
            return
        glossary = deepcopy(self.report.get("glossary", {}))
        self.cancel_box()
        self.set_busy(True)
        self.status.set("正在使用所選翻譯引擎翻譯此區文字與本批角色對照；圖片留在本機。")
        def run():
            try:
                from .translators import translator_from_settings
                translator = translator_from_settings()
                text = translate_region(region, glossary, translator)
                self.events.put({"kind": "translation", "id": region["id"], "text": text,
                                 "provider": translator.fingerprint})
            except Exception as error:
                self.events.put(error)
        self.worker = threading.Thread(target=run, daemon=False)
        self.worker.start()

    def draw(self):
        if not hasattr(self, "canvas"):
            return
        # Resize gestures use a fixed view transform; a view/size change cancels
        # only the uncommitted drag, so zoom cannot cause coordinate jumps.
        self.resize_drag = None
        im = (self.result if self.display.get() == "result" else self.original).copy()
        if self.display.get() == "mask" and self.mask is not None:
            rgb = np.asarray(im).copy()
            rgb[self.mask] = np.rint(rgb[self.mask] * .4 + np.array([255, 30, 60]) * .6).astype(np.uint8)
            im = Image.fromarray(rgb)
        crop = (0, 0, im.width, im.height)
        if self.index is not None:
            box = self.report["regions"][self.index]["bbox"]
            if self.zoom.get():
                x1, y1, x2, y2 = box
                pad = max(30, round(max(x2 - x1, y2 - y1) * .25))
                crop = (max(0, x1 - pad), max(0, y1 - pad), min(im.width, x2 + pad), min(im.height, y2 + pad))
        im = im.crop(crop)
        width, height = max(1, self.canvas.winfo_width()), max(1, self.canvas.winfo_height())
        scale = min(width / im.width, height / im.height)
        im = im.resize((max(1, round(im.width * scale)), max(1, round(im.height * scale))), Image.Resampling.LANCZOS)
        ox, oy = (width - im.width) // 2, (height - im.height) // 2
        self.mapping = (scale, ox, oy, crop)
        self.photo = ImageTk.PhotoImage(im)
        self.canvas.delete("all")
        self.canvas.create_image(ox, oy, image=self.photo, anchor="nw")
        if self.index is not None:
            self.draw_region_frame(self.report["regions"][self.index]["bbox"])

    def paint(self, event):
        if self.mask is None or self.brush.get() not in {"add", "remove"} or self.busy:
            return
        scale, ox, oy, crop = self.mapping
        x, y = round((event.x - ox) / scale + crop[0]), round((event.y - oy) / scale + crop[1])
        r = self.report["regions"][self.index]
        x1, y1, x2, y2 = r["bbox"]
        margin = 0 if r.get("manual") else max(3, round(min(self.original.size) * .005))
        brush = np.zeros(self.mask.shape, np.uint8)
        cv2.circle(brush, (x, y), max(1, round(self.brush_size.get() / scale)), 1, -1)
        allowed = np.zeros_like(brush)
        allowed[max(0, y1 - margin):min(self.original.height, y2 + margin),
                max(0, x1 - margin):min(self.original.width, x2 + margin)] = 1
        self.mask[(brush & allowed) > 0] = self.brush.get() == "add"
        r["mask_edited"] = True
        self.display.set("mask")
        self.draw()
        self.draw_brush_cursor(event)
        self.changed()

    def apply(self):
        if self.busy:
            return
        self.commit()
        self.cancel_box()
        # Invalidate any in-flight preview so it cannot replace a saved result.
        self.edit_version += 1
        self.preview_pending = False
        if self.preview_timer is not None:
            self.root.after_cancel(self.preview_timer)
            self.preview_timer = None
        snapshot = deepcopy(self.report)
        self.set_busy(True)
        self.status.set("正在本機重新清字與排版；完成後另存修訂，不呼叫雲端翻譯。")
        def run():
            try:
                from .restoration import RestorationModels
                if self.restorer is None:
                    self.restorer = RestorationModels(self.models)
                im, report, mask = rerender(snapshot, self.models, self.restorer)
                require_rendered_translations(report)
                path = save_revision(self.report_path, im, report, mask)
                self.events.put((im, report, path))
            except Exception as error:
                self.events.put(error)
        self.worker = threading.Thread(target=run, daemon=False)
        self.worker.start()

    def set_busy(self, busy):
        self.busy = busy
        for control in [self.apply_button, self.preview_button, self.enable_button, self.box_button,
                        self.translate_button, self.reread_button, self.delete_button, self.clean_button, self.font_control,
                        *self.brush_buttons]:
            control.configure(state="disabled" if busy else "normal")
        self.source.configure(state="disabled" if busy else "normal")
        self.translation.configure(state="disabled" if busy else "normal")
        self.regions.configure(state="disabled" if busy else "normal")
        self.direction_control.configure(state="disabled" if busy else "readonly")
        if not busy:
            region = self.report["regions"][self.index] if self.index is not None else {}
            for control in (self.source, self.translation, self.font_control, self.enable_button):
                control.configure(state="normal" if region else "disabled")
            self.direction_control.configure(state="readonly" if region else "disabled")
            self.translate_button.configure(state="normal" if region else "disabled")
            self.reread_button.configure(state="normal" if region else "disabled")
            self.delete_button.configure(state="normal" if region.get("manual") else "disabled")
            self.clean_button.configure(state="normal" if region.get("manual") else "disabled")
            self.apply_button.configure(state="normal" if all("erase_mask" in r for r in self.report["regions"]) else "disabled")

    def poll(self):
        if self.worker and self.worker.is_alive():
            self.root.after(100, self.poll)
            return
        try:
            event = self.events.get_nowait()
        except queue.Empty:
            event = None
        if event is not None:
            if isinstance(event, dict) and event.get("kind") == "preview":
                self.receive_preview(event)
                self.root.after(100, self.poll)
                return
            self.set_busy(False)
            if isinstance(event, dict) and event.get("kind") == "candidates":
                current = self.report["regions"][self.index]["id"] if self.index is not None else None
                if event["id"] == current and event["items"]:
                    self.candidate_box.configure(values=event["items"], state="readonly")
                    self.status.set(f"找到 {len(event['items'])} 個辨識結果，請從「重新辨識」旁的選單挑最接近的，再按「翻譯此區」。")
                else:
                    self.status.set("重新辨識沒有得到不同的結果。")
                self.root.after(100, self.poll)
                return
            if isinstance(event, Exception):
                self.status.set(str(event))
                messagebox.showerror("修訂失敗", str(event), parent=self.root)
            elif isinstance(event, dict):
                self.commit()
                if event["kind"] == "region":
                    self.report["regions"].append(event["region"])
                    index = len(self.report["regions"]) - 1
                    self.display.set("mask")
                    self.status.set(event["region"]["reason"])
                else:
                    index = next(i for i, r in enumerate(self.report["regions"]) if r["id"] == event["id"])
                    self.report["regions"][index].update(translation=event["text"], enabled=True,
                        translation_provider=event["provider"], reason="譯文已填入，正在更新預覽；核對後可儲存成品。")
                    self.status.set("此區翻譯完成，正在更新預覽；核對後按「儲存成品」。")
                self.index = None
                self.refresh_list()
                self.regions.selection_set(index)
                self.select()
                self.set_busy(False)
                self.changed(show_result=event["kind"] == "translation")
            else:
                self.result, self.report, path = event
                self.saved_report_path = Path(path)
                self.dirty = False
                index, self.index = self.index, None
                self.refresh_list()
                if index is not None:
                    self.regions.selection_set(index)
                    self.select()
                self.display.set("result")
                self.draw()
                self.status.set(f"已保存：{path}｜貼字 {self.report['translated']} 區，保留 {self.report['preserved']} 區。")
        self.root.after(100, self.poll)
        if self.preview_pending and self.preview_timer is None and not self.busy and not (self.preview_worker and self.preview_worker.is_alive()):
            self.preview_timer = self.root.after(self.preview_delay, self.start_preview)

    def close(self):
        if self.busy or self.preview_worker and self.preview_worker.is_alive():
            messagebox.showinfo("工作尚未完成", "請等待本次辨識、翻譯或修訂保存完成。", parent=self.root)
            return
        if self.dirty and not messagebox.askyesno("尚未儲存", "要放棄未儲存的修改並關閉嗎？", parent=self.root):
            return
        if self.preview_timer is not None:
            self.root.after_cancel(self.preview_timer)
        self.root.destroy()


def open_review(report_path, models, parent=None):
    root = tk.Toplevel(parent) if parent is not None else tk.Tk()
    try:
        window = ReviewWindow(root, report_path, models)
    except Exception:
        root.destroy()
        raise
    if parent is None:
        root.mainloop()
    return window
