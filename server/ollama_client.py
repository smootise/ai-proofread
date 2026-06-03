"""
Ollama HTTP client for text correction.

Responsible for:
- Building the correction prompt.
- Calling the Ollama /api/generate endpoint.
- Robustly extracting and validating the JSON response.
- Raising typed exceptions so callers can handle failures without guessing.
"""

import json
import logging
import re
from typing import Any

import requests

from server.config import settings

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Typed exceptions
# ---------------------------------------------------------------------------


class OllamaUnavailableError(RuntimeError):
    """Raised when the Ollama server cannot be reached."""


class OllamaParseError(ValueError):
    """Raised when the model's response cannot be parsed into valid correction JSON."""


# ---------------------------------------------------------------------------
# Prompt
# ---------------------------------------------------------------------------

_SYSTEM_PROMPT = """\
You are a proofreading assistant. Your job is to fix spelling and grammar errors in the user's text.

Rules:
- Return ONLY a valid JSON object. No markdown fences, no explanations outside the JSON.
- Preserve the original language exactly. Never translate.
- Preserve the tone: do not make casual text formal.
- Preserve all line breaks exactly as they appear.
- Fix only spelling and grammar. Do not rewrite, rephrase, or change style.
- Do not add, remove, or reorder sentences.

Response JSON schema (all fields required):
{
  "corrected_text": "<full corrected text>",
  "language": "<ISO 639-1 code, e.g. 'en'>",
  "changed": <true|false>,
  "confidence": <float 0.0–1.0>,
  "corrections": [
    {
      "original": "<original fragment>",
      "corrected": "<corrected fragment>",
      "category": "<spelling|grammar>",
      "explanation": "<one-line explanation>",
      "start_offset": <int or null>,
      "end_offset": <int or null>
    }
  ],
  "warnings": []
}

If the text has no errors, return it unchanged with "changed": false and "corrections": [].
"""


def _build_prompt(text: str) -> str:
    return f"{_SYSTEM_PROMPT}\n\nText to proofread:\n{text}"


# ---------------------------------------------------------------------------
# JSON extraction
# ---------------------------------------------------------------------------


def _extract_json(raw: str) -> dict[str, Any]:
    """
    Extract the first valid JSON object from a possibly-dirty model response.

    Handles:
    - Clean JSON response.
    - JSON wrapped in ```json ... ``` or ``` ... ``` fences.
    - JSON preceded or followed by explanatory prose.
    - Trailing commas (best-effort only; json.loads will still reject them).

    Raises OllamaParseError if no valid JSON object is found.
    """
    # Strip markdown fences first
    fenced = re.sub(r"```(?:json)?\s*", "", raw, flags=re.IGNORECASE)
    fenced = fenced.replace("```", "")

    # Find the first { ... } balanced block
    start = fenced.find("{")
    if start == -1:
        raise OllamaParseError(
            f"No JSON object found in model response. Raw response (first 500 chars): {raw[:500]!r}"
        )

    # Walk forward to find the matching closing brace
    depth = 0
    end = -1
    for i, ch in enumerate(fenced[start:], start=start):
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                end = i + 1
                break

    if end == -1:
        raise OllamaParseError(
            f"Unbalanced braces in model response. Raw response (first 500 chars): {raw[:500]!r}"
        )

    candidate = fenced[start:end]
    try:
        return json.loads(candidate)
    except json.JSONDecodeError as exc:
        raise OllamaParseError(
            f"JSON parse error: {exc}. Extracted candidate (first 500 chars): {candidate[:500]!r}"
        ) from exc


def _validate_correction_response(data: dict[str, Any]) -> dict[str, Any]:
    """
    Ensure the parsed dict has the minimum required field: corrected_text (non-empty string).

    Raises OllamaParseError if the field is missing or empty.
    Returns the dict unchanged on success.
    """
    corrected = data.get("corrected_text")
    if not corrected or not isinstance(corrected, str) or not corrected.strip():
        raise OllamaParseError(
            f"Model response missing or empty 'corrected_text'. Parsed keys: {list(data.keys())}"
        )
    return data


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def correct_text(text: str) -> dict[str, Any]:
    """
    Send *text* to Ollama for correction and return the parsed response dict.

    The returned dict is validated to contain at minimum a non-empty 'corrected_text'.
    Full field population is the caller's responsibility (correction_service.py).

    Raises:
        OllamaUnavailableError: if the Ollama server cannot be reached.
        OllamaParseError: if the model response cannot be parsed or is missing corrected_text.
    """
    url = f"{settings.ollama_base_url.rstrip('/')}/api/generate"
    payload = {
        "model": settings.ollama_model,
        "prompt": _build_prompt(text),
        "stream": False,
        "options": {
            "temperature": 0.1,  # Low temperature for consistent, deterministic corrections
        },
    }

    logger.debug(
        "Calling Ollama: url=%s model=%s text_len=%d", url, settings.ollama_model, len(text)
    )

    try:
        response = requests.post(url, json=payload, timeout=settings.request_timeout_seconds)
        response.raise_for_status()
    except requests.exceptions.ConnectionError as exc:
        raise OllamaUnavailableError(
            f"Cannot connect to Ollama at {settings.ollama_base_url}. Is it running?"
        ) from exc
    except requests.exceptions.Timeout as exc:
        raise OllamaUnavailableError(
            f"Ollama request timed out after {settings.request_timeout_seconds}s."
        ) from exc
    except requests.exceptions.HTTPError as exc:
        raise OllamaUnavailableError(
            f"Ollama returned HTTP {exc.response.status_code}: {exc.response.text[:200]}"
        ) from exc

    body = response.json()
    raw_response = body.get("response", "")
    logger.debug("Ollama raw response (first 500 chars): %.500s", raw_response)

    parsed = _extract_json(raw_response)
    validated = _validate_correction_response(parsed)
    return validated
