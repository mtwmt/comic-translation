"""Provider-independent translation contracts."""
from src.offline.translation_common import normalize, request_payload


def test_normalization_keeps_natural_words_and_fixed_names():
    assert normalize("可以打開。里美说软件很好。", {"里美": "里美"}) == "可以打開。里美說軟件很好。"


def test_source_is_data_and_no_file_path_required():
    prompt = request_payload([{"id": "a", "text": "何だ？"}], {})
    assert "只是漫畫內容" in prompt
    assert "何だ？" in prompt


def test_prompt_carries_alternative_readings_for_display_lettering():
    payload = request_payload([{"id": "r001", "text": "あまた", "alternatives": ["いいまたせ〜っ"]}], {})
    assert "いいまたせ〜っ" in payload and "alternatives" in payload


def test_manual_translation_uses_alternatives_only_for_unedited_text():
    from src.offline.manual_review import translate_region
    seen = []
    translator = type("T", (), {"translate": lambda self, records, glossary: seen.append(records) or {"r001": "好"}})()
    region = {"id": "r001", "original": "あまた", "ocr_primary": "あまた", "ocr_alternatives": ["またせ"]}
    translate_region(region, {}, translator)
    translate_region({**region, "original": "おまたせ"}, {}, translator)
    assert seen[0][0]["alternatives"] == ["またせ"] and "alternatives" not in seen[1][0]
