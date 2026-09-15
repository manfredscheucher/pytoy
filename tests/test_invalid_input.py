"""Tests for how the assembler and .toyo loader handle INVALID input — bad
instructions, bad values, missing operands, oversized programs, garbage files.

The contract these pin down:
  * assemble() never raises; it returns a non-empty `errors` list instead.
  * all errors in a file are collected, not just the first.
  * mem is always 256 bytes even on failure (no IndexError on overflow).
  * empty / comment-only input is valid (no errors).
  * parse_toyo() tolerates garbage and returns a 256-byte image.

Run: python3 -m pytest tests/test_invalid_input.py -q
"""

from pytoy.assembler import assemble
from pytoy.simulator import parse_toyo


# ── missing operand ─────────────────────────────────────────────────────────

def test_missing_operand():
    _, _, _, _, errors, _ = assemble("load")
    assert len(errors) == 1
    assert errors[0].startswith("line 1:")
    assert "needs an operand" in errors[0]


# ── unknown label ───────────────────────────────────────────────────────────

def test_unknown_label():
    _, _, _, _, errors, _ = assemble("load nowhere")
    assert len(errors) == 1
    assert errors[0].startswith("line 1:")
    assert "nowhere" in errors[0]


# ── bad data value ──────────────────────────────────────────────────────────

def test_bad_data_value():
    _, _, _, _, errors, _ = assemble("stop\n# data\nx: notanumber")
    assert len(errors) == 1
    assert errors[0].startswith("line 3:")   # the data line
    assert "notanumber" in errors[0]


# ── unknown instruction ─────────────────────────────────────────────────────

def test_unknown_mnemonic_reports_bad_value_or_unknown_instruction():
    # A token that is neither an opcode nor a valid value is reported as a bad
    # value / unknown instruction, prefixed with its line number.
    _, _, _, _, errors, _ = assemble("foobar")
    assert len(errors) == 1
    assert errors[0].startswith("line 1:")
    assert "foobar" in errors[0]


def test_unknown_instruction_with_operand_ignores_the_operand():
    # `foobar 5` is not an opcode, so `foobar` is treated as a data token (and
    # fails); the trailing `5` is silently dropped. Pins this quirky behaviour.
    _, _, _, _, errors, _ = assemble("foobar 5")
    assert len(errors) == 1
    assert "foobar" in errors[0]


# ── multiple errors collected ───────────────────────────────────────────────

def test_all_errors_are_collected_not_just_the_first():
    src = "load\nadd bad\n# data\nx: nope"
    _, _, _, _, errors, _ = assemble(src)
    assert len(errors) == 3
    assert any("needs an operand" in e for e in errors)
    assert any("bad" in e for e in errors)
    assert any("nope" in e for e in errors)


# ── program too big ─────────────────────────────────────────────────────────

def test_program_too_big_reports_error_and_does_not_crash():
    mem, _, _, _, errors, _ = assemble("nop\n" * 257)
    assert len(errors) == 1
    assert "too big" in errors[0].lower()
    assert len(mem) == 256   # no IndexError / truncation crash


# ── empty / comment-only input is valid ─────────────────────────────────────

def test_empty_input_is_not_an_error():
    _, _, _, _, errors, _ = assemble("")
    assert errors == []


def test_comment_only_input_is_not_an_error():
    _, _, _, _, errors, _ = assemble("# just a comment\n\n   \n")
    assert errors == []


# ── invalid inputs never raise, mem stays 256 bytes ─────────────────────────

def test_assemble_never_raises_and_mem_is_always_256():
    for src in ("load", "load x", "foobar 5", "stop\n# data\nx: bad",
                "nop\n" * 300, "", "# c"):
        mem, listing, syms, data_addrs, errors, ds = assemble(src)
        assert len(mem) == 256


# ── .toyo loader tolerates garbage ──────────────────────────────────────────

def test_parse_toyo_tolerates_garbage():
    mem = parse_toyo("this is not a toyo listing\n@@@\n123 abc")
    assert len(mem) == 256
    assert all(b == 0 for b in mem)   # nothing parseable -> all zero


def test_parse_toyo_reads_valid_data_lines():
    # a real .toyo data line: "  ADDR   BYTE  source"
    mem = parse_toyo("  5   00010100  load a\ngarbage line")
    assert mem[5] == 0b00010100
