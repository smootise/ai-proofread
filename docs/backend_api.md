Backend API
Overview

The backend is a FastAPI service responsible for:

Request validation
Ollama correction
JSON parsing
SQLite logging
Structured response
Local web UI (V2)
Health endpoint
GET /health

Response:

{
  "status": "ok"
}
Proofread endpoint
POST /proofread

Request:

{
  "text": "I have teh report ready.",
  "source_app": "Slack",
  "window_title": "Slack",
  "mode": "selected_text"
}

Allowed mode values:

selected_text
whole_field
unknown

Response:

{
  "corrected_text": "I have the report ready.",
  "language": "en",
  "changed": true,
  "confidence": 0.95,
  "corrections": [
    {
      "original": "teh",
      "corrected": "the",
      "category": "spelling",
      "explanation": "Spelling correction.",
      "start_offset": null,
      "end_offset": null
    }
  ],
  "warnings": []
}

The client should only paste corrected_text.

Web UI endpoints (V2)

All UI routes are under /ui. They serve server-rendered HTML (Jinja2 templates).
They are localhost-only — do not expose without adding authentication.

GET /ui                             Dashboard with summary stats
GET /ui/history                     Correction history list (filter/search/paginate)
GET /ui/history/{id}                Detail view: metadata, before/after diff, correction fragments
GET /ui/history/{id}/delete         Delete confirmation page (no-JS fallback)
POST /ui/history/{id}/delete        Perform single-event cascade delete → 303 redirect

Query params for GET /ui/history:

changed         — "changed", "unchanged", or omit for all
language        — exact language code (e.g. "en")
category        — exact category (e.g. "spelling")
source_app      — exact source app name
q               — free-text search in original_text / corrected_text
page            — page number (default 1, page_size 50)

Delete behaviour:

Deleting an event removes the correction_events row AND all linked correction_items in
a single transaction. This is a hard delete — no soft-delete or undo. Only single-event
delete is supported; there is no bulk delete.

After a successful POST /ui/history/{id}/delete, the server redirects (303) to:
  /ui/history?deleted={id}

After an unknown-id delete, the server redirects (303) to /ui/history with no query param.

Ollama config

Defaults:

OLLAMA_BASE_URL=http://localhost:11434
OLLAMA_MODEL=gemma4:e4b

Model must be configurable.

Model prompt requirements

The model must be instructed to:

Return valid JSON only.
Preserve original language.
Preserve tone.
Preserve line breaks.
Fix spelling and grammar only.
Avoid style rewrites.
Avoid markdown fences.
Avoid explanations outside JSON.
SQLite tables

correction_events fields:

id
created_at
source_app
window_title
mode
original_text
corrected_text
language
changed
confidence
model_name
latency_ms
error

correction_items fields:

id
event_id
original_text
corrected_text
category
explanation
start_offset
end_offset
accepted_status

For V1, accepted_status defaults to:

auto_applied

The V2 UI displays accepted_status as read-only. Per-correction accept/reject is deferred to V2.5.

Store full original and corrected text by default.

V2 adds the following idempotent indexes (created in init_db on every startup):

correction_events(created_at)
correction_events(source_app)
correction_events(language)
correction_items(event_id)
correction_items(category)
