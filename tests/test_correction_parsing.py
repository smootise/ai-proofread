"""
Tests for the JSON extraction logic in server/ollama_client.py.

Covers:
- Clean JSON response.
- JSON wrapped in ```json ... ``` markdown fences.
- JSON wrapped in ``` ... ``` fences (no language tag).
- JSON preceded and followed by explanatory prose.
- Invalid / unparseable JSON.
- Valid JSON but missing corrected_text.
- Valid JSON with empty corrected_text.
"""

import pytest

from server.ollama_client import OllamaParseError, _extract_json, _validate_correction_response

# ---------------------------------------------------------------------------
# _extract_json
# ---------------------------------------------------------------------------

CLEAN_JSON = {
    "corrected_text": "I have the report ready.",
    "language": "en",
    "changed": True,
    "confidence": 0.95,
    "corrections": [
        {
            "original": "teh",
            "corrected": "the",
            "category": "spelling",
            "explanation": "Spelling correction.",
            "start_offset": None,
            "end_offset": None,
        }
    ],
    "warnings": [],
}

CLEAN_JSON_STR = """\
{
  "corrected_text": "I have the report ready.",
  "language": "en",
  "changed": true,
  "confidence": 0.95,
  "corrections": [
    {
      "original": "teh",
      "corrected": "the",
      "category": "spelling",
      "explanation": "Spelling correction.",
      "start_offset": null,
      "end_offset": null
    }
  ],
  "warnings": []
}"""


def test_extract_json_clean() -> None:
    result = _extract_json(CLEAN_JSON_STR)
    assert result["corrected_text"] == "I have the report ready."
    assert result["changed"] is True
    assert len(result["corrections"]) == 1


def test_extract_json_fenced_json_tag() -> None:
    raw = "```json\n" + CLEAN_JSON_STR + "\n```"
    result = _extract_json(raw)
    assert result["corrected_text"] == "I have the report ready."


def test_extract_json_fenced_no_tag() -> None:
    raw = "```\n" + CLEAN_JSON_STR + "\n```"
    result = _extract_json(raw)
    assert result["corrected_text"] == "I have the report ready."


def test_extract_json_leading_prose() -> None:
    raw = "Here is the corrected text:\n\n" + CLEAN_JSON_STR
    result = _extract_json(raw)
    assert result["corrected_text"] == "I have the report ready."


def test_extract_json_trailing_prose() -> None:
    raw = CLEAN_JSON_STR + "\n\nI hope that helps!"
    result = _extract_json(raw)
    assert result["corrected_text"] == "I have the report ready."


def test_extract_json_surrounding_prose() -> None:
    raw = "Here is the JSON:\n" + CLEAN_JSON_STR + "\nLet me know if you need anything else."
    result = _extract_json(raw)
    assert result["corrected_text"] == "I have the report ready."


def test_extract_json_no_json_raises() -> None:
    with pytest.raises(OllamaParseError, match="No JSON object found"):
        _extract_json("This response has no JSON at all.")


def test_extract_json_unbalanced_braces_raises() -> None:
    with pytest.raises(OllamaParseError, match="Unbalanced braces"):
        _extract_json('{"corrected_text": "oops"')


def test_extract_json_invalid_syntax_raises() -> None:
    # Trailing comma — json.loads rejects this
    with pytest.raises(OllamaParseError, match="JSON parse error"):
        _extract_json('{"corrected_text": "hello",}')


# ---------------------------------------------------------------------------
# _validate_correction_response
# ---------------------------------------------------------------------------


def test_validate_ok() -> None:
    data = {"corrected_text": "Good text.", "language": "en", "changed": False, "confidence": 1.0}
    result = _validate_correction_response(data)
    assert result is data  # returns the same dict


def test_validate_missing_corrected_text_raises() -> None:
    with pytest.raises(OllamaParseError, match="missing or empty 'corrected_text'"):
        _validate_correction_response({"language": "en"})


def test_validate_empty_corrected_text_raises() -> None:
    with pytest.raises(OllamaParseError, match="missing or empty 'corrected_text'"):
        _validate_correction_response({"corrected_text": ""})


def test_validate_whitespace_only_corrected_text_raises() -> None:
    with pytest.raises(OllamaParseError, match="missing or empty 'corrected_text'"):
        _validate_correction_response({"corrected_text": "   "})


def test_validate_none_corrected_text_raises() -> None:
    with pytest.raises(OllamaParseError, match="missing or empty 'corrected_text'"):
        _validate_correction_response({"corrected_text": None})
