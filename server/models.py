"""
Pydantic request/response models for the /proofread API.

These models are the contract between the Python client and the FastAPI backend.
Do not add fields here without updating docs/backend_api.md.
"""

from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


class CaptureMode(str, Enum):
    selected_text = "selected_text"
    whole_field = "whole_field"
    unknown = "unknown"


class ProofreadRequest(BaseModel):
    text: str = Field(..., description="The raw text to proofread.")
    source_app: str = Field(
        default="unknown", description="Name of the source application (e.g. 'Slack')."
    )
    window_title: str = Field(default="", description="Title of the active window at capture time.")
    mode: CaptureMode = Field(default=CaptureMode.unknown, description="How the text was captured.")


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
