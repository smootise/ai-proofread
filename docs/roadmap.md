Roadmap
V1

Windows proof-of-concept.

Included:

AutoHotkey hotkey
Python client bridge
FastAPI backend
Ollama correction
SQLite logging
Clipboard recovery fallback
V2

Clean local web UI.

Potential features:

Correction history
Before/after diff
Correction explanations
Ability to delete stored correction events
Optional review popup
V2.5

Personalization and feedback loop.

Potential features:

Per-correction accept/reject
Track rejected suggestions
Avoid repeatedly suggesting corrections the user often rejects
Store correction preference patterns
Start distinguishing “mistake” from “intentional style”
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
Keep backend platform-independent