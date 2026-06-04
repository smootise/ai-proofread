Roadmap
V1 ✅ Complete

Windows proof-of-concept.

Included:

AutoHotkey hotkey
Python client bridge
FastAPI backend
Ollama correction
SQLite logging
Clipboard recovery fallback
V2 ✅ Complete

Clean local web UI.

Included:

Dashboard with summary stats (total, changed/unchanged/error counts, top categories, top source apps)
Correction history list with filter/search/pagination
Before/after diff view (word-level, line-break-preserving, server-side difflib)
Correction detail page with per-fragment table (original, corrected, category, explanation)
accepted_status column displayed read-only (V2.5 accept/reject deferred)
Single-event delete with two-step confirmation (cascade to items)
Localhost-only, no auth — all UI under /ui prefix
Server-rendered Jinja2 templates, minimal plain CSS, tiny vanilla JS (confirm only)
No schema migration — V1 data is preserved as-is
V2.5

Personalization and feedback loop.

Potential features:

Per-correction accept/reject (accepted_status column already exists in correction_items)
Track rejected suggestions
Avoid repeatedly suggesting corrections the user often rejects
Store correction preference patterns
Start distinguishing "mistake" from "intentional style"
V3

Learning and ML insights.

Potential features:

Mistake analytics dashboard
Clustering recurring errors
Progress tracking over time
Detect mistakes that decreased over time
Surface common misspellings
Surface recurring grammar/conjugation issues
Optional exercise generation
Future platform/deployment

Potential features:

Move backend to TrueNAS
Run Ollama on TrueNAS with RTX 2060 Super
Add Docker/Compose deployment
Add macOS input adapter
Add authentication before exposing web UI to a LAN/TrueNAS address
Keep backend platform-independent
