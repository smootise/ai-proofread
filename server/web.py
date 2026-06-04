"""
V2 web UI routes for browsing correction history.

All routes are mounted under the /ui prefix (see main.py).

Routes:
    GET  /ui                              — Dashboard with summary stats.
    GET  /ui/history                      — Correction history list (filterable, paginated).
    GET  /ui/history/{event_id}           — Detail view for one correction event.
    GET  /ui/history/{event_id}/delete    — Delete confirmation page.
    POST /ui/history/{event_id}/delete    — Perform single-event cascade delete.

V1 endpoints (GET /health, POST /proofread) are untouched.
"""

import logging
from typing import Optional

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

from server.history_service import get_dashboard_stats, get_event_detail, list_history, remove_event

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
