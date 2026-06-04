"""
History service — thin orchestration layer for the V2 web UI.

Wraps database query/delete helpers and returns template-ready data.
Keeps route handlers in web.py small and keeps business logic testable
independently of the HTTP layer.
"""

import logging
import sqlite3
from typing import Any, Optional

from server.config import settings
from server.database import (
    count_events,
    delete_event,
    get_event,
    get_items_for_event,
    get_stats,
    list_events,
)
from server.diffing import build_diff

logger = logging.getLogger(__name__)

PAGE_SIZE_DEFAULT = 50


# ---------------------------------------------------------------------------
# Dashboard
# ---------------------------------------------------------------------------


def get_dashboard_stats() -> dict[str, Any]:
    """Return aggregated stats for the dashboard page."""
    try:
        return get_stats(settings.db_path)
    except Exception as exc:
        logger.error("Failed to load dashboard stats: %s", exc)
        return {
            "total": 0,
            "changed": 0,
            "unchanged": 0,
            "errors": 0,
            "top_categories": [],
            "top_source_apps": [],
            "_db_error": True,
        }


# ---------------------------------------------------------------------------
# History list
# ---------------------------------------------------------------------------


def list_history(
    *,
    changed: Optional[str] = None,
    language: Optional[str] = None,
    category: Optional[str] = None,
    source_app: Optional[str] = None,
    q: Optional[str] = None,
    page: int = 1,
    page_size: int = PAGE_SIZE_DEFAULT,
) -> dict[str, Any]:
    """
    Return paginated correction events plus pagination metadata.

    The `changed` filter accepts the strings "changed", "unchanged", or None/empty for all.
    All filter values are forwarded to database.list_events as-is (already validated/sanitised
    by the route layer before calling here).
    """
    # Normalise the `changed` string filter to a bool or None.
    changed_bool: Optional[bool] = None
    if changed == "changed":
        changed_bool = True
    elif changed == "unchanged":
        changed_bool = False

    # Treat empty strings as None (unset filter).
    language = language or None
    category = category or None
    source_app = source_app or None
    q = q or None

    offset = (max(page, 1) - 1) * page_size

    try:
        rows = list_events(
            settings.db_path,
            changed=changed_bool,
            language=language,
            category=category,
            source_app=source_app,
            q=q,
            limit=page_size,
            offset=offset,
        )
        total = count_events(
            settings.db_path,
            changed=changed_bool,
            language=language,
            category=category,
            source_app=source_app,
            q=q,
        )
    except Exception as exc:
        logger.error("Failed to list events: %s", exc)
        rows = []
        total = 0

    total_pages = max(1, (total + page_size - 1) // page_size)
    current_page = max(1, min(page, total_pages))

    return {
        "events": [_format_event_row(r) for r in rows],
        "total": total,
        "page": current_page,
        "page_size": page_size,
        "total_pages": total_pages,
        # Pass filters back so templates can pre-fill form fields.
        "filters": {
            "changed": changed or "",
            "language": language or "",
            "category": category or "",
            "source_app": source_app or "",
            "q": q or "",
        },
    }


# ---------------------------------------------------------------------------
# Detail
# ---------------------------------------------------------------------------


def get_event_detail(event_id: int) -> Optional[dict[str, Any]]:
    """
    Return the full detail dict for a single correction event, or None if not found.

    Includes:
    - All event metadata (formatted for display).
    - before/after HTML diff (via diffing.build_diff).
    - List of correction items.
    """
    try:
        event_row = get_event(settings.db_path, event_id)
    except Exception as exc:
        logger.error("Failed to load event %d: %s", event_id, exc)
        return None

    if event_row is None:
        return None

    try:
        item_rows = get_items_for_event(settings.db_path, event_id)
    except Exception as exc:
        logger.error("Failed to load items for event %d: %s", event_id, exc)
        item_rows = []

    original_text = event_row["original_text"]
    corrected_text = event_row["corrected_text"]
    diff_html = build_diff(original_text, corrected_text)

    return {
        **_format_event_row(event_row),
        "original_text": original_text,
        "corrected_text": corrected_text,
        "diff_html": diff_html,
        "fragments": [_format_item_row(r) for r in item_rows],
    }


# ---------------------------------------------------------------------------
# Delete
# ---------------------------------------------------------------------------


def remove_event(event_id: int) -> bool:
    """
    Cascade-delete a single correction event and its items.

    Returns True if deleted, False if not found.
    """
    try:
        return delete_event(settings.db_path, event_id)
    except Exception as exc:
        logger.error("Failed to delete event %d: %s", event_id, exc)
        return False


# ---------------------------------------------------------------------------
# Internal formatters
# ---------------------------------------------------------------------------


def _format_event_row(row: sqlite3.Row) -> dict[str, Any]:
    """Convert a correction_events sqlite3.Row to a plain dict safe for templates."""
    d = dict(row)
    # Normalise the changed integer to a Python bool (or None for error events).
    raw_changed = d.get("changed")
    if raw_changed is None:
        d["changed"] = None
    else:
        d["changed"] = bool(raw_changed)

    # Provide a short preview of the original text (for the history list).
    orig = d.get("original_text") or ""
    d["original_preview"] = (orig[:80] + "…") if len(orig) > 80 else orig

    return d


def _format_item_row(row: sqlite3.Row) -> dict[str, Any]:
    """Convert a correction_items sqlite3.Row to a plain dict safe for templates."""
    return dict(row)
