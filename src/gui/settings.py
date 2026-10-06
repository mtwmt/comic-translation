"""Persisted preferences: output directory and character-name glossary."""
from __future__ import annotations

import json
from pathlib import Path
from tkinter import filedialog

from src.offline.batch import parse_glossary
from src.offline.storage import atomic_json
from src.offline.translators import DEFAULT_MODELS, PROVIDERS, configured_choice, list_models
from src.platforms import current as platform_support


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

    def pipeline_choice(self):
        choice = self.translator_choice()
        from src.offline.generation_options import effective_options
        options = effective_options(self.preferences, *choice) if platform_support.TRANSLATION_OPTIONS else {}
        return (*choice, 180, options) if options else choice

    def refresh_translation_controls(self):
        controls = getattr(self, "translation_controls", None)
        if controls:
            controls.refresh()

    def cached_model_names(self, provider):
        if not platform_support.CACHE_MODEL_CATALOG:
            return []
        catalogs = self.preferences.get("translator_model_catalogs", {})
        names = catalogs.get(provider, []) if isinstance(catalogs, dict) else []
        from src.offline.cli_common import MODEL_NAME
        return list(dict.fromkeys(name for name in names if isinstance(name, str)
                                 and MODEL_NAME.fullmatch(name))) if isinstance(names, list) else []

    def initialize_model_list(self):
        provider = self.provider_from_label()
        capabilities = self.preferences.get("translator_model_capabilities", {})
        provider_caps = capabilities.get(provider) if isinstance(capabilities, dict) else None
        missing_options = platform_support.TRANSLATION_OPTIONS and provider in ("codex", "claude") \
            and (not isinstance(provider_caps, dict) or not provider_caps
                 or provider == "claude" and self.model_name.get().strip() not in provider_caps)
        if platform_support.CACHE_MODEL_CATALOG and (not self.cached_model_names(provider) or missing_options):
            self._request_model_list(quiet=True)

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
        self.model_box.configure(values=self.cached_model_names(provider))
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
        self.refresh_translation_controls()

    def refresh_model_list(self):
        """Ask the chosen CLI which models it offers (background; never blocks Tk)."""
        self._request_model_list()

    def _request_model_list(self, quiet=False):
        if self.busy:
            return
        provider = self.provider_from_label()
        request_id = getattr(self, "model_request_id", 0) + 1
        self.model_request_id = request_id
        if not quiet:
            self.status.set(f"正在向 {PROVIDERS[provider]} 查詢可用模型…")
        def fetch():
            try:
                items = list_models(provider)
                self.events.put({"models": provider, "request_id": request_id, "quiet": quiet, "items": items,
                                 "capabilities": getattr(items, "capabilities", {})})
            except Exception as error:
                self.events.put({"models": provider, "request_id": request_id, "quiet": quiet, "items": [], "error_text": str(error)})
        import threading
        threading.Thread(target=fetch, daemon=True).start()

    def show_model_list(self, event):
        if event["models"] != self.provider_from_label():
            return
        if "request_id" in event and event["request_id"] != getattr(self, "model_request_id", None):
            return
        names = [name for name, _ in event["items"]]
        error = event.get("error_text")
        if names and not error:
            if platform_support.CACHE_MODEL_CATALOG:
                catalogs = self.preferences.get("translator_model_catalogs", {})
                catalogs = dict(catalogs) if isinstance(catalogs, dict) else {}
                catalogs[event["models"]] = names
                capabilities = self.preferences.get("translator_model_capabilities", {})
                capabilities = dict(capabilities) if isinstance(capabilities, dict) else {}
                capabilities[event["models"]] = event.get("capabilities", {})
                try:
                    self.write_settings(translator_model_catalogs=catalogs,
                                        translator_model_capabilities=capabilities)
                except OSError as save_error:
                    error = f"已取得清單，但無法保存：{save_error}"
            self.model_box.configure(values=names)
        self.refresh_translation_controls()
        if self.busy:
            return  # A metadata response must not replace the running-page status.
        if error:
            self.status.set(f"模型清單查詢或保存失敗，保留既有選項，也可直接輸入名稱：{error}")
        elif not event.get("quiet"):
            self.status.set(f"{PROVIDERS[event['models']]} CLI 回傳 {len(names)} 個模型選項；實際權限依帳號與額度，也可直接輸入名稱。")
