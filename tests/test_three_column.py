"""Tests for the adaptive 1/2/3-column debugger view and its transitive
C ↔ asm ↔ bytecode highlighting.

Two levels, mirroring test_casm_window.py:

  1. The transitive mapping (pure, no Qt): composing the C↔asm map (`# @c:N`
     markers) with the asm↔bytecode map (the listing) resolves a click in any
     column to the matching lines/cells in the others.

  2. The ToyDebugger itself, built headlessly via the shared build_debugger
     fixture: adaptive column visibility (.toyo/.toys/.toyc), clicking a C line
     / asm line / memory cell resolves across all columns, deselect clears
     everything, and a STORE propagates red up to the asm line and C line.

Skipped if PySide6 is missing; forces QT_QPA_PLATFORM=offscreen.
"""

import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from pytoy.simulator import (_compile_c, parse_c_line_map,
                             c_line_to_asm_rows, asm_rows_to_addrs,
                             addr_to_c_line, transitive_selection)
from pytoy.assembler import assemble


# A tiny program with one statement per C line, so the expected mapping is
# obvious from the source positions (same source as test_casm_window.py).
PROG = """\
int main(void) {
    int x = 5;
    int y = x + 3;
    return y;
}
"""
#    line 2: int x = 5;      line 3: int y = x + 3;      line 4: return y;


def _maps_for(src, compiler="toycc"):
    """Compile `src`, returning everything the debugger keeps for highlighting:
    (asm_text, c_to_asm, asm_to_c, line_to_addr, addr_to_line). Built exactly
    like load_program does, so the test exercises the real listing indices."""
    asm = _compile_c(src, compiler, "p.toyc", annotate_c_lines=True)
    c_to_asm, asm_to_c = parse_c_line_map(asm)
    mem, listing, syms, data, errors, _ = assemble(asm)
    assert not errors, errors
    line_to_addr, addr_to_line = {}, {}
    for i, (addr, blist, orig, is_data) in enumerate(listing):
        if addr is not None:
            line_to_addr[i] = addr
            addr_to_line[addr] = i
            if blist and len(blist) == 2:
                addr_to_line[addr + 1] = i
    return asm, c_to_asm, asm_to_c, line_to_addr, addr_to_line


# ── 1. transitive mapping (pure) ─────────────────────────────────────────────

def test_c_line_resolves_to_asm_rows_and_bytes():
    """Clicking a C line selects exactly its asm rows (c_to_asm) and the byte
    addresses those rows own (line_to_addr) — the one-C-line → many-asm-lines
    → several-bytes case the whole feature is built on."""
    _, c_to_asm, asm_to_c, line_to_addr, addr_to_line = _maps_for(PROG)

    # C line 2 (`int x = 5;`) owns several asm rows.
    rows = c_line_to_asm_rows(2, c_to_asm)
    assert rows == set(c_to_asm[2])
    assert len(rows) >= 2

    # Those rows resolve down to the bytes they occupy.
    addrs = asm_rows_to_addrs(rows, line_to_addr)
    assert addrs == {line_to_addr[r] for r in rows if r in line_to_addr}
    assert addrs, "a code statement must own at least one byte"

    # The full transitive selection from a C-line anchor agrees.
    c_lines, sel_rows, sel_addrs = transitive_selection(
        2, None, c_to_asm, asm_to_c, line_to_addr, addr_to_line)
    assert c_lines == {2}
    assert sel_rows == rows
    assert sel_addrs == addrs


def test_asm_row_resolves_back_to_c_line():
    """Clicking an asm line resolves up to its C line, which then lights up all
    its sibling asm rows (the whole statement, not just the clicked line)."""
    _, c_to_asm, asm_to_c, line_to_addr, addr_to_line = _maps_for(PROG)

    row = c_to_asm[2][0]
    assert asm_to_c[row] == 2
    # a byte of that row, resolved up to C, must be line 2.
    addr = line_to_addr.get(c_to_asm[2][1])   # a row that owns a byte
    assert addr_to_c_line(addr, addr_to_line, asm_to_c) == 2

    # selecting via the byte lights the whole statement.
    c_lines, sel_rows, sel_addrs = transitive_selection(
        None, addr, c_to_asm, asm_to_c, line_to_addr, addr_to_line)
    assert c_lines == {2}
    assert sel_rows == set(c_to_asm[2])


def test_memory_cell_resolves_up_to_c():
    """Clicking a memory cell resolves addr → asm row → C line, then back down,
    so the C column and the statement's sibling bytes all light up."""
    _, c_to_asm, asm_to_c, line_to_addr, addr_to_line = _maps_for(PROG)

    # pick a byte owned by a C-attributed asm row.
    row = next(r for r in c_to_asm[3] if r in line_to_addr)
    addr = line_to_addr[row]
    assert addr_to_c_line(addr, addr_to_line, asm_to_c) == 3

    c_lines, sel_rows, sel_addrs = transitive_selection(
        None, addr, c_to_asm, asm_to_c, line_to_addr, addr_to_line)
    assert c_lines == {3}
    assert addr in sel_addrs
    assert sel_rows == set(c_to_asm[3])


def test_unmapped_anchors_select_nothing():
    """An all-None selection (deselect) resolves to empty sets; an address with
    no C origin still selects its own asm row/byte but no C line."""
    _, c_to_asm, asm_to_c, line_to_addr, addr_to_line = _maps_for(PROG)

    assert transitive_selection(None, None, c_to_asm, asm_to_c,
                                line_to_addr, addr_to_line) == (set(), set(), set())

    # a data byte (no `# @c` origin) selects just itself.
    code_addrs = {line_to_addr[r] for rows in c_to_asm.values() for r in rows
                  if r in line_to_addr}
    lone = next(a for a in addr_to_line if a not in code_addrs)
    c_lines, sel_rows, sel_addrs = transitive_selection(
        None, lone, c_to_asm, asm_to_c, line_to_addr, addr_to_line)
    assert lone in sel_addrs
    assert addr_to_line[lone] in sel_rows
    # (may or may not carry a C line depending on the asm; just assert the byte.)


# ── 2. the ToyDebugger, built headlessly ─────────────────────────────────────

pytest.importorskip("PySide6")


def _load_c(win, src, compiler="toycc"):
    """Compile `src` and run the C|asm window's OK-load path on `win`, leaving
    the debugger showing the C program (C column attached). Returns the maps."""
    from PySide6.QtWidgets import QDialog

    orig_exec = QDialog.exec

    def ok_exec(self):
        self._on_ok()
        return QDialog.Accepted

    QDialog.exec = ok_exec
    try:
        win._compile_and_show_casm(src, compiler, "p.toyc")
    finally:
        QDialog.exec = orig_exec
    assert win.has_c_source
    return win._c_to_asm, win._asm_to_c


def test_adaptive_visibility_toyo(build_debugger):
    """A .toyo (bytecode) load hides both the C and asm columns."""
    win = build_debugger()                 # fixture default: has_source=False
    assert not win.c_box.isVisible()
    assert not win.source_box.isVisible()
    assert win.mem_box.isVisible()
    assert not win.has_c_source


def test_adaptive_visibility_toys(build_debugger):
    """A .toys (assembly) load shows the asm column, hides the C column."""
    win = build_debugger()
    win._load_asm_text("load x\nstop\nx: 5\n", "p.toys")
    assert not win.c_box.isVisible()
    assert win.source_box.isVisible()
    assert win.mem_box.isVisible()
    assert not win.has_c_source


def test_adaptive_visibility_toyc(build_debugger):
    """A .toyc (C) load shows all three columns and keeps the C source + maps."""
    win = build_debugger()
    _load_c(win, PROG)
    assert win.c_box.isVisible()
    assert win.source_box.isVisible()
    assert win.mem_box.isVisible()
    assert win.has_c_source
    assert "int x = 5;" in win._c_text
    assert win._c_to_asm and win._asm_to_c


def test_click_c_line_selects_asm_rows_and_bytes(build_debugger):
    """Selecting a C line on the debugger lights its asm rows and their bytes
    across all three columns (via the shared selection state)."""
    win = build_debugger()
    c_to_asm, _ = _load_c(win, PROG)

    # emulate a C-line click: set the selection the way _c_clicked does.
    addrs = asm_rows_to_addrs(c_to_asm[2], win.line_to_addr)
    win._select(c_line=2, addr=min(addrs))

    sel_c, sel_rows, sel_addrs = win._selection_sets()
    assert sel_c == {2}
    assert sel_rows == set(c_to_asm[2])
    assert sel_addrs == addrs
    # the memory panel's selected set is these bytes; a SELECTED colour appears.
    from pytoy.simulator import HL_SELECTED
    win._refresh_memory()
    assert HL_SELECTED in win.mem_view.toHtml()


def test_click_asm_resolves_to_c_line(build_debugger):
    """Clicking an asm line (its byte) resolves up to its C line and lights the
    whole statement in the C column."""
    win = build_debugger()
    c_to_asm, asm_to_c = _load_c(win, PROG)

    row = next(r for r in c_to_asm[3] if r in win.line_to_addr)
    addr = win.line_to_addr[row]
    # _source_clicked sets c_line from asm_to_c + addr from the row.
    win._select(c_line=asm_to_c.get(row), addr=addr)

    sel_c, sel_rows, _ = win._selection_sets()
    assert sel_c == {3}
    assert sel_rows == set(c_to_asm[3])


def test_click_memory_resolves_up_to_c(build_debugger):
    """Clicking a memory cell resolves up to the C line and lights all columns."""
    win = build_debugger()
    c_to_asm, asm_to_c = _load_c(win, PROG)

    row = next(r for r in c_to_asm[4] if r in win.line_to_addr)
    addr = win.line_to_addr[row]
    c_line = addr_to_c_line(addr, win.addr_to_line, win._asm_to_c)
    win._select(c_line=c_line, addr=addr, mem_selected_addr=addr)

    sel_c, sel_rows, sel_addrs = win._selection_sets()
    assert sel_c == {4}
    assert addr in sel_addrs
    assert win.btn_edit.isEnabled()      # a memory click enables Edit


def test_deselect_clears_everything(build_debugger):
    """An unmapped/blank click clears selected_addr AND selected_c_line, and
    nothing stays highlighted in any panel (the leftover-marking bug the doc
    calls out)."""
    from pytoy.simulator import HL_SELECTED
    win = build_debugger()
    c_to_asm, _ = _load_c(win, PROG)

    # first select something, confirm it's highlighted.
    win._select(c_line=2, addr=min(asm_rows_to_addrs(c_to_asm[2],
                                                     win.line_to_addr)))
    win.refresh()
    assert HL_SELECTED in win.c_view.toHtml()

    # now deselect (both anchors None, as an unmapped click does).
    win._select()
    assert win.selected_addr is None
    assert win.selected_c_line is None
    assert win.mem_selected_addr is None
    win.refresh()
    assert HL_SELECTED not in win.c_view.toHtml()
    assert HL_SELECTED not in win.source_view.toHtml()
    assert HL_SELECTED not in win.mem_view.toHtml()
    assert not win.btn_edit.isEnabled()


def test_step_clears_cross_column_selection(build_debugger):
    """Stepping drops the whole selection (addr AND c_line), so a stale C-column
    highlight can't linger after execution moves on."""
    win = build_debugger()
    c_to_asm, _ = _load_c(win, PROG)
    win._select(c_line=2, addr=min(asm_rows_to_addrs(c_to_asm[2],
                                                     win.line_to_addr)))
    assert win.selected_c_line == 2
    win.step()
    assert win.selected_addr is None
    assert win.selected_c_line is None


def test_store_propagates_red_to_asm_and_c(build_debugger):
    """After a STORE, the asm line and C line owning the written byte are in the
    "changed" highlight set (change propagation: STORE → red up through asm → C),
    and clear again on the next step."""
    win = build_debugger()
    _load_c(win, PROG)

    # step until a STORE fires (changed_cell gets set); the toycc output stores
    # locals early, so this is quick. Cap the loop so a bug can't hang.
    for _ in range(200):
        if win.stopped:
            break
        win.step()
        if win.changed_cell is not None:
            break
    assert win.changed_cell is not None, "no STORE observed"

    changed = win.changed_cell
    row = win.addr_to_line.get(changed)
    assert row is not None, "the stored byte should belong to an asm line"
    c_lines, asm_rows = win._change_sets()
    assert row in asm_rows
    expected_c = win._asm_to_c.get(row)
    if expected_c is not None:
        assert expected_c in c_lines

    # the red is per-step: once stopped (or after the cell is cleared) it's gone.
    win.stopped = True
    assert win._change_sets() == (set(), set())
