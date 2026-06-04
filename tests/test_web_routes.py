"""
Tests for V2 web UI routes (server/web.py) using FastAPI TestClient.

Covers:
- GET /ui            — dashboard renders (200, contains stat headings).
- GET /ui/history    — history list renders (200); filters echoed in form.
- GET /ui/history/{id} — detail renders (200); unknown id → 404.
- GET /ui/history/{id}/delete — confirm page (200); unknown id → 404.
- POST /ui/history/{id}/delete — deletes event, redirects 303 to /ui/history?deleted={id}.

V1 regression:
- GET /health  → 200, {"status": "ok"}.
- POST /proofread (mocked Ollama) → 200, ProofreadResponse shape intact.

All tests use a temporary SQLite database (monkeypatched settings.db_path).
"""

import json
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
)
from server.main import app


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def db(tmp_path: Path) -> Path:
    """Initialised temp database; monkeypatches settings.db_path."""
    db_path = tmp_path / "test.db"
    init_db(db_path)
    with patch("server.history_service.settings") as mock_settings:
        mock_settings.db_path = db_path
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
    )
    defaults.update(kwargs)
    return insert_event(db, CorrectionEventRow(**defaults))


# ---------------------------------------------------------------------------
# V1 regression
# ---------------------------------------------------------------------------


def test_health_endpoint_unchanged(client) -> None:
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}


def test_proofread_endpoint_shape_unchanged(client) -> None:
    """POST /proofread returns a ProofreadResponse-shaped JSON when Ollama is mocked."""
    mock_result = {
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
    with patch("server.correction_service.correct_text", return_value=mock_result):
        with patch("server.correction_service.insert_event", return_value=1):
            with patch("server.correction_service.insert_items"):
                resp = client.post(
                    "/proofread",
                    json={
                        "text": "I have teh report ready.",
                        "source_app": "Notepad",
                    },
                )
    assert resp.status_code == 200
    body = resp.json()
    assert "corrected_text" in body
    assert "changed" in body
    assert "corrections" in body
    assert isinstance(body["corrections"], list)


# ---------------------------------------------------------------------------
# Dashboard
# ---------------------------------------------------------------------------


def test_dashboard_renders_empty(client, db) -> None:
    resp = client.get("/ui")
    assert resp.status_code == 200
    assert "Dashboard" in resp.text
    # Empty state message
    assert "No corrections logged yet" in resp.text or "Total events" in resp.text


def test_dashboard_renders_with_data(client, db) -> None:
    eid = _seed_event(db)
    insert_items(
        db, eid, [CorrectionItemRow(original_text="teh", corrected_text="the", category="spelling")]
    )
    resp = client.get("/ui")
    assert resp.status_code == 200
    assert "Dashboard" in resp.text


# ---------------------------------------------------------------------------
# History list
# ---------------------------------------------------------------------------


def test_history_list_empty(client, db) -> None:
    resp = client.get("/ui/history")
    assert resp.status_code == 200
    assert "History" in resp.text
    assert "No corrections match" in resp.text or "No corrections logged" in resp.text


def test_history_list_shows_events(client, db) -> None:
    _seed_event(db)
    _seed_event(db)
    resp = client.get("/ui/history")
    assert resp.status_code == 200
    assert "Notepad" in resp.text


def test_history_list_filter_changed(client, db) -> None:
    _seed_event(db, changed=True)
    _seed_event(db, changed=False)
    resp = client.get("/ui/history?changed=changed")
    assert resp.status_code == 200
    # The filter value should be reflected in the form.
    assert 'value="changed"' in resp.text or "changed" in resp.text


def test_history_list_filter_source_app(client, db) -> None:
    _seed_event(db, source_app="Slack")
    _seed_event(db, source_app="Firefox")
    resp = client.get("/ui/history?source_app=Slack")
    assert resp.status_code == 200
    assert "Slack" in resp.text


def test_history_list_deleted_notice(client, db) -> None:
    eid = _seed_event(db)
    resp = client.get(f"/ui/history?deleted={eid}")
    assert resp.status_code == 200
    assert str(eid) in resp.text  # The deleted-id notice should mention the id.


# ---------------------------------------------------------------------------
# Event detail
# ---------------------------------------------------------------------------


def test_event_detail_found(client, db) -> None:
    eid = _seed_event(db)
    resp = client.get(f"/ui/history/{eid}")
    assert resp.status_code == 200
    assert f"#{eid}" in resp.text
    assert "Notepad" in resp.text


def test_event_detail_shows_diff(client, db) -> None:
    eid = _seed_event(db)
    resp = client.get(f"/ui/history/{eid}")
    assert resp.status_code == 200
    # Diff block or "no changes" or "not stored"
    assert (
        "diff-block" in resp.text
        or "no changes" in resp.text.lower()
        or "not stored" in resp.text.lower()
    )


def test_event_detail_shows_fragments(client, db) -> None:
    eid = _seed_event(db)
    insert_items(
        db,
        eid,
        [CorrectionItemRow(original_text="teh", corrected_text="the", category="spelling", explanation="Typo.")],
    )
    resp = client.get(f"/ui/history/{eid}")
    assert resp.status_code == 200
    assert "teh" in resp.text
    assert "spelling" in resp.text


def test_event_detail_null_text_graceful(client, db) -> None:
    """Events with NULL original/corrected text should not crash the detail page."""
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
    resp = client.get(f"/ui/history/{eid}")
    assert resp.status_code == 200
    assert "not stored" in resp.text.lower() or "Full text" in resp.text


def test_event_detail_not_found(client, db) -> None:
    resp = client.get("/ui/history/99999")
    assert resp.status_code == 404
    assert "Not Found" in resp.text or "not found" in resp.text.lower()


# ---------------------------------------------------------------------------
# Delete confirm (GET)
# ---------------------------------------------------------------------------


def test_delete_confirm_found(client, db) -> None:
    eid = _seed_event(db)
    resp = client.get(f"/ui/history/{eid}/delete")
    assert resp.status_code == 200
    assert "Delete" in resp.text
    assert str(eid) in resp.text


def test_delete_confirm_not_found(client, db) -> None:
    resp = client.get("/ui/history/99999/delete")
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Delete execute (POST)
# ---------------------------------------------------------------------------


def test_delete_execute_removes_event(client, db) -> None:
    eid = _seed_event(db)
    insert_items(db, eid, [CorrectionItemRow(original_text="teh", corrected_text="the")])

    resp = client.post(f"/ui/history/{eid}/delete", follow_redirects=False)
    assert resp.status_code == 303
    assert f"deleted={eid}" in resp.headers["location"]

    # Verify the event is gone.
    from server.database import get_event, get_items_for_event
    assert get_event(db, eid) is None
    assert get_items_for_event(db, eid) == []


def test_delete_execute_unknown_id_redirects_gracefully(client, db) -> None:
    resp = client.post("/ui/history/99999/delete", follow_redirects=False)
    assert resp.status_code == 303
    assert "/ui/history" in resp.headers["location"]


def test_delete_execute_does_not_remove_other_events(client, db) -> None:
    eid1 = _seed_event(db)
    eid2 = _seed_event(db)

    client.post(f"/ui/history/{eid1}/delete", follow_redirects=False)

    from server.database import get_event
    assert get_event(db, eid2) is not None
