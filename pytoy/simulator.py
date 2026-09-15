#!/usr/bin/env python3
"""
Toy CPU Simulator + GUI

The CPU semantics live in pytoy.core; the assembler lives in pytoy.assembler.
This module is the runnable front end: the terminal simulator and the PySide6
debugger GUI. The command-line entry point lives in run.py at the repo root.
"""

import sys

from .core import (decode, execute_one, is_code_store, _overwrite_msg,
                   _describe, _esc, WRITES_ACC)
from .assembler import assemble, show_assembly, export

# ── Simulator ──────────────────────────────────────────────────────────────

def _warn_continue(msg):
    """Print a warning and ask whether to keep running. Returns True to
    continue. On a non-interactive terminal (EOF), stops (returns False)."""
    print(f"\nWARNING: {msg}", file=sys.stderr)
    try:
        return input("Continue anyway? [y/N] ").strip().lower().startswith('y')
    except EOFError:
        return False

def simulate(mem_in, syms, data_addrs, step=False, show_mem=False, verbose=False,
             addr_orig=None, code_guard=None):
    # code_guard: if set (an address), warn when a STORE writes below it, i.e.
    # into the code region. None disables the check.
    mem  = list(mem_in)
    rsym = {v: k for k, v in syms.items()}
    acc, pc, step_num = 0, 0, 0
    touched = set(data_addrs)
    if addr_orig is None:
        addr_orig = {}
    # visible addresses for verbose mode: all program addresses
    visible = set(addr_orig.keys()) if verbose else set()

    def sym(a): return rsym.get(a, str(a))

    def mem_dump():
        parts = []
        for i in sorted(touched):
            name = rsym.get(i, f"[{i}]")
            parts.append(f"{name}={mem[i]}")
        return "  mem: " + ", ".join(parts) if parts else "  mem: (empty)"

    def vertical_mem(cur_pc, cur_acc, step_num=0, cmd_desc="", cmd_bytes="", cur_arg=None, stopped=False, dump=False):
        lines = []
        if stopped:
            lines.append(f"Stopped after {step_num} steps.")
        else:
            lines.append(f"Step #{step_num}:")
        lines.append(f"  ACC={cur_acc}=b{cur_acc:08b}")
        lines.append(f"  PC={cur_pc}")
        if cmd_bytes:
            n = len(cmd_bytes.split())
            lines.append(f"  OP{n}={cmd_bytes}")
        if cmd_desc:
            lines.append(f"  EXPLAIN: {cmd_desc}")
        lines.append("")
        # memory listing
        lines.append("memory:")
        lines.append("       address        value  original")
        for a in sorted(visible):
            if a == cur_pc:
                marker = ">>"
            elif a == cur_arg:
                marker = "**"
            else:
                marker = "  "
            v = mem[a]
            orig = addr_orig.get(a, '')
            orig_str = f"  {orig}" if orig else ""
            lines.append(f"  {marker} {a:3d}=b{a:08b}  {v:3d}=b{v:08b}{orig_str}")
        # optional mem dump
        if dump:
            lines.append("")
            lines.append("memory dump:")
            lines.append(f"  {mem_dump()}")
        return "\n".join(lines)

    def emit_verbose_frame(cur_pc, stopped=False):
        """Print one full verbose frame (state + memory table) and, in step
        mode, wait for Enter. When stopped, describe the halted machine."""
        if stopped:
            print(vertical_mem(cur_pc, acc, step_num=step_num,
                               cmd_bytes="b00000000", stopped=True, dump=show_mem))
            return
        ins, arg, _ = decode(mem, cur_pc)
        d, bs = _describe(ins, arg, sym, mem)
        print(vertical_mem(cur_pc, acc, step_num=step_num, cmd_desc=d,
                           cmd_bytes=bs, cur_arg=arg, dump=show_mem))
        print()
        if step:
            try: input("[Enter] > ")
            except EOFError: pass

    # show initial state before the first instruction
    if verbose:
        emit_verbose_frame(pc)

    while True:
        instr, arg_addr, _ = decode(mem, pc)

        if not verbose:
            desc, _ = _describe(instr, arg_addr, sym, mem)
            line = f"PC={pc:3d}  ACC={acc:3d}  {desc}"
            if step:
                print(f"\n{line}")
                if show_mem: print(mem_dump())
                try: input("       [Enter] > ")
                except EOFError: pass

        if instr == 0:  # STOP
            break

        # guard: ask before a STORE overwrites code
        if is_code_store(mem, pc, code_guard):
            if not _warn_continue(_overwrite_msg(pc, acc, arg_addr, code_guard)):
                print("Aborted.", file=sys.stderr)
                return acc

        next_pc, acc, arg_addr, _ = execute_one(mem, pc, acc)
        if instr == 21:  # STORE wrote memory
            touched.add(arg_addr)
        step_num += 1

        if verbose:
            visible.update(touched)   # show any newly written addresses
            emit_verbose_frame(next_pc)
        elif not step:
            print(line)
            if show_mem: print(mem_dump())

        pc = next_pc

    # STOP
    if verbose:
        emit_verbose_frame(pc, stopped=True)
    else:
        print(f"\nPC={pc:3d}  ACC={acc:3d}  STOP")
        if show_mem: print(mem_dump())
    return acc

def parse_toyo(text):
    """Parse an exported .toyo byte listing back into a 256-byte memory image.

    Reads the '  ADDR   BYTES  SOURCE' data lines (see export()): a line whose
    first token is a decimal address, followed by one or two 8-bit binary
    byte-strings. Comment lines (starting with '#') and blanks are ignored, so
    the '# SYMBOLS' section is skipped. Returns mem[256]."""
    mem = [0] * 256
    for line in text.splitlines():
        s = line.strip()
        if not s or s.startswith('#'):
            continue
        tok = s.split()
        if not tok[0].isdigit():
            continue
        addr = int(tok[0])
        # following tokens that are 8-char binary strings are the bytes
        offset = 0
        for t in tok[1:]:
            if len(t) == 8 and all(c in '01' for c in t):
                if 0 <= addr + offset < 256:
                    mem[addr + offset] = int(t, 2)
                offset += 1
            else:
                break   # first non-byte token starts the source text
    return mem

# ── Speed control ──────────────────────────────────────────────────────────

# Auto-run speed is expressed as steps per second. The timer interval in
# milliseconds is 1000/sps. Clamp sps to a safe range so the interval never
# becomes 0 (would busy-loop) or absurdly large.
SPS_MIN = 0.1
SPS_MAX = 1000.0

def sps_to_interval(sps):
    """Convert steps-per-second (float) to a QTimer interval in milliseconds.
    Clamps sps to [SPS_MIN, SPS_MAX]. e.g. 0.5 -> 2000, 10 -> 100."""
    try:
        sps = float(sps)
    except (TypeError, ValueError):
        sps = 10.0
    sps = max(SPS_MIN, min(SPS_MAX, sps))
    return 1000.0 / sps

# ── Change highlight ───────────────────────────────────────────────────────

def step_change(opcode, arg_addr):
    """Decide what a single executed step wrote, for the GUI's change highlight.
    Returns (changed_cell, acc_written): changed_cell is the memory address
    written by a STORE (opcode 21), else None; acc_written is True iff the
    instruction writes the accumulator — regardless of whether the value
    actually changed, so a `load` of the value already in ACC still lights up.
    The ACC-writer classification lives in core.WRITES_ACC, next to execute_one,
    so it can't drift from the CPU semantics. Pure — no Qt, no mem access."""
    changed_cell = arg_addr if opcode == 21 else None
    return changed_cell, opcode in WRITES_ACC

# ── GUI Debugger ──────────────────────────────────────────────────────────

def gui_main(mem, listing, syms, data_addrs, code_guard=None, has_source=True):
    """Launch PySide6 graphical debugger. has_source=False (a .toyo) hides the
    source panel and shows only memory, matching the Load button's .toyo path."""
    from PySide6.QtWidgets import (QApplication, QMainWindow, QWidget,
                                   QHBoxLayout, QVBoxLayout, QTextEdit,
                                   QPushButton, QSplitter, QMessageBox,
                                   QLabel, QDoubleSpinBox, QFileDialog)
    from PySide6.QtCore import Qt, QTimer
    from PySide6.QtGui import QFont, QTextCursor, QShortcut, QKeySequence

    class ToyDebugger(QMainWindow):
        def __init__(self, mem_original, listing, syms, data_addrs, code_guard,
                     has_source=True):
            super().__init__()
            self.setWindowTitle("pytoy")
            self.resize(1000, 700)

            self._build_ui()
            self._setup_shortcuts()
            self.load_program(mem_original, listing, syms, data_addrs, code_guard,
                              has_source=has_source)

        def load_program(self, mem_original, listing, syms, data_addrs,
                         code_guard=None, has_source=True):
            """Point the debugger at a new program: rebuild the address maps and
            reset the machine. has_source=False (e.g. a .toyo load) hides the
            left source panel and shows only memory."""
            self.mem_original = list(mem_original)
            self.listing = listing
            self.syms = syms
            self.data_addrs = set(data_addrs)
            self.code_guard = code_guard   # data-region start, or None
            self.rsym = {v: k for k, v in syms.items()}
            self.has_source = has_source

            # build addr→line map and addr→orig map
            self.addr_to_line = {}
            self.line_to_addr = {}
            self.addr_orig = {}
            for i, (addr, blist, orig, is_data) in enumerate(listing):
                if addr is not None:
                    self.addr_to_line[addr] = i
                    self.line_to_addr[i] = addr
                    self.addr_orig[addr] = orig.rstrip()
                    if blist and len(blist) == 2:
                        self.addr_orig[addr + 1] = ''
                        self.addr_to_line[addr + 1] = i

            # collect all visible addresses
            self.visible = set(self.addr_orig.keys())

            self.source_view.setVisible(has_source)
            self.reset()

        def _build_ui(self):
            mono = QFont("Menlo, Courier New, monospace")
            mono.setPointSize(13)
            mono.setStyleHint(QFont.Monospace)

            central = QWidget()
            self.setCentralWidget(central)
            main_layout = QVBoxLayout(central)
            main_layout.setContentsMargins(4, 4, 4, 4)

            splitter = QSplitter(Qt.Horizontal)
            main_layout.addWidget(splitter, stretch=1)

            # left: source code
            self.source_view = QTextEdit()
            self.source_view.setReadOnly(True)
            self.source_view.setFont(mono)
            self.source_view.setLineWrapMode(QTextEdit.NoWrap)
            splitter.addWidget(self.source_view)

            # right: memory + variables
            self.mem_view = QTextEdit()
            self.mem_view.setReadOnly(True)
            self.mem_view.setFont(mono)
            self.mem_view.setLineWrapMode(QTextEdit.NoWrap)
            splitter.addWidget(self.mem_view)

            self.source_view.mouseReleaseEvent = self._source_clicked
            self.mem_view.mouseReleaseEvent = self._mem_clicked

            splitter.setSizes([500, 500])

            # bottom bar
            bottom = QHBoxLayout()
            main_layout.addLayout(bottom)

            self.btn_load = QPushButton("Load…")
            self.btn_load.setFont(mono)
            bottom.addWidget(self.btn_load)
            self.btn_load.clicked.connect(self._load_clicked)

            bottom.addStretch(1)

            self.btn_step = QPushButton("Step")
            self.btn_run = QPushButton("Run")
            bottom.addWidget(self.btn_step)
            bottom.addWidget(self.btn_run)

            # speed control (steps per second, float) — next to Run
            spd_label = QLabel("steps/sec:")
            spd_label.setFont(mono)
            bottom.addWidget(spd_label)
            self.spin_speed = QDoubleSpinBox()
            self.spin_speed.setFont(mono)
            self.spin_speed.setRange(SPS_MIN, SPS_MAX)
            self.spin_speed.setDecimals(2)
            self.spin_speed.setValue(1.0)   # 1 step/sec by default
            bottom.addWidget(self.spin_speed)
            self.spin_speed.valueChanged.connect(self._speed_changed)

            self.btn_reset = QPushButton("Reset")
            bottom.addWidget(self.btn_reset)

            for btn in (self.btn_step, self.btn_run, self.btn_reset):
                btn.setFont(mono)

            self.btn_step.clicked.connect(self.step)
            self.btn_run.clicked.connect(self._toggle_run)
            self.btn_reset.clicked.connect(self.reset)

            self.timer = QTimer()
            self.timer.timeout.connect(self._run_tick)

        def _setup_shortcuts(self):
            QShortcut(QKeySequence(Qt.Key_Space), self, self.step)
            QShortcut(QKeySequence(Qt.Key_Return), self, self.step)
            QShortcut(QKeySequence(Qt.Key_R), self, self._toggle_run)
            QShortcut(QKeySequence(Qt.Key_Escape), self, self.reset)

        def reset(self):
            self.mem = list(self.mem_original)
            self.acc = 0
            self.pc = 0
            self.touched = set(self.data_addrs)
            self.stopped = False
            self.step_count = 0
            self.arg_addr = None
            self.selected_addr = None
            self.changed_cell = None    # cell written in the last step (blue)
            self.acc_written = False     # did the last step write ACC?
            self.overwrite_ok = False   # re-arm the code-overwrite prompt
            self._mem_line_addrs = {}
            self.timer.stop()
            self.btn_step.setEnabled(True)
            self.btn_run.setEnabled(True)
            self.btn_run.setText("Run")
            self.refresh()

        def _sym(self, a):
            return self.rsym.get(a, str(a))

        def _start_timer(self):
            """Start/restart the auto-run timer at the current steps/sec."""
            self.timer.start(int(round(sps_to_interval(self.spin_speed.value()))))
            self.btn_run.setText("Stop")
            self.btn_step.setEnabled(False)   # no single-stepping while running

        def _speed_changed(self, _value):
            """Apply a new speed immediately if we're currently auto-running."""
            if self.timer.isActive():
                self._start_timer()

        def _halt(self):
            """Stop execution: freeze the machine and disable Step/Run."""
            self.stopped = True
            self.timer.stop()
            self.btn_step.setEnabled(False)
            self.btn_run.setEnabled(False)
            self.btn_run.setText("Run")
            self.refresh()

        def step(self):
            if self.stopped:
                return

            instr, arg_addr, _ = decode(self.mem, self.pc)

            if instr == 0:  # STOP
                self._halt()
                return

            # guard: ask before a STORE overwrites code (once per run — after
            # the user says continue, don't nag on every loop iteration)
            if (is_code_store(self.mem, self.pc, self.code_guard)
                    and not self.overwrite_ok):
                was_running = self.timer.isActive()
                self.timer.stop()   # pause auto-run while asking
                msg = _overwrite_msg(self.pc, self.acc, arg_addr,
                                     self.code_guard) + "\n\nContinue anyway?"
                reply = QMessageBox.warning(
                    self, "Code overwrite detected", msg,
                    QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
                if reply != QMessageBox.Yes:
                    self._halt()
                    return
                self.overwrite_ok = True          # don't ask again this run
                if was_running:
                    self._start_timer()           # resume auto-run

            self.pc, self.acc, arg_addr, _ = execute_one(self.mem, self.pc, self.acc)
            if instr == 21:  # STORE wrote memory
                self.touched.add(arg_addr)
            self.changed_cell, self.acc_written = step_change(instr, arg_addr)
            self.step_count += 1
            self.selected_addr = None
            self.arg_addr = arg_addr
            self.visible.update(self.touched)
            self.refresh()

        def _toggle_run(self):
            """Run/Stop toggle: start auto-run, or pause it if already running."""
            if self.stopped:
                return
            if self.timer.isActive():
                self.timer.stop()
                self.btn_run.setText("Run")
                self.btn_step.setEnabled(True)   # re-enable stepping when paused
            else:
                self._start_timer()

        def _load_clicked(self):
            """Open a .toys (assembly source) or .toyo (byte listing) file and
            reload the debugger with it."""
            path, _ = QFileDialog.getOpenFileName(
                self, "Load program", "",
                "Toy programs (*.toys *.toyo);;All files (*)")
            if not path:
                return
            try:
                text = open(path).read()
            except Exception as e:
                QMessageBox.critical(self, "Load failed",
                                     f"Could not read file:\n{e}")
                return

            if path.lower().endswith(".toyo"):
                try:
                    mem = parse_toyo(text)
                except Exception as e:
                    QMessageBox.critical(self, "Load failed",
                                         f"Could not parse .toyo file:\n{e}")
                    return
                # a .toyo has no re-runnable source: show only the memory panel.
                # Build a minimal listing so every byte is visible in memory.
                listing = [(a, [mem[a]], "", True) for a in range(256)]
                self.load_program(mem, listing, {}, set(range(256)),
                                  code_guard=None, has_source=False)
            else:
                mem, listing, syms, data_addrs, errors, data_start = assemble(text)
                if errors:
                    QMessageBox.critical(self, "Assembly failed",
                                         "\n".join(errors))
                    return
                self.load_program(mem, listing, syms, data_addrs,
                                  code_guard=None, has_source=True)

        def _run_tick(self):
            if self.stopped:
                self.timer.stop()
                return
            self.step()

        def _source_clicked(self, event):
            QTextEdit.mouseReleaseEvent(self.source_view, event)
            cursor = self.source_view.cursorForPosition(event.pos())
            line = cursor.blockNumber()
            addr = self.line_to_addr.get(line)
            if addr is not None:
                self.selected_addr = addr
                self.refresh()

        def _mem_clicked(self, event):
            QTextEdit.mouseReleaseEvent(self.mem_view, event)
            cursor = self.mem_view.cursorForPosition(event.pos())
            line = cursor.blockNumber()
            addr = self._mem_line_addrs.get(line)
            if addr is not None:
                self.selected_addr = addr
                self.refresh()

        def refresh(self):
            self._refresh_source()
            self._refresh_memory()

        def _refresh_source(self):
            lines = []
            pc_line = self.addr_to_line.get(self.pc)
            sel_line = self.addr_to_line.get(self.selected_addr) if self.selected_addr is not None else None
            # find which source line the current instruction references
            instr, cur_arg, _ = decode(self.mem, self.pc)
            arg_line = self.addr_to_line.get(cur_arg) if cur_arg is not None else None
            # the source line(s) of the current instruction's bytes: the opcode at
            # pc, plus the operand byte at pc+1 for a two-byte instruction. For a
            # normal `load a` both bytes map to the same line; for hand-written raw
            # bytes (iop: 20 / iarg: 0) they are two separate lines — mark both.
            pc_lines = {pc_line}
            if cur_arg is not None:
                pc_lines.add(self.addr_to_line.get((self.pc + 1) % 256))
            pc_lines.discard(None)
            for i, (addr, blist, orig, is_data) in enumerate(self.listing):
                if i in pc_lines:
                    marker = ">>"
                elif i == arg_line:
                    marker = "**"
                else:
                    marker = "  "
                text = orig.rstrip() if orig else ""
                escaped = _esc(text)
                if i == sel_line:
                    lines.append(f'<span style="background-color:#ffcc66;">{marker} {escaped}</span>')
                elif i in pc_lines:
                    lines.append(f'<span style="background-color:#ffffaa;">{marker} {escaped}</span>')
                elif i == arg_line:
                    lines.append(f'<span style="background-color:#aaffaa;">{marker} {escaped}</span>')
                else:
                    lines.append(f'{marker} {escaped}')
            html = '<pre style="margin:0;">' + '\n'.join(lines) + '</pre>'
            self.source_view.setHtml(html)

            # auto-scroll to PC line
            if pc_line is not None:
                cursor = self.source_view.textCursor()
                cursor.movePosition(QTextCursor.Start)
                for _ in range(pc_line):
                    cursor.movePosition(QTextCursor.Down)
                self.source_view.setTextCursor(cursor)
                self.source_view.ensureCursorVisible()

        def _refresh_memory(self):
            lines = []

            # status info on top
            instr, cur_arg, _ = decode(self.mem, self.pc)
            desc, bs = _describe(instr, cur_arg, self._sym, self.mem)
            # the bytes of the current instruction: the opcode at pc, plus the
            # operand byte at pc+1 for two-byte instructions (load/add/goto/…).
            pc_bytes = {self.pc}
            if cur_arg is not None:
                pc_bytes.add((self.pc + 1) % 256)
            n = len(bs.split())
            if self.stopped:
                lines.append(f'<b>Stopped after {self.step_count} steps.</b>')
            else:
                lines.append(f'<b>Step #{self.step_count}:</b>')
            acc_line = _esc(f"  ACC={self.acc}=b{self.acc:08b}")
            if self.acc_written and not self.stopped and self.step_count > 0:
                acc_line = f'<span style="background-color:#99ccff;">{acc_line}</span>'
            lines.append(acc_line)
            lines.append(_esc(f"  PC={self.pc}"))
            lines.append(_esc(f"  OP{n}={bs}"))
            lines.append(_esc(f"  EXPLAIN: {desc}"))
            lines.append('')

            # unified memory listing
            self._mem_line_addrs = {}
            lines.append(f'<b>memory:</b>')
            lines.append(_esc(f"      {'address':>14}  {'value':>14}"))
            for a in sorted(self.visible):
                line_idx = len(lines)
                self._mem_line_addrs[line_idx] = a
                marker = ">>" if a == self.pc else "  "
                v = self.mem[a]
                text = f"  {marker} {a:3d}=b{a:08b}  {v:3d}=b{v:08b}"
                escaped = _esc(text)
                # precedence: selected > PC > argument > changed. The change
                # highlight is the lowest — it only lingers from the last step,
                # so a live PC byte or the current instruction's argument (green)
                # always wins over it, and it never shows once stopped.
                changed = self.changed_cell if not self.stopped else None
                if a == self.selected_addr:
                    lines.append(f'<span style="background-color:#ffcc66;">{escaped}</span>')
                elif a in pc_bytes:      # opcode + operand byte of the current instr
                    lines.append(f'<span style="background-color:#ffffaa;">{escaped}</span>')
                elif a == cur_arg:       # address this instruction reads/writes
                    lines.append(f'<span style="background-color:#aaffaa;">{escaped}</span>')
                elif a == changed:       # cell written in the last step
                    lines.append(f'<span style="background-color:#99ccff;">{escaped}</span>')
                else:
                    lines.append(escaped)

            html = '<pre style="margin:0;">' + '\n'.join(lines) + '</pre>'
            self.mem_view.setHtml(html)

    import signal
    signal.signal(signal.SIGINT, signal.SIG_DFL)

    app = QApplication.instance() or QApplication(sys.argv)
    win = ToyDebugger(mem, listing, syms, data_addrs, code_guard, has_source)
    win.show()
    app.exec()


def empty_gui():
    """Open the debugger with an empty, zeroed 256-byte memory and no source,
    so `run.py` with no arguments opens a usable window. The user can then load
    an example via the Load button."""
    mem = [0] * 256
    # show every byte in the memory panel; no source, no symbols
    listing = [(a, [mem[a]], "", True) for a in range(256)]
    gui_main(mem, listing, {}, set(range(256)), code_guard=None,
             has_source=False)
