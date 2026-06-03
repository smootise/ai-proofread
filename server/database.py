"""
SQLite persistence layer for correction events.

Owns:
- Schema creation (idempotent, safe to call on every startup).
- Inserting correction_events rows (success and failure).
- Inserting correction_items rows linked to an event.

Tables match the schema in docs/backend_api.md.
Uses only the standard-library sqlite3 module (no ORM).
"""

import logging
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Schema
# ---------------------------------------------------------------------------

_CREATE_CORRECTION_EVENTS = """
CREATE TABLE IF NOT EXISTS correction_events (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    created_at      TEXT    NOT NULL,
    source_app      TEXT    NOT NULL,
    window_title    TEXT    NOT NULL DEFAULT '',
    mode            TEXT    NOT NULL DEFAULT 'unknown',
    original_text   TEXT,
    corrected_text  TEXT,
    language        TEXT,
    changed         INTEGER,
    confidence      REAL,
    model_name      TEXT    NOT NULL,
    latency_ms      INTEGER,
    error           TEXT
);
"""

_CREATE_CORRECTION_ITEMS = """
CREATE TABLE IF NOT EXISTS correction_items (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    event_id        INTEGER NOT NULL REFERENCES correction_events(id),
    original_text   TEXT    NOT NULL,
    corrected_text  TEXT    NOT NULL,
    category        TEXT    NOT NULL DEFAULT '',
    explanation     TEXT    NOT NULL DEFAULT '',
    start_offset    INTEGER,
    end_offset      INTEGER,
    accepted_status TEXT    NOT NULL DEFAULT 'auto_applied'
);
"""

# ---------------------------------------------------------------------------
# Connection helpers
# ---------------------------------------------------------------------------


def _get_connection(db_path: Path) -> sqlite3.Connection:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def init_db(db_path: Path) -> None:
    """Create tables if they do not already exist. Safe to call on every startup."""
    logger.info("Initialising database at %s", db_path)
    with _get_connection(db_path) as conn:
        conn.execute(_CREATE_CORRECTION_EVENTS)
        conn.execute(_CREATE_CORRECTION_ITEMS)
        conn.commit()
    logger.info("Database ready.")


# ---------------------------------------------------------------------------
# Data classes (plain, no Pydantic dependency in the DB layer)
# ---------------------------------------------------------------------------


@dataclass
class CorrectionEventRow:
    source_app: str
    window_title: str
    mode: str
    model_name: str
    original_text: Optional[str] = None
    corrected_text: Optional[str] = None
    language: Optional[str] = None
    changed: Optional[bool] = None
    confidence: Optional[float] = None
    latency_ms: Optional[int] = None
    error: Optional[str] = None


@dataclass
class CorrectionItemRow:
    original_text: str
    corrected_text: str
    category: str = ""
    explanation: str = ""
    start_offset: Optional[int] = None
    end_offset: Optional[int] = None
    accepted_status: str = "auto_applied"


# ---------------------------------------------------------------------------
# Insert helpers
# ---------------------------------------------------------------------------


def insert_event(db_path: Path, row: CorrectionEventRow) -> int:
    """
    Insert a correction_events row and return the new row id.

    Always sets created_at to the current UTC timestamp.
    """
    created_at = datetime.now(tz=timezone.utc).isoformat()
    sql = """
        INSERT INTO correction_events (
            created_at, source_app, window_title, mode,
            original_text, corrected_text, language, changed,
            confidence, model_name, latency_ms, error
        ) VALUES (
            :created_at, :source_app, :window_title, :mode,
            :original_text, :corrected_text, :language, :changed,
            :confidence, :model_name, :latency_ms, :error
        )
    """
    params = {
        "created_at": created_at,
        "source_app": row.source_app,
        "window_title": row.window_title,
        "mode": row.mode,
        "original_text": row.original_text,
        "corrected_text": row.corrected_text,
        "language": row.language,
        "changed": int(row.changed) if row.changed is not None else None,
        "confidence": row.confidence,
        "model_name": row.model_name,
        "latency_ms": row.latency_ms,
        "error": row.error,
    }
    with _get_connection(db_path) as conn:
        cursor = conn.execute(sql, params)
        conn.commit()
        event_id = cursor.lastrowid
    logger.debug("Inserted correction_event id=%d error=%r", event_id, row.error)
    return event_id


def insert_items(db_path: Path, event_id: int, items: list[CorrectionItemRow]) -> None:
    """Insert correction_items rows linked to the given event_id."""
    if not items:
        return
    sql = """
        INSERT INTO correction_items (
            event_id, original_text, corrected_text,
            category, explanation, start_offset, end_offset, accepted_status
        ) VALUES (
            :event_id, :original_text, :corrected_text,
            :category, :explanation, :start_offset, :end_offset, :accepted_status
        )
    """
    rows = [
        {
            "event_id": event_id,
            "original_text": item.original_text,
            "corrected_text": item.corrected_text,
            "category": item.category,
            "explanation": item.explanation,
            "start_offset": item.start_offset,
            "end_offset": item.end_offset,
            "accepted_status": item.accepted_status,
        }
        for item in items
    ]
    with _get_connection(db_path) as conn:
        conn.executemany(sql, rows)
        conn.commit()
    logger.debug("Inserted %d correction_item(s) for event_id=%d", len(items), event_id)
