"""Headless (offscreen) test for the assembly panel's line-number gutter.

The gutter is display-only: it shows the 1-based source-line index at the start
of each row (e.g. `  3 | >> load x`) but is never written into the listing's
`orig` fields or any saved file. This builds a real ToyDebugger offscreen (like
test_io_gui.py), renders the source panel, and checks the numbers are present,
right-aligned, sequential from 1, that a known instruction shows its expected
number, and that the numbers are absent from self.listing's orig text.

Skipped automatically if PySide6 is missing.
"""

import os
import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

pytest.importorskip("PySide6")


def _build_debugger(src):
    from PySide6.QtWidgets import QApplication
    app = QApplication.instance() or QApplication([])

    from pytoy import simulator
    from pytoy.assembler import assemble

    mem, listing, syms, data_addrs, errors, _ = assemble(src)
    assert not errors, errors

    # Windows other tests may have left around, so we can pick out the one we
    # build below rather than trusting topLevelWidgets() ordering.
    before = {id(w) for w in app.topLevelWidgets()}

    # gui_main blocks on app.exec(); no-op it so we only build + show.
    orig_exec = QApplication.exec
    QApplication.exec = lambda self: 0
    try:
        simulator.gui_main(mem, listing, syms, data_addrs,
                           code_guard=None, has_source=True)
    finally:
        QApplication.exec = orig_exec

    wins = [w for w in app.topLevelWidgets()
            if w.__class__.__name__ == "ToyDebugger" and id(w) not in before]
    assert wins, "ToyDebugger window was not constructed"
    return wins[-1], listing


# A program with comments, a label, blanks and data so every kind of listing
# row gets a number (matching what a text editor shows for the .toys file).
SRC = """# demo program
start:
  load x
  add y
  store x

x: 5
y: 7
"""


def test_source_gutter_offscreen():
    win, listing = _build_debugger(SRC)
    try:
        win._refresh_source()
        text = win.source_view.toPlainText()
        rows = text.splitlines()

        # one rendered row per listing row.
        assert len(rows) == len(listing), (len(rows), len(listing))

        # Each row starts with a right-aligned number, a separator " | ", then
        # the marker/code. Numbers are sequential from 1.
        width = len(str(len(listing)))
        for i, row in enumerate(rows):
            expected_gutter = f"{i + 1:>{width}} | "
            assert row.startswith(expected_gutter), (i, repr(row))

        # First number is 1, last is len(listing); all right-aligned to `width`.
        assert rows[0].startswith(f"{'1':>{width}} | ")
        assert rows[-1].startswith(f"{len(listing):>{width}} | ")

        # A known instruction: `load x` is listing index 2 -> displayed line 3.
        load_idx = next(i for i, (_, _, orig, _) in enumerate(listing)
                        if orig.strip() == "load x")
        assert load_idx == 2
        assert f"{load_idx + 1:>{width}} | " in rows[load_idx]
        assert "load x" in rows[load_idx]

        # View-only: the gutter separator and numbers are not in any orig field,
        # and each orig equals the original source line (no number prepended).
        for i, (addr, blist, orig, is_data) in enumerate(win.listing):
            assert " | " not in orig, orig
            assert orig == listing[i][2]

        # Clicking a row still selects its address: the gutter is inline (not an
        # extra line), so blockNumber(row i) still maps to listing index i, which
        # addr_to_line/line_to_addr round-trip for the known instruction.
        assert win.line_to_addr.get(load_idx) is not None
        assert win.addr_to_line[win.line_to_addr[load_idx]] == load_idx
    finally:
        win.close()
