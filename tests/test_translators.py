import hashlib
import json

import pytest

from src.offline import agy_provider, claude_provider, cli_common, codex_provider, translators
from src.offline.translation_common import PROMPT_VERSION


@pytest.mark.parametrize("provider,cls,default", [
    ("agy", agy_provider.AgyTranslator, "gemini-3.8-flash-medium"),
    ("claude", claude_provider.ClaudeTranslator, "sonnet"),
    ("codex", codex_provider.CodexTranslator, "gpt-5.5"),
])
def test_factory_loads_selected_adapter_and_preserves_batch_fingerprint(tmp_path, monkeypatch, provider, cls, default):
    executable = tmp_path / "fake-cli"
    executable.write_text("fixture")
    monkeypatch.setattr(cli_common.shutil, "which", lambda _: str(executable))
    translator = translators.create_translator(provider)
    assert type(translator) is cls
    assert translator.model == default
    assert translator.timeout == 180
    assert translator.fingerprint == {
        "provider": f"{provider}-cli", "model": default, "prompt": PROMPT_VERSION,
        "normalization": "s2t-protected-names-1", "cli_sha256": hashlib.sha256(b"fixture").hexdigest(),
    }
    settings = tmp_path / "settings.json"
    settings.write_text(json.dumps({"translator_provider": provider,
                                   "translator_models": {provider: "selected-model"}}))
    selected = translators.translator_from_settings(settings)
    assert type(selected) is cls and selected.model == "selected-model"
    assert translators.create_translator(provider, model="selected-model", timeout=45).timeout == 45


def test_model_queries_are_dispatched_to_the_selected_provider(monkeypatch):
    for provider, module in [("agy", agy_provider), ("claude", claude_provider), ("codex", codex_provider)]:
        models = [(f"{provider}-model", "Available model")]
        monkeypatch.setattr(module, "list_models", lambda models=models: models)
        assert translators.list_models(provider) == models
    with pytest.raises(ValueError, match="不支援"):
        translators.list_models("unknown")
    with pytest.raises(ValueError, match="不支援"):
        translators.create_translator("unknown")

def test_paid_api_environment_is_removed(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "x")
    monkeypatch.setenv("OPENAI_API_KEY", "x")
    monkeypatch.setenv("HARMLESS", "1")
    env = cli_common.clean_environment()
    assert "ANTHROPIC_API_KEY" not in env and "OPENAI_API_KEY" not in env and env["HARMLESS"] == "1"


def test_model_names_are_validated_and_choice_falls_back_to_defaults():
    assert cli_common.check_model_name("claude-sonnet-5-5") and cli_common.check_model_name("sonnet[1m]")
    for bad in ("", "-rf", "a b", "a;b", "x" * 200):
        with pytest.raises(ValueError):
            cli_common.check_model_name(bad)
    assert translators.configured_choice({}) == ("agy", translators.DEFAULT_MODELS["agy"])
    prefs = {"translator_provider": "codex", "translator_models": {"codex": "gpt-6-sol"}}
    assert translators.configured_choice(prefs) == ("codex", "gpt-6-sol")
    assert translators.configured_choice({"translator_provider": "bogus"})[0] == "agy"


def test_agy_models_are_parsed_from_cli_output(monkeypatch):
    from src.offline import agy_provider
    monkeypatch.setattr(agy_provider, "run_cli", lambda *a, **k: "Fetching available models...\ngemini-x-low\tGemini X (Low)\n")
    assert agy_provider.list_models("/fake/agy") == [("gemini-x-low", "Gemini X (Low)")]


@pytest.mark.parametrize('provider,model', [('codex', 'gpt-6.1-sol'), ('claude', 'claude-opus-5-5')])
def test_generation_options_fingerprint_and_saved_model_preferences(tmp_path, monkeypatch, provider, model):
    executable = tmp_path / 'cli'
    executable.write_text('fixture')
    monkeypatch.setattr(cli_common.shutil, 'which', lambda _: str(executable))
    base = translators.create_translator(provider, model).fingerprint
    off = translators.create_translator(provider, model, options={'fast': False})
    assert off.fingerprint == base
    options = {'effort': 'xhigh', 'fast': True}
    selected = translators.create_translator(provider, model, options=options)
    assert selected.fingerprint == {**base, **options}
    settings = tmp_path / 'settings.json'
    settings.write_text(json.dumps({'translator_provider': provider, 'translator_models': {provider: model},
        'translator_options': {provider: {model: options}},
        'translator_model_capabilities': {provider: {model: {'efforts': ['low', 'xhigh'], 'fast': True}}}}))
    from src.platforms import current
    monkeypatch.setattr(current, 'TRANSLATION_OPTIONS', True)
    assert translators.translator_from_settings(settings).fingerprint == selected.fingerprint
    monkeypatch.setattr(current, 'TRANSLATION_OPTIONS', False)
    assert translators.translator_from_settings(settings).fingerprint == base


def test_corrupted_or_unsupported_saved_options_cannot_enable_fast():
    from src.offline.generation_options import configured_options, effective_options
    preferences = {'translator_options': {'codex': {'model': {'effort': [], 'fast': 'yes'}}}}
    assert configured_options(preferences, 'codex', 'model') == {'fast': False}
    preferences['translator_options']['codex']['model'] = {'effort': 'xhigh', 'fast': True}
    assert effective_options(preferences, 'codex', 'model') == {'effort': None, 'fast': False}
