"""Fresh-reviewer probe for Part 3 (EditCDialog / _switch_compiler).

Covers GAPS not in tests/test_part3.py:
  A. Edit-C that OVERFLOWS at assemble (not just compile error) -> rollback.
  B. Edit-C with _current_compiler = None (detect fallback path).
  C. Switch with _current_path = None (placeholder name "program.toyc").
  D. Button visibility after a non-C load that FOLLOWS a C load.
  E. _detect_compilers in EditCDialog reads the PATH on disk, not the edited
     text -> demonstrate the mismatch is harmless (compile still catches).

Headless, offscreen, same style as tests/test_part3.py. Run:
  QT_QPA_PLATFORM=offscreen python3 scripts/probe/probe_part3_review.py
"""
import os, sys
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from PySide6.QtWidgets import QApplication, QDialog, QMessageBox
from pytoy import simulator

ROOT = os.path.join(os.path.dirname(__file__), "..", "..")
SUM3 = os.path.join(ROOT, "examples/c/03-programs/sum3.toyc")
BIGINT = os.path.join(ROOT, "examples/c/03-programs/bigint_add.toyc")

def read(p): return open(p).read()

app = QApplication.instance() or QApplication(sys.argv)

def new_win():
    mem = [0]*256
    listing = [(a, [mem[a]], "", True) for a in range(256)]
    before = set(app.topLevelWidgets())
    orig = QApplication.exec
    QApplication.exec = lambda self: 0
    try:
        simulator.gui_main(mem, listing, {}, set(range(256)),
                           code_guard=None, has_source=False)
    finally:
        QApplication.exec = orig
    return [w for w in app.topLevelWidgets()
            if w not in before and w.__class__.__name__ == "ToyDebugger"][-1]

def load_c(win, src, compiler, path):
    orig = QDialog.exec
    QDialog.exec = lambda self: (self._on_ok(), QDialog.Accepted)[1]
    try:
        win._compile_and_show_casm(src, compiler, path)
    finally:
        QDialog.exec = orig

def drive_edit(win, new_c):
    orig = QDialog.exec
    def save_exec(self):
        self.edit.setPlainText(new_c)
        self._on_save()
        return QDialog.Accepted if self.result() else QDialog.Rejected
    QDialog.exec = save_exec
    try:
        win._edit_c_clicked()
    finally:
        QDialog.exec = orig

results = []
def check(name, cond, detail=""):
    results.append((name, bool(cond), detail))
    print(f"[{'PASS' if cond else 'FAIL'}] {name} {detail}")

# ── A. edit-C overflow at ASSEMBLE stage -> rollback ─────────────────────────
win = new_win()
load_c(win, read(SUM3), "minicc", SUM3)   # minicc accepts sum3
old_c = win._c_text
old_compiler = win._current_compiler
old_asm = win._asm_text
errs = []
simulator.show_error_dialog = lambda *a, **k: errs.append(a)
# replace with bigint (minicc compiles it, but it overflows 240 at assemble)
drive_edit(win, read(BIGINT))
check("A edit-overflow fired error dialog", bool(errs))
check("A edit-overflow C column still visible", win.c_box.isVisible())
check("A edit-overflow has_c_source intact", win.has_c_source)
check("A edit-overflow _c_text unchanged", win._c_text == old_c)
check("A edit-overflow compiler unchanged", win._current_compiler == old_compiler)
check("A edit-overflow asm unchanged", win._asm_text == old_asm)

# ── B. edit with _current_compiler = None (detect fallback) ──────────────────
win = new_win()
load_c(win, read(SUM3), "toycc", SUM3)
win._current_compiler = None          # force the fallback branch
errs2 = []
simulator.show_error_dialog = lambda *a, **k: errs2.append(a)
drive_edit(win, read(SUM3) + "\n// b\n")
check("B compiler-None edit succeeded (no error)", not errs2)
check("B compiler-None edit pinned a compiler", win._current_compiler in ("toycc","minicc"),
      f"-> {win._current_compiler}")
check("B compiler-None edit kept C column", win.has_c_source and win.c_box.isVisible())

# ── C. switch with _current_path = None (placeholder name) ───────────────────
win = new_win()
load_c(win, read(SUM3), "toycc", SUM3)
win._current_path = None              # simulate a C attached without a path
errs3 = []
simulator.show_error_dialog = lambda *a, **k: errs3.append(a)
try:
    win._switch_compiler()
    crashed = False
except Exception as e:
    crashed = True
    print("   switch raised:", repr(e))
check("C switch path=None did not crash", not crashed)
check("C switch path=None flipped to minicc", win._current_compiler == "minicc",
      f"-> {win._current_compiler}")
check("C switch path=None kept C column + maps", win.has_c_source and bool(win._c_to_asm))

# ── D. button visibility after non-C load following C load ───────────────────
win = new_win()
load_c(win, read(SUM3), "toycc", SUM3)
check("D switch button visible after C load", win.btn_switch_compiler.isVisible())
win._load_asm_text("load x\nstop\nx: 5\n", "p.toys")   # non-C load
check("D switch button HIDDEN after asm load", not win.btn_switch_compiler.isVisible())
check("D c_box hidden after asm load", not win.c_box.isVisible())
check("D has_c_source False after asm load", not win.has_c_source)

# ── E. _detect_compilers reads disk path, not edited text ────────────────────
# Load from the real SUM3 path (both accept), unpin compiler, then edit to C
# that the DISK file's detection would accept but is itself invalid -> compile
# must still catch it (detection picks a compiler, _compile_c runs edited text).
win = new_win()
load_c(win, read(SUM3), "toycc", SUM3)   # _current_path = real SUM3 on disk
win._current_compiler = None
errsE = []
simulator.show_error_dialog = lambda *a, **k: errsE.append(a)
old_cE = win._c_text
drive_edit(win, "int main(void){ return nope(; }\n")  # syntax error
check("E bad edit (compiler None) caught by compile", bool(errsE))
check("E bad edit left C unchanged", win._c_text == old_cE)

print("\nSUMMARY:",
      sum(1 for _,ok,_ in results if ok), "pass /",
      sum(1 for _,ok,_ in results if not ok), "fail")
