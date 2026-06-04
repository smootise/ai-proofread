"""
FastAPI application entrypoint.

Endpoints:
    GET  /health              — liveness check
    POST /proofread           — proofread submitted text via Ollama and log to SQLite

    GET  /ui                  — V2 web UI: dashboard with summary stats
    GET  /ui/history          — V2 web UI: correction history list
    GET  /ui/history/{id}     — V2 web UI: correction detail
    GET  /ui/history/{id}/delete  — V2 web UI: delete confirmation
    POST /ui/history/{id}/delete  — V2 web UI: perform cascade delete

Run with:
    uvicorn server.main:app --host 127.0.0.1 --reload

IMPORTANT: Bind to 127.0.0.1 (localhost only). The web UI displays stored private text and
has no authentication. Do not expose to a LAN/TrueNAS address without adding auth first.
"""

import logging
from pathlib import Path
from urllib.parse import urlencode

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from server.config import settings
from server.correction_service import CorrectionError, proofread
from server.database import init_db
from server.models import ProofreadRequest, ProofreadResponse
from server import web as web_module

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)-8s %(name)s — %(message)s",
)
logger = logging.getLogger(__name__)

app = FastAPI(title="Proofreader", version="2.0.0")

# ---------------------------------------------------------------------------
# Jinja2 templates + static files (V2 web UI)
# ---------------------------------------------------------------------------

_SERVER_DIR = Path(__file__).parent
_templates = Jinja2Templates(directory=str(_SERVER_DIR / "templates"))


def _build_qs_filter(filters: dict, **overrides) -> str:
    """
    Jinja2 filter: merge a filters dict with keyword overrides and return a
    URL query string (without the leading '?').

    Usage in template: {{ filters | build_qs(page=page+1) }}
    """
    merged = {k: v for k, v in filters.items() if v}
    merged.update({k: v for k, v in overrides.items() if v is not None})
    return urlencode(merged)


_templates.env.filters["build_qs"] = _build_qs_filter

app.mount("/static", StaticFiles(directory=str(_SERVER_DIR / "static")), name="static")

# Inject the shared templates instance into the web router module, then register it.
web_module.set_templates(_templates)
app.include_router(web_module.router)


# ---------------------------------------------------------------------------
# Startup
# ---------------------------------------------------------------------------


@app.on_event("startup")
def on_startup() -> None:
    logger.info("Starting proofreader backend (model=%s)", settings.ollama_model)
    init_db(settings.db_path)


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}


@app.post("/proofread", response_model=ProofreadResponse)
def proofread_endpoint(request: ProofreadRequest) -> ProofreadResponse:
    """
    Proofread the submitted text.

    Returns a structured correction response.
    Returns HTTP 422 for validation errors (handled by FastAPI/Pydantic automatically).
    Returns HTTP 503 for backend/Ollama failures.
    """
    try:
        return proofread(request)
    except CorrectionError as exc:
        logger.warning("Correction failed: %s", exc)
        raise HTTPException(status_code=503, detail=str(exc)) from exc


# ---------------------------------------------------------------------------
# Global error handler — ensure no internal details leak on unexpected errors
# ---------------------------------------------------------------------------


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    logger.exception("Unhandled exception on %s %s", request.method, request.url.path)
    return JSONResponse(status_code=500, content={"detail": "Internal server error."})
