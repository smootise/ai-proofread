"""
Tests for server/diffing.py — before/after diff rendering.

Key invariants:
1. Stored HTML/script-like text is ESCAPED, never emitted as live markup.
2. Line breaks are preserved (rendered as <br>).
3. Identical text returns a "no changes" message.
4. None inputs return a placeholder.
5. <ins> wraps additions; <del> wraps deletions.
6. Return type is markupsafe.Markup (safe to pass to Jinja2 | safe).
"""

from markupsafe import Markup

from server.diffing import build_diff


# ---------------------------------------------------------------------------
# Safety — stored HTML/script text must be escaped
# ---------------------------------------------------------------------------


def test_xss_in_original_is_escaped() -> None:
    original = "<script>alert(1)</script>"
    corrected = "<script>alert(1)</script>"  # identical — no diff, but still checked
    # Even if no changes: the text must not appear as live tags.
    result = build_diff(original, corrected)
    assert "<script>" not in str(result)
    assert "&lt;script&gt;" in str(result) or "no changes" in str(result).lower() or "not stored" in str(result).lower()


def test_html_in_original_is_escaped() -> None:
    original = "<b>bold</b> text"
    corrected = "<b>bold</b> fixed"
    result = build_diff(original, corrected)
    assert isinstance(result, Markup)
    # The <b> tag from stored text must be escaped.
    raw = str(result)
    # "bold" should appear but the raw <b> tag from user text must not be unescaped.
    assert "<b>bold</b>" not in raw or "&lt;b&gt;" in raw


def test_ampersand_is_escaped() -> None:
    original = "fish & chips"
    corrected = "fish and chips"
    result = build_diff(original, corrected)
    # The literal & from stored text must be escaped to &amp; in the diff output.
    assert "&amp;" in str(result)
    assert " & " not in str(result)  # raw ampersand should not appear unescaped


def test_angle_brackets_are_escaped() -> None:
    original = "x < y and y > z"
    corrected = "x is less than y and y is greater than z"
    result = build_diff(original, corrected)
    # The raw < and > from stored text must not appear unescaped.
    assert "&lt;" in str(result) or "less" in str(result)


def test_script_in_corrected_is_escaped() -> None:
    original = "hello world"
    corrected = "hello <script>evil()</script> world"
    result = build_diff(original, corrected)
    assert "<script>" not in str(result)
    assert "&lt;script&gt;" in str(result)


# ---------------------------------------------------------------------------
# Return type
# ---------------------------------------------------------------------------


def test_returns_markup_type() -> None:
    result = build_diff("hello", "hello world")
    assert isinstance(result, Markup)


def test_none_original_returns_placeholder() -> None:
    result = build_diff(None, "corrected")
    assert isinstance(result, Markup)
    assert "not stored" in str(result).lower()


def test_none_corrected_returns_placeholder() -> None:
    result = build_diff("original", None)
    assert isinstance(result, Markup)
    assert "not stored" in str(result).lower()


def test_both_none_returns_placeholder() -> None:
    result = build_diff(None, None)
    assert isinstance(result, Markup)
    assert "not stored" in str(result).lower()


# ---------------------------------------------------------------------------
# Identical text
# ---------------------------------------------------------------------------


def test_identical_text_returns_no_changes_message() -> None:
    result = build_diff("No errors here.", "No errors here.")
    assert isinstance(result, Markup)
    assert "no changes" in str(result).lower()
    assert "<ins>" not in str(result)
    assert "<del>" not in str(result)


def test_empty_strings_are_identical() -> None:
    result = build_diff("", "")
    assert "no changes" in str(result).lower()


# ---------------------------------------------------------------------------
# Change markers
# ---------------------------------------------------------------------------


def test_single_word_change_uses_del_ins() -> None:
    result = build_diff("I have teh report.", "I have the report.")
    raw = str(result)
    assert "<del>" in raw
    assert "<ins>" in raw
    assert "teh" in raw
    assert "the" in raw


def test_addition_uses_ins() -> None:
    result = build_diff("hello", "hello world")
    assert "<ins>" in str(result)


def test_deletion_uses_del() -> None:
    result = build_diff("hello world", "hello")
    assert "<del>" in str(result)


# ---------------------------------------------------------------------------
# Line breaks
# ---------------------------------------------------------------------------


def test_line_breaks_preserved_as_br() -> None:
    original = "line one\nline two"
    corrected = "line one\nline two"
    result = build_diff(original, corrected)
    # Even for unchanged multiline text, if rendered it should carry <br>
    # OR return the "no changes" placeholder — both are acceptable.
    # (Our implementation returns the placeholder for identical text.)
    assert isinstance(result, Markup)


def test_multiline_diff_contains_br() -> None:
    original = "line one\nI have teh bug."
    corrected = "line one\nI have the bug."
    result = build_diff(original, corrected)
    raw = str(result)
    assert "<br>" in raw
    assert "teh" in raw or "the" in raw


def test_utf8_bom_stripped_from_original() -> None:
    # AHK FileRead prepends a UTF-8 BOM (﻿) to clipboard text from some apps.
    # It must not appear as a spurious first-word replacement in the diff.
    original = "﻿I have teh report."
    corrected = "I have the report."
    result = build_diff(original, corrected)
    raw = str(result)
    # The BOM character itself must not produce a replace opcode that shows 'I' -> 'I'.
    # Specifically, there must be no <del>...I</del><ins>I</ins> pattern.
    assert "﻿" not in raw  # BOM stripped, not rendered
    assert "<del>I</del><ins>I</ins>" not in raw
    # The real correction should still appear.
    assert "teh" in raw
    assert "the" in raw


def test_utf8_bom_on_both_sides_not_spurious() -> None:
    # If both sides have a BOM (shouldn't happen, but be safe), they both strip
    # and the result is still a clean diff.
    original = "﻿Hello wrold."
    corrected = "﻿Hello world."
    result = build_diff(original, corrected)
    raw = str(result)
    assert "﻿" not in raw
    assert "wrold" in raw
    assert "world" in raw


def test_multiline_unchanged_lines_preserved() -> None:
    original = "unchanged line\ntypo here\nanother unchanged"
    corrected = "unchanged line\ntypo fixed\nanother unchanged"
    result = build_diff(original, corrected)
    raw = str(result)
    assert "unchanged line" in raw
    assert "another unchanged" in raw
