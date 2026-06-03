"""
FastAPI application entrypoint.

Endpoints:
    GET  /health     — liveness check
    POST /proofread  — proofread submitted text via Ollama and log to SQLite

Run with:
    uvicorn server.main:app --reload
"""

import logging

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse

from server.config import settings
from server.correction_service import CorrectionError, proofread
from server.database import init_db
from server.models import ProofreadRequest, ProofreadResponse

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)-8s %(name)s — %(message)s",
)
logger = logging.getLogger(__name__)

app = FastAPI(title="Proofreader", version="1.0.0")


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
