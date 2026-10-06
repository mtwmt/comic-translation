"""Select subscription translators and models, and load saved preferences."""
from __future__ import annotations

import json
from pathlib import Path

from . import agy_provider, claude_provider, codex_provider

PROVIDERS = {"agy": "AGY（Antigravity）", "claude": "Claude Code", "codex": "Codex（ChatGPT）"}
DEFAULT_PROVIDER = "agy"
DEFAULT_MODELS = {"agy": agy_provider.DEFAULT_MODEL, "claude": claude_provider.DEFAULT_MODEL,
                  "codex": codex_provider.DEFAULT_MODEL}


def list_models(provider):
    """(id, label) pairs the user can choose from; an empty list means type one in."""
    if provider == "agy":
        return agy_provider.list_models()
    if provider == "claude":
        return claude_provider.list_models()
    if provider == "codex":
        return codex_provider.list_models()
    raise ValueError("不支援的翻譯引擎")


def create_translator(provider=DEFAULT_PROVIDER, model=None, timeout=180, options=None):
    model = model or DEFAULT_MODELS.get(provider)
    from .generation_options import validate_options
    options = validate_options(provider, **(options or {}))
    if provider == "agy":
        return agy_provider.AgyTranslator(timeout=timeout, model=model)
    if provider == "claude":
        return claude_provider.ClaudeTranslator(timeout=timeout, model=model, **options)
    if provider == "codex":
        return codex_provider.CodexTranslator(timeout=timeout, model=model, **options)
    raise ValueError("不支援的翻譯引擎")


def configured_choice(preferences):
    """(provider, model) from saved GUI settings, falling back to defaults."""
    provider = preferences.get("translator_provider")
    if provider not in PROVIDERS:
        provider = DEFAULT_PROVIDER
    models = preferences.get("translator_models")
    model = models.get(provider) if isinstance(models, dict) else None
    return provider, model if isinstance(model, str) and model else DEFAULT_MODELS[provider]


def translator_from_settings(settings_path=None):
    """Build the translator the GUI is configured for (used by the review window and CLI)."""
    from .batch import STATE_ROOT
    path = Path(settings_path or STATE_ROOT / "settings.json")
    try:
        preferences = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(preferences, dict):
            preferences = {}
    except (OSError, ValueError):
        preferences = {}
    from src.platforms import current as platform_support
    from .generation_options import effective_options
    provider, model = configured_choice(preferences)
    options = effective_options(preferences, provider, model) if platform_support.TRANSLATION_OPTIONS else {}
    return create_translator(provider, model, options=options)
