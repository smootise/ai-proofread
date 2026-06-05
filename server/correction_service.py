"""
Correction service — orchestrates the full proofread pipeline.

Responsibilities:
- Validate text length against MIN_CHARS / MAX_CHARS.
- Call ollama_client.correct_text() and measure latency.
- Persist the correction event and items to SQLite (including failure events).
- Assemble and return the ProofreadResponse.
- Raise CorrectionError on any failure so main.py can return a safe HTTP response.
"""

import logging
import time
from typing import Optional

from server.config import settings
from server.database import CorrectionEventRow, CorrectionItemRow, insert_event, insert_items
from server.models import Correction, ProofreadRequest, ProofreadResponse
from server.ollama_client import OllamaParseError, OllamaUnavailableError, correct_text

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Typed service error
# ---------------------------------------------------------------------------


class CorrectionError(RuntimeError):
    """Raised when correction fails for any reason. Message is safe to surface to the client."""


# ---------------------------------------------------------------------------
# Service
# ---------------------------------------------------------------------------


def proofread(request: ProofreadRequest) -> ProofreadResponse:
    """
    Run the full correction pipeline for the given request.

    Always logs an event to SQLite (with error= set on failure).
    Raises CorrectionError on any failure — callers must not paste anything.
    """
    text = request.text
    db_path = settings.db_path

    # -- Length validation (before any DB write or Ollama call) --
    if len(text) < settings.min_chars:
        raise CorrectionError(
            f"Text is too short ({len(text)} chars, minimum {settings.min_chars})."
        )
    if len(text) > settings.max_chars:
        raise CorrectionError(
            f"Text is too long ({len(text)} chars, maximum {settings.max_chars})."
        )

    # -- Call Ollama and measure latency --
    error_message: Optional[str] = None
    raw_result: Optional[dict] = None
    start = time.monotonic()

    try:
        raw_result = correct_text(text)
    except OllamaUnavailableError as exc:
        error_message = f"Ollama unavailable: {exc}"
        logger.warning(error_message)
    except OllamaParseError as exc:
        error_message = f"Ollama parse error: {exc}"
        logger.warning(error_message)
    except Exception as exc:
        error_message = f"Unexpected correction error: {exc}"
        logger.exception(error_message)

    latency_ms = int((time.monotonic() - start) * 1000)

    # -- Determine what to store --
    original_to_store = text if settings.store_full_text else None
    corrected_to_store: Optional[str] = None
    language: Optional[str] = None
    changed: Optional[bool] = None
    confidence: Optional[float] = None
    corrections: list[Correction] = []

    if raw_result is not None:
        corrected_text_value = raw_result.get("corrected_text", "")
        corrected_to_store = corrected_text_value if settings.store_full_text else None
        language = raw_result.get("language", "unknown")
        changed = bool(raw_result.get("changed", False))
        confidence = float(raw_result.get("confidence", 1.0))

        raw_corrections = raw_result.get("corrections") or []
        for c in raw_corrections:
            if not isinstance(c, dict):
                continue
            try:
                corrections.append(
                    Correction(
                        original=c.get("original", ""),
                        corrected=c.get("corrected", ""),
                        category=c.get("category", ""),
                        explanation=c.get("explanation", ""),
                        start_offset=c.get("start_offset"),
                        end_offset=c.get("end_offset"),
                    )
                )
            except Exception as exc:
                logger.warning("Skipping malformed correction item: %r — %s", c, exc)

    # -- Persist to SQLite --
    # Use review_pending for review-path requests; auto_applied for the fast path.
    initial_review_status = "review_pending" if request.review else "auto_applied"
    event_row = CorrectionEventRow(
        source_app=request.source_app,
        window_title=request.window_title,
        mode=request.mode.value,
        model_name=settings.ollama_model,
        original_text=original_to_store,
        corrected_text=corrected_to_store,
        language=language,
        changed=changed,
        confidence=confidence,
        latency_ms=latency_ms,
        error=error_message,
        review_status=initial_review_status,
    )
    try:
        event_id = insert_event(db_path, event_row)
    except Exception as exc:
        # DB write failure: log but do not silence the upstream error
        logger.error("Failed to persist correction event: %s", exc)
        event_id = -1

    if raw_result is not None and corrections and event_id > 0:
        item_rows = [
            CorrectionItemRow(
                original_text=c.original,
                corrected_text=c.corrected,
                category=c.category,
                explanation=c.explanation,
                start_offset=c.start_offset,
                end_offset=c.end_offset,
            )
            for c in corrections
        ]
        try:
            insert_items(db_path, event_id, item_rows)
        except Exception as exc:
            logger.error("Failed to persist correction items: %s", exc)

    # -- Raise on failure (after DB logging) --
    if error_message is not None:
        raise CorrectionError(error_message)

    return ProofreadResponse(
        corrected_text=raw_result["corrected_text"],
        language=language or "unknown",
        changed=changed or False,
        confidence=confidence or 1.0,
        corrections=corrections,
        warnings=[],
        event_id=event_id if event_id > 0 else None,
    )
