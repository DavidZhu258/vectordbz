import pytest

from vectordbz_v2.llm_json import parse_llm_json


def test_parse_llm_json_accepts_fenced_json():
    parsed = parse_llm_json('```json\n{"ok": true, "items": [1]}\n```')

    assert parsed == {"ok": True, "items": [1]}


def test_parse_llm_json_ignores_preamble_and_trailing_text():
    parsed = parse_llm_json('Here is the report:\n{"stats": {"total": 2}}\nDone.')

    assert parsed == {"stats": {"total": 2}}


def test_parse_llm_json_raises_clear_error_when_no_json_object_exists():
    with pytest.raises(ValueError, match="No JSON object"):
        parse_llm_json("I could not produce the report today.")
