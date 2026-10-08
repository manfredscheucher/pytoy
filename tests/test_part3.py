"""Part 3 of the three-column view: right-click-to-edit on the C column and the
in-place compiler-switch button (full C toycc <-> mini C minicc).

Built headlessly on the shared build_debugger fixture, driving the closure-local
EditCDialog the same way test_casm_window.py / test_three_column.py drive the
C|asm window: monkeypatch QDialog.exec so the dialog's own Save/OK path runs
without opening a modal window. show_error_dialog is stubbed so an error path
records that it fired instead of blocking on a modal.

Fixtures (verified by scripts/probe/probe_compiler_accept.py):
  - sum3.toyc            both minicc and toycc accept + assemble -> switch OK
  - fibonacci_rec.toyc   minicc rejects (recursion, MiniError at compile)
  - bigint_add.toyc      minicc compiles but overflows 240 bytes (assemble error)

Skipped if PySide6 is missing; forces QT_QPA_PLATFORM=offscreen.
"""

import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

pytest.importorskip("PySide6")

from pytoy import simulator

_ROOT = os.path.join(os.path.dirname(__file__), "..")
SUM3 = os.path.join(_ROOT, "examples/c/03-programs/sum3.toyc")
FIB_REC = os.path.join(_ROOT, "examples/c/03-programs/fibonacci_rec.toyc")
BIGINT = os.path.join(_ROOT, "examples/c/03-programs/bigint_add.toyc")


def _read(path):
    return open(path).read()


def _load_c(win, src, compiler, path="p.toyc"):
    """Compile `src` with `compiler` and run the C|asm window's OK-load path,
    leaving the debugger showing the C program on that compiler."""
    from PySide6.QtWidgets import QDialog

    orig_exec = QDialog.exec

    def ok_exec(self):
        self._on_ok()
        return QDialog.Accepted

    QDialog.exec = ok_exec
    try:
        win._compile_and_show_casm(src, compiler, path)
    finally:
        QDialog.exec = orig_exec
    assert win.has_c_source
    assert win._current_compiler == compiler


# ── C-column right-click edit ─────────────────────────────────────────────────

def test_edit_c_valid_recompiles_and_reattaches(build_debugger, monkeypatch):
    """A valid C edit recompiles with the active compiler, reloads the program,
    updates _c_text, re-parses the C↔asm maps, and keeps the C column visible."""
    win = build_debugger()
    _load_c(win, _read(SUM3), "toycc", SUM3)
    old_maps = dict(win._c_to_asm)

    # drive EditCDialog's Save with new (still valid) C: toggle a literal so the
    # asm genuinely changes but both compilers still accept it.
    new_c = _read(SUM3).replace("return", "return ", 1)  # harmless reformat
    # make a real change: rename nothing, just add a trailing comment line.
    new_c = _read(SUM3) + "\n// edited\n"

    from PySide6.QtWidgets import QDialog
    orig_exec = QDialog.exec

    def save_exec(self):
        self.edit.setPlainText(new_c)
        self._on_save()
        return QDialog.Accepted if self.result() else QDialog.Rejected

    QDialog.exec = save_exec
    try:
        win._edit_c_clicked()
    finally:
        QDialog.exec = orig_exec

    assert win.has_c_source
    assert win.c_box.isVisible()
    assert "// edited" in win._c_text
    assert win._current_compiler == "toycc"
    assert win._c_to_asm            # maps re-parsed, non-empty
    # a trailing comment doesn't change code layout, so the map should still map.
    assert win._asm_to_c


def test_edit_c_invalid_keeps_old_program(build_debugger, monkeypatch):
    """An invalid C edit (compile error) pops show_error_dialog and leaves the
    program and _c_text unchanged — the dialog would stay open for a fix."""
    win = build_debugger()
    _load_c(win, _read(SUM3), "toycc", SUM3)
    old_c = win._c_text
    old_maps = dict(win._c_to_asm)

    errors = []
    monkeypatch.setattr(simulator, "show_error_dialog",
                        lambda *a, **k: errors.append(a))

    bad_c = "int main(void) { return nope(; }\n"   # syntax error

    from PySide6.QtWidgets import QDialog
    orig_exec = QDialog.exec

    def save_exec(self):
        self.edit.setPlainText(bad_c)
        self._on_save()           # should NOT accept
        return QDialog.Accepted if self.result() else QDialog.Rejected

    QDialog.exec = save_exec
    try:
        win._edit_c_clicked()
    finally:
        QDialog.exec = orig_exec

    assert errors, "a compile error should have shown the error dialog"
    assert win._c_text == old_c            # unchanged
    assert win._c_to_asm == old_maps       # unchanged
    assert win._current_compiler == "toycc"
    assert win.has_c_source


def test_edit_c_without_c_source_informs(build_debugger, monkeypatch):
    """Right-clicking the C panel with no C loaded pops an information box and
    opens no editor."""
    win = build_debugger()
    win._load_asm_text("load x\nstop\nx: 5\n", "p.toys")
    assert not win.has_c_source

    info = []
    from PySide6.QtWidgets import QMessageBox
    monkeypatch.setattr(QMessageBox, "information",
                        lambda *a, **k: info.append(a))
    win._edit_c_clicked()
    assert info, "should have shown a 'Nothing to edit' information box"


# ── compiler switch button ────────────────────────────────────────────────────

def test_switch_success_toycc_to_minicc(build_debugger):
    """A program both compilers accept switches toycc -> minicc in place: the
    compiler flips, the program reassembles, and the C column stays."""
    win = build_debugger()
    _load_c(win, _read(SUM3), "toycc", SUM3)
    assert win._current_compiler == "toycc"
    assert win.btn_switch_compiler.isVisible()

    win._switch_compiler()

    assert win._current_compiler == "minicc"
    assert win.has_c_source
    assert win.c_box.isVisible()
    assert win._c_to_asm            # fresh maps after the recompile
    # button now offers the way back (to full C).
    assert "full C" in win.btn_switch_compiler.text()

    # and back again.
    win._switch_compiler()
    assert win._current_compiler == "toycc"
    assert "mini C" in win.btn_switch_compiler.text()


def test_switch_failure_recursion_rolls_back(build_debugger, monkeypatch):
    """Switching a recursive program toycc -> minicc fails at compile (MiniError):
    the error dialog fires and the simulator stays on toycc, program unchanged."""
    win = build_debugger()
    _load_c(win, _read(FIB_REC), "toycc", FIB_REC)
    before_asm = win._asm_text
    before_mem = list(win.mem_original)

    errors = []
    monkeypatch.setattr(simulator, "show_error_dialog",
                        lambda *a, **k: errors.append(a))

    win._switch_compiler()

    assert errors, "a MiniError should have shown the error dialog"
    assert win._current_compiler == "toycc"      # stayed put
    assert win._asm_text == before_asm           # program unchanged
    assert win.mem_original == before_mem
    assert win.has_c_source


def test_switch_failure_overflow_rolls_back(build_debugger, monkeypatch):
    """minicc 'compiles' bigint_add but the result overflows 240 bytes, so the
    assemble step inside the switch fails: stay on toycc, program unchanged."""
    win = build_debugger()
    _load_c(win, _read(BIGINT), "toycc", BIGINT)
    before_asm = win._asm_text
    before_mem = list(win.mem_original)

    errors = []
    monkeypatch.setattr(simulator, "show_error_dialog",
                        lambda *a, **k: errors.append(a))

    win._switch_compiler()

    assert errors, "the overflow must surface via show_error_dialog"
    assert win._current_compiler == "toycc"
    assert win._asm_text == before_asm
    assert win.mem_original == before_mem
    assert win.has_c_source
