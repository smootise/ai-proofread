CLAUDE.md — Project Charter & Coding Guardrails
Purpose

Primary context file for Claude Code. Keep this lean: project-wide rules only.

Detailed implementation docs live in:

docs/v1_scope.md — V1 requirements and non-goals
docs/architecture.md — client/server split and future TrueNAS path
docs/clipboard_flow.md — Windows clipboard/hotkey behavior
docs/backend_api.md — FastAPI, Ollama, SQLite contracts
docs/roadmap.md — V2/V3 roadmap and future ideas
Project Summary

Name: TBD proofreader app
Mission: Local-first proofreading tool for Windows. A global hotkey captures selected text, or falls back to the whole focused input field, sends it to a local correction backend, replaces it in-place, and logs corrections for future learning.

Primary V1 apps: Slack, Firefox, Discord, WhatsApp Desktop, Notepad baseline.

Long-term goal: Build a proofreader that can explain corrections, learn from accepted/rejected suggestions, and surface recurring mistake patterns over time.

V1 Scope

Build only the V1 proof of concept.

Included:

AutoHotkey v1.1 global hotkey: Ctrl+Alt+P
Clipboard-based selected text capture
Automatic Ctrl+A fallback when no selection is detected
Python client bridge
FastAPI backend
Ollama correction, default model gemma4:e4b
SQLite correction logging
JSON response internally
Paste only corrected_text
Leave original text in clipboard after successful correction
Restore previous clipboard on failure
Preserve tone and line breaks
Fix spelling and grammar only

Excluded from V1:

Review popup
Web dashboard
ML/clustering
Per-correction accept/reject
Rich-text preservation
macOS support
Cloud model APIs
TrueNAS deployment files unless explicitly requested
Architecture Rule

Design as a client/server app from day one.

AutoHotkey hotkey
  -> Python client bridge
  -> FastAPI backend
  -> Ollama
  -> SQLite

The Windows client should only handle input capture/replacement. The backend owns correction, storage, and future analytics/UI.

The backend URL must be configurable so it can later move from Windows to TrueNAS.

Coding Standards
Python 3.11+
PEP8 compliant
Black formatting, line length 100
Avoid flake8 E/F errors
Type hints on new/modified functions
Use logging for diagnostics
Use print only for intentional CLI/stdout contract output
Tests with pytest for parsing, config, and database logic
Keep modules small and explicit
Do not silently swallow failures that could cause text loss
Configuration

Use .env; commit .env.example.

Important defaults:

PROOFREADER_API_URL=http://localhost:8000
OLLAMA_BASE_URL=http://localhost:11434
OLLAMA_MODEL=gemma4:e4b
DATABASE_URL=sqlite:///./data/proofreader.db
MIN_CHARS=3
MAX_CHARS=5000
REQUEST_TIMEOUT_SECONDS=30
CLIPBOARD_TIMEOUT_SECONDS=0.5
PASTE_RESTORE_DELAY_MS=150
STORE_FULL_TEXT=true
Documentation Rules
Update README.md when setup, commands, ENV vars, or run instructions change.
Update docs/v1_scope.md when V1 behavior changes.
Update docs/architecture.md when module boundaries or deployment assumptions change.
Update docs/clipboard_flow.md when hotkey or clipboard behavior changes.
Update docs/backend_api.md when API, Ollama, or SQLite contracts change.
Update docs/roadmap.md when future scope changes.
Keep detailed implementation notes out of CLAUDE.md.
Claude Code Working Rules

Before large changes:

Explain the plan.
List files to create/modify.
Identify risks.
Keep implementation limited to V1.
Ask before expanding scope.

Do not implement V2/V3 features early.

Most important V1 success criterion: reliable text capture and replacement without accidental text loss.