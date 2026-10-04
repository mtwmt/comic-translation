"""Persisted preferences: output directory and character-name glossary."""
from __future__ import annotations

import json
from pathlib import Path
from tkinter import filedialog

from src.offline.batch import parse_glossary
from src.offline.storage import atomic_json
from src.offline.translators import DEFAULT_MODELS, PROVIDERS, configured_choice, list_models


class SettingsMixin:
    def load_preferences(self, settings_path):
        self.settings = settings_path
        self.preferences = {}
        if self.settings.exists():
            try:
                saved = json.loads(self.settings.read_text(encoding="utf-8"))
                if isinstance(saved, dict):
                    self.preferences = saved
            except (ValueError, OSError):
                pass

    def update_name_count(self):
        count = len([line for line in self.glossary.get("1.0", "end").splitlines() if line.strip()])
        self.names_title.configure(text=f"角色名稱對照（{count} 組）")

    def output_description(self):
        return str(self.output_directory / "final") if self.output_directory else "來源旁的 translated/final（預設）"

    def write_settings(self, **updates):
        values = {**getattr(self, "preferences", {}), **updates}
        atomic_json(self.settings, values)
        self.preferences = values

    def pick_output(self):
        if self.busy:
            return
        initial = self.output_directory or next(iter(self.source_roots.values()), Path.home())
        path = filedialog.askdirectory(parent=self.root, title="選擇輸出資料夾（成品存入 final）",
                                       initialdir=str(initial))
        if path:
            self.set_output_directory(Path(path))

    def set_output_directory(self, path):
        if self.busy:
            return
        try:
            output = Path(path).expanduser().resolve() if path else None
            self.write_settings(output_directory=str(output) if output else None)
        except (ValueError, OSError) as error:
            self.status.set(f"無法儲存輸出位置：{error}")
            return
        self.output_directory = output
        self.output_path.set(self.output_description())
        self.reset_output_button.configure(state="normal" if output else "disabled")
        self.status.set("已儲存輸出位置。新批次使用此位置；繼續舊批次沿用原位置。")

    def save_glossary(self):
        try:
            text = self.glossary.get("1.0", "end").strip()
            mapping = parse_glossary(text)
            self.write_settings(glossary=text)
        except (ValueError, OSError) as error:
            self.status.set(str(error))
            return
        if hasattr(self, "names_title"):
            self.update_name_count()
        self.status.set(f"已儲存 {len(mapping)} 組角色名稱。新批次使用此對照；繼續舊批次會沿用該批原有對照。")

    # -- translator engine and model -------------------------------------
    def translator_choice(self):
        return configured_choice(getattr(self, "preferences", {}))

    def save_translator_choice(self, provider, model):
        models = dict(self.preferences.get("translator_models") or {})
        models[provider] = model
        self.write_settings(translator_provider=provider, translator_models=models)
        self.pipeline = None  # the translator is part of the pipeline; rebuild on next run

    def provider_from_label(self):
        labels = {label: key for key, label in PROVIDERS.items()}
        return labels.get(self.provider_label.get(), self.translator_choice()[0])

    def on_provider_selected(self, event=None):
        if self.busy:
            return
        provider = self.provider_from_label()
        saved = (self.preferences.get("translator_models") or {}).get(provider)
        model = saved if isinstance(saved, str) and saved else DEFAULT_MODELS[provider]
        self.model_name.set(model)
        self.apply_translator_choice(provider, model)
        self.refresh_model_list()

    def on_model_committed(self, event=None):
        if not self.busy:
            self.apply_translator_choice(self.provider_from_label(), self.model_name.get().strip())

    def apply_translator_choice(self, provider, model):
        try:
            from src.offline.cli_common import check_model_name
            self.save_translator_choice(provider, check_model_name(model))
        except (ValueError, OSError) as error:
            self.status.set(f"無法儲存翻譯引擎設定：{error}")
            return
        self.status.set(f"翻譯引擎：{PROVIDERS[provider]}／{model}。新批次使用；續跑舊批次須沿用原模型。")

    def refresh_model_list(self):
        """Ask the chosen CLI which models it offers (background; never blocks Tk)."""
        provider = self.provider_from_label()
        self.status.set(f"正在向 {PROVIDERS[provider]} 查詢可用模型…")
        def fetch():
            try:
                self.events.put({"models": provider, "items": list_models(provider)})
            except Exception as error:
                self.events.put({"models": provider, "items": [], "error_text": str(error)})
        import threading
        threading.Thread(target=fetch, daemon=True).start()

    def show_model_list(self, event):
        if event["models"] != self.provider_from_label():
            return
        names = [name for name, _ in event["items"]]
        self.model_box.configure(values=names)
        if event.get("error_text"):
            self.status.set(f"無法取得模型清單，可直接輸入模型名稱：{event['error_text']}")
        else:
            self.status.set(f"{PROVIDERS[event['models']]} 有 {len(names)} 個模型可選；也可直接輸入名稱。")
