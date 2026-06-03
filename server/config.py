"""
Application configuration loaded from environment variables / .env file.

All settings have documented defaults that match .env.example.
Consumers should import the module-level `settings` singleton.
"""

import re
from dataclasses import dataclass, field
from pathlib import Path

from dotenv import load_dotenv
import os

load_dotenv()


def _parse_db_path(database_url: str) -> Path:
    """
    Convert a sqlite:///./relative/path or sqlite:////absolute/path URL
    to a Path object.

    Examples:
        sqlite:///./data/proofreader.db  -> Path("data/proofreader.db")
        sqlite:////tmp/proofreader.db    -> Path("/tmp/proofreader.db")
    """
    match = re.match(r"sqlite:///(.*)", database_url)
    if not match:
        raise ValueError(
            f"Unsupported DATABASE_URL format: {database_url!r}. Expected sqlite:///..."
        )
    raw = match.group(1)
    # sqlite:///./relative  -> Path("./relative")
    # sqlite:////absolute   -> Path("/absolute")
    return Path(raw)


@dataclass(frozen=True)
class Settings:
    proofreader_api_url: str = field(default="http://localhost:8000")
    ollama_base_url: str = field(default="http://localhost:11434")
    ollama_model: str = field(default="gemma4:e4b")
    database_url: str = field(default="sqlite:///./data/proofreader.db")
    min_chars: int = field(default=3)
    max_chars: int = field(default=5000)
    request_timeout_seconds: int = field(default=30)
    clipboard_timeout_seconds: float = field(default=0.5)
    paste_restore_delay_ms: int = field(default=150)
    store_full_text: bool = field(default=True)

    @property
    def db_path(self) -> Path:
        return _parse_db_path(self.database_url)


def _load_settings() -> Settings:
    def _bool(val: str) -> bool:
        return val.strip().lower() in ("1", "true", "yes", "on")

    return Settings(
        proofreader_api_url=os.getenv("PROOFREADER_API_URL", "http://localhost:8000"),
        ollama_base_url=os.getenv("OLLAMA_BASE_URL", "http://localhost:11434"),
        ollama_model=os.getenv("OLLAMA_MODEL", "gemma4:e4b"),
        database_url=os.getenv("DATABASE_URL", "sqlite:///./data/proofreader.db"),
        min_chars=int(os.getenv("MIN_CHARS", "3")),
        max_chars=int(os.getenv("MAX_CHARS", "5000")),
        request_timeout_seconds=int(os.getenv("REQUEST_TIMEOUT_SECONDS", "30")),
        clipboard_timeout_seconds=float(os.getenv("CLIPBOARD_TIMEOUT_SECONDS", "0.5")),
        paste_restore_delay_ms=int(os.getenv("PASTE_RESTORE_DELAY_MS", "150")),
        store_full_text=_bool(os.getenv("STORE_FULL_TEXT", "true")),
    )


settings: Settings = _load_settings()
