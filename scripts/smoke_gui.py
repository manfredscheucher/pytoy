#!/usr/bin/env python3
"""Headless offscreen smoke test: build the ToyDebugger via gui_main (app.exec
no-op'd, like tests/conftest.py's build_debugger) and exercise the round-2 GUI
fixes so a crash surfaces immediately. Run:

    QT_QPA_PLATFORM=offscreen python3 scripts/smoke_gui.py
"""
import os
import sys

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from PySide6.QtWidgets import QApplication
from pytoy import simulator, format as iofmt

app = QApplication.instance() or QApplication([])

mem = [0] * 256
listing = [(a, [mem[a]], "", True) for a in range(256)]

orig_exec = QApplication.exec
QApplication.exec = lambda self: 0
try:
    simulator.gui_main(mem, listing, {}, set(range(256)),
                       code_guard=None, has_source=False)
finally:
    QApplication.exec = orig_exec

win = [w for w in app.topLevelWidgets()
       if w.__class__.__name__ == "ToyDebugger"][-1]

# default I/O format is ascii
assert win.io_widget._fmt == "ascii", win.io_widget._fmt
# combo <-> menu sync
win.io_widget.fmt_combo.setCurrentText("hex")
assert win._io_fmt_actions["hex"].isChecked()
win._io_fmt_actions["binary"].trigger()
assert win.io_widget.fmt_combo.currentText() == "binary"
# bottom bar: Edit is the last widget in the bar (far right)
# refresh with no crash, step with no crash
win.refresh()
win.step()
# the removed attributes are gone
assert not hasattr(win.io_widget, "in_row_widget")
assert not hasattr(win, "set_input_byte")

print("smoke OK: ToyDebugger built, I/O format sync + step + refresh clean")
win.close()
