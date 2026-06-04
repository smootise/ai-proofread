"""
Tests for V2 database read/query/delete helpers (server/database.py).

Uses tmp_path for isolated in-memory-equivalent SQLite files (no shared state).

Covers:
- list_events: basic, changed/unchanged filter, language filter, source_app filter,
  category filter (EXISTS on items), free-text q filter, limit/offset pagination.
- count_events: mirrors list_events filters.
- get_event: found, not found, item_count column.
- get_items_for_event: linked rows, empty, ordered by id.
- get_stats: totals, changed/unchanged/error counts, top categories, top source apps.
- delete_event: cascade (items + event gone), returns True on success, False on unknown id,
  does not touch other events.
- init_db: idempotent index creation (no error on repeated calls).
"""

import sqlite3
from pathlib import Path

import pytest

from server.database import (
    CorrectionEventRow,
    CorrectionItemRow,
    count_events,
    delete_event,
    get_event,
    get_items_for_event,
    get_stats,
    init_db,
    insert_event,
    insert_items,
    list_events,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _conn(db_path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    return conn


def _evt(db: Path, **kwargs) -> int:
    """Insert a minimal event and return its id. Keyword args override defaults."""
    defaults = dict(
        source_app="Notepad",
        window_title="Untitled",
        mode="selected_text",
        model_name="gemma4:e4b",
        language="en",
        changed=True,
        original_text="I have teh report.",
        corrected_text="I have the report.",
    )
    defaults.update(kwargs)
    return insert_event(db, CorrectionEventRow(**defaults))


def _item(db: Path, event_id: int, **kwargs) -> None:
    defaults = dict(
        original_text="teh",
        corrected_text="the",
        category="spelling",
        explanation="Typo.",
    )
    defaults.update(kwargs)
    insert_items(db, event_id, [CorrectionItemRow(**defaults)])


# ---------------------------------------------------------------------------
# init_db — idempotent indexes
# ---------------------------------------------------------------------------


def test_init_db_indexes_are_idempotent(tmp_path: Path) -> None:
    db = tmp_path / "test.db"
    init_db(db)
    init_db(db)  # Should not raise on repeated call
    with _conn(db) as conn:
        indexes = {
            r[0]
            for r in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='index'"
            ).fetchall()
        }
    assert "idx_events_created_at" in indexes
    assert "idx_events_source_app" in indexes
    assert "idx_events_language" in indexes
    assert "idx_items_event_id" in indexes
    assert "idx_items_category" in indexes


# ---------------------------------------------------------------------------
# list_events
# ---------------------------------------------------------------------------


def test_list_events_returns_all(tmp_path: Path) -> None:
    db = tmp_path / "test.db"
    init_db(db)
    _evt(db)
    _evt(db)
    rows = list_events(db)
    assert len(rows) == 2


def test_list_events_filter_changed_true(tmp_path: Path) -> None:
    db = tmp_path / "test.db"
    init_db(db)
    _evt(db, changed=True)
    _evt(db, changed=False)
    rows = list_events(db, changed=True)
    assert len(rows) == 1
    assert rows[0]["changed"] == 1


def test_list_events_filter_changed_false(tmp_path: Path) -> None:
    db = tmp_path / "test.db"
    init_db(db)
    _evt(db, changed=True)
    _evt(db, changed=False)
    rows = list_events(db, changed=False)
    assert len(rows) == 1
    assert rows[0]["changed"] == 0


def test_list_events_filter_language(tmp_path: Path) -> None:
    db = tmp_path / "test.db"
    init_db(db)
    _evt(db, language="en")
    _evt(db, language="fr")
    rows = list_events(db, language="fr")
    assert len(rows) == 1
    assert rows[0]["language"] == "fr"


def test_list_events_filter_source_app(tmp_path: Path) -> None:
    db = tmp_path / "test.db"
    init_db(db)
    _evt(db, source_app="Slack")
    _evt(db, source_app="Firefox")
    rows = list_events(db, source_app="Slack")
    assert len(rows) == 1
    assert rows[0]["source_app"] == "Slack"


def test_list_events_filter_q_matches_original(tmp_path: Path) -> None:
    db = tmp_path / "test.db"
    init_db(db)
    _evt(db, original_text="Hello teh world")
    _evt(db, original_text="Nothing here")
    rows = list_events(db, q="teh")
    assert len(rows) == 1
    assert "teh" in rows[0]["original_text"]


def test_list_events_filter_q_matches_corrected(tmp_path: Path) -> None:
    db = tmp_path / "test.db"
    init_db(db)
    _evt(db, corrected_text="Hello the world")
    _evt(db, corrected_text="Nothing here")
    rows = list_events(db, q="the world")
    assert len(rows) == 1


def test_list_events_filter_category(tmp_path: Path) -> None:
    db = tmp_path / "test.db"
    init_db(db)
    eid1 = _evt(db)
    _item(db, eid1, category="grammar")
    eid2 = _evt(db)
    _item(db, eid2, category="spelling")

    rows = list_events(db, category="grammar")
    assert len(rows) == 1
    assert rows[0]["id"] == eid1


def test_list_events_category_no_match(tmp_path: Path) -> None:
    db = tmp_path / "test.db"
    init_db(db)
    eid = _evt(db)
    _item(db, eid, category="spelling")
    rows = list_events(db, category="grammar")
    assert len(rows) == 0


def test_list_events_order_newest_first(tmp_path: Path) -> None:
    db = tmp_path / "test.db"
    init_db(db)
    id1 = _evt(db)
    id2 = _evt(db)
    rows = list_events(db)
    assert rows[0]["id"] == id2
    assert rows[1]["id"] == id1


def test_list_events_pagination(tmp_path: Path) -> None:
    db = tmp_path / "test.db"
    init_db(db)
    for _ in range(5):
        _evt(db)
    page1 = list_events(db, limit=3, offset=0)
    page2 = list_events(db, limit=3, offset=3)
    assert len(page1) == 3
    assert len(page2) == 2
    # No overlap.
    ids1 = {r["id"] for r in page1}
    ids2 = {r["id"] for r in page2}
    assert ids1.isdisjoint(ids2)


def test_list_events_includes_item_count(tmp_path: Path) -> None:
    db = tmp_path / "test.db"
    init_db(db)
    eid = _evt(db)
    _item(db, eid)
    _item(db, eid)
    rows = list_events(db)
    assert rows[0]["item_count"] == 2


# ---------------------------------------------------------------------------
# count_events
# ---------------------------------------------------------------------------


def test_count_events_total(tmp_path: Path) -> None:
    db = tmp_path / "test.db"
    init_db(db)
    _evt(db)
    _evt(db)
    assert count_events(db) == 2


def test_count_events_with_filter(tmp_path: Path) -> None:
    db = tmp_path / "test.db"
    init_db(db)
    _evt(db, changed=True)
    _evt(db, changed=False)
    assert count_events(db, changed=True) == 1
    assert count_events(db, changed=False) == 1


def test_count_events_empty(tmp_path: Path) -> None:
    db = tmp_path / "test.db"
    init_db(db)
    assert count_events(db) == 0


# ---------------------------------------------------------------------------
# get_event
# ---------------------------------------------------------------------------


def test_get_event_found(tmp_path: Path) -> None:
    db = tmp_path / "test.db"
    init_db(db)
    eid = _evt(db)
    row = get_event(db, eid)
    assert row is not None
    assert row["id"] == eid


def test_get_event_not_found(tmp_path: Path) -> None:
    db = tmp_path / "test.db"
    init_db(db)
    assert get_event(db, 9999) is None


def test_get_event_item_count(tmp_path: Path) -> None:
    db = tmp_path / "test.db"
    init_db(db)
    eid = _evt(db)
    _item(db, eid)
    _item(db, eid)
    row = get_event(db, eid)
    assert row["item_count"] == 2


# ---------------------------------------------------------------------------
# get_items_for_event
# ---------------------------------------------------------------------------


def test_get_items_for_event_found(tmp_path: Path) -> None:
    db = tmp_path / "test.db"
    init_db(db)
    eid = _evt(db)
    _item(db, eid, original_text="teh", corrected_text="the")
    _item(db, eid, original_text="recieve", corrected_text="receive")
    items = get_items_for_event(db, eid)
    assert len(items) == 2


def test_get_items_for_event_empty(tmp_path: Path) -> None:
    db = tmp_path / "test.db"
    init_db(db)
    eid = _evt(db)
    assert get_items_for_event(db, eid) == []


def test_get_items_for_event_belongs_to_event(tmp_path: Path) -> None:
    db = tmp_path / "test.db"
    init_db(db)
    eid1 = _evt(db)
    eid2 = _evt(db)
    _item(db, eid1, original_text="a", corrected_text="b")
    _item(db, eid2, original_text="c", corrected_text="d")
    items1 = get_items_for_event(db, eid1)
    items2 = get_items_for_event(db, eid2)
    assert len(items1) == 1
    assert len(items2) == 1
    assert items1[0]["original_text"] == "a"
    assert items2[0]["original_text"] == "c"


# ---------------------------------------------------------------------------
# get_stats
# ---------------------------------------------------------------------------


def test_get_stats_empty(tmp_path: Path) -> None:
    db = tmp_path / "test.db"
    init_db(db)
    stats = get_stats(db)
    assert stats["total"] == 0
    assert stats["changed"] == 0
    assert stats["unchanged"] == 0
    assert stats["errors"] == 0
    assert stats["top_categories"] == []
    assert stats["top_source_apps"] == []


def test_get_stats_totals(tmp_path: Path) -> None:
    db = tmp_path / "test.db"
    init_db(db)
    _evt(db, changed=True, source_app="Slack")
    _evt(db, changed=False, source_app="Firefox")
    _evt(db, changed=None, error="Ollama unavailable", source_app="Slack")
    stats = get_stats(db)
    assert stats["total"] == 3
    assert stats["changed"] == 1
    assert stats["unchanged"] == 1
    assert stats["errors"] == 1


def test_get_stats_top_categories(tmp_path: Path) -> None:
    db = tmp_path / "test.db"
    init_db(db)
    for _ in range(3):
        eid = _evt(db)
        _item(db, eid, category="spelling")
    eid = _evt(db)
    _item(db, eid, category="grammar")
    stats = get_stats(db)
    cats = dict(stats["top_categories"])
    assert cats["spelling"] == 3
    assert cats["grammar"] == 1


def test_get_stats_top_source_apps(tmp_path: Path) -> None:
    db = tmp_path / "test.db"
    init_db(db)
    _evt(db, source_app="Slack")
    _evt(db, source_app="Slack")
    _evt(db, source_app="Firefox")
    stats = get_stats(db)
    apps = dict(stats["top_source_apps"])
    assert apps["Slack"] == 2
    assert apps["Firefox"] == 1


# ---------------------------------------------------------------------------
# delete_event
# ---------------------------------------------------------------------------


def test_delete_event_removes_event_and_items(tmp_path: Path) -> None:
    db = tmp_path / "test.db"
    init_db(db)
    eid = _evt(db)
    _item(db, eid)
    _item(db, eid)

    result = delete_event(db, eid)

    assert result is True
    assert get_event(db, eid) is None
    assert get_items_for_event(db, eid) == []


def test_delete_event_returns_false_for_unknown_id(tmp_path: Path) -> None:
    db = tmp_path / "test.db"
    init_db(db)
    assert delete_event(db, 9999) is False


def test_delete_event_does_not_touch_other_events(tmp_path: Path) -> None:
    db = tmp_path / "test.db"
    init_db(db)
    eid1 = _evt(db)
    eid2 = _evt(db)
    _item(db, eid1)
    _item(db, eid2)

    delete_event(db, eid1)

    # eid2 and its item must still exist.
    assert get_event(db, eid2) is not None
    assert len(get_items_for_event(db, eid2)) == 1


def test_delete_event_idempotent_second_call(tmp_path: Path) -> None:
    db = tmp_path / "test.db"
    init_db(db)
    eid = _evt(db)
    assert delete_event(db, eid) is True
    assert delete_event(db, eid) is False  # Already gone — not an error
