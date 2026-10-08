"""Headless (offscreen) test for the GUI's Examples browser.

Builds the ExamplesDialog under an offscreen QApplication and checks that it
lists the known examples grouped by category -> subfolder, keeps minicc and
toycc as SEPARATE top-level C nodes, and that loading a known asm example and a
compiled C example actually populates the debugger's memory without error.

The GUI classes (ToyDebugger, ExamplesDialog) live inside gui_main()'s closure,
so we build a real debugger window headlessly the same way test_io_gui.py does
and reach the dialog through the window's _examples_clicked wiring.

Skipped automatically if PySide6 is missing; forces QT_QPA_PLATFORM=offscreen.
"""

import os
import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

pytest.importorskip("PySide6")

from pytoy.examples_index import grouped_examples


def _build_window():
    """Construct a real ToyDebugger offscreen and return (app, win)."""
    from PySide6.QtWidgets import QApplication
    app = QApplication.instance() or QApplication([])
    from pytoy import simulator

    mem = [0] * 256
    listing = [(a, [mem[a]], "", True) for a in range(256)]

    orig_exec = QApplication.exec
    QApplication.exec = lambda self: 0
    try:
        simulator.gui_main(mem, listing, {}, set(range(256)),
                           code_guard=None, has_source=False)
    finally:
        QApplication.exec = orig_exec

    wins = [w for w in app.topLevelWidgets()
            if w.__class__.__name__ == "ToyDebugger"]
    assert wins, "ToyDebugger window was not constructed"
    win = wins[-1]
    # Destroy the window on close so it leaves topLevelWidgets() — otherwise a
    # lingering ToyDebugger pollutes the next offscreen GUI test's wins[-1].
    from PySide6.QtCore import Qt
    win.setAttribute(Qt.WA_DeleteOnClose, True)
    return app, win


def _top_level_labels(tree):
    return [tree.topLevelItem(i).text(0) for i in range(tree.topLevelItemCount())]


def _top_node(tree, label):
    for i in range(tree.topLevelItemCount()):
        node = tree.topLevelItem(i)
        if node.text(0) == label:
            return node
    raise AssertionError(f"top-level node {label!r} not found")


def _leaves(node):
    """All (Example, compiler) tuples under `node` (depth-first over groups)."""
    from PySide6.QtCore import Qt
    out = []
    for i in range(node.childCount()):
        child = node.child(i)
        choice = child.data(0, Qt.UserRole)
        if choice is not None:
            out.append(choice)
        out.extend(_leaves(child))
    return out


def test_examples_dialog_grouping_and_load():
    app, win = _build_window()
    try:
        # Reach ExamplesDialog via the same class the button uses. It is a
        # closure-local class; grab it off an instance the window can make.
        # _examples_clicked builds one; instead we build it directly through the
        # window's module by instantiating the class the button references.
        dlg = _make_dialog(win)

        tree = dlg.tree
        labels = _top_level_labels(tree)

        groups = grouped_examples()

        # Assembly node present with the known subfolders as group children.
        assert "Assembly" in labels
        asm_node = _top_node(tree, "Assembly")
        asm_subs = [asm_node.child(i).text(0)
                    for i in range(asm_node.childCount())]
        assert asm_subs == list(groups["asm"].keys())
        # 01-basics should hold all its asm examples as leaves.
        basics = asm_node.child(asm_subs.index("01-basics"))
        basic_names = [basics.child(i).text(0)
                       for i in range(basics.childCount())]
        assert basic_names == [e.display_name
                               for e in groups["asm"]["01-basics"]]

        # C kept SEPARATE: both "C (minicc)" and "C (toycc)" are top-level nodes.
        assert "C (minicc)" in labels
        assert "C (toycc)" in labels

        # Every leaf under a C node carries that node's compiler, and the example
        # actually accepts it. A both-compilers example appears under both.
        minicc_choices = _leaves(_top_node(tree, "C (minicc)"))
        toycc_choices = _leaves(_top_node(tree, "C (toycc)"))
        assert minicc_choices and toycc_choices
        for ex, comp in minicc_choices:
            assert comp == "minicc" and "minicc" in ex.compilers
        for ex, comp in toycc_choices:
            assert comp == "toycc" and "toycc" in ex.compilers

        # A recursive C example (toycc only) must NOT appear under minicc.
        minicc_names = {ex.display_name for ex, _ in minicc_choices}
        toycc_names = {ex.display_name for ex, _ in toycc_choices}
        assert "fibonacci_rec" in toycc_names
        assert "fibonacci_rec" not in minicc_names

        # Bytecode node lists the .toyo listings as leaves.
        if groups["toyo"]:
            assert "Bytecode" in labels
            toyo_node = _top_node(tree, "Bytecode")
            toyo_names = [toyo_node.child(i).text(0)
                          for i in range(toyo_node.childCount())]
            expected = [e.display_name
                        for exs in groups["toyo"].values() for e in exs]
            assert toyo_names == expected

        dlg.close()

        # Loading a known asm example populates memory with a real program.
        asm_example = groups["asm"]["01-basics"][0]
        win._load_example(asm_example, None)
        assert any(b != 0 for b in win.mem), "asm example loaded empty memory"
        assert win._current_path == asm_example.path
        assert win.has_source is True

        # Loading a C example (compiled with toycc) also populates memory.
        c_example, compiler = toycc_choices[0]
        win._load_example(c_example, compiler)
        assert any(b != 0 for b in win.mem), "compiled C example loaded empty"
        assert win._current_path == c_example.path
        assert win.has_source is True
    finally:
        win.close()
        app.processEvents()   # let WA_DeleteOnClose remove it now


def _make_dialog(win):
    """Build an ExamplesDialog the way the button does, without opening it
    modally. The class is closure-local, so reach it through _examples_clicked's
    code object is awkward; instead monkeypatch exec to capture the instance."""
    from PySide6.QtWidgets import QDialog

    captured = {}
    orig_exec = QDialog.exec

    def fake_exec(self):
        captured["dlg"] = self
        return QDialog.Rejected   # don't block; _examples_clicked then no-ops

    QDialog.exec = fake_exec
    try:
        win._examples_clicked()
    finally:
        QDialog.exec = orig_exec
    assert "dlg" in captured, "ExamplesDialog was not constructed"
    return captured["dlg"]
