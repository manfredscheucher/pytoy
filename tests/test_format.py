"""Tests for pytoy.format — byte formatters, memory map, 7-segment, directives.
Pure, no Qt."""

import pytest
from pytoy import format as F


def test_memory_map():
    assert F.IO_BASE == 240 and F.IO_COUNT == 15
    assert F.IO_READY == 255 and F.SP_TOP == 239
    assert F.IO_SYMBOLS["io0"] == 240 and F.IO_SYMBOLS["io14"] == 254
    assert F.IO_SYMBOLS["ready"] == 255
    # io cells + ready cover 240..255 with no gaps
    assert set(F.IO_LABELS) == set(range(240, 256))
    assert F.IO_CELL_LABELS[240] == "io0" and F.READY_LABEL[255] == "ready"


def test_formatters():
    assert F.format_byte(42, "decimal") == "42"
    assert F.format_byte(42, "binary") == "00101010"
    assert F.format_byte(255, "hex") == "FF"
    assert F.format_byte(0, "hex") == "00"
    assert F.format_byte(65, "ascii") == "A"
    assert F.format_byte(10, "ascii") == "·"      # non-printable placeholder
    assert F.format_byte(127, "ascii") == "·"     # DEL is not printable here


def test_format_wraps_mod_256():
    assert F.format_byte(256, "decimal") == "0"
    assert F.format_byte(-1, "decimal") == "255"


# NOTE: "7segment" is disabled for now (wrong display model), so it is not in
# FORMATS and has no formatter/parser test here. The seven_segment() helper is
# parked/commented out in format.py for a future redo.


def test_ascii_non_printable_is_middle_dot():
    # printable chars show as themselves; non-printable (incl. 0) show as "·",
    # kept distinct from a real "." (code 46).
    assert F.format_byte(65, "ascii") == "A"
    assert F.format_byte(46, "ascii") == "."      # a real dot stays a dot
    assert F.format_byte(0, "ascii") == "·"       # NUL -> middle dot
    assert F.format_byte(10, "ascii") == "·"      # newline -> middle dot
    assert F.format_byte(127, "ascii") == "·"     # DEL -> middle dot


def test_parse_input_round_trips():
    assert F.parse_input("42") == 42
    assert F.parse_input("255") == 255
    assert F.parse_input("FF", "hex") == 255
    assert F.parse_input("1010", "binary") == 10
    assert F.parse_input("A", "ascii") == 65
    assert F.parse_input("00001111") == 15        # 8-char binary via core.parse_val
    assert F.parse_input("0x2a") == 42


def test_parse_input_errors():
    with pytest.raises(ValueError):
        F.parse_input("", "ascii")
    with pytest.raises(ValueError):
        F.parse_input("notanumber", "decimal")


def test_directives_defaults():
    d = F.parse_directives("just some code\nno directives")
    assert d == {"output": "decimal"}


def test_directives_asm_and_c():
    d = F.parse_directives("# pytoy: output=ascii\nload ready\n")
    assert d["output"] == "ascii"
    d = F.parse_directives("// pytoy: output=decimal\n", "//")
    assert d["output"] == "decimal"


def test_directives_ignores_unknown_keys():
    # only `output` is recognised; anything else is silently ignored
    d = F.parse_directives("# pytoy: output=hex, bogus=1\n")
    assert d == {"output": "hex"}


def test_directives_ignores_invalid_values():
    # an unknown output mode falls back to the default (decimal), not crash
    d = F.parse_directives("# pytoy: output=rainbow\n")
    assert d["output"] == "decimal"
