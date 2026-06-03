"""
Python client bridge between AutoHotkey and the FastAPI backend.

Protocol (temp-file based, robust to Unicode / multiline / special characters):
    Input:  captured text read from --input-file (UTF-8)
    Output: corrected_text written to --output-file (UTF-8) on success only
    Exit:   0 = success, 1 = any failure

AutoHotkey checks the exit code.  On exit 0 it reads the output file and pastes
its contents.  On non-zero exit it restores the previous clipboard — no paste.

Usage (called by AutoHotkey):
    python client/proofread_client.py \
        --input-file  "C:\path\to\proofread_in_<pid>.txt" \
        --output-file "C:\path\to\proofread_out_<pid>.txt" \
        [--source-app "Slack"] \
        [--window-title "Slack | #general"] \
        [--mode selected_text|whole_field|unknown]
"""

import argparse
import logging
import sys
from pathlib import Path

import requests
from dotenv import load_dotenv

load_dotenv()

from server.config import settings  # noqa: E402 — after load_dotenv

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)-8s %(name)s — %(message)s",
    stream=sys.stderr,  # All diagnostic output goes to stderr; stdout is reserved
)
logger = logging.getLogger(__name__)


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Proofreader client bridge")
    parser.add_argument(
        "--input-file", required=True, help="Path to UTF-8 file containing captured text."
    )
    parser.add_argument(
        "--output-file", required=True, help="Path where corrected_text will be written (UTF-8)."
    )
    parser.add_argument("--source-app", default="unknown", help="Source application name.")
    parser.add_argument("--window-title", default="", help="Active window title.")
    parser.add_argument(
        "--mode", default="unknown", choices=["selected_text", "whole_field", "unknown"]
    )
    return parser.parse_args()


def main() -> int:
    """
    Entry point. Returns exit code: 0 = success, 1 = failure.
    On failure, nothing is written to the output file.
    """
    args = _parse_args()
    input_path = Path(args.input_file)
    output_path = Path(args.output_file)

    # -- Read captured text --
    try:
        text = input_path.read_text(encoding="utf-8")
    except OSError as exc:
        logger.error("Cannot read input file %s: %s", input_path, exc)
        return 1

    if not text.strip():
        logger.error("Input file is empty; nothing to proofread.")
        return 1

    # -- Build request --
    payload = {
        "text": text,
        "source_app": args.source_app,
        "window_title": args.window_title,
        "mode": args.mode,
    }

    # -- Call backend --
    url = f"{settings.proofreader_api_url.rstrip('/')}/proofread"
    logger.info(
        "POST %s (source_app=%r mode=%r text_len=%d)", url, args.source_app, args.mode, len(text)
    )

    try:
        response = requests.post(url, json=payload, timeout=settings.request_timeout_seconds)
        response.raise_for_status()
    except requests.exceptions.ConnectionError:
        logger.error(
            "Cannot connect to backend at %s. Is the server running?", settings.proofreader_api_url
        )
        return 1
    except requests.exceptions.Timeout:
        logger.error("Backend request timed out after %ds.", settings.request_timeout_seconds)
        return 1
    except requests.exceptions.HTTPError as exc:
        logger.error(
            "Backend returned HTTP %d: %s", exc.response.status_code, exc.response.text[:200]
        )
        return 1

    # -- Extract corrected_text --
    try:
        data = response.json()
        corrected_text = data.get("corrected_text", "")
    except Exception as exc:
        logger.error("Failed to parse backend response: %s", exc)
        return 1

    if not corrected_text or not corrected_text.strip():
        logger.error("Backend returned empty corrected_text; aborting.")
        return 1

    # -- Write output file --
    try:
        output_path.write_text(corrected_text, encoding="utf-8")
    except OSError as exc:
        logger.error("Cannot write output file %s: %s", output_path, exc)
        return 1

    logger.info("Correction successful (changed=%s)", data.get("changed"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
