"""Shared pytest fixtures / import path for the pytoy tests."""

import sys, os

import pytest

_ROOT = os.path.join(os.path.dirname(__file__), '..')

# make the pytoy package importable from the repo root
sys.path.insert(0, _ROOT)

# Run Qt headless unless the caller already chose a platform, so the GUI tests
# don't need a display (equivalent to QT_QPA_PLATFORM=offscreen on the CLI).
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")


# ── shared GUI harness ───────────────────────────────────────────────────────
# The GUI classes (ToyDebugger and its closure-local dialogs) live inside
# gui_main()'s closure, so a test can only reach them by actually building a
# window. Every GUI test did the same dance by hand: record the ToyDebugger
# windows that already exist, run gui_main with app.exec() no-op'd, then pick the
# NEW ToyDebugger (a lingering window from an earlier test must not be mistaken
# for this one). The `build_debugger` fixture centralises that and, crucially,
# DESTROYS any ToyDebugger it (or a careless earlier test) left behind between
# tests — hardening the suite against the stale-window isolation flakiness.

@pytest.fixture
def build_debugger():
    """Factory fixture: call it to construct a ToyDebugger offscreen.

        def test_x(build_debugger):
            win = build_debugger()                      # empty zeroed program
            win = build_debugger(mem=my_mem, has_source=True, ...)

    Any keyword is forwarded to gui_main (mem/listing/syms/data_addrs get sane
    defaults for an empty 256-byte program). Returns the freshly built
    ToyDebugger. Every window built through the fixture is tracked and closed +
    destroyed at test teardown, so none leaks into the next GUI test's
    topLevelWidgets(); a one-shot autouse-style sweep at entry also clears any
    ToyDebugger a non-fixture test left around.
    """
    pytest.importorskip("PySide6")
    from PySide6.QtWidgets import QApplication
    from PySide6.QtCore import Qt
    from pytoy import simulator

    app = QApplication.instance() or QApplication([])

    def _destroy_all_debuggers():
        for w in list(app.topLevelWidgets()):
            if w.__class__.__name__ == "ToyDebugger":
                w.setAttribute(Qt.WA_DeleteOnClose, True)
                w.close()
        app.processEvents()

    # Sweep away any ToyDebugger a non-fixture test forgot to clean up, so this
    # test starts from a known-clean top-level-widget set.
    _destroy_all_debuggers()

    built = []

    def _make(mem=None, listing=None, syms=None, data_addrs=None, **kw):
        if mem is None:
            mem = [0] * 256
        if listing is None:
            listing = [(a, [mem[a]], "", True) for a in range(256)]
        if syms is None:
            syms = {}
        if data_addrs is None:
            data_addrs = set(range(256))
        kw.setdefault("code_guard", None)
        kw.setdefault("has_source", False)

        before = set(app.topLevelWidgets())
        orig_exec = QApplication.exec
        QApplication.exec = lambda self: 0
        try:
            simulator.gui_main(mem, listing, syms, data_addrs, **kw)
        finally:
            QApplication.exec = orig_exec

        new = [w for w in app.topLevelWidgets()
               if w not in before and w.__class__.__name__ == "ToyDebugger"]
        assert new, "ToyDebugger window was not constructed"
        win = new[-1]
        win.setAttribute(Qt.WA_DeleteOnClose, True)
        built.append(win)
        return win

    yield _make

    for win in built:
        win.close()
    app.processEvents()
    # final sweep: nothing this test built (or spawned) may survive into the next
    _destroy_all_debuggers()
