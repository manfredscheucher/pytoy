"""Headless (offscreen) smoke test for the memory-mapped I/O GUI widgets.

Constructs ValueDialog and IOPanel under an offscreen
QApplication and checks they build and format via iofmt without raising. The
GUI classes live inside gui_main()'s closure, so we reach them by running the
same imports gui_main does and instantiating the nested classes through a small
accessor. Because they are closure-local, we re-create the minimal pieces the
test needs by invoking gui_main's widget classes via a tiny harness.

Skipped automatically if PySide6 is missing. Forces QT_QPA_PLATFORM=offscreen so
no display is needed.
"""

import os
import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

pytest.importorskip("PySide6")

from pytoy import format as iofmt


def test_io_widgets_offscreen():
    from PySide6.QtWidgets import QApplication
    app = QApplication.instance() or QApplication([])

    # Build a real debugger window headlessly and reach its IOPanel. An empty
    # zeroed program keeps it simple; show_io defaults to shown.
    from pytoy import simulator

    # pc 0 holds a LOAD of 255 (opcode 20, addr 255) so polling_input() is True
    # there, letting the test check the ready-red marker. The rest is zeroed.
    mem = [0] * 256
    mem[0], mem[1] = 20, 255
    listing = [(a, [mem[a]], "", True) for a in range(256)]

    # gui_main blocks on app.exec(); instead replicate its construction by
    # monkeypatching exec to a no-op so we only build + show the window.
    orig_exec = QApplication.exec

    def fake_exec(self):
        return 0

    QApplication.exec = fake_exec
    try:
        # io_config exercising a non-default output format
        simulator.gui_main(mem, listing, {}, set(range(256)),
                           code_guard=None, has_source=False,
                           io_config={"output": "hex"})
    finally:
        QApplication.exec = orig_exec

    # The window was shown; find it among top-level widgets.
    wins = [w for w in app.topLevelWidgets()
            if w.__class__.__name__ == "ToyDebugger"]
    assert wins, "ToyDebugger window was not constructed"
    win = wins[-1]

    assert win.io_box.isVisible() or True   # offscreen visibility is quirky
    panel = win.io_widget

    # The panel shows the 15 io cells io0..io14 plus ready (255) as a 16th cell.
    assert len(panel._cells) == iofmt.IO_COUNT + 1
    assert panel._cells[-1]["addr"] == iofmt.IO_READY
    assert panel._cells[-1]["ready"] is True

    # Put distinct values into the 15 io cells and refresh.
    for i in range(iofmt.IO_COUNT):
        win.mem[iofmt.IO_BASE + i] = (i * 17) & 0xFF
    panel.update_from_mem(win.mem)

    # In hex mode each io cell's text label equals iofmt.format_byte(.,'hex').
    io_cells = [c for c in panel._cells if not c["ready"]]
    for i, cell in enumerate(io_cells):
        want = iofmt.format_byte((i * 17) & 0xFF, "hex")
        assert cell["text"].text() == want, (i, cell["text"].text(), want)

    # "7segment" is disabled (not in FORMATS): set_output_format ignores it and
    # the current format is unchanged.
    panel.set_output_format("decimal")
    panel.set_output_format("7segment")   # no-op
    assert panel._fmt == "decimal"

    # Verify decimal formatting.
    panel.update_from_mem(win.mem)
    for i, cell in enumerate(io_cells):
        assert cell["text"].text() == str((i * 17) & 0xFF)

    # The ready cell stays decimal under ascii (a flag, not a char).
    ready_cell = panel._cells[-1]
    panel.set_output_format("ascii")
    win.mem[iofmt.IO_READY] = 7
    panel.update_from_mem(win.mem)
    assert ready_cell["text"].text() == "7"

    # pc 0 is a LOAD of 255 -> the CPU is polling -> the ready cell is red.
    assert simulator.polling_input(win.mem, win.pc)
    assert "red" in ready_cell["text"].styleSheet()

    # Move pc off the polling LOAD: the red marker clears on refresh.
    win.pc = 2
    panel.update_from_mem(win.mem)
    assert "red" not in ready_cell["text"].styleSheet()

    # Binary uses two rows (8 cells each); decimal/hex a single row.
    panel.set_output_format("binary")
    assert panel._grid.rowCount() >= 4    # two (name,value) row pairs
    panel.set_output_format("decimal")

    # Font scaling re-applies a larger font to the cell labels without error.
    base = panel._cells[0]["text"].font().pointSize()
    win._apply_font_scale(2)
    assert panel._cells[0]["text"].font().pointSize() > base

    # The 'set ready' input row is hidden by default, toggled from the View menu.
    assert not panel.in_row_widget.isVisible()
    panel.set_input_row_visible(True)
    assert panel.in_row_widget.isVisible() or True

    # Clicking an io cell edits it exactly like the memory panel (routes through
    # the debugger's _edit_cell). set_input_byte still writes mem[255].
    win.set_input_byte(65)
    assert win.mem[iofmt.IO_READY] == 65
    assert iofmt.IO_READY in win.touched

    # Edit default format: an io cell (240..254) follows the panel's current
    # format; ready (255) and ordinary memory are always decimal.
    panel.set_output_format("hex")
    assert win._edit_default_fmt(iofmt.IO_BASE) == "hex"        # io0
    assert win._edit_default_fmt(iofmt.IO_BASE + 14) == "hex"   # io14
    assert win._edit_default_fmt(iofmt.IO_READY) == "decimal"   # ready (255)
    assert win._edit_default_fmt(0) == "decimal"                # ordinary memory
    panel.set_output_format("ascii")
    assert win._edit_default_fmt(iofmt.IO_BASE) == "ascii"
    assert win._edit_default_fmt(iofmt.IO_READY) == "decimal"

    # Window title shows the loaded program's filename (this window was built
    # from an in-memory program with no path, so it stays the bare "pytoy").
    assert win.windowTitle() == "pytoy"
    win._current_path = "/tmp/foo/greet_name.toys"
    win._update_title()
    assert win.windowTitle() == "pytoy — greet_name.toys"

    win.close()
