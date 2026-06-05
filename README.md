# AI Proofreader (V2.5)

Local-first Windows proofreading tool. Two hotkeys, two workflows:

- **Ctrl+Alt+P** — fast path: correct and paste immediately, no interruption.
- **Ctrl+Alt+Shift+P** — review path: see the proposed correction in a popup before deciding.

Selected text is corrected in place. If nothing is selected, the whole input field is corrected.
A local web UI lets you browse correction history, view before/after diffs, and delete stored events.

---

## How it works

### Fast path (`Ctrl+Alt+P`) — unchanged from V1

```
AutoHotkey (Ctrl+Alt+P)
  → captures text via clipboard
  → Python client bridge (temp file)
  → FastAPI backend + Ollama (gemma4:e4b)
  → SQLite log
  → pastes corrected text
  → leaves original text in clipboard as recovery fallback
```

### Review path (`Ctrl+Alt+Shift+P`) — new in V2.5

```
AutoHotkey (Ctrl+Alt+Shift+P)
  → captures text + stores source window handle
  → Python review client (client/review_client.py)
  → FastAPI backend + Ollama (gemma4:e4b)
  → SQLite log (review_status = review_pending)
  → pywebview popup loads /ui/review/{event_id}
  → user clicks: Accept & apply / Copy corrected text / Reject
  → JSON decision file written
  → AHK branches:
      accept  → re-focus source window → Ctrl+V → corrected text stays in clipboard
      copy    → corrected text in clipboard; no paste
      reject  → previous clipboard restored; nothing pasted
```

### Web UI

```
Browser → GET /ui, /ui/history, /ui/history/{id}, /ui/review/{id}
  → FastAPI backend (Jinja2 templates)
  → SQLite (read-only for the UI; delete and review decisions supported)
```

The client and server are separate: the backend can later move to a TrueNAS server by
changing one env var (`PROOFREADER_API_URL`).

---

## Requirements

- **Windows 10/11**
- **[AutoHotkey v1.1](https://www.autohotkey.com/download/1.x/)** (not v2 — syntax differs)
- **Python 3.11+**
  - Python 3.14: pydantic requires a pre-release wheel — see Setup below
- **[Ollama](https://ollama.com/)** running locally with the configured model pulled
- **[Microsoft Edge WebView2 Runtime](https://developer.microsoft.com/en-us/microsoft-edge/webview2/)** — required for the `Ctrl+Alt+Shift+P` review popup only. Usually already installed on Windows 10/11 with Edge.

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
pip install fastapi uvicorn python-dotenv requests jinja2 pywebview httpx2 pytest pytest-mock black ruff
```

### 3. Pull the Ollama model

```bat
ollama pull gemma4:e4b
```

The model name must match `OLLAMA_MODEL` in your `.env`.

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

> **Privacy note:** The web UI is served on localhost with no authentication. It displays
> the full text of everything you have proofread. Do not change `--host 127.0.0.1` to
> `0.0.0.0` or a LAN address without adding authentication first.

### 5. Open the web UI

Visit **http://127.0.0.1:8000/ui** in your browser to view correction history.

### 6. Load the AutoHotkey script

Double-click `ahk\proofreader_hotkey.ahk` (requires AutoHotkey v1.1 installed).

You'll see an AHK icon in the system tray. Both hotkeys are now active.

If your Python interpreter is not on `PATH`, edit the `PythonExe` variable at the top of
the script to the full path (e.g. `C:\Python311\python.exe`).

---

## Usage

### Fast path (`Ctrl+Alt+P`)

1. Select text in any app (or place your cursor in a text field).
2. Press **Ctrl+Alt+P**.
3. Wait ~2–5 seconds for the correction.
4. The corrected text replaces your selection (or the whole field).
5. The **original text** is left on your clipboard — paste it back with **Ctrl+V** to undo.

### Review path (`Ctrl+Alt+Shift+P`) — new in V2.5

1. Select text in any app (or place your cursor in a text field).
2. Press **Ctrl+Alt+Shift+P**.
3. Wait ~2–5 seconds for the correction.
4. A popup appears showing the proposed correction with a before/after diff.
5. Choose one of three actions:
   - **Accept & apply** — closes the popup, re-focuses the source window, pastes the corrected text. The **corrected text** stays on your clipboard.
   - **Copy corrected text** — closes the popup, puts the corrected text on your clipboard. No paste, no re-focus. Use this for apps where automatic refocus + paste is unreliable.
   - **Reject** — closes the popup, restores your previous clipboard. Nothing is pasted.
6. Pressing **Esc** or closing the popup window acts as cancel (restores clipboard).

### Web UI (V2 + V2.5)

| Page | URL | What you can do |
|---|---|---|
| Dashboard | `/ui` | Stats overview: total events, changed/unchanged, top categories and source apps |
| History | `/ui/history` | Browse all corrections; filter by status, language, category, source app, or free text; paginate |
| Detail | `/ui/history/{id}` | Full metadata, before/after word diff, per-fragment breakdown, **review status** |
| Delete | `/ui/history/{id}/delete` | Confirm and permanently delete an event (removes all linked fragments) |
| Review popup | `/ui/review/{id}` | Opened automatically by the `Ctrl+Alt+Shift+P` hotkey via pywebview |

The history and detail pages now show a **Review status** badge for each event:

| Badge | Meaning |
|---|---|
| `auto` | Fast path — text was applied immediately |
| `pending` | Review popup was opened; decision not yet recorded |
| `accepted` | User accepted and the correction was pasted |
| `copied` | User chose "Copy only" |
| `rejected` | User explicitly rejected |
| `canceled` | Popup closed without a choice |

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
| `REVIEW_POPUP_WIDTH` | `800` | Width of the review popup window in pixels. |
| `REVIEW_POPUP_HEIGHT` | `700` | Height of the review popup window in pixels. |

---

## Running tests

```bat
python -m pytest tests/ -v
```

---

## Manual test matrix

### Fast path (`Ctrl+Alt+P`) — success cases

| App | Test | Expected |
|---|---|---|
| Notepad | Select text → Ctrl+Alt+P | Selected text replaced; **original** on clipboard |
| Notepad | No selection → Ctrl+Alt+P | Whole field corrected |
| Firefox | Select text in `<textarea>` → Ctrl+Alt+P | Text replaced in field |
| Slack | Type draft with typos → Ctrl+Alt+P (no selection) | Draft corrected; **no message sent** |
| Discord | Same as Slack | Draft corrected; **no message sent** |
| WhatsApp Desktop | Same as Slack | Draft corrected; **no message sent** |

### Fast path — failure cases

| Scenario | Expected |
|---|---|
| Backend stopped | Nothing pasted; clipboard restored; tray tip shown |
| Ollama stopped | Nothing pasted; clipboard restored; tray tip shown |
| Text under 3 chars | Nothing pasted; clipboard restored |
| Text over 5000 chars | Nothing pasted; clipboard restored |
| Ollama returns garbage | Nothing pasted; clipboard restored |

### Review path (`Ctrl+Alt+Shift+P`) — manual checks

| Test | Expected |
|---|---|
| Ctrl+Alt+Shift+P in Notepad (selected text) | Popup opens; shows diff; buttons visible |
| Click "Accept & apply" | Popup closes; Notepad re-focused; text pasted; **corrected** text on clipboard |
| Click "Copy corrected text" | Popup closes; no paste; **corrected** text on clipboard |
| Click "Reject" | Popup closes; nothing pasted; previous clipboard restored |
| Press Esc / close popup window | Same as reject |
| Close source window before accepting | Copy-only fallback; tray tip; no blind paste |
| Backend stopped | No popup; clipboard restored; tray tip |
| WebView2 not installed | No popup; clipboard restored; tray tip |

### V2 web UI — manual checks

| Check | Expected |
|---|---|
| Visit `/ui` with no history | "No corrections logged yet" message |
| Visit `/ui` after corrections | Stats show correct counts; top categories/apps populated |
| `/ui/history` — filter by "changed only" | Only events with `changed=true` shown |
| `/ui/history?q=hello` | Only events whose text contains "hello" |
| Detail page for changed event | Before/after diff shows strikethrough deletions (red) and insertions (green) |
| Detail page shows review status | "Review status" row in metadata table |
| History list shows review badge | `auto`, `accepted`, `copied`, etc. |
| Detail page for error event | Metadata shows error message; diff shows "Full text not stored" |
| Delete via confirm page (no JS) | GET confirm → POST → redirect → deleted-id notice |
| Unknown event id | 404 page (no stack trace) |

---

## Database migration

V2.5 adds a `review_status` column to `correction_events`. The migration runs automatically
when the backend starts (`init_db` in `server/database.py`). It is idempotent — safe to
run multiple times, never requires deleting the existing database. Existing V1/V2 rows get
the default value `auto_applied`.

---

## Project structure

```
ai-proofread/
  ahk/
    proofreader_hotkey.ahk    Ctrl+Alt+P (fast) + Ctrl+Alt+Shift+P (review) hotkeys
  client/
    proofread_client.py       Fast-path client: temp file → HTTP → temp file
    review_client.py          V2.5: review client with pywebview popup + JS API bridge
  server/
    main.py                   FastAPI app (API + web UI wiring)
    config.py                 Settings loaded from .env
    models.py                 Pydantic models (ProofreadRequest/Response, ReviewStatus, etc.)
    database.py               SQLite schema + idempotent migration + all CRUD helpers
    ollama_client.py          Ollama HTTP client + JSON extraction
    correction_service.py     Proofread pipeline orchestration
    history_service.py        Read/stats/delete/set_review_status orchestration for the UI
    diffing.py                difflib-based before/after diff → MarkupSafe HTML
    web.py                    APIRouter(/ui): all UI + review route handlers
    templates/                Jinja2 templates (autoescaped)
      base.html               Site chrome (nav + footer)
      popup_base.html         V2.5: chrome-free base for the review popup
      dashboard.html
      history.html
      detail.html
      confirm_delete.html
      review.html             V2.5: review popup page (diff + 3 buttons)
      review_not_found.html   V2.5: 404 fallback for the review popup
      404.html
    static/                   Static assets (no build step)
      style.css
      app.js
  data/
    .gitkeep                  SQLite DB created here at runtime
  tests/
    test_correction_parsing.py
    test_config.py
    test_database.py
    test_history_queries.py   DB read/delete query tests
    test_diffing.py           Diff escaping and line-break tests
    test_web_routes.py        V2 UI route tests + V1 regression
    test_review_routes.py     V2.5: migration, review routes, decision recording
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

## What V2.5 does NOT include

- Per-correction accept/reject (deferred to V3)
- ML, clustering, progress tracking, or preference learning (V3)
- macOS support
- Rich-text preservation
- Cloud model APIs

See `docs/roadmap.md` for the V3 plan.
