"""
Python review client for the V2.5 review-before-apply workflow.

Called by the AutoHotkey Ctrl+Alt+Shift+P hotkey via the same temp-file protocol
as proofread_client.py.

Protocol:
    Input:   captured text read from --input-file (UTF-8)
    Output:  JSON decision file written to --output-file (UTF-8) on any terminal outcome:
                 {"decision": "accept"|"copy"|"reject"|"cancel", "corrected_text": "..."}
             The file is ALWAYS written (even for reject/cancel) so AHK can branch cleanly.
    Exit:    0 = popup was shown and user made a decision (including reject/cancel)
             1 = hard failure (backend unreachable, pywebview failed, etc.)
             On exit 1, the output file is absent → AHK restores previous clipboard.

Clipboard semantics (enforced on the AHK side, based on the decision file):
    accept  → paste corrected text, leave corrected text in clipboard
    copy    → leave corrected text in clipboard, no paste
    reject  → restore previous clipboard, no paste
    cancel  → restore previous clipboard, no paste (window closed without explicit choice)

Usage (called by AutoHotkey):
    python client/review_client.py
        --input-file  "C:\\path\\to\\proofread_in_<pid>.txt"
        --output-file "C:\\path\\to\\proofread_decision_<pid>.json"
        [--source-app  "Slack"]
        [--window-title "Slack | #general"]
        [--mode selected_text|whole_field|unknown]

Dependencies:
    pywebview (pip install pywebview)
    WebView2 Runtime (https://developer.microsoft.com/en-us/microsoft-edge/webview2/)
"""

import argparse
import json
import logging
import os
import sys
import threading
from pathlib import Path
from typing import Optional

import requests
from dotenv import load_dotenv

# Load .env from the repo root (two levels up from this file: client/ -> repo root)
_repo_root = Path(__file__).resolve().parent.parent
load_dotenv(_repo_root / ".env")

# Log to both stderr and a persistent log file so failures are diagnosable
# when the process is run hidden (no console) by AutoHotkey.
_log_file = Path(os.environ.get("TEMP", ".")) / "proofreader_review.log"
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)-8s %(name)s - %(message)s",
    handlers=[
        logging.StreamHandler(sys.stderr),
        logging.FileHandler(str(_log_file), encoding="utf-8"),
    ],
)
logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Settings
# ---------------------------------------------------------------------------


def _get_settings() -> dict:
    return {
        "api_url": os.getenv("PROOFREADER_API_URL", "http://localhost:8000"),
        "timeout": int(os.getenv("REQUEST_TIMEOUT_SECONDS", "30")),
        "popup_width": int(os.getenv("REVIEW_POPUP_WIDTH", "800")),
        "popup_height": int(os.getenv("REVIEW_POPUP_HEIGHT", "700")),
    }


# ---------------------------------------------------------------------------
# Argument parsing
# ---------------------------------------------------------------------------


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Proofreader review client")
    parser.add_argument(
        "--input-file", required=True, help="Path to UTF-8 file containing captured text."
    )
    parser.add_argument(
        "--output-file",
        required=True,
        help="Path where the JSON decision will be written (UTF-8).",
    )
    parser.add_argument("--source-app", default="unknown", help="Source application name.")
    parser.add_argument("--window-title", default="", help="Active window title.")
    parser.add_argument(
        "--mode",
        default="unknown",
        choices=["selected_text", "whole_field", "unknown"],
    )
    return parser.parse_args()


# ---------------------------------------------------------------------------
# Backend call
# ---------------------------------------------------------------------------


def _call_proofread(
    cfg: dict,
    text: str,
    source_app: str,
    window_title: str,
    mode: str,
) -> Optional[dict]:
    """
    POST /proofread with review=True.

    Returns the parsed JSON response dict on success, or None on failure.
    The response includes event_id (V2.5 addition) which is the review token.
    """
    url = f"{cfg['api_url'].rstrip('/')}/proofread"
    payload = {
        "text": text,
        "source_app": source_app,
        "window_title": window_title,
        "mode": mode,
        "review": True,
    }
    logger.info(
        "POST %s (review=True source_app=%r mode=%r text_len=%d)",
        url,
        source_app,
        mode,
        len(text),
    )
    try:
        response = requests.post(url, json=payload, timeout=cfg["timeout"])
        response.raise_for_status()
        return response.json()
    except requests.exceptions.ConnectionError:
        logger.error("Cannot connect to backend at %s. Is the server running?", cfg["api_url"])
    except requests.exceptions.Timeout:
        logger.error("Backend request timed out after %ds.", cfg["timeout"])
    except requests.exceptions.HTTPError as exc:
        logger.error(
            "Backend returned HTTP %d: %s",
            exc.response.status_code,
            exc.response.text[:200],
        )
    except Exception as exc:
        logger.error("Unexpected error calling backend: %s", exc)
    return None


# ---------------------------------------------------------------------------
# Decision file
# ---------------------------------------------------------------------------


def _write_decision(output_path: Path, decision: str, corrected_text: str) -> bool:
    """
    Write the JSON decision file that AHK reads to determine the OS action.

    Always written, even for reject/cancel, so AHK can branch on the decision
    rather than checking for file absence (which is the error/failure signal).

    Returns True on success, False on I/O error.
    """
    payload = {"decision": decision, "corrected_text": corrected_text}
    try:
        output_path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
        logger.info(
            "Wrote decision file: decision=%r corrected_len=%d", decision, len(corrected_text)
        )
        return True
    except OSError as exc:
        logger.error("Cannot write decision file %s: %s", output_path, exc)
        return False


# ---------------------------------------------------------------------------
# pywebview JS API bridge
# ---------------------------------------------------------------------------


class ReviewApi:
    """
    Exposed to JavaScript as ``window.pywebview.api``.

    The popup page calls ``window.pywebview.api.decide(decision, correctedText)``
    when the user clicks Accept, Copy, or Reject (or presses Esc).
    """

    def __init__(self, output_path: Path, window_ref_holder: list) -> None:
        # window_ref_holder is a one-element list set after webview.create_window,
        # used here to destroy the window from the JS API callback.
        self._output_path = output_path
        self._window_ref_holder = window_ref_holder
        self._decided = False

    def decide(self, decision: str, corrected_text: str) -> None:
        """
        Called by the JavaScript in the review popup.

        Writes the decision file, then destroys the pywebview window so
        webview.start() returns and the client process can exit.
        """
        if self._decided:
            # Guard against double-calls (e.g. Esc + button click race).
            logger.warning("decide() called more than once — ignoring duplicate call")
            return
        self._decided = True

        logger.info("JS API: decide called with decision=%r", decision)
        _write_decision(self._output_path, decision, corrected_text or "")

        # Destroy the window on a short delay so the JS fetch() in the page
        # has a chance to complete before the WebView2 process is torn down.
        def _close():
            import time

            time.sleep(0.3)
            if self._window_ref_holder:
                try:
                    self._window_ref_holder[0].destroy()
                except Exception as exc:
                    logger.warning("Error destroying pywebview window: %s", exc)

        threading.Thread(target=_close, daemon=True).start()

    @property
    def decided(self) -> bool:
        return self._decided


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main() -> int:
    """
    Entry point. Returns exit code:
        0 = popup shown and decision recorded (accept/copy/reject/cancel all return 0)
        1 = hard failure (backend unreachable, pywebview missing, etc.)
    """
    args = _parse_args()
    cfg = _get_settings()
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

    # -- Call backend for correction --
    data = _call_proofread(cfg, text, args.source_app, args.window_title, args.mode)
    if data is None:
        # Backend unreachable or error — no popup; AHK restores clipboard.
        return 1

    corrected_text = data.get("corrected_text", "")
    if not corrected_text or not corrected_text.strip():
        logger.error("Backend returned empty corrected_text; aborting.")
        return 1

    event_id: Optional[int] = data.get("event_id")
    if event_id is None:
        logger.error("Backend response missing event_id; cannot load review popup.")
        return 1

    # -- Launch pywebview popup --
    review_url = f"{cfg['api_url'].rstrip('/')}/ui/review/{event_id}"
    logger.info("Opening review popup for event_id=%d at %s", event_id, review_url)

    try:
        import webview  # pywebview — not installed by default; import deferred to here
    except ImportError:
        logger.error(
            "pywebview is not installed. "
            "Install it with: pip install pywebview\n"
            "Also ensure the WebView2 Runtime is installed: "
            "https://developer.microsoft.com/en-us/microsoft-edge/webview2/"
        )
        return 1

    # window_ref_holder is populated after create_window; passed into the API object.
    window_ref_holder: list = []
    api = ReviewApi(output_path, window_ref_holder)

    try:
        window = webview.create_window(
            title="Review correction — Proofreader",
            url=review_url,
            js_api=api,
            width=cfg["popup_width"],
            height=cfg["popup_height"],
            resizable=True,
            on_top=True,
        )
        window_ref_holder.append(window)
    except Exception as exc:
        logger.error("Failed to create pywebview window: %s", exc)
        return 1

    try:
        webview.start()
    except Exception as exc:
        logger.error("pywebview.start() raised: %s", exc)
        # If the window was never shown, write a cancel decision so AHK restores clipboard.
        if not api.decided:
            _write_decision(output_path, "cancel", corrected_text)
        return 1

    # webview.start() returns after the window is closed.
    # If the user closed the window without clicking a button, write a cancel decision.
    if not api.decided:
        logger.info("Window closed without explicit decision — writing cancel")
        _write_decision(output_path, "cancel", corrected_text)

    return 0


if __name__ == "__main__":
    sys.exit(main())
