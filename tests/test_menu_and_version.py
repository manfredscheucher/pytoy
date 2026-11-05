"""Tests for the File/View/Help menu additions and the version helper.

Pure logic (version parsing, reference text, save-format selection) is tested
directly; the menu wiring is checked by building a real offscreen ToyDebugger
via the build_debugger fixture and inspecting its menu bar / actions — no event
loop, so these stay fast.
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest

from pytoy import version as ver
from pytoy import simulator


# ── version helper (pure) ──────────────────────────────────────────────────

def _version_file():
    return open(os.path.join(os.path.dirname(__file__), "..", "VERSION")).read().strip()


def test_version_lines_start_with_the_version_file():
    assert ver.version_lines()[0] == f"pytoy {_version_file()}"


def test_version_lines_show_commit_and_modified(monkeypatch):
    answers = {"rev-parse": "abc123", "status": " M x", "show": "2026-11-05"}
    monkeypatch.setattr(ver, "_git", lambda *a: answers[a[0]])
    assert ver.version_lines()[1:] == ["commit abc123 (modified)", "committed 2026-11-05"]


def test_version_helper_degrades_without_git(monkeypatch):
    # without git only the VERSION file is left
    monkeypatch.setattr(ver, "_git", lambda *a: None)
    assert ver.version_lines() == [f"pytoy {_version_file()}"]


# ── reference text (pure) ──────────────────────────────────────────────────

def test_reference_lists_all_14_instructions():
    text = simulator._REFERENCE_TEXT
    from pytoy.core import _INSTR
    for op, (name, _kind) in _INSTR.items():
        assert name.lower() in text, name
    # the 14 real mnemonics + nop = 15 rows; spot-check a few
    for m in ("load", "store", "ifzero", "goto", "xor", "nop"):
        assert m in text


def test_reference_mentions_shortcuts():
    text = simulator._REFERENCE_TEXT
    for s in ("Space", "Backspace", "reload", "save"):
        assert s.lower() in text.lower()


def test_every_opcode_has_a_reference_effect():
    # guard against the hardcoded `effects` dict drifting from core._INSTR: a new
    # opcode must get an effect string, or this fails loudly instead of silently
    # rendering a blank effect. Each mnemonic row reads
    # "<name> <opcode> <bytes> <effect…>", so a row with an effect has >= 4
    # whitespace tokens.
    from pytoy.core import _INSTR
    text = simulator._REFERENCE_TEXT
    for _op, (name, _kind) in _INSTR.items():
        row = next((ln for ln in text.splitlines()
                    if ln.strip().startswith(name.lower() + " ")), None)
        assert row is not None, f"no reference row for {name}"
        assert len(row.split()) >= 4, f"{name} has no effect text: {row!r}"


# ── menu wiring (offscreen window) ─────────────────────────────────────────

def _menu_titles(win):
    return [a.text() for a in win.menuBar().actions()]


def test_menus_present(build_debugger):
    win = build_debugger()
    titles = _menu_titles(win)
    assert any("File" in t for t in titles)
    assert any("View" in t for t in titles)
    assert any("Help" in t for t in titles)


def test_line_numbers_toggle(build_debugger):
    win = build_debugger()
    assert win._line_numbers is True       # default on
    win._toggle_line_numbers(False)
    assert win._line_numbers is False
    win._toggle_line_numbers(True)
    assert win._line_numbers is True


def test_save_formats_bytecode_always(build_debugger):
    # empty program (no source): only .toyo is offered
    win = build_debugger()
    exts = [ext for _lbl, ext in win._save_formats()]
    assert exts == [".toyo"]


def test_save_formats_with_asm(build_debugger):
    # a program loaded with assembly source offers .toyo + .toys (not .toyc)
    win = build_debugger()
    win._asm_text = "load x\nstop\nx: 42\n"
    win._c_text = None
    exts = [ext for _lbl, ext in win._save_formats()]
    assert ".toyo" in exts and ".toys" in exts and ".toyc" not in exts


def test_save_formats_with_c(build_debugger):
    # a C program offers all three
    win = build_debugger()
    win._asm_text = "load x\nstop\n"
    win._c_text = "int main(void){return 42;}\n"
    exts = [ext for _lbl, ext in win._save_formats()]
    assert set(exts) == {".toyo", ".toys", ".toyc"}


def test_toyo_save_holds_hand_edits_not_run_stores(build_debugger):
    """A .toyo Save writes the program as built plus the hand edits, as plain
    integers; what a run stored stays out."""
    win = build_debugger()
    win.mem[7] = 123                     # a run stored this
    win.hand_edits = {9: 77}             # a hand edit
    values = [int(x) for x in win._bytecode_text().split()]
    assert values[9] == 77
    assert len(values) == 10
    assert values[7] == win.mem_original[7]
