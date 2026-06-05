"""
V2/V2.5 web UI routes for browsing correction history and the review popup.

All routes are mounted under the /ui prefix (see main.py).

Routes:
    GET  /ui                              — Dashboard with summary stats.
    GET  /ui/history                      — Correction history list (filterable, paginated).
    GET  /ui/history/{event_id}           — Detail view for one correction event.
    GET  /ui/history/{event_id}/delete    — Delete confirmation page.
    POST /ui/history/{event_id}/delete    — Perform single-event cascade delete.

    GET  /ui/review/{event_id}            — V2.5 review popup page (pywebview window).
    POST /ui/review/{event_id}/decision   — V2.5 record the user's review decision.

V1 endpoints (GET /health, POST /proofread) are untouched.
"""

import logging
from typing import Optional

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

from server.history_service import (
    get_dashboard_stats,
    get_event_detail,
    list_history,
    remove_event,
    set_review_status,
)
from server.models import ReviewDecisionRequest, ReviewStatus

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/ui")

# Templates instance is set by main.py after it configures the Jinja2 environment
# so that the template directory path is resolved once at startup.
_templates: Optional[Jinja2Templates] = None


def set_templates(templates: Jinja2Templates) -> None:
    """Called by main.py to inject the shared Jinja2Templates instance."""
    global _templates
    _templates = templates


def _t() -> Jinja2Templates:
    if _templates is None:
        raise RuntimeError("Templates not initialised — call web.set_templates() at startup.")
    return _templates


# ---------------------------------------------------------------------------
# Dashboard
# ---------------------------------------------------------------------------


@router.get("/", response_class=HTMLResponse)
async def dashboard(request: Request) -> HTMLResponse:
    stats = get_dashboard_stats()
    return _t().TemplateResponse(
        request=request,
        name="dashboard.html",
        context={"stats": stats},
    )


# ---------------------------------------------------------------------------
# History list
# ---------------------------------------------------------------------------


@router.get("/history", response_class=HTMLResponse)
async def history_list(
    request: Request,
    changed: str = "",
    language: str = "",
    category: str = "",
    source_app: str = "",
    q: str = "",
    page: int = 1,
    deleted: str = "",
) -> HTMLResponse:
    data = list_history(
        changed=changed or None,
        language=language or None,
        category=category or None,
        source_app=source_app or None,
        q=q or None,
        page=page,
    )
    return _t().TemplateResponse(
        request=request,
        name="history.html",
        context={
            **data,
            "deleted_id": int(deleted) if deleted.isdigit() else None,
        },
    )


# ---------------------------------------------------------------------------
# Event detail
# ---------------------------------------------------------------------------


@router.get("/history/{event_id}", response_class=HTMLResponse)
async def event_detail(request: Request, event_id: int) -> HTMLResponse:
    detail = get_event_detail(event_id)
    if detail is None:
        return _t().TemplateResponse(
            request=request,
            name="404.html",
            context={"message": f"Correction event #{event_id} not found."},
            status_code=404,
        )
    return _t().TemplateResponse(
        request=request,
        name="detail.html",
        context={"event": detail},
    )


# ---------------------------------------------------------------------------
# Delete — confirm (GET) and execute (POST)
# ---------------------------------------------------------------------------


@router.get("/history/{event_id}/delete", response_class=HTMLResponse)
async def delete_confirm(request: Request, event_id: int) -> HTMLResponse:
    detail = get_event_detail(event_id)
    if detail is None:
        return _t().TemplateResponse(
            request=request,
            name="404.html",
            context={"message": f"Correction event #{event_id} not found."},
            status_code=404,
        )
    return _t().TemplateResponse(
        request=request,
        name="confirm_delete.html",
        context={"event": detail},
    )


@router.post("/history/{event_id}/delete")
async def delete_execute(event_id: int) -> RedirectResponse:
    deleted = remove_event(event_id)
    if deleted:
        logger.info("Deleted correction event %d via web UI", event_id)
        redirect_url = f"/ui/history?deleted={event_id}"
    else:
        logger.warning("Delete requested for unknown event %d", event_id)
        redirect_url = "/ui/history"
    return RedirectResponse(url=redirect_url, status_code=303)


# ---------------------------------------------------------------------------
# Review popup — V2.5
# ---------------------------------------------------------------------------

# Mapping from the decision string sent by the popup JS to the ReviewStatus enum value.
_DECISION_TO_STATUS: dict[str, str] = {
    "accept": ReviewStatus.review_accepted_applied.value,
    "copy": ReviewStatus.review_copied_to_clipboard.value,
    "reject": ReviewStatus.review_rejected.value,
    "cancel": ReviewStatus.review_canceled.value,
}


@router.get("/review/{event_id}", response_class=HTMLResponse)
async def review_popup(request: Request, event_id: int) -> HTMLResponse:
    """
    Render the review popup page for the given correction event.

    Called by the pywebview window opened by review_client.py.
    Reuses get_event_detail (diff + correction items) from the history service.
    Returns 404 if the event is not found.
    """
    detail = get_event_detail(event_id)
    if detail is None:
        return _t().TemplateResponse(
            request=request,
            name="review_not_found.html",
            context={"event_id": event_id},
            status_code=404,
        )
    return _t().TemplateResponse(
        request=request,
        name="review.html",
        context={"event": detail},
    )


@router.post("/review/{event_id}/decision")
async def review_decision(event_id: int, body: ReviewDecisionRequest) -> JSONResponse:
    """
    Record the user's review decision for the given correction event.

    Called by the pywebview JS API bridge (via an XHR/fetch from the popup page)
    before the popup window closes.

    Returns {"ok": true} on success, {"ok": false, "error": "..."} if the event
    is not found or the update fails.
    """
    status_value = _DECISION_TO_STATUS.get(body.decision)
    if status_value is None:
        # Should not happen given Pydantic's Literal validation.
        return JSONResponse(
            {"ok": False, "error": f"Unknown decision: {body.decision!r}"},
            status_code=400,
        )

    updated = set_review_status(event_id, status_value)
    if not updated:
        logger.warning(
            "Review decision %r for unknown event %d — status not recorded",
            body.decision,
            event_id,
        )
        return JSONResponse(
            {"ok": False, "error": f"Event {event_id} not found."},
            status_code=404,
        )

    logger.info(
        "Review decision %r recorded for event %d → review_status=%r",
        body.decision,
        event_id,
        status_value,
    )
    return JSONResponse({"ok": True})
