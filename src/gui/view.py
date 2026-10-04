"""Widget construction. Each section builds into `self` the attributes the mixins use."""
from __future__ import annotations

import time
import tkinter as tk
from pathlib import Path
from tkinter import ttk

from src.gui.widgets import ProgressLine
from src.offline.translators import PROVIDERS

NAMES_HINT = "每行一組：日文原名=繁中譯名\n例如：マリオ=瑪利歐\n\n儲存後，下次開始翻譯時套用。\n續跑沿用原批次對照。"


class ViewMixin:
    def build_toolbar(self, frame):
        toolbar = ttk.Frame(frame, style="Card.TFrame")
        toolbar.grid(row=0, column=0, sticky="ew", pady=(0, 6))
        ttk.Button(toolbar, text="加入圖片", command=self.pick_files).pack(side="left")
        ttk.Button(toolbar, text="加入資料夾", command=self.pick_folder).pack(side="left", padx=6)
        self.show_log = tk.BooleanVar(value=False)
        ttk.Label(toolbar, text="雲端文字翻譯・需網路，圖片留在本機", style="Muted.TLabel").pack(side="right")

    def build_content_split(self, frame):
        self.content_split = tk.PanedWindow(frame, orient="vertical", sashwidth=6, showhandle=False,
                                            sashrelief="raised", sashcursor="sb_v_double_arrow",
                                            borderwidth=0, relief="flat",
                                            background=ttk.Style(self.root).lookup("TFrame", "background"))
        self.content_split.grid(row=1, column=0, sticky="nsew", pady=(0, 2))

    def build_names_panel(self):
        names_area = ttk.Frame(self.content_split, style="Card.TFrame")
        names_header = ttk.Frame(names_area, style="Card.TFrame")
        names_header.pack(fill="x", pady=(2, 4))
        self.names_title = ttk.Label(names_header, text="角色名稱對照", style="Heading.TLabel")
        self.names_title.pack(side="left")
        ttk.Label(names_header, text="↕ 拖曳上方分隔線調整高度", style="Muted.TLabel").pack(side="left", padx=(12, 0))
        self.names_panel = ttk.Frame(names_area, style="Card.TFrame")
        self.names_panel.pack(fill="both", expand=True)
        self.names_panel.columnconfigure(0, weight=3, uniform="names")
        self.names_panel.columnconfigure(1, weight=2, uniform="names")
        self.names_panel.rowconfigure(0, weight=1)
        names_input = ttk.Frame(self.names_panel, style="Card.TFrame")
        names_input.grid(row=0, column=0, sticky="nsew")
        self.glossary = tk.Text(names_input, width=1, height=8, undo=True, wrap="word", font="TkTextFont")
        self.glossary_scroll = ttk.Scrollbar(names_input, orient="vertical", command=self.glossary.yview)
        self.glossary.configure(yscrollcommand=self.glossary_scroll.set)
        self.glossary_scroll.pack(side="right", fill="y")
        self.glossary.pack(side="left", fill="both", expand=True)
        self.names_help = ttk.Frame(self.names_panel, style="Card.TFrame", padding=(12, 0, 0, 0))
        self.names_help.grid(row=0, column=1, sticky="nsew")
        names_hint = ttk.Label(self.names_help, text=NAMES_HINT, style="Muted.TLabel", wraplength=300)
        names_hint.pack(anchor="w", fill="x")
        self.names_help.bind("<Configure>", lambda event: names_hint.configure(wraplength=max(120, event.width - 12)))
        self.save_names_button = ttk.Button(self.names_help, text="儲存對照", command=self.save_glossary)
        self.save_names_button.pack(anchor="w", pady=(6, 4))
        return names_area

    def build_list_panel(self, names_area):
        self.list_panel = ttk.Frame(self.content_split, style="Border.TFrame")
        self.content_split.add(self.list_panel, minsize=180, stretch="always")
        self.content_split.add(names_area, minsize=170, stretch="never")
        list_toolbar = ttk.Frame(self.list_panel, padding=(4, 2), style="Card.TFrame")
        list_toolbar.pack(fill="x")
        ttk.Label(list_toolbar, text="圖片清單", style="Heading.TLabel").pack(side="left", padx=(0, 6))
        self.select_all_button = ttk.Button(list_toolbar, text="全選", style="Link.TButton", command=self.select_all)
        self.select_all_button.pack(side="left")
        self.select_none_button = ttk.Button(list_toolbar, text="全取消", style="Link.TButton", command=self.select_none)
        self.select_none_button.pack(side="left")
        self.remove_button = ttk.Button(list_toolbar, text="移除選取", style="Quiet.TButton", command=self.remove_staged)
        self.remove_button.pack(side="left", padx=(6, 4))
        self.clear_button = ttk.Button(list_toolbar, text="清空清單", style="Quiet.TButton", command=self.clear_staged)
        self.clear_button.pack(side="left")
        self.staging_title = ttk.Label(list_toolbar, text="已選 0／0 張", style="Muted.TLabel")
        self.staging_title.pack(side="right", padx=4)
        batch_actions = ttk.Frame(self.list_panel, padding=(4, 4, 4, 0), style="Card.TFrame")
        batch_actions.pack(side="bottom", fill="x")
        self.start_button = ttk.Button(batch_actions, text="開始翻譯", command=self.primary_action, style="Primary.TButton", default="active", state="disabled")
        self.start_button.pack(side="left", padx=(0, 6))
        self.review_button = ttk.Button(batch_actions, text="修訂選取圖片", command=self.review)
        self.review_button.pack(side="left")
        source_frame = ttk.Frame(self.list_panel, style="Card.TFrame")
        source_frame.pack(fill="both", expand=True)
        self.source_list = ttk.Treeview(source_frame, columns=("check", "name", "state"), show="headings", height=5)
        for key, title, width, minimum in [("check", "", 40, 40), ("name", "檔名", 520, 300), ("state", "狀態", 190, 155)]:
            self.source_list.heading(key, text=title, anchor="w")
            self.source_list.column(key, width=width, minwidth=minimum, stretch=key == "name", anchor="center" if key == "check" else "w")
        source_scroll = ttk.Scrollbar(source_frame, orient="vertical", command=self.source_list.yview)
        self.source_list.configure(yscrollcommand=source_scroll.set)
        source_scroll.pack(side="right", fill="y")
        self.source_list.pack(side="left", fill="both", expand=True)
        self.source_list.bind("<<TreeviewSelect>>", lambda event: self.update_selection())
        self.source_list.bind("<Button-1>", self.click_checkbox)
        self.source_list.bind("<space>", self.toggle_focused)
        self.drop = ttk.Label(source_frame, text="把圖片或資料夾拖到這裡\n或按上方「加入圖片」", anchor="center", style="Muted.TLabel", justify="center")
        self.drop.place(relx=.5, rely=.5, anchor="center")
        self.enable_drag_and_drop()

    def enable_drag_and_drop(self):
        try:
            from tkinterdnd2 import DND_FILES
            for target in (self.drop, self.source_list):
                target.drop_target_register(DND_FILES)
                target.dnd_bind("<<Drop>>", lambda event: self.add([Path(p) for p in self.root.tk.splitlist(event.data)]))
        except (AttributeError, tk.TclError):
            self.drop.configure(text="按上方「加入圖片」選擇圖片或資料夾")

    def build_output_row(self, frame):
        meta = ttk.Frame(frame, style="Card.TFrame")
        meta.grid(row=4, column=0, sticky="ew", pady=(6, 6))
        meta.columnconfigure(1, weight=1)
        ttk.Label(meta, text="儲存至", style="Muted.TLabel").grid(row=0, column=0, padx=(0, 8))
        self.output_entry = ttk.Entry(meta, textvariable=self.output_path, state="readonly", width=1)
        self.output_entry.grid(row=0, column=1, sticky="ew")
        self.choose_output_button = ttk.Button(meta, text="選擇資料夾…", command=self.pick_output, style="Compact.TButton")
        self.choose_output_button.grid(row=0, column=2, padx=(8, 4))
        self.reset_output_button = ttk.Button(meta, text="恢復預設", command=lambda: self.set_output_directory(None),
                                              style="Compact.TButton", state="normal" if self.output_directory else "disabled")
        self.reset_output_button.grid(row=0, column=3)

    def build_progress(self, frame):
        self.progress_text = tk.StringVar(value="尚未加入圖片")
        self.progress_bar = ProgressLine(frame)
        self.progress_bar.grid(row=5, column=0, sticky="ew", pady=(0, 6))
        self.progress_bar.grid_remove()
        controls = ttk.Frame(frame, style="Card.TFrame")
        controls.grid(row=6, column=0, sticky="ew")
        summary = ttk.Frame(controls, style="Card.TFrame")
        summary.pack(side="left", fill="x", expand=True)
        ttk.Label(summary, textvariable=self.progress_text, style="Heading.TLabel").pack(anchor="w")
        ttk.Label(summary, text="完成後只輸出合成 PNG", style="Muted.TLabel").pack(anchor="w", pady=(4, 0))
        self.output_button = ttk.Button(controls, text="開啟成品", command=self.open_output)
        self.output_button.pack(side="right", padx=(10, 0))

    def build_activity_and_status(self, frame):
        activity = ttk.Frame(frame, style="Card.TFrame")
        self.activity_frame = activity
        activity.grid(row=7, column=0, sticky="ew", pady=(6, 0))
        self.activity_bar = ttk.Progressbar(activity, mode="indeterminate", length=60)
        self.activity_bar.pack(side="left")
        self.elapsed_text = tk.StringVar(value="")
        ttk.Label(activity, textvariable=self.elapsed_text, style="Muted.TLabel").pack(side="left", padx=6)
        self.activity_frame.grid_remove()
        self.stage_started = time.monotonic()
        status_label = ttk.Label(frame, textvariable=self.status, style="Muted.TLabel", wraplength=880)
        status_label.grid(row=8, column=0, sticky="ew", pady=(4, 0))
        frame.bind("<Configure>", lambda event: status_label.configure(wraplength=max(600, event.width - 40)))

    def build_maintenance_and_log(self, frame):
        maintenance = ttk.Frame(frame, style="Card.TFrame")
        maintenance.grid(row=9, column=0, sticky="ew", pady=(6, 0))
        self.prepare_button = ttk.Button(maintenance, text="下載／檢查所需檔案…", command=self.prepare)
        self.prepare_button.pack(side="left")
        self.build_translator_controls(frame)
        self.log_toggle = ttk.Checkbutton(maintenance, text="顯示詳細紀錄", variable=self.show_log,
                                          command=self.toggle_log, style="Log.TCheckbutton")
        self.log_toggle.pack(side="left", padx=8)
        self.log_window = tk.Toplevel(self.root)
        self.log_window.title("漫畫翻譯 · 詳細紀錄")
        self.log_window.geometry("760x360")
        self.log_window.withdraw()
        self.log_window.protocol("WM_DELETE_WINDOW", self.hide_log)
        self.log = tk.Text(self.log_window, height=5, state="disabled", wrap="word", relief="flat", padx=10, pady=8)
        self.log.pack(fill="both", expand=True)

    def build_translator_controls(self, frame):
        row = ttk.Frame(frame, style="Card.TFrame")
        row.grid(row=10, column=0, sticky="ew", pady=(6, 0))
        provider, model = self.translator_choice()
        ttk.Label(row, text="翻譯引擎", style="Muted.TLabel").pack(side="left")
        self.provider_label = tk.StringVar(value=PROVIDERS[provider])
        self.provider_box = ttk.Combobox(row, textvariable=self.provider_label, values=list(PROVIDERS.values()),
                                         state="readonly", width=16)
        self.provider_box.pack(side="left", padx=(6, 12))
        self.provider_box.bind("<<ComboboxSelected>>", self.on_provider_selected)
        ttk.Label(row, text="模型", style="Muted.TLabel").pack(side="left")
        self.model_name = tk.StringVar(value=model)
        self.model_box = ttk.Combobox(row, textvariable=self.model_name, width=28)
        self.model_box.pack(side="left", padx=(6, 6), fill="x", expand=True)
        for sequence in ("<<ComboboxSelected>>", "<Return>", "<FocusOut>"):
            self.model_box.bind(sequence, self.on_model_committed)
        self.model_refresh_button = ttk.Button(row, text="查詢可用模型", command=self.refresh_model_list,
                                               style="Compact.TButton")
        self.model_refresh_button.pack(side="left")
