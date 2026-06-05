"""
SQLite persistence layer for correction events.

Owns:
- Schema creation (idempotent, safe to call on every startup).
- Inserting correction_events rows (success and failure).
- Inserting correction_items rows linked to an event.
- Reading and querying correction_events / correction_items (V2 web UI).
- Deleting correction events (cascade to items) (V2 web UI).

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
    error           TEXT,
    review_status   TEXT    NOT NULL DEFAULT 'auto_applied'
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


_CREATE_INDEXES = [
    # correction_events indexes — support list ordering and filtering
    "CREATE INDEX IF NOT EXISTS idx_events_created_at    ON correction_events(created_at)",
    "CREATE INDEX IF NOT EXISTS idx_events_source_app    ON correction_events(source_app)",
    "CREATE INDEX IF NOT EXISTS idx_events_language      ON correction_events(language)",
    "CREATE INDEX IF NOT EXISTS idx_events_review_status ON correction_events(review_status)",
    # correction_items indexes — support joins, cascade-delete queries, and category filtering
    "CREATE INDEX IF NOT EXISTS idx_items_event_id  ON correction_items(event_id)",
    "CREATE INDEX IF NOT EXISTS idx_items_category  ON correction_items(category)",
]


def init_db(db_path: Path) -> None:
    """
    Create tables and indexes if they do not already exist. Safe to call on every startup.

    Also applies idempotent schema migrations for columns added after the initial schema.
    Existing rows are unaffected — SQLite column defaults fill in any missing values.
    """
    logger.info("Initialising database at %s", db_path)
    with _get_connection(db_path) as conn:
        conn.execute(_CREATE_CORRECTION_EVENTS)
        conn.execute(_CREATE_CORRECTION_ITEMS)

        # V2.5 migration: add review_status column if it does not yet exist.
        # Run BEFORE the index creation so that idx_events_review_status can be
        # created even when upgrading from the V1/V2 schema that lacks the column.
        # Existing rows receive the DEFAULT value ('auto_applied') automatically.
        existing_cols = {
            row["name"] for row in conn.execute("PRAGMA table_info(correction_events)")
        }
        if "review_status" not in existing_cols:
            logger.info("Migrating: adding review_status column to correction_events")
            conn.execute(
                "ALTER TABLE correction_events "
                "ADD COLUMN review_status TEXT NOT NULL DEFAULT 'auto_applied'"
            )

        for idx_sql in _CREATE_INDEXES:
            conn.execute(idx_sql)

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
    review_status: str = "auto_applied"


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
            confidence, model_name, latency_ms, error, review_status
        ) VALUES (
            :created_at, :source_app, :window_title, :mode,
            :original_text, :corrected_text, :language, :changed,
            :confidence, :model_name, :latency_ms, :error, :review_status
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
        "review_status": row.review_status,
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


# ---------------------------------------------------------------------------
# Read helpers (V2 web UI)
# ---------------------------------------------------------------------------


def list_events(
    db_path: Path,
    *,
    changed: Optional[bool] = None,
    language: Optional[str] = None,
    category: Optional[str] = None,
    source_app: Optional[str] = None,
    q: Optional[str] = None,
    limit: int = 50,
    offset: int = 0,
) -> list[sqlite3.Row]:
    """
    Return correction_events rows matching the given filters, newest first.

    Filters:
    - changed: True → only changed events; False → only unchanged; None → all.
    - language: exact match on the language column.
    - category: event must have at least one correction_item with this category.
    - source_app: exact match on the source_app column.
    - q: LIKE filter over original_text OR corrected_text (case-insensitive, wrapped in %).
    - limit/offset: pagination.

    Each returned row includes an extra `item_count` column (number of linked items).
    """
    conditions: list[str] = []
    params: list = []

    if changed is not None:
        conditions.append("e.changed = ?")
        params.append(1 if changed else 0)
    if language is not None:
        conditions.append("e.language = ?")
        params.append(language)
    if source_app is not None:
        conditions.append("e.source_app = ?")
        params.append(source_app)
    if q:
        conditions.append("(e.original_text LIKE ? OR e.corrected_text LIKE ?)")
        like = f"%{q}%"
        params.extend([like, like])
    if category is not None:
        conditions.append(
            "EXISTS (SELECT 1 FROM correction_items ci WHERE ci.event_id = e.id AND ci.category = ?)"
        )
        params.append(category)

    where = f"WHERE {' AND '.join(conditions)}" if conditions else ""
    sql = f"""
        SELECT e.*,
               (SELECT COUNT(*) FROM correction_items ci WHERE ci.event_id = e.id) AS item_count
          FROM correction_events e
         {where}
         ORDER BY e.created_at DESC, e.id DESC
         LIMIT ? OFFSET ?
    """
    params.extend([limit, offset])

    with _get_connection(db_path) as conn:
        rows = conn.execute(sql, params).fetchall()
    return rows


def count_events(
    db_path: Path,
    *,
    changed: Optional[bool] = None,
    language: Optional[str] = None,
    category: Optional[str] = None,
    source_app: Optional[str] = None,
    q: Optional[str] = None,
) -> int:
    """Return the total count of correction_events matching the given filters (for pagination)."""
    conditions: list[str] = []
    params: list = []

    if changed is not None:
        conditions.append("e.changed = ?")
        params.append(1 if changed else 0)
    if language is not None:
        conditions.append("e.language = ?")
        params.append(language)
    if source_app is not None:
        conditions.append("e.source_app = ?")
        params.append(source_app)
    if q:
        conditions.append("(e.original_text LIKE ? OR e.corrected_text LIKE ?)")
        like = f"%{q}%"
        params.extend([like, like])
    if category is not None:
        conditions.append(
            "EXISTS (SELECT 1 FROM correction_items ci WHERE ci.event_id = e.id AND ci.category = ?)"
        )
        params.append(category)

    where = f"WHERE {' AND '.join(conditions)}" if conditions else ""
    sql = f"SELECT COUNT(*) FROM correction_events e {where}"

    with _get_connection(db_path) as conn:
        result = conn.execute(sql, params).fetchone()
    return result[0]


def get_event(db_path: Path, event_id: int) -> Optional[sqlite3.Row]:
    """Return a single correction_events row by id, or None if not found."""
    sql = """
        SELECT e.*,
               (SELECT COUNT(*) FROM correction_items ci WHERE ci.event_id = e.id) AS item_count
          FROM correction_events e
         WHERE e.id = ?
    """
    with _get_connection(db_path) as conn:
        return conn.execute(sql, (event_id,)).fetchone()


def get_items_for_event(db_path: Path, event_id: int) -> list[sqlite3.Row]:
    """Return all correction_items rows for the given event_id."""
    sql = """
        SELECT * FROM correction_items
         WHERE event_id = ?
         ORDER BY id ASC
    """
    with _get_connection(db_path) as conn:
        return conn.execute(sql, (event_id,)).fetchall()


def get_stats(db_path: Path) -> dict:
    """
    Return aggregate statistics for the dashboard.

    Keys:
    - total: total correction events.
    - changed: events where changed = 1.
    - unchanged: events where changed = 0.
    - errors: events where error IS NOT NULL.
    - top_categories: list of (category, count) tuples, top 5.
    - top_source_apps: list of (source_app, count) tuples, top 5.
    """
    with _get_connection(db_path) as conn:
        total = conn.execute("SELECT COUNT(*) FROM correction_events").fetchone()[0]
        changed_count = conn.execute(
            "SELECT COUNT(*) FROM correction_events WHERE changed = 1"
        ).fetchone()[0]
        unchanged_count = conn.execute(
            "SELECT COUNT(*) FROM correction_events WHERE changed = 0"
        ).fetchone()[0]
        error_count = conn.execute(
            "SELECT COUNT(*) FROM correction_events WHERE error IS NOT NULL"
        ).fetchone()[0]
        top_categories = conn.execute("""
            SELECT category, COUNT(*) AS cnt
              FROM correction_items
             WHERE category != ''
             GROUP BY category
             ORDER BY cnt DESC
             LIMIT 5
            """).fetchall()
        top_source_apps = conn.execute("""
            SELECT source_app, COUNT(*) AS cnt
              FROM correction_events
             GROUP BY source_app
             ORDER BY cnt DESC
             LIMIT 5
            """).fetchall()

    return {
        "total": total,
        "changed": changed_count,
        "unchanged": unchanged_count,
        "errors": error_count,
        "top_categories": [(r["category"], r["cnt"]) for r in top_categories],
        "top_source_apps": [(r["source_app"], r["cnt"]) for r in top_source_apps],
    }


# ---------------------------------------------------------------------------
# Delete helpers (V2 web UI)
# ---------------------------------------------------------------------------


def delete_event(db_path: Path, event_id: int) -> bool:
    """
    Delete a correction_event and all its correction_items in a single transaction.

    Returns True if the event was found and deleted, False if no row matched.
    Single-event delete only — does not accept a list of ids.
    """
    with _get_connection(db_path) as conn:
        conn.execute("DELETE FROM correction_items WHERE event_id = ?", (event_id,))
        cursor = conn.execute("DELETE FROM correction_events WHERE id = ?", (event_id,))
        conn.commit()
        deleted = cursor.rowcount > 0

    if deleted:
        logger.info("Deleted correction_event id=%d (cascade to items)", event_id)
    else:
        logger.warning("delete_event: no correction_event found with id=%d", event_id)
    return deleted


def update_review_status(db_path: Path, event_id: int, review_status: str) -> bool:
    """
    Update the review_status of a single correction_events row.

    Returns True if the row was found and updated, False if no row matched.
    """
    sql = "UPDATE correction_events SET review_status = ? WHERE id = ?"
    with _get_connection(db_path) as conn:
        cursor = conn.execute(sql, (review_status, event_id))
        conn.commit()
        updated = cursor.rowcount > 0

    if updated:
        logger.info("Updated review_status=%r for event id=%d", review_status, event_id)
    else:
        logger.warning("update_review_status: no correction_event found with id=%d", event_id)
    return updated
