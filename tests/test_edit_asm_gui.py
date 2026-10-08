"""Headless (offscreen) test for the GUI's right-click "Edit assembly" window.

Builds a real ToyDebugger offscreen (same harness as test_io_gui.py /
test_examples_browser.py), loads a small asm program, and drives the edit flow
programmatically:

  * the loaded program's source is retained in win._asm_text,
  * opening the edit dialog, changing the source to a DIFFERENT valid program
    and Saving re-assembles + reloads (memory reflects the new asm, _asm_text
    updates),
  * editing to INVALID asm keeps the old program (Save fails gracefully),
  * a .toyo / no-source window offers nothing to edit (graceful no-op).

Skipped automatically if PySide6 is missing; forces QT_QPA_PLATFORM=offscreen.
"""

import os
import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

pytest.importorskip("PySide6")


# Two valid programs whose single data byte lands at address 3 with distinct
# values (40 vs 99), plus one that fails to assemble (unknown label).
ASM_A = "        load  x\n        stop\nx:      40\n"
ASM_B = "        load  x\n        stop\nx:      99\n"
ASM_BAD = "        load  nope\n        stop\n"


def _build_window(has_source):
    """Construct a real ToyDebugger offscreen and return (app, win).

    The newly built window is picked as the last ToyDebugger among top-level
    widgets; WA_DeleteOnClose keeps a lingering window from polluting the next
    GUI test's wins[-1] (the suite's GUI-test isolation quirk)."""
    from PySide6.QtWidgets import QApplication
    app = QApplication.instance() or QApplication([])
    from pytoy import simulator

    mem = [0] * 256
    listing = [(a, [mem[a]], "", True) for a in range(256)]

    pre = set(w for w in app.topLevelWidgets()
              if w.__class__.__name__ == "ToyDebugger")

    orig_exec = QApplication.exec
    QApplication.exec = lambda self: 0
    try:
        simulator.gui_main(mem, listing, {}, set(range(256)),
                           code_guard=None, has_source=has_source)
    finally:
        QApplication.exec = orig_exec

    wins = [w for w in app.topLevelWidgets()
            if w.__class__.__name__ == "ToyDebugger" and w not in pre]
    assert wins, "ToyDebugger window was not constructed"
    win = wins[-1]
    from PySide6.QtCore import Qt
    win.setAttribute(Qt.WA_DeleteOnClose, True)
    return app, win


def _open_edit_dialog(win):
    """Open the Edit-assembly dialog the way the right-click does, without
    blocking. EditAsmDialog is closure-local, so capture the instance by
    monkeypatching QDialog.exec to a no-op before invoking the handler."""
    from PySide6.QtWidgets import QDialog

    captured = {}
    orig_exec = QDialog.exec

    def fake_exec(self):
        captured["dlg"] = self
        return QDialog.Rejected   # don't block; handler then just returns

    QDialog.exec = fake_exec
    try:
        win._edit_asm_clicked()
    finally:
        QDialog.exec = orig_exec
    return captured.get("dlg")


def test_edit_asm_retain_and_save_reloads():
    app, win = _build_window(has_source=True)
    try:
        # Load a small asm program; its source must be retained for editing.
        assert win._load_asm_text(ASM_A, "/tmp/a.toys") is True
        assert win._asm_text == ASM_A
        assert win.mem[3] == 40            # data byte 'x'

        # Right-click opens the edit dialog, prefilled with the source.
        dlg = _open_edit_dialog(win)
        assert dlg is not None, "edit dialog was not constructed"
        assert dlg.edited_text() == ASM_A

        # Edit to a DIFFERENT valid program and Save: it re-assembles + reloads.
        dlg.edit.setPlainText(ASM_B)
        dlg._on_save()
        assert win.mem[3] == 99            # new program loaded
        assert win._asm_text == ASM_B      # retained source updated

        # Editing to INVALID asm keeps the old program; Save fails gracefully
        # (an error dialog is shown by _load_asm_text, suppressed here).
        from pytoy import simulator
        orig = simulator.show_error_dialog
        simulator.show_error_dialog = lambda *a, **k: None
        try:
            dlg2 = _open_edit_dialog(win)
            dlg2.edit.setPlainText(ASM_BAD)
            dlg2._on_save()
        finally:
            simulator.show_error_dialog = orig
        assert win.mem[3] == 99            # unchanged — bad asm not applied
        assert win._asm_text == ASM_B      # retained source unchanged
    finally:
        win.close()
        app.processEvents()


def test_edit_asm_no_source_is_noop():
    # A .toyo / empty startup window has no assembly source: the edit handler
    # shows an info box and does nothing. We suppress the modal info box and
    # assert no edit dialog is built and memory is untouched.
    app, win = _build_window(has_source=False)
    try:
        assert win._asm_text is None
        from PySide6.QtWidgets import QMessageBox
        orig = QMessageBox.information
        QMessageBox.information = staticmethod(lambda *a, **k: QMessageBox.Ok)
        try:
            dlg = _open_edit_dialog(win)
        finally:
            QMessageBox.information = orig
        assert dlg is None, "no edit dialog should open without a source"
    finally:
        win.close()
        app.processEvents()
