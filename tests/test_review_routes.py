"""
Tests for V2.5 review routes and DB migration.

Covers:
- DB migration: idempotency, old rows get 'auto_applied' default.
- POST /proofread: returns event_id; review=True stores 'review_pending'.
- GET  /ui/review/{id}: renders diff + items + 3 buttons; 404 on unknown id.
- POST /ui/review/{id}/decision: each decision sets the expected review_status.
- V2 history + detail: review_status badge appears without breaking existing output.
- V1 regression: /health and basic /proofread shape unchanged.
"""

import sqlite3
from pathlib import Path
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from server.database import (
    CorrectionEventRow,
    CorrectionItemRow,
    init_db,
    insert_event,
    insert_items,
    update_review_status,
    get_event,
)
from server.main import app

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def db(tmp_path: Path) -> Path:
    """Initialised temp database; monkeypatches settings.db_path for all server modules."""
    db_path = tmp_path / "test.db"
    init_db(db_path)
    with (
        patch("server.history_service.settings") as mock_settings,
        patch("server.correction_service.settings") as mock_cs_settings,
    ):
        mock_settings.db_path = db_path
        mock_cs_settings.db_path = db_path
        mock_cs_settings.min_chars = 3
        mock_cs_settings.max_chars = 5000
        mock_cs_settings.store_full_text = True
        mock_cs_settings.ollama_model = "gemma4:e4b"
        yield db_path


@pytest.fixture()
def client(db: Path):
    """TestClient with the temp db wired in."""
    with TestClient(app, raise_server_exceptions=True) as c:
        yield c


def _seed_event(db: Path, **kwargs) -> int:
    defaults = dict(
        source_app="Notepad",
        window_title="Untitled",
        mode="selected_text",
        model_name="gemma4:e4b",
        language="en",
        changed=True,
        original_text="I have teh report ready.",
        corrected_text="I have the report ready.",
        review_status="auto_applied",
    )
    defaults.update(kwargs)
    return insert_event(db, CorrectionEventRow(**defaults))


# ---------------------------------------------------------------------------
# DB migration tests
# ---------------------------------------------------------------------------


class TestDbMigration:
    def test_fresh_db_has_review_status_column(self, tmp_path: Path) -> None:
        """init_db on a new DB creates review_status column."""
        db_path = tmp_path / "fresh.db"
        init_db(db_path)

        conn = sqlite3.connect(str(db_path))
        cols = {row[1] for row in conn.execute("PRAGMA table_info(correction_events)")}
        conn.close()
        assert "review_status" in cols

    def test_migration_adds_column_to_existing_db(self, tmp_path: Path) -> None:
        """init_db on an old schema (no review_status) adds the column idempotently."""
        db_path = tmp_path / "old.db"

        # Create old schema manually — no review_status column.
        conn = sqlite3.connect(str(db_path))
        conn.execute("""
            CREATE TABLE correction_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                created_at TEXT NOT NULL,
                source_app TEXT NOT NULL,
                window_title TEXT NOT NULL DEFAULT '',
                mode TEXT NOT NULL DEFAULT 'unknown',
                original_text TEXT,
                corrected_text TEXT,
                language TEXT,
                changed INTEGER,
                confidence REAL,
                model_name TEXT NOT NULL,
                latency_ms INTEGER,
                error TEXT
            )
        """)
        conn.execute("""
            CREATE TABLE correction_items (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                event_id INTEGER NOT NULL,
                original_text TEXT NOT NULL,
                corrected_text TEXT NOT NULL,
                category TEXT NOT NULL DEFAULT '',
                explanation TEXT NOT NULL DEFAULT '',
                start_offset INTEGER,
                end_offset INTEGER,
                accepted_status TEXT NOT NULL DEFAULT 'auto_applied'
            )
        """)
        # Insert a legacy row (no review_status).
        conn.execute("""
            INSERT INTO correction_events
                (created_at, source_app, window_title, mode, model_name)
            VALUES ('2025-01-01T00:00:00', 'Slack', '', 'selected_text', 'gemma4:e4b')
        """)
        conn.commit()
        conn.close()

        # Run migration.
        init_db(db_path)

        # Column should now exist.
        conn = sqlite3.connect(str(db_path))
        cols = {row[1] for row in conn.execute("PRAGMA table_info(correction_events)")}
        assert "review_status" in cols

        # Old row should have the default value.
        row = conn.execute(
            "SELECT review_status FROM correction_events WHERE source_app='Slack'"
        ).fetchone()
        conn.close()
        assert row is not None
        assert row[0] == "auto_applied"

    def test_migration_is_idempotent(self, tmp_path: Path) -> None:
        """Running init_db twice does not raise."""
        db_path = tmp_path / "idem.db"
        init_db(db_path)
        init_db(db_path)  # Should not raise.

    def test_new_event_gets_auto_applied_by_default(self, tmp_path: Path) -> None:
        """Events inserted without specifying review_status get 'auto_applied'."""
        db_path = tmp_path / "default.db"
        init_db(db_path)
        event_id = insert_event(
            db_path,
            CorrectionEventRow(
                source_app="Notepad",
                window_title="",
                mode="unknown",
                model_name="gemma4:e4b",
            ),
        )
        row = get_event(db_path, event_id)
        assert row["review_status"] == "auto_applied"

    def test_update_review_status(self, tmp_path: Path) -> None:
        db_path = tmp_path / "upd.db"
        init_db(db_path)
        event_id = insert_event(
            db_path,
            CorrectionEventRow(
                source_app="Slack",
                window_title="",
                mode="selected_text",
                model_name="gemma4:e4b",
                review_status="review_pending",
            ),
        )
        result = update_review_status(db_path, event_id, "review_accepted_applied")
        assert result is True
        row = get_event(db_path, event_id)
        assert row["review_status"] == "review_accepted_applied"

    def test_update_review_status_unknown_id(self, tmp_path: Path) -> None:
        db_path = tmp_path / "upd2.db"
        init_db(db_path)
        result = update_review_status(db_path, 99999, "review_accepted_applied")
        assert result is False


# ---------------------------------------------------------------------------
# POST /proofread with review flag
# ---------------------------------------------------------------------------

_MOCK_OLLAMA_RESULT = {
    "corrected_text": "I have the report ready.",
    "language": "en",
    "changed": True,
    "confidence": 0.95,
    "corrections": [
        {
            "original": "teh",
            "corrected": "the",
            "category": "spelling",
            "explanation": "Typo.",
            "start_offset": None,
            "end_offset": None,
        }
    ],
    "warnings": [],
}


class TestProofreadEndpoint:
    def test_proofread_returns_event_id(self, client, db) -> None:
        """POST /proofread now returns an event_id field."""
        with patch("server.correction_service.correct_text", return_value=_MOCK_OLLAMA_RESULT):
            resp = client.post(
                "/proofread",
                json={"text": "I have teh report ready.", "source_app": "Notepad"},
            )
        assert resp.status_code == 200
        body = resp.json()
        assert "event_id" in body
        assert isinstance(body["event_id"], int)
        assert body["event_id"] > 0

    def test_proofread_fast_path_stores_auto_applied(self, client, db) -> None:
        """Fast-path (review omitted) stores review_status='auto_applied'."""
        with patch("server.correction_service.correct_text", return_value=_MOCK_OLLAMA_RESULT):
            resp = client.post(
                "/proofread",
                json={"text": "I have teh report ready.", "source_app": "Notepad"},
            )
        assert resp.status_code == 200
        event_id = resp.json()["event_id"]
        row = get_event(db, event_id)
        assert row["review_status"] == "auto_applied"

    def test_proofread_review_flag_stores_pending(self, client, db) -> None:
        """review=true stores review_status='review_pending'."""
        with patch("server.correction_service.correct_text", return_value=_MOCK_OLLAMA_RESULT):
            resp = client.post(
                "/proofread",
                json={
                    "text": "I have teh report ready.",
                    "source_app": "Notepad",
                    "review": True,
                },
            )
        assert resp.status_code == 200
        event_id = resp.json()["event_id"]
        row = get_event(db, event_id)
        assert row["review_status"] == "review_pending"

    def test_proofread_existing_fields_unchanged(self, client, db) -> None:
        """All pre-V2.5 response fields are still present and correct."""
        with patch("server.correction_service.correct_text", return_value=_MOCK_OLLAMA_RESULT):
            resp = client.post(
                "/proofread",
                json={"text": "I have teh report ready.", "source_app": "Notepad"},
            )
        assert resp.status_code == 200
        body = resp.json()
        assert body["corrected_text"] == "I have the report ready."
        assert body["changed"] is True
        assert isinstance(body["corrections"], list)
        assert isinstance(body["warnings"], list)


# ---------------------------------------------------------------------------
# GET /ui/review/{id}
# ---------------------------------------------------------------------------


class TestReviewPopupPage:
    def test_review_page_renders(self, client, db) -> None:
        eid = _seed_event(db)
        insert_items(
            db,
            eid,
            [CorrectionItemRow(original_text="teh", corrected_text="the", category="spelling")],
        )
        resp = client.get(f"/ui/review/{eid}")
        assert resp.status_code == 200
        # Should contain the review-specific action buttons.
        assert "Accept" in resp.text or "accept" in resp.text.lower()
        assert "Reject" in resp.text or "reject" in resp.text.lower()
        assert "Copy" in resp.text or "copy" in resp.text.lower()

    def test_review_page_shows_diff(self, client, db) -> None:
        eid = _seed_event(db)
        resp = client.get(f"/ui/review/{eid}")
        assert resp.status_code == 200
        assert (
            "diff-block" in resp.text
            or "no changes" in resp.text.lower()
            or "not stored" in resp.text.lower()
        )

    def test_review_page_shows_fragments(self, client, db) -> None:
        eid = _seed_event(db)
        insert_items(
            db,
            eid,
            [CorrectionItemRow(original_text="teh", corrected_text="the", category="spelling")],
        )
        resp = client.get(f"/ui/review/{eid}")
        assert resp.status_code == 200
        assert "teh" in resp.text
        assert "spelling" in resp.text

    def test_review_page_not_found(self, client, db) -> None:
        resp = client.get("/ui/review/99999")
        assert resp.status_code == 404

    def test_review_page_no_change_event(self, client, db) -> None:
        """Events with changed=False should still render without error."""
        eid = _seed_event(db, changed=False)
        resp = client.get(f"/ui/review/{eid}")
        assert resp.status_code == 200

    def test_review_page_null_text_graceful(self, client, db) -> None:
        """Events with NULL original/corrected should not crash the review page."""
        eid = insert_event(
            db,
            CorrectionEventRow(
                source_app="Notepad",
                window_title="",
                mode="unknown",
                model_name="gemma4:e4b",
                original_text=None,
                corrected_text=None,
                changed=None,
                error="Ollama unavailable",
            ),
        )
        resp = client.get(f"/ui/review/{eid}")
        assert resp.status_code == 200


# ---------------------------------------------------------------------------
# POST /ui/review/{id}/decision
# ---------------------------------------------------------------------------


_DECISION_MAP = {
    "accept": "review_accepted_applied",
    "copy": "review_copied_to_clipboard",
    "reject": "review_rejected",
    "cancel": "review_canceled",
}


class TestReviewDecision:
    @pytest.mark.parametrize("decision,expected_status", list(_DECISION_MAP.items()))
    def test_decision_sets_correct_status(
        self, client, db, decision: str, expected_status: str
    ) -> None:
        eid = _seed_event(db, review_status="review_pending")
        resp = client.post(
            f"/ui/review/{eid}/decision",
            json={"decision": decision},
        )
        assert resp.status_code == 200
        assert resp.json()["ok"] is True

        row = get_event(db, eid)
        assert row["review_status"] == expected_status

    def test_decision_unknown_event_returns_404(self, client, db) -> None:
        resp = client.post(
            "/ui/review/99999/decision",
            json={"decision": "accept"},
        )
        assert resp.status_code == 404
        assert resp.json()["ok"] is False

    def test_decision_invalid_value_rejected(self, client, db) -> None:
        eid = _seed_event(db)
        resp = client.post(
            f"/ui/review/{eid}/decision",
            json={"decision": "INVALID"},
        )
        assert resp.status_code == 422  # Pydantic Literal validation


# ---------------------------------------------------------------------------
# V2 history / detail display of review_status
# ---------------------------------------------------------------------------


class TestReviewStatusInUI:
    def test_history_list_shows_review_badge(self, client, db) -> None:
        _seed_event(db, review_status="review_accepted_applied")
        resp = client.get("/ui/history")
        assert resp.status_code == 200
        # The badge text for accepted (short form in history list)
        assert "accepted" in resp.text

    def test_history_list_auto_applied_badge(self, client, db) -> None:
        _seed_event(db, review_status="auto_applied")
        resp = client.get("/ui/history")
        assert resp.status_code == 200
        assert "auto" in resp.text

    def test_detail_shows_review_status(self, client, db) -> None:
        eid = _seed_event(db, review_status="review_copied_to_clipboard")
        resp = client.get(f"/ui/history/{eid}")
        assert resp.status_code == 200
        assert "review_copied_to_clipboard" in resp.text or "copied" in resp.text

    def test_detail_auto_applied_shows_label(self, client, db) -> None:
        eid = _seed_event(db, review_status="auto_applied")
        resp = client.get(f"/ui/history/{eid}")
        assert resp.status_code == 200
        assert "auto_applied" in resp.text or "auto" in resp.text


# ---------------------------------------------------------------------------
# V1 regression
# ---------------------------------------------------------------------------


class TestV1Regression:
    def test_health_endpoint_unchanged(self, client) -> None:
        resp = client.get("/health")
        assert resp.status_code == 200
        assert resp.json() == {"status": "ok"}

    def test_existing_web_routes_unbroken(self, client, db) -> None:
        eid = _seed_event(db)
        assert client.get("/ui").status_code == 200
        assert client.get("/ui/history").status_code == 200
        assert client.get(f"/ui/history/{eid}").status_code == 200
        assert client.get(f"/ui/history/{eid}/delete").status_code == 200
