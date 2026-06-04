Architecture
Principle

Design as a client/server app from day one.

The Windows side should be thin and OS-specific. The backend should be reusable and eventually deployable to TrueNAS.

V1 architecture
AutoHotkey v1.1
  -> captures text
  -> calls Python client bridge
  -> pastes corrected text

Python client bridge
  -> sends HTTP request to backend
  -> returns corrected text to AutoHotkey

FastAPI backend
  -> validates request
  -> calls Ollama
  -> parses JSON
  -> logs to SQLite
  -> returns structured response

V2 additions (web UI)

The FastAPI backend now also serves a local web UI:

FastAPI backend (V2)
  -> GET /health, POST /proofread  (unchanged V1 API)
  -> GET /ui, GET /ui/history, GET /ui/history/{id}
  -> GET/POST /ui/history/{id}/delete
     -> history_service.py  (query/stats/delete orchestration)
     -> database.py         (read/delete helpers added alongside V1 inserts)
     -> diffing.py          (stdlib difflib, server-side before/after diff)
     -> server/templates/   (Jinja2, autoescaped)
     -> server/static/      (style.css, app.js — no build step)

Module boundaries:

server/main.py            FastAPI app: API routes + web router registration + Jinja2/static setup
server/web.py             APIRouter(prefix="/ui"): UI route handlers
server/history_service.py Thin orchestration for UI: list/detail/stats/delete
server/database.py        All DB access: schema, inserts (V1), reads/deletes (V2 additions)
server/diffing.py         Before/after word-level diff → MarkupSafe HTML
server/correction_service.py  Proofread pipeline (unchanged)
server/ollama_client.py   Ollama HTTP client (unchanged)
server/models.py          Pydantic request/response models (unchanged)
server/config.py          Settings singleton (unchanged)

Security note:

The web UI displays full stored private text and has no authentication.
Always bind to 127.0.0.1 (localhost only):

  uvicorn server.main:app --host 127.0.0.1

If you move the backend to a LAN or TrueNAS address, add authentication before exposing /ui.

Future TrueNAS architecture
Windows machine:
- AutoHotkey
- Python client bridge
- Clipboard/input manipulation

TrueNAS server:
- FastAPI backend (including web UI)
- Ollama
- SQLite database
- Future analytics/ML jobs

The client must use configurable PROOFREADER_API_URL.

Project structure
proofreader/
  CLAUDE.md
  README.md
  .env.example
  requirements.txt

  ahk/
    proofreader_hotkey.ahk

  client/
    proofread_client.py

  server/
    main.py
    config.py
    database.py
    models.py
    ollama_client.py
    correction_service.py
    history_service.py      (V2)
    diffing.py              (V2)
    web.py                  (V2)
    templates/              (V2 Jinja2 templates)
      base.html
      dashboard.html
      history.html
      detail.html
      confirm_delete.html
      404.html
    static/                 (V2 static assets)
      style.css
      app.js

  data/
    .gitkeep

  docs/
    v1_scope.md
    architecture.md
    clipboard_flow.md
    backend_api.md
    roadmap.md

  tests/
    test_correction_parsing.py
    test_database.py
    test_config.py
    test_history_queries.py  (V2)
    test_diffing.py          (V2)
    test_web_routes.py       (V2)

Dependency guidance

V1 + V2 dependencies:

fastapi
uvicorn
pydantic
python-dotenv
requests
jinja2 (V2 templating; markupsafe ships with it)
pytest
black
ruff

Do not introduce frontend frameworks, task queues, vector databases, or ML dependencies in V2.
