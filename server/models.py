"""
Pydantic request/response models for the /proofread API.

These models are the contract between the Python client and the FastAPI backend.
Do not add fields here without updating docs/backend_api.md.
"""

from enum import Enum
from typing import Literal, Optional

from pydantic import BaseModel, Field


class CaptureMode(str, Enum):
    selected_text = "selected_text"
    whole_field = "whole_field"
    unknown = "unknown"


class ReviewStatus(str, Enum):
    """How a correction event was resolved after it was created."""

    auto_applied = "auto_applied"
    """Fast path (Ctrl+Alt+P) — text was pasted immediately without review."""

    review_pending = "review_pending"
    """Review path (Ctrl+Alt+Shift+P) — popup opened, user has not yet decided."""

    review_accepted_applied = "review_accepted_applied"
    """User accepted the correction and it was pasted into the source app."""

    review_rejected = "review_rejected"
    """User explicitly clicked the Reject button in the popup."""

    review_canceled = "review_canceled"
    """User closed the popup window or pressed Esc without choosing an action."""

    review_copied_to_clipboard = "review_copied_to_clipboard"
    """User chose 'Copy corrected text' — correction is on clipboard, not pasted."""


class ProofreadRequest(BaseModel):
    text: str = Field(..., description="The raw text to proofread.")
    source_app: str = Field(
        default="unknown", description="Name of the source application (e.g. 'Slack')."
    )
    window_title: str = Field(default="", description="Title of the active window at capture time.")
    mode: CaptureMode = Field(default=CaptureMode.unknown, description="How the text was captured.")
    review: bool = Field(
        default=False,
        description=(
            "When true, the event is stored with review_status='review_pending'. "
            "Used by the review client (Ctrl+Alt+Shift+P). "
            "The fast-path client never sets this; omitting it keeps existing behaviour."
        ),
    )


class Correction(BaseModel):
    original: str
    corrected: str
    category: str = Field(description="e.g. 'spelling' or 'grammar'.")
    explanation: str
    start_offset: Optional[int] = None
    end_offset: Optional[int] = None


class ProofreadResponse(BaseModel):
    corrected_text: str
    language: str = Field(default="unknown")
    changed: bool
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)
    corrections: list[Correction] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    # V2.5 addition — the DB row id for this correction event.
    # Optional so old clients (which ignore unknown fields) are unaffected.
    event_id: Optional[int] = Field(
        default=None,
        description="The correction_events row id. Used by the review client to load the popup.",
    )


class ReviewDecisionRequest(BaseModel):
    """Body for POST /ui/review/{event_id}/decision."""

    decision: Literal["accept", "copy", "reject", "cancel"] = Field(
        ...,
        description=(
            "The user's choice in the review popup. "
            "'accept' → review_accepted_applied, "
            "'copy' → review_copied_to_clipboard, "
            "'reject' → review_rejected, "
            "'cancel' → review_canceled."
        ),
    )
