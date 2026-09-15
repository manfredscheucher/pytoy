"""Pure-logic tests for highlight_row() — the full-width renderer both GUI
panels use. With one active colour the whole row is that colour; with several,
characters alternate through the colours (a fine per-character checkerboard).
No Qt needed.

Run: python3 -m pytest tests/test_highlight_row.py -q
"""

import re

from pytoy.simulator import (highlight_row, ROW_WIDTH,
                             HL_SELECTED, HL_PC, HL_ARG, HL_CHANGE)


def test_no_colours_returns_escaped_padded_plain_text():
    out = highlight_row("hi", [])
    assert "<span" not in out
    assert out.startswith("hi")
    assert len(out) == ROW_WIDTH  # padded to full width


def test_single_colour_fills_the_whole_row_in_one_span():
    out = highlight_row("x", [HL_PC])
    assert out.count("<span") == 1
    assert out == f'<span style="background-color:{HL_PC};">' + "x".ljust(ROW_WIDTH) + "</span>"


def test_two_colours_alternate_per_character():
    out = highlight_row("ab", [HL_PC, HL_CHANGE])
    # one span per character across the whole padded width
    assert out.count("<span") == ROW_WIDTH
    # character 0 -> PC, character 1 -> CHANGE, character 2 -> PC, ...
    colours = re.findall(r'background-color:(#[0-9a-fA-F]+);', out)
    assert colours[0] == HL_PC
    assert colours[1] == HL_CHANGE
    assert colours[2] == HL_PC
    assert colours[3] == HL_CHANGE


def test_three_colours_cycle_every_three_chars():
    out = highlight_row("abc", [HL_SELECTED, HL_PC, HL_ARG])
    colours = re.findall(r'background-color:(#[0-9a-fA-F]+);', out)
    assert colours[0] == HL_SELECTED
    assert colours[1] == HL_PC
    assert colours[2] == HL_ARG
    assert colours[3] == HL_SELECTED  # cycle repeats


def test_all_characters_are_rendered_no_loss():
    out = highlight_row("hello world", [HL_PC, HL_ARG, HL_CHANGE])
    chunks = re.findall(r'>([^<]*)</span>', out)
    assert sum(len(c) for c in chunks) == ROW_WIDTH


def test_html_special_chars_are_escaped():
    # single colour path
    out1 = highlight_row("a<b>&c", [HL_PC])
    assert "&lt;" in out1 and "&gt;" in out1 and "&amp;" in out1
    assert "<b>" not in out1
    # multi-colour path escapes each character too
    out2 = highlight_row("<&>", [HL_PC, HL_ARG])
    assert "&lt;" in out2 and "&amp;" in out2 and "&gt;" in out2
    assert "<&>" not in out2.replace("&lt;", "").replace("&gt;", "")


def test_text_longer_than_width_is_not_truncated_when_unstyled():
    long = "z" * (ROW_WIDTH + 10)
    out = highlight_row(long, [])
    assert out == long  # already >= width, returned as-is (escaped)


def test_multicolour_covers_full_padded_width():
    # every character position gets exactly one span, across the full width
    out = highlight_row("x", [HL_PC, HL_ARG])
    assert out.count("<span") == ROW_WIDTH
