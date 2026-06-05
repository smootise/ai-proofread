"""
Before/after diff renderer for the V2 web UI.

Produces an HTML string that highlights word-level changes between two text
versions using <ins> (additions) and <del> (deletions).

Safety contract:
- Every stored-text fragment is HTML-escaped with markupsafe.escape() BEFORE
  being wrapped in any HTML tag.
- Raw stored text is NEVER passed to Markup() directly.
- Only the final assembled diff string — built from already-escaped fragments
  plus our own static <ins>/<del>/<span>/<br> tags — is wrapped in
  markupsafe.Markup so Jinja2 skips auto-escaping on the composed result.
- Templates must render the return value of build_diff() with {{ diff | safe }}
  (or markupsafe.Markup directly), and ONLY for values from this module.
"""

import difflib
from typing import Optional

from markupsafe import Markup, escape


def build_diff(original: Optional[str], corrected: Optional[str]) -> Markup:
    """
    Build an inline before/after diff as a safe HTML Markup object.

    - Preserves line breaks (renders as <br> in the output).
    - Uses word-level difflib.SequenceMatcher to highlight changes.
    - All stored text is HTML-escaped before wrapping in tags.

    Returns:
        A Markup object safe to render with {{ diff | safe }} in Jinja2.

    Edge cases:
        - Either argument is None: returns a placeholder message.
        - Both texts are equal: returns a "no changes" message.
        - Empty string: treated as equal to empty string.
    """
    if original is None or corrected is None:
        return Markup('<span class="diff-unavailable">Full text not stored for this event.</span>')

    # Strip UTF-8 BOM (﻿) that AutoHotkey's FileRead prepends when reading
    # clipboard content written by Notepad or certain Windows apps. The BOM is
    # not part of the user's text and must not appear as a spurious first-word diff.
    original = original.lstrip("﻿")
    corrected = corrected.lstrip("﻿")

    if original == corrected:
        return Markup('<span class="diff-unchanged">No changes — text was already correct.</span>')

    # Split on newlines, keep the delimiter so we can restore line structure.
    original_lines = original.splitlines(keepends=False)
    corrected_lines = corrected.splitlines(keepends=False)

    # Align lines with difflib.  We use ndiff at the line level so we can then
    # do a finer word-level diff within changed lines.
    html_parts: list[str] = []

    # Walk the line-level diff and apply word-level highlighting on changed lines.
    matcher = difflib.SequenceMatcher(None, original_lines, corrected_lines, autojunk=False)
    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        if tag == "equal":
            for line in original_lines[i1:i2]:
                html_parts.append(str(escape(line)))
                html_parts.append("<br>")
        elif tag == "replace":
            # Word-level diff within each changed line group.
            orig_block = "\n".join(original_lines[i1:i2])
            corr_block = "\n".join(corrected_lines[j1:j2])
            html_parts.append(_word_diff(orig_block, corr_block))
            html_parts.append("<br>")
        elif tag == "delete":
            for line in original_lines[i1:i2]:
                html_parts.append(f"<del>{escape(line)}</del>")
                html_parts.append("<br>")
        elif tag == "insert":
            for line in corrected_lines[j1:j2]:
                html_parts.append(f"<ins>{escape(line)}</ins>")
                html_parts.append("<br>")

    # Remove trailing <br> if present.
    while html_parts and html_parts[-1] == "<br>":
        html_parts.pop()

    return Markup("".join(html_parts))


def _word_diff(original: str, corrected: str) -> str:
    """
    Return an HTML string (not yet Markup) with word-level <del>/<ins> tags.

    Both inputs are plain strings; every fragment is escaped before tagging.
    The return value is a plain str of already-safe HTML — caller wraps in Markup.
    """
    orig_words = _tokenize(original)
    corr_words = _tokenize(corrected)

    matcher = difflib.SequenceMatcher(None, orig_words, corr_words, autojunk=False)
    parts: list[str] = []

    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        if tag == "equal":
            parts.append(str(escape("".join(orig_words[i1:i2]))))
        elif tag == "replace":
            parts.append(f'<del>{escape("".join(orig_words[i1:i2]))}</del>')
            parts.append(f'<ins>{escape("".join(corr_words[j1:j2]))}</ins>')
        elif tag == "delete":
            parts.append(f'<del>{escape("".join(orig_words[i1:i2]))}</del>')
        elif tag == "insert":
            parts.append(f'<ins>{escape("".join(corr_words[j1:j2]))}</ins>')

    return "".join(parts)


def _tokenize(text: str) -> list[str]:
    """
    Split text into tokens that preserve whitespace between words.

    Each token is either a word or a run of whitespace, so that joining
    all tokens reconstructs the original text exactly.
    """
    import re

    return re.split(r"(\s+)", text)
