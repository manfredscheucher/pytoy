"""The memory panel shows "# old: N" on a cell a STORE just overwrote, for that
one step only. Runs a tiny program headlessly and inspects the rendered memory
HTML after each step.

Program:
  0: LOAD 5     ; ACC = mem[5] = 42
  2: STORE 10   ; mem[10] = 42  (was 99)  -> "# old: 99" on cell 10
  4: STOP

Skipped if PySide6 is missing; forces the offscreen Qt platform.
"""

import os
import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PySide6")


def _build_window(mem):
    """Build a ToyDebugger headlessly from the given memory and return the newly
    created window (filtering out any left over from earlier tests)."""
    from PySide6.QtWidgets import QApplication
    from pytoy import simulator

    app = QApplication.instance() or QApplication([])
    before = set(app.topLevelWidgets())

    listing = [(a, [mem[a]], "", True) for a in range(256)]
    orig_exec = QApplication.exec
    QApplication.exec = lambda self: 0
    try:
        simulator.gui_main(mem, listing, {}, set(range(256)),
                           code_guard=None, has_source=False)
    finally:
        QApplication.exec = orig_exec

    new = [w for w in app.topLevelWidgets()
           if w not in before and w.__class__.__name__ == "ToyDebugger"]
    assert new, "ToyDebugger window was not constructed"
    return new[-1]


def _mem_html(win):
    win._refresh_memory()
    return win.mem_view.toPlainText()


def test_old_value_shown_only_for_the_step_after_the_store():
    mem = [0] * 256
    mem[0], mem[1] = 20, 5     # LOAD 5   -> ACC = mem[5] = 42
    mem[2], mem[3] = 21, 10    # STORE 10 -> mem[10]=42, was 99
    mem[4] = 0                 # STOP
    mem[5] = 42                # source value
    mem[10] = 99               # the value STORE overwrites
    win = _build_window(mem)
    try:
        # before anything runs: no "# old" anywhere.
        assert "# old" not in _mem_html(win)

        win.step()                      # LOAD 5 -> ACC=42, no memory write
        assert "# old" not in _mem_html(win)
        assert win.acc == 42

        win.step()                      # STORE 10 -> mem[10]=42, was 99
        assert win.mem[10] == 42
        assert win.changed_cell == 10
        assert win.changed_cell_prev == 99
        html = _mem_html(win)
        assert "# old: 99" in html

        win.step()                      # STOP -> change highlight gone
        assert "# old" not in _mem_html(win)

        # STOP takes no history snapshot, so stepping back undoes the STORE
        # itself: mem[10] is restored and the annotation is gone.
        win.step_back()
        assert win.mem[10] == 99
        assert win.changed_cell is None
        assert "# old" not in _mem_html(win)
    finally:
        win.close()


def test_old_value_survives_step_back_between_two_stores():
    """changed_cell_prev is part of the undo snapshot, so stepping back from a
    second STORE restores the first STORE's "# old" annotation."""
    mem = [0] * 256
    mem[0], mem[1] = 20, 20     # LOAD 20   -> ACC = 7
    mem[2], mem[3] = 21, 10     # STORE 10  -> mem[10]=7, was 99  (# old: 99)
    mem[4], mem[5] = 21, 11     # STORE 11  -> mem[11]=7, was 88  (# old: 88)
    mem[6] = 0                  # STOP
    mem[20] = 7
    mem[10] = 99
    mem[11] = 88
    win = _build_window(mem)
    try:
        win.step()              # LOAD
        win.step()              # STORE 10
        assert "# old: 99" in _mem_html(win)
        win.step()              # STORE 11
        html = _mem_html(win)
        assert "# old: 88" in html
        assert "# old: 99" not in html      # only the latest store annotates

        win.step_back()         # back onto STORE 10's result
        assert win.changed_cell == 10
        assert win.changed_cell_prev == 99
        html = _mem_html(win)
        assert "# old: 99" in html
        assert "# old: 88" not in html
    finally:
        win.close()
