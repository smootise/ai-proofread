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
Future TrueNAS architecture
Windows machine:
- AutoHotkey
- Python client bridge
- Clipboard/input manipulation

TrueNAS server:
- FastAPI backend
- Ollama
- SQLite database
- Future web UI
- Future analytics/ML jobs

The client must use configurable PROOFREADER_API_URL.

Suggested project structure
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
Dependency guidance

Prefer simple dependencies for V1:

fastapi
uvicorn
pydantic
python-dotenv
requests or httpx
pytest
black
ruff or flake8

Do not introduce frontend frameworks, task queues, vector databases, or ML dependencies in V1.