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
V2.5 ✅ Complete

Review-before-apply workflow.

Included:

Second hotkey Ctrl+Alt+Shift+P for the review path
Same safe clipboard capture as the fast path (Ctrl+Alt+P is unchanged)
pywebview popup loads the proposed correction from the backend before applying it
Three-button review UI: Accept & apply / Copy corrected text / Reject
Accept: re-focuses original window, pastes corrected text, leaves corrected text in clipboard
Copy only: leaves corrected text in clipboard; no paste; no re-focus (safe fallback)
Reject / Cancel: restores previous clipboard; nothing pasted
Safe refocus: falls back to copy-only if the original window can no longer be activated
review_status column on correction_events (idempotent migration; V1/V2 data preserved)
V2 history and detail UI shows review_status badge (read-only)
Popup reuses V2 diff + correction-items markup and CSS (no extra frontend code)
TrueNAS-compatible: all new OS interaction is client-side; backend additions are pure HTTP/SQLite

Not included (deferred to V3):

Per-correction accept/reject
Personalization / preference learning
ML, clustering, or analytics
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
