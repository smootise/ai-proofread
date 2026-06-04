# AI Proofreader (V2)

Local-first Windows proofreading tool. Press **Ctrl+Alt+P** anywhere to fix spelling and grammar without leaving your app.

Selected text is corrected in place. If nothing is selected, the whole input field is corrected. The original text is left on your clipboard as a recovery fallback.

A local web UI lets you browse correction history, view before/after diffs, and delete stored events.

---

## How it works

```
AutoHotkey (Ctrl+Alt+P)
  → captures text via clipboard
  → Python client bridge (temp file)
  → FastAPI backend
  → Ollama (gemma4:e4b)
  → SQLite log
  → pastes corrected text
```

The web UI is served by the same backend:

```
Browser → GET /ui, /ui/history, /ui/history/{id}
  → FastAPI backend (Jinja2 templates)
  → SQLite (read-only for the UI, delete supported)
```

The client and server are separate: the backend can later move to a TrueNAS server by changing one env var (`PROOFREADER_API_URL`).

---

## Requirements

- **Windows 10/11**
- **[AutoHotkey v1.1](https://www.autohotkey.com/download/1.x/)** (not v2 — syntax differs)
- **Python 3.11+**
  - Python 3.14: pydantic requires a pre-release wheel — see Setup below
- **[Ollama](https://ollama.com/)** running locally with the configured model pulled

---

## Setup

### 1. Clone and configure

```bat
cd ai-proofread
copy .env.example .env
```

Edit `.env` if your Ollama URL or model name differs from the defaults.

### 2. Install Python dependencies

**Python 3.11 – 3.13:**
```bat
pip install -r requirements.txt
```

**Python 3.14 (pydantic pre-release required):**
```bat
pip install "pydantic>=2.14.0a1" --pre
pip install fastapi uvicorn python-dotenv requests jinja2 httpx2 pytest pytest-mock black ruff
```

### 3. Pull the Ollama model

```bat
ollama pull gemma4:e4b
```

The model name must match `OLLAMA_MODEL` in your `.env`. Change `OLLAMA_MODEL` if you want to use a different model.

### 4. Start the backend

From the repo root, bind to localhost only (the web UI displays stored private text):

```bat
uvicorn server.main:app --host 127.0.0.1 --reload
```

Verify it's running:

```bat
curl http://localhost:8000/health
```

Expected: `{"status":"ok"}`

> **Privacy note:** The web UI is served on localhost with no authentication. It displays the full text of everything you have proofread. Do not change `--host 127.0.0.1` to `0.0.0.0` or a LAN address without adding authentication first.

### 5. Open the web UI

Visit **http://127.0.0.1:8000/ui** in your browser to view correction history.

### 6. Load the AutoHotkey script

Double-click `ahk\proofreader_hotkey.ahk` (requires AutoHotkey v1.1 installed).

You'll see an AHK icon in the system tray. The hotkey is now active.

If your Python interpreter is not on `PATH`, edit the `PythonExe` variable at the top of the script to the full path (e.g. `C:\Python311\python.exe`).

---

## Usage

### Hotkey (V1 — unchanged)

1. Select text in any app (or place your cursor in a text field).
2. Press **Ctrl+Alt+P**.
3. Wait ~2–5 seconds for the correction.
4. The corrected text replaces your selection (or the whole field).
5. The **original text** is left on your clipboard — paste it back with **Ctrl+V** to undo.

### Web UI (V2)

| Page | URL | What you can do |
|---|---|---|
| Dashboard | `/ui` | Stats overview: total events, changed/unchanged, top categories and source apps |
| History | `/ui/history` | Browse all corrections; filter by status, language, category, source app, or free text; paginate |
| Detail | `/ui/history/{id}` | Full metadata, before/after word diff, per-fragment breakdown |
| Delete | `/ui/history/{id}/delete` | Confirm and permanently delete an event (removes all linked fragments) |

---

## Environment variables

All variables have defaults in `.env.example`. Copy to `.env` to override.

| Variable | Default | Description |
|---|---|---|
| `PROOFREADER_API_URL` | `http://localhost:8000` | Backend URL. Change to your TrueNAS host when moving the backend. |
| `OLLAMA_BASE_URL` | `http://localhost:11434` | Ollama server URL. |
| `OLLAMA_MODEL` | `gemma4:e4b` | Ollama model to use. Must match a pulled model. |
| `DATABASE_URL` | `sqlite:///./data/proofreader.db` | SQLite database path. |
| `MIN_CHARS` | `3` | Minimum text length (characters) to proofread. |
| `MAX_CHARS` | `5000` | Maximum text length (characters). |
| `REQUEST_TIMEOUT_SECONDS` | `30` | HTTP timeout for Ollama calls. |
| `CLIPBOARD_TIMEOUT_SECONDS` | `0.5` | How long AHK waits for clipboard after Ctrl+C. |
| `PASTE_RESTORE_DELAY_MS` | `150` | Delay after paste before restoring clipboard. |
| `STORE_FULL_TEXT` | `true` | Store full original/corrected text in SQLite. Set to `false` to store metadata only (the diff and detail pages will show "Full text not stored"). |

---

## Running tests

```bat
python -m pytest tests/ -v
```

---

## Manual test matrix

### V1 hotkey — success cases

| App | Test | Expected |
|---|---|---|
| Notepad | Select text → Ctrl+Alt+P | Selected text replaced; original on clipboard |
| Notepad | No selection → Ctrl+Alt+P | Whole field corrected |
| Firefox | Select text in `<textarea>` → Ctrl+Alt+P | Text replaced in field |
| Slack | Type draft with typos → Ctrl+Alt+P (no selection) | Draft corrected; **no message sent** |
| Discord | Same as Slack | Draft corrected; **no message sent** |
| WhatsApp Desktop | Same as Slack | Draft corrected; **no message sent** |

### V1 hotkey — failure cases

| Scenario | Expected |
|---|---|
| Backend stopped | Nothing pasted; clipboard restored; tray tip shown |
| Ollama stopped | Nothing pasted; clipboard restored; tray tip shown |
| Text under 3 chars | Nothing pasted; clipboard restored |
| Text over 5000 chars | Nothing pasted; clipboard restored |
| Ollama returns garbage | Nothing pasted; clipboard restored |

### V2 web UI — manual checks

| Check | Expected |
|---|---|
| Visit `/ui` with no history | "No corrections logged yet" message |
| Visit `/ui` after corrections | Stats show correct counts; top categories/apps populated |
| `/ui/history` — filter by "changed only" | Only events with `changed=true` shown |
| `/ui/history?q=hello` | Only events whose text contains "hello" |
| Detail page for changed event | Before/after diff shows strikethrough deletions (red) and insertions (green) |
| Detail page for error event | Metadata shows error message; diff shows "Full text not stored" or placeholder |
| Delete via confirm page (no JS) | GET confirm → POST → redirect → deleted-id notice on history list |
| Delete via inline button | JS confirm() dialog → POST → same redirect |
| Unknown event id | 404 page (no stack trace) |

---

## Project structure

```
ai-proofread/
  ahk/
    proofreader_hotkey.ahk    AutoHotkey v1.1 hotkey (Windows-only)
  client/
    proofread_client.py       Python bridge: temp file → HTTP → temp file
  server/
    main.py                   FastAPI app (API + web UI wiring)
    config.py                 Settings loaded from .env
    models.py                 Pydantic request/response models
    database.py               SQLite schema, inserts (V1), reads/deletes (V2)
    ollama_client.py          Ollama HTTP client + JSON extraction
    correction_service.py     Proofread pipeline orchestration
    history_service.py        V2: read/stats/delete orchestration for the UI
    diffing.py                V2: difflib-based before/after diff → MarkupSafe HTML
    web.py                    V2: APIRouter(/ui) — all UI route handlers
    templates/                V2: Jinja2 templates (autoescaped)
      base.html
      dashboard.html
      history.html
      detail.html
      confirm_delete.html
      404.html
    static/                   V2: static assets (no build step)
      style.css
      app.js
  data/
    .gitkeep                  SQLite DB created here at runtime
  tests/
    test_correction_parsing.py
    test_config.py
    test_database.py
    test_history_queries.py   V2: DB read/delete query tests
    test_diffing.py           V2: diff escaping and line-break tests
    test_web_routes.py        V2: UI route tests + V1 regression
  docs/
    v1_scope.md
    architecture.md
    clipboard_flow.md
    backend_api.md
    roadmap.md
  .env.example
  requirements.txt
  CLAUDE.md
```

---

## What V2 does NOT include

- Per-correction accept/reject (column exists in DB; UI deferred to V2.5)
- ML, clustering, progress tracking, or preference learning (V3)
- Review-before-apply popup (deferred)
- macOS support
- Rich-text preservation
- Cloud model APIs

See `docs/roadmap.md` for the V2.5/V3 plan.
