"""Windows reasoning/speed controls, separate from the macOS view."""
from __future__ import annotations

import tkinter as tk
from tkinter import ttk

from src.offline.generation_options import EFFORT_LABELS, effective_options


class TranslationControls:
    def __init__(self, gui):
        self.gui = gui
        self.frame = ttk.Frame(gui.model_box.master, style="Card.TFrame")
        self.frame.pack(side="right", before=gui.model_box, fill="y", padx=(6, 12))
        ttk.Label(self.frame, text="思考強度", style="Muted.TLabel").pack(side="left")
        self.effort = tk.StringVar(value=EFFORT_LABELS[None])
        self.effort_box = ttk.Combobox(self.frame, textvariable=self.effort, width=7, state="readonly")
        self.effort_box.pack(side="left", padx=(6, 0), fill="y")
        self.effort_box.bind("<<ComboboxSelected>>", self.commit)
        self.fast = tk.BooleanVar(value=False)
        self.fast_button = ttk.Checkbutton(self.frame, variable=self.fast, command=self.commit)
        self.refresh()

    def capabilities(self):
        saved = self.gui.preferences.get("translator_model_capabilities", {})
        catalog = saved.get(self.gui.provider_from_label(), {}) if isinstance(saved, dict) else {}
        model = self.gui.model_name.get().strip()
        result = catalog.get(model, {}) if isinstance(catalog, dict) else {}
        if self.gui.provider_from_label() == "agy":
            # Older caches already contain real AGY variant names; use them
            # immediately without requiring another catalog request.
            from src.offline.agy_provider import model_capabilities
            result = model_capabilities(self.gui.cached_model_names("agy")).get(model, {})
        return result if isinstance(result, dict) else {}

    def current_options(self):
        provider = self.gui.provider_from_label()
        if provider not in ("codex", "claude"):
            return {}
        return effective_options(self.gui.preferences, provider, self.gui.model_name.get().strip())

    def refresh(self):
        provider = self.gui.provider_from_label()
        caps = self.capabilities()
        levels = caps.get("efforts", [])
        labels = [label for level, label in EFFORT_LABELS.items() if level is not None and level in levels]
        if provider == "agy":
            options = {"effort": caps.get("selected_effort"), "fast": False}
        else:
            labels.insert(0, EFFORT_LABELS[None])
            options = self.current_options()
        if not labels:
            labels = [EFFORT_LABELS[None]]
        self.effort.set(EFFORT_LABELS[options["effort"]])
        self.fast.set(options["fast"])
        busy = self.gui.busy
        self.effort_box.configure(values=labels, state="readonly" if levels and not busy else "disabled")
        fast_label = {"agy": "Fast", "claude": "Fast（額外計費）", "codex": "Fast（較耗額度）"}
        self.fast_button.configure(text=fast_label[provider],
                                   state="normal" if caps.get("fast") is True and not busy else "disabled")
        if caps.get("fast") is True:
            self.fast_button.pack(side="left", padx=(8, 0))
        else:
            self.fast_button.pack_forget()

    def commit(self, event=None):
        if self.gui.busy:
            return
        provider = self.gui.provider_from_label()
        model = self.gui.model_name.get().strip()
        caps = self.capabilities()
        effort = next((level for level, label in EFFORT_LABELS.items() if label == self.effort.get()), None)
        if provider == "agy":
            target = caps.get("effort_models", {}).get(effort)
            if not target:
                self.refresh()
                return
            try:
                self.gui.save_translator_choice(provider, target)
            except (ValueError, OSError) as error:
                self.gui.status.set(f"無法儲存 AGY 思考強度：{error}")
                self.refresh()
                return
            self.gui.model_name.set(target)
            self.gui.status.set(f"AGY 思考強度：{EFFORT_LABELS[effort]}／{target}。新批次使用；續跑須沿用原模型。")
            self.refresh()
            return
        options = {"effort": effort if effort in caps.get("efforts", []) else None,
                   "fast": self.fast.get() and caps.get("fast") is True}
        saved = self.gui.preferences.get("translator_options", {})
        saved = dict(saved) if isinstance(saved, dict) else {}
        models = saved.get(provider, {})
        models = dict(models) if isinstance(models, dict) else {}
        models[model] = options
        saved[provider] = models
        try:
            self.gui.write_settings(translator_options=saved)
        except OSError as error:
            self.gui.status.set(f"無法儲存思考強度與 Fast：{error}")
            self.refresh()
            return
        self.gui.pipeline = None
        self.gui.status.set("已儲存思考強度與 Fast。新批次使用；續跑須沿用該批原設定。")
        self.refresh()
