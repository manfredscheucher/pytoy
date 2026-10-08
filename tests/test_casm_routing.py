"""Routing + error paths for the "C in the simulator" load flow, and the C↔asm
line map under trickier programs. Complements test_casm_window.py (which covers
the happy-path window) and test_c_line_annotation.py (compiler-level markers).

Two levels, same as the sibling file:

  1. parse_c_line_map / _compile_c (pure, no Qt): the `# @c:N` map stays correct
     for nested if/while and for a recursive program, and an empty-body program
     doesn't crash the mapper.

  2. the GUI routing (built through the shared `build_debugger` fixture): the
     error paths that the happy-path tests never touch — a .toyc neither compiler
     accepts, a compile failure, an unreadable file — must surface an error and
     NOT open a window / load a program. Plus a Cancel on the C|asm window leaves
     the debugger untouched.
"""

import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from pytoy.simulator import parse_c_line_map, _compile_c


# ── 1. line map under trickier programs (pure) ───────────────────────────────

NESTED = """\
int main(void) {
    int s = 0;
    int i = 0;
    while (i < 5) {
        if (i == 2) {
            s = s + 10;
        }
        i = i + 1;
    }
    return s;
}
"""
#  2: int s = 0;     3: int i = 0;     4: while     5: if
#  6: s = s + 10;    8: i = i + 1;    10: return s;


@pytest.mark.parametrize("compiler", ["minicc", "toycc"])
def test_line_map_nested_if_while(compiler):
    """Statements inside a nested while/if still map to their own C line, and
    every mapped asm row's marker agrees with the inverse — for BOTH compilers.
    This guards the carry-through on toycc's rebuilds and minicc's direct emit."""
    asm = _compile_c(NESTED, compiler, "n.toyc", annotate_c_lines=True)
    c_to_asm, asm_to_c = parse_c_line_map(asm)

    # The body statements each produce at least one attributed asm row: the two
    # declarations, the body of the if, the loop increment, and the final return
    # (a deeply nested statement still carries its own C line).
    for c_line in (2, 3, 6, 8, 10):
        assert c_line in c_to_asm, (compiler, c_line, sorted(c_to_asm))

    # The condition lines (while on 4 / if on 5) emit code too; whichever rows
    # carry a marker, the forward and inverse maps must agree everywhere.
    for c_line, rows in c_to_asm.items():
        assert rows == sorted(rows)
        for r in rows:
            assert asm_to_c[r] == c_line
    all_rows = {r for rows in c_to_asm.values() for r in rows}
    assert set(asm_to_c) == all_rows

    # No marker points past the end of the C source (off-by-one guard): the
    # program has 12 lines, so every mapped C line is in range.
    assert max(c_to_asm) <= NESTED.count("\n")


def test_line_map_recursive_toycc():
    """Recursion goes through CallLifter + the liveness pass + the peephole on
    toycc; the recursive-call statement line must still have attributed rows and
    a consistent inverse (minicc rejects recursion, so toycc-only)."""
    src = ("int f(int n) {\n"
           "    if (n == 0) return 0;\n"       # line 2
           "    return f(n - 1) + 1;\n"        # line 3: the recursive call
           "}\n"
           "int main(void) {\n"
           "    return f(3);\n"                # line 6
           "}\n")
    asm = _compile_c(src, "toycc", "r.toyc", annotate_c_lines=True)
    c_to_asm, asm_to_c = parse_c_line_map(asm)
    assert 3 in c_to_asm and 6 in c_to_asm, sorted(c_to_asm)
    for c_line, rows in c_to_asm.items():
        for r in rows:
            assert asm_to_c[r] == c_line


@pytest.mark.parametrize("compiler", ["minicc", "toycc"])
def test_line_map_minimal_program_no_crash(compiler):
    """A one-statement program maps cleanly: parse_c_line_map never raises and
    the single return statement is attributed."""
    src = "int main(void) {\n    return 7;\n}\n"      # return on line 2
    asm = _compile_c(src, compiler, "m.toyc", annotate_c_lines=True)
    c_to_asm, asm_to_c = parse_c_line_map(asm)
    assert c_to_asm, "expected at least the return statement attributed"
    assert 2 in c_to_asm
    # inverse consistent
    assert all(asm_to_c[r] == c for c, rows in c_to_asm.items() for r in rows)


# ── 2. GUI routing error paths (shared build_debugger fixture) ───────────────

pytest.importorskip("PySide6")


def test_load_toyc_neither_compiler_shows_error_no_window(build_debugger, tmp_path):
    """A .toyc neither minicc nor toycc accepts: _load_toyc shows the shared
    error dialog and opens NO window / loads nothing (regression guard for the
    `if not accepted` branch, which the happy-path tests skip)."""
    from pytoy import simulator
    from PySide6.QtWidgets import QDialog

    win = build_debugger()

    bad = tmp_path / "junk.toyc"
    bad.write_text("this is not C at all @@@ ;;;")

    errors = []
    orig_err = simulator.show_error_dialog
    simulator.show_error_dialog = lambda title, msg="": errors.append((title, msg))

    opened = []
    orig_exec = QDialog.exec
    QDialog.exec = lambda self: opened.append(self) or QDialog.Rejected
    try:
        win._load_toyc(str(bad))
    finally:
        simulator.show_error_dialog = orig_err
        QDialog.exec = orig_exec

    assert errors, "neither-compiler case must surface an error dialog"
    assert "Cannot compile" in errors[0][0]
    assert not opened, "no C|asm window should open when nothing compiles"
    assert all(b == 0 for b in win.mem), "nothing should have loaded"
    assert win._current_path is None


def test_compile_failure_shows_error_no_window(build_debugger):
    """_compile_and_show_casm with source the chosen compiler rejects: the error
    dialog fires and no CAsmDialog is constructed (the compile-error branch)."""
    from pytoy import simulator
    from PySide6.QtWidgets import QDialog

    win = build_debugger()

    errors = []
    orig_err = simulator.show_error_dialog
    simulator.show_error_dialog = lambda title, msg="": errors.append((title, msg))

    opened = []
    orig_exec = QDialog.exec
    QDialog.exec = lambda self: opened.append(self) or QDialog.Rejected
    try:
        # recursion: toycc accepts it but force minicc, which rejects it.
        win._compile_and_show_casm("int f(int n){return f(n);}\n"
                                   "int main(void){return f(1);}\n",
                                   "minicc", "rec.toyc")
    finally:
        simulator.show_error_dialog = orig_err
        QDialog.exec = orig_exec

    assert errors, "a compile failure must surface the error dialog"
    assert "minicc failed" in errors[0][0]
    assert not opened, "no window should open on a compile failure"
    assert all(b == 0 for b in win.mem)
    assert win._current_path is None


def test_load_toyc_unreadable_file(build_debugger, tmp_path):
    """_load_toyc on a path that can't be read: the read-failure branch pops a
    critical box and returns without loading. We point at a directory (open()
    raises) and suppress the modal box."""
    from PySide6.QtWidgets import QMessageBox

    win = build_debugger()

    calls = []
    orig = QMessageBox.critical
    QMessageBox.critical = staticmethod(lambda *a, **k: calls.append(a))
    try:
        win._load_toyc(str(tmp_path))      # a directory -> open() raises
    finally:
        QMessageBox.critical = orig

    assert calls, "an unreadable .toyc must raise the load-failed box"
    assert all(b == 0 for b in win.mem)
    assert win._current_path is None


def test_casm_cancel_leaves_debugger_untouched(build_debugger):
    """Cancelling the C|asm window (exec() != Accepted) must NOT load the program
    nor record a path/compiler — only OK commits. Complements the OK-path test in
    test_casm_window.py."""
    from PySide6.QtWidgets import QDialog

    win = build_debugger()

    orig_exec = QDialog.exec
    QDialog.exec = lambda self: QDialog.Rejected      # user cancels
    try:
        win._compile_and_show_casm("int main(void){int x=5;return x;}\n",
                                   "toycc", "p.toyc")
    finally:
        QDialog.exec = orig_exec

    assert all(b == 0 for b in win.mem), "Cancel must not load the program"
    assert win._current_path is None
    assert win._current_compiler is None


def test_fixture_cleans_up_between_gui_tests(build_debugger):
    """Sanity: the fixture hands back a fresh ToyDebugger and no stale one leaks
    in. (The teardown sweep is what actually hardens the suite; here we just
    confirm the build side gives a clean, single new window.)"""
    from PySide6.QtWidgets import QApplication
    app = QApplication.instance()
    win = build_debugger()
    debuggers = [w for w in app.topLevelWidgets()
                 if w.__class__.__name__ == "ToyDebugger"]
    assert win in debuggers
