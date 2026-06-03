Backend API
Overview

The backend is a FastAPI service responsible for:

Request validation
Ollama correction
JSON parsing
SQLite logging
Structured response
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

Minimum correction_events fields:

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

Minimum correction_items fields:

id
event_id
original_text
corrected_text
category
explanation
start_offset
end_offset
accepted_status

For V1, accepted_status should default to:

auto_applied

Store full original and corrected text by default.