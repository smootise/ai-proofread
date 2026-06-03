"""
Tests for the SQLite persistence layer (server/database.py).

Uses an in-memory database path (tmp_path fixture) so tests are isolated
and leave no files on disk.

Covers:
- Schema init is idempotent.
- insert_event returns an integer id.
- insert_event stores all fields correctly.
- insert_items links rows to event_id.
- accepted_status defaults to 'auto_applied'.
- Error events (with error= set) are stored.
- STORE_FULL_TEXT=False: text fields are None.
"""

import sqlite3
from pathlib import Path

from server.database import (
    CorrectionEventRow,
    CorrectionItemRow,
    init_db,
    insert_event,
    insert_items,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _conn(db_path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    return conn


# ---------------------------------------------------------------------------
# Schema
# ---------------------------------------------------------------------------


def test_init_db_creates_tables(tmp_path: Path) -> None:
    db = tmp_path / "test.db"
    init_db(db)
    with _conn(db) as conn:
        tables = {
            r[0]
            for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
        }
    assert "correction_events" in tables
    assert "correction_items" in tables


def test_init_db_is_idempotent(tmp_path: Path) -> None:
    db = tmp_path / "test.db"
    init_db(db)
    init_db(db)  # Should not raise
    with _conn(db) as conn:
        count = conn.execute("SELECT COUNT(*) FROM correction_events").fetchone()[0]
    assert count == 0


# ---------------------------------------------------------------------------
# insert_event
# ---------------------------------------------------------------------------


def _minimal_event(**kwargs) -> CorrectionEventRow:
    defaults = dict(
        source_app="Notepad",
        window_title="Untitled - Notepad",
        mode="selected_text",
        model_name="gemma4:e4b",
    )
    defaults.update(kwargs)
    return CorrectionEventRow(**defaults)


def test_insert_event_returns_id(tmp_path: Path) -> None:
    db = tmp_path / "test.db"
    init_db(db)
    event_id = insert_event(db, _minimal_event())
    assert isinstance(event_id, int)
    assert event_id > 0


def test_insert_event_stores_fields(tmp_path: Path) -> None:
    db = tmp_path / "test.db"
    init_db(db)
    row = _minimal_event(
        original_text="I have teh report.",
        corrected_text="I have the report.",
        language="en",
        changed=True,
        confidence=0.95,
        latency_ms=312,
    )
    event_id = insert_event(db, row)
    with _conn(db) as conn:
        r = conn.execute("SELECT * FROM correction_events WHERE id = ?", (event_id,)).fetchone()
    assert r["source_app"] == "Notepad"
    assert r["original_text"] == "I have teh report."
    assert r["corrected_text"] == "I have the report."
    assert r["language"] == "en"
    assert r["changed"] == 1
    assert abs(r["confidence"] - 0.95) < 1e-6
    assert r["latency_ms"] == 312
    assert r["error"] is None


def test_insert_event_error_stored(tmp_path: Path) -> None:
    db = tmp_path / "test.db"
    init_db(db)
    row = _minimal_event(error="Ollama unavailable: connection refused")
    event_id = insert_event(db, row)
    with _conn(db) as conn:
        r = conn.execute("SELECT error FROM correction_events WHERE id = ?", (event_id,)).fetchone()
    assert "Ollama unavailable" in r["error"]


def test_insert_event_without_text_when_store_full_text_false(tmp_path: Path) -> None:
    db = tmp_path / "test.db"
    init_db(db)
    row = _minimal_event(original_text=None, corrected_text=None, changed=False)
    event_id = insert_event(db, row)
    with _conn(db) as conn:
        r = conn.execute(
            "SELECT original_text, corrected_text FROM correction_events WHERE id = ?", (event_id,)
        ).fetchone()
    assert r["original_text"] is None
    assert r["corrected_text"] is None


def test_multiple_events_get_distinct_ids(tmp_path: Path) -> None:
    db = tmp_path / "test.db"
    init_db(db)
    id1 = insert_event(db, _minimal_event())
    id2 = insert_event(db, _minimal_event())
    assert id1 != id2


# ---------------------------------------------------------------------------
# insert_items
# ---------------------------------------------------------------------------


def _minimal_item(**kwargs) -> CorrectionItemRow:
    defaults = dict(
        original_text="teh", corrected_text="the", category="spelling", explanation="Typo."
    )
    defaults.update(kwargs)
    return CorrectionItemRow(**defaults)


def test_insert_items_links_to_event(tmp_path: Path) -> None:
    db = tmp_path / "test.db"
    init_db(db)
    event_id = insert_event(db, _minimal_event())
    insert_items(
        db,
        event_id,
        [_minimal_item(), _minimal_item(original_text="recieve", corrected_text="receive")],
    )
    with _conn(db) as conn:
        rows = conn.execute(
            "SELECT * FROM correction_items WHERE event_id = ?", (event_id,)
        ).fetchall()
    assert len(rows) == 2
    assert rows[0]["event_id"] == event_id


def test_insert_items_accepted_status_defaults_auto_applied(tmp_path: Path) -> None:
    db = tmp_path / "test.db"
    init_db(db)
    event_id = insert_event(db, _minimal_event())
    insert_items(db, event_id, [_minimal_item()])
    with _conn(db) as conn:
        row = conn.execute(
            "SELECT accepted_status FROM correction_items WHERE event_id = ?", (event_id,)
        ).fetchone()
    assert row["accepted_status"] == "auto_applied"


def test_insert_items_no_items_is_noop(tmp_path: Path) -> None:
    db = tmp_path / "test.db"
    init_db(db)
    event_id = insert_event(db, _minimal_event())
    insert_items(db, event_id, [])  # Should not raise
    with _conn(db) as conn:
        count = conn.execute(
            "SELECT COUNT(*) FROM correction_items WHERE event_id = ?", (event_id,)
        ).fetchone()[0]
    assert count == 0


def test_insert_items_stores_offsets(tmp_path: Path) -> None:
    db = tmp_path / "test.db"
    init_db(db)
    event_id = insert_event(db, _minimal_event())
    item = _minimal_item(start_offset=5, end_offset=8)
    insert_items(db, event_id, [item])
    with _conn(db) as conn:
        row = conn.execute(
            "SELECT start_offset, end_offset FROM correction_items WHERE event_id = ?", (event_id,)
        ).fetchone()
    assert row["start_offset"] == 5
    assert row["end_offset"] == 8
