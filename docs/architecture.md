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

V2.5 additions (review-before-apply workflow)

A second hotkey opens a pywebview popup for the user to review a proposed correction:

AutoHotkey Ctrl+Alt+Shift+P (new)
  -> captures text (same clipboard flow as V1)
  -> stores source window handle for re-focus
  -> client/review_client.py (new)
     -> POST /proofread (review=True) → event_id + corrected_text
     -> pywebview window loads GET /ui/review/{event_id}
     -> user clicks Accept / Copy / Reject
     -> JS API bridge calls decide(decision, correctedText)
     -> writes JSON decision file: {"decision": "...", "corrected_text": "..."}
     -> closes window; exits
  -> AHK reads decision file, branches:
     accept → WinActivate + Ctrl+V; leave corrected text in clipboard
     copy   → leave corrected text in clipboard; no paste
     reject/cancel → restore previous clipboard; no paste

FastAPI backend (V2.5 additions — V1/V2 unchanged)
  -> GET /ui/review/{event_id}     Review popup page (HTML, pywebview)
  -> POST /ui/review/{event_id}/decision  Record user's decision → update review_status
     -> history_service.set_review_status
     -> database.update_review_status
  -> POST /proofread now also accepts optional review=True, returns event_id
  -> correction_events table gains review_status column (idempotent migration in init_db)

Module boundaries:

server/main.py            FastAPI app: API routes + web router registration + Jinja2/static setup
server/web.py             APIRouter(prefix="/ui"): UI route handlers (V2 + V2.5 review routes)
server/history_service.py Thin orchestration for UI: list/detail/stats/delete + set_review_status
server/database.py        All DB access: schema, inserts (V1), reads/deletes (V2), update_review_status (V2.5)
server/diffing.py         Before/after word-level diff → MarkupSafe HTML (unchanged)
server/correction_service.py  Proofread pipeline (event_id returned in response, review_status threaded)
server/ollama_client.py   Ollama HTTP client (unchanged)
server/models.py          Pydantic models (ProofreadResponse.event_id, ReviewStatus, ReviewDecisionRequest added)
server/config.py          Settings singleton (unchanged)

client/review_client.py   V2.5 review client: pywebview bridge, JS API, decision file I/O

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
    test_review_routes.py    (V2.5)

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

V2.5 additional dependency:

pywebview — wraps the Windows WebView2 (Edge) runtime for the review popup.
Requires the Microsoft Edge WebView2 Runtime to be installed on the machine:
https://developer.microsoft.com/en-us/microsoft-edge/webview2/

Do not introduce frontend frameworks, task queues, vector databases, or ML dependencies.
