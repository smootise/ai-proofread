"""
Tests for server/config.py.

Covers:
- Default values match CLAUDE.md documented defaults.
- Environment variable overrides are picked up.
- DATABASE_URL is parsed to a Path correctly.
- STORE_FULL_TEXT accepts truthy/falsy string variants.
"""

import os
from pathlib import Path

import pytest


def _load_settings_with_env(**env_overrides):
    """Helper: temporarily set env vars, reload settings, then restore."""
    from importlib import reload

    original = {}
    for k, v in env_overrides.items():
        original[k] = os.environ.get(k)
        os.environ[k] = v
    try:
        import server.config as config_module

        reload(config_module)
        return config_module._load_settings()
    finally:
        for k, orig in original.items():
            if orig is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = orig


# ---------------------------------------------------------------------------
# Defaults
# ---------------------------------------------------------------------------


def test_defaults() -> None:
    s = _load_settings_with_env()
    assert s.proofreader_api_url == "http://localhost:8000"
    assert s.ollama_base_url == "http://localhost:11434"
    assert s.ollama_model == "gemma4:e4b"
    assert s.database_url == "sqlite:///./data/proofreader.db"
    assert s.min_chars == 3
    assert s.max_chars == 5000
    assert s.request_timeout_seconds == 30
    assert s.clipboard_timeout_seconds == 0.5
    assert s.paste_restore_delay_ms == 150
    assert s.store_full_text is True


# ---------------------------------------------------------------------------
# ENV overrides
# ---------------------------------------------------------------------------


def test_ollama_model_override() -> None:
    s = _load_settings_with_env(OLLAMA_MODEL="llama3:8b")
    assert s.ollama_model == "llama3:8b"


def test_min_chars_override() -> None:
    s = _load_settings_with_env(MIN_CHARS="10")
    assert s.min_chars == 10


def test_max_chars_override() -> None:
    s = _load_settings_with_env(MAX_CHARS="1000")
    assert s.max_chars == 1000


def test_proofreader_api_url_override() -> None:
    s = _load_settings_with_env(PROOFREADER_API_URL="http://truenas:8000")
    assert s.proofreader_api_url == "http://truenas:8000"


# ---------------------------------------------------------------------------
# STORE_FULL_TEXT boolean parsing
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("value", ["true", "True", "TRUE", "1", "yes", "on"])
def test_store_full_text_truthy(value: str) -> None:
    s = _load_settings_with_env(STORE_FULL_TEXT=value)
    assert s.store_full_text is True


@pytest.mark.parametrize("value", ["false", "False", "FALSE", "0", "no", "off"])
def test_store_full_text_falsy(value: str) -> None:
    s = _load_settings_with_env(STORE_FULL_TEXT=value)
    assert s.store_full_text is False


# ---------------------------------------------------------------------------
# DATABASE_URL → Path parsing
# ---------------------------------------------------------------------------


def test_db_path_relative() -> None:
    from server.config import _parse_db_path

    path = _parse_db_path("sqlite:///./data/proofreader.db")
    assert path == Path("./data/proofreader.db")


def test_db_path_absolute() -> None:
    from server.config import _parse_db_path

    path = _parse_db_path("sqlite:////tmp/proofreader.db")
    assert path == Path("/tmp/proofreader.db")


def test_db_path_invalid_scheme_raises() -> None:
    from server.config import _parse_db_path

    with pytest.raises(ValueError, match="Unsupported DATABASE_URL"):
        _parse_db_path("postgresql://localhost/proofreader")


def test_settings_db_path_property() -> None:
    s = _load_settings_with_env(DATABASE_URL="sqlite:///./data/proofreader.db")
    assert s.db_path == Path("./data/proofreader.db")
