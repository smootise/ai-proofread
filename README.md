# AI Proofreader (V1)

Local-first Windows proofreading tool. Press **Ctrl+Alt+P** anywhere to fix spelling and grammar without leaving your app.

Selected text is corrected in place. If nothing is selected, the whole input field is corrected. The original text is left on your clipboard as a recovery fallback.

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
pip install fastapi uvicorn python-dotenv requests pytest pytest-mock black ruff
```

### 3. Pull the Ollama model

```bat
ollama pull gemma4:e4b
```

The model name must match `OLLAMA_MODEL` in your `.env`. Change `OLLAMA_MODEL` if you want to use a different model.

### 4. Start the backend

From the repo root:

```bat
uvicorn server.main:app --reload
```

Verify it's running:

```bat
curl http://localhost:8000/health
```

Expected: `{"status":"ok"}`

### 5. Load the AutoHotkey script

Double-click `ahk\proofreader_hotkey.ahk` (requires AutoHotkey v1.1 installed).

You'll see an AHK icon in the system tray. The hotkey is now active.

If your Python interpreter is not on `PATH`, edit the `PythonExe` variable at the top of the script to the full path (e.g. `C:\Python311\python.exe`).

---

## Usage

1. Select text in any app (or place your cursor in a text field).
2. Press **Ctrl+Alt+P**.
3. Wait ~2–5 seconds for the correction.
4. The corrected text replaces your selection (or the whole field).
5. The **original text** is left on your clipboard — paste it back with **Ctrl+V** to undo.

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
| `STORE_FULL_TEXT` | `true` | Store full original/corrected text in SQLite. |

---

## Running tests

```bat
python -m pytest tests/ -v
```

---

## Manual test matrix

Run these after setup to verify V1 works end-to-end.

### Success cases

| App | Test | Expected |
|---|---|---|
| Notepad | Select text → Ctrl+Alt+P | Selected text replaced; original on clipboard |
| Notepad | No selection → Ctrl+Alt+P | Whole field corrected |
| Firefox | Select text in `<textarea>` → Ctrl+Alt+P | Text replaced in field |
| Slack | Type draft with typos → Ctrl+Alt+P (no selection) | Draft corrected; **no message sent** |
| Discord | Same as Slack | Draft corrected; **no message sent** |
| WhatsApp Desktop | Same as Slack | Draft corrected; **no message sent** |

### Failure cases

| Scenario | Expected |
|---|---|
| Backend stopped | Nothing pasted; clipboard restored; tray tip shown |
| Ollama stopped | Nothing pasted; clipboard restored; tray tip shown |
| Text under 3 chars | Nothing pasted; clipboard restored |
| Text over 5000 chars | Nothing pasted; clipboard restored |
| Ollama returns garbage | Nothing pasted; clipboard restored |

### Clipboard behavior

| Scenario | Expected |
|---|---|
| Pre-existing clipboard content; correction fails | Original clipboard content restored exactly |
| Successful correction | Corrected text pasted; **original captured text** now on clipboard |
| Selection equals current clipboard content | Still detected and corrected (uses clear+copy, not comparison) |

---

## Project structure

```
ai-proofread/
  ahk/
    proofreader_hotkey.ahk   AutoHotkey v1.1 hotkey (Windows-only)
  client/
    proofread_client.py      Python bridge: temp file → HTTP → temp file
  server/
    main.py                  FastAPI app (GET /health, POST /proofread)
    config.py                Settings loaded from .env
    models.py                Pydantic request/response models
    database.py              SQLite schema + inserts
    ollama_client.py         Ollama HTTP client + JSON extraction
    correction_service.py    Orchestration: validate → correct → persist → respond
  data/
    .gitkeep                 SQLite DB created here at runtime
  tests/
    test_correction_parsing.py
    test_database.py
    test_config.py
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

## What V1 does NOT include

- Web UI or correction history dashboard
- Per-correction accept/reject
- ML, clustering, or analytics
- macOS support
- Rich-text preservation
- Cloud model APIs

See `docs/roadmap.md` for the V2/V3 plan.
