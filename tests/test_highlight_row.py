"""Pure-logic tests for highlight_row() — the full-width multi-colour stripe
renderer both GUI panels use. No Qt needed.

Run: python3 -m pytest tests/test_highlight_row.py -q
"""

from pytoy.simulator import (highlight_row, ROW_WIDTH,
                             HL_SELECTED, HL_PC, HL_ARG, HL_CHANGE)


def test_no_colours_returns_escaped_padded_plain_text():
    out = highlight_row("hi", [])
    assert "<span" not in out
    # &lt; etc. would appear if escaping ran; here just check no markup + padded
    assert out.startswith("hi")
    assert len(out) == ROW_WIDTH  # padded to full width


def test_single_colour_fills_the_whole_row():
    out = highlight_row("x", [HL_PC])
    assert out.count("<span") == 1
    assert HL_PC in out
    # the coloured chunk is the full padded width
    assert out == f'<span style="background-color:{HL_PC};">' + "x".ljust(ROW_WIDTH) + "</span>"


def test_two_colours_split_5050():
    out = highlight_row("ab", [HL_PC, HL_CHANGE])
    assert out.count("<span") == 2
    assert HL_PC in out and HL_CHANGE in out
    # PC stripe comes first (fixed left-to-right order)
    assert out.index(HL_PC) < out.index(HL_CHANGE)


def test_three_colours_split_in_order():
    out = highlight_row("abc", [HL_SELECTED, HL_PC, HL_ARG])
    assert out.count("<span") == 3
    assert out.index(HL_SELECTED) < out.index(HL_PC) < out.index(HL_ARG)


def test_stripes_cover_the_full_width_without_gaps():
    # Concatenated chunk lengths must equal the padded width (no lost chars).
    import re
    out = highlight_row("hello world", [HL_PC, HL_ARG, HL_CHANGE])
    chunks = re.findall(r'>([^<]*)</span>', out)
    assert sum(len(c) for c in chunks) == ROW_WIDTH


def test_html_special_chars_are_escaped():
    out = highlight_row("a<b>&c", [HL_PC])
    assert "&lt;" in out and "&gt;" in out and "&amp;" in out
    assert "<b>" not in out  # the literal tag must not survive


def test_text_longer_than_width_is_not_truncated_when_unstyled():
    long = "z" * (ROW_WIDTH + 10)
    out = highlight_row(long, [])
    assert out == long  # already >= width, returned as-is (escaped)
