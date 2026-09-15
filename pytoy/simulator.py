#!/usr/bin/env python3
"""
Toy CPU Simulator + GUI

The CPU semantics live in pytoy.core; the assembler lives in pytoy.assembler.
This module is the runnable front end: the terminal simulator and the PySide6
debugger GUI. The command-line entry point lives in run.py at the repo root.
"""

import sys

from .core import (decode, execute_one, is_code_store, _overwrite_msg,
                   _describe, _esc, WRITES_ACC, parse_val)
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


# ── Row highlighting (full-width, multi-colour) ─────────────────────────────

# The highlight colours, in a fixed cycle order. A line can carry several roles
# at once (e.g. a byte that is both the PC and the just-written cell); instead
# of one colour winning, the row's characters alternate through all the active
# colours, in this order.
HL_SELECTED = "#ffcc66"   # orange: the address the user clicked
HL_PC       = "#ffffaa"   # yellow: the byte(s) of the current instruction
HL_ARG      = "#aaffaa"   # green:  the address this instruction reads/writes
HL_CHANGE   = "#99ccff"   # blue:   the cell/ACC written in the last step
HL_DATA     = "#ffcccc"   # light red: a data byte now differs from the original
HL_CODE     = "#ff6666"   # strong red: a code byte was overwritten at runtime

# Pad every rendered row to this width so a background colour fills the whole
# line out to the panel's right edge, not just behind the text.
ROW_WIDTH = 80

def highlight_row(text, colours, width=ROW_WIDTH):
    """Render one panel row as full-width HTML, its characters coloured by
    *alternating* through `colours`.

    `text` is the raw (unescaped) row text; `colours` is a list of hex colours
    (already de-duplicated, may be empty). The text is padded to `width`, then
    character j gets colours[j % len(colours)] — so with two active colours the
    row is a fine per-character checkerboard of the two, three colours cycle
    every three characters, and so on. With one colour the whole row is that
    colour; with none it's returned escaped but unstyled. Runs of the same
    colour are merged into one span so a single-colour row is one span, not N.
    Pure — no Qt."""
    padded = text.ljust(width)[:width] if len(text) < width else text
    if not colours:
        return _esc(padded)
    n = len(colours)
    if n == 1:
        return f'<span style="background-color:{colours[0]};">{_esc(padded)}</span>'
    # >1 colour: character j gets colours[j % n]. Emit one span per maximal run
    # of the same colour (with >1 colour that's every single character, since
    # adjacent characters always differ in colour).
    out = []
    for j, ch in enumerate(padded):
        colour = colours[j % n]
        out.append(f'<span style="background-color:{colour};">{_esc(ch)}</span>')
    return "".join(out)

def line_changed_bytes(mem, mem_original, addr, blist):
    """True if any byte a source line owns now differs from the freshly-
    assembled original. A line owns len(blist) bytes starting at `addr` (1 for
    data / one-byte ops, 2 for two-byte instructions). False for comment/blank
    lines (addr is None or blist empty). Pure — no Qt."""
    if addr is None or not blist:
        return False
    return any(mem[addr + k] != mem_original[addr + k]
               for k in range(len(blist)))

# ── Step-back history (undo) ────────────────────────────────────────────────

class History:
    """A stack of machine-state snapshots for the debugger's step-back (undo).

    A snapshot is a plain dict of field-name -> value. The caller lists which
    fields are mutable containers (mem, touched, visible) so History copies them
    on push and on pop — the machine keeps mutating its own mem/sets, so both
    directions must copy or the snapshot would alias the live state. Pure Python,
    no Qt, so the undo logic is testable without a GUI."""

    def __init__(self, mutable_fields=("mem", "touched", "visible")):
        self._mutable = tuple(mutable_fields)
        self._stack = []

    def __len__(self):
        return len(self._stack)

    def clear(self):
        self._stack.clear()

    @staticmethod
    def _copy_value(v):
        if isinstance(v, list):
            return list(v)
        if isinstance(v, (set, frozenset)):
            return set(v)
        return v

    def push(self, state):
        """Snapshot `state` (a dict of field -> value), copying mutable ones."""
        snap = {}
        for k, v in state.items():
            snap[k] = self._copy_value(v) if k in self._mutable else v
        self._stack.append(snap)

    def pop(self):
        """Return the most recent snapshot (mutable fields copied again so the
        caller can mutate freely), or None if the stack is empty."""
        if not self._stack:
            return None
        snap = self._stack.pop()
        return {k: (self._copy_value(v) if k in self._mutable else v)
                for k, v in snap.items()}

# ── GUI Debugger ──────────────────────────────────────────────────────────

def gui_main(mem, listing, syms, data_addrs, code_guard=None, has_source=True,
             source_path=None):
    """Launch PySide6 graphical debugger. has_source=False (a .toyo) hides the
    source panel and shows only memory, matching the Load button's .toyo path.
    source_path is the file this program was loaded from (e.g. the CLI argument)
    so Reload can re-read it even before the Load button is ever used."""
    from PySide6.QtWidgets import (QApplication, QMainWindow, QWidget,
                                   QHBoxLayout, QVBoxLayout, QTextEdit,
                                   QPushButton, QSplitter, QMessageBox,
                                   QLabel, QDoubleSpinBox, QFileDialog,
                                   QInputDialog)
    from PySide6.QtCore import Qt, QTimer
    from PySide6.QtGui import QFont, QTextCursor, QShortcut, QKeySequence

    class ToyDebugger(QMainWindow):
        def __init__(self, mem_original, listing, syms, data_addrs, code_guard,
                     has_source=True, source_path=None):
            super().__init__()
            self.setWindowTitle("pytoy")
            self.resize(1000, 700)

            # path of the last file loaded (CLI arg or Load button), for Reload
            self._current_path = source_path
            self._build_ui()
            self._setup_shortcuts()
            self.load_program(mem_original, listing, syms, data_addrs, code_guard,
                              has_source=has_source)
            # a CLI-loaded file means Reload has something to re-read right away
            self.btn_reload.setEnabled(self._current_path is not None)

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

            # our own right-click handler drives the live-edit dialog, so suppress
            # QTextEdit's native context menu (Copy/Paste/…) on the memory panel.
            self.mem_view.setContextMenuPolicy(Qt.NoContextMenu)
            self.mem_view.setToolTip("Right-click a cell to edit its value")

            self.source_view.mouseReleaseEvent = self._source_clicked
            self.mem_view.mouseReleaseEvent = self._mem_clicked

            splitter.setSizes([500, 500])

            # bottom bar
            bottom = QHBoxLayout()
            main_layout.addLayout(bottom)

            self.btn_load = QPushButton("Load…")
            self.btn_load.setFont(mono)
            self.btn_load.setToolTip("Open an assembly (.toys) or byte (.toyo) "
                                     "file")
            bottom.addWidget(self.btn_load)
            self.btn_load.clicked.connect(self._load_clicked)

            # Reload re-reads the current file from disk (edit it externally,
            # then reload). Disabled until a file has actually been loaded.
            self.btn_reload = QPushButton("Reload")
            self.btn_reload.setFont(mono)
            self.btn_reload.setEnabled(False)   # enabled once a file is loaded
            self.btn_reload.setToolTip("Re-read the current file from disk "
                                       "(picks up external edits)")
            bottom.addWidget(self.btn_reload)
            self.btn_reload.clicked.connect(self._reload_clicked)

            bottom.addStretch(1)

            self.btn_step = QPushButton("Step")
            self.btn_run = QPushButton("Run")
            self.btn_step.setToolTip("Execute one instruction (Space)")
            self.btn_run.setToolTip("Auto-run / pause (R)")
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

            # Undo and Reset sit together on the right: Undo (one step/edit back)
            # left of Reset (restart from step 0).
            self.btn_back = QPushButton("Undo")
            self.btn_reset = QPushButton("Reset")
            self.btn_back.setToolTip("Undo the last step or edit (Backspace)")
            self.btn_reset.setToolTip("Restart this program from step 0, "
                                      "restoring the original file (Esc)")
            bottom.addWidget(self.btn_back)
            bottom.addWidget(self.btn_reset)

            for btn in (self.btn_back, self.btn_step, self.btn_run, self.btn_reset):
                btn.setFont(mono)

            self.btn_back.clicked.connect(self.step_back)
            self.btn_step.clicked.connect(self.step)
            self.btn_run.clicked.connect(self._toggle_run)
            self.btn_reset.clicked.connect(self.reset)

            self.timer = QTimer()
            self.timer.timeout.connect(self._run_tick)

        def _setup_shortcuts(self):
            QShortcut(QKeySequence(Qt.Key_Space), self, self.step)
            QShortcut(QKeySequence(Qt.Key_Return), self, self.step)
            QShortcut(QKeySequence(Qt.Key_Backspace), self, self.step_back)
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
            self._has_live_edits = False # any right-click edits since load/reset?
            self._mem_line_addrs = {}
            self._history = History()   # snapshots for step-back (undo)
            self.timer.stop()
            self.btn_step.setEnabled(True)
            self.btn_run.setEnabled(True)
            # nothing has happened yet: nothing to undo, nothing to reset
            self.btn_back.setEnabled(False)
            self.btn_reset.setEnabled(False)
            self.btn_run.setText("Run")
            self.refresh()

        def _mark_dirty(self):
            """A step or edit just happened: enable Undo and Reset."""
            self.btn_back.setEnabled(True)
            self.btn_reset.setEnabled(True)

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

            # Snapshot the pre-execution state (incl. the current overwrite_ok)
            # so this step can be fully undone. Taken before the overwrite prompt
            # so undo also re-arms the prompt; popped again if the user aborts.
            self._push_history()

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
                    self._history.pop()   # this step didn't run: drop its snapshot
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
            self._mark_dirty()
            self.refresh()

        # All machine state that step-back must capture and restore. mem/touched/
        # visible are mutable containers (History copies them); the rest scalars.
        _SNAPSHOT_FIELDS = ("mem", "touched", "visible", "acc", "pc", "stopped",
                            "step_count", "arg_addr", "selected_addr",
                            "changed_cell", "acc_written", "overwrite_ok",
                            "_has_live_edits")

        def _push_history(self):
            """Save the current machine state onto the undo stack."""
            self._history.push({f: getattr(self, f)
                                for f in self._SNAPSHOT_FIELDS})

        def step_back(self):
            """Undo the last executed step, restoring the machine to the state
            just before it ran. No-op if there is nothing to undo."""
            snap = self._history.pop()
            if snap is None:
                return
            self.timer.stop()   # never auto-run while stepping back
            for f in self._SNAPSHOT_FIELDS:
                setattr(self, f, snap[f])
            # stepping back always lands on a runnable (non-halted) state, so
            # re-enable the controls the halt may have disabled.
            self.btn_step.setEnabled(True)
            self.btn_run.setEnabled(True)
            self.btn_run.setText("Run")
            # once the stack is empty we're back at the initial state: nothing
            # left to undo or reset.
            has_history = len(self._history) > 0
            self.btn_back.setEnabled(has_history)
            self.btn_reset.setEnabled(has_history)
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

        def _confirm_discard(self):
            """Ask before throwing away hand edits. Only prompts when the user
            has made live memory edits (right-click) — plain stepping is not
            worth a prompt, since loading/reloading is expected to reset
            execution anyway. Returns True to proceed, False to cancel."""
            if not self._has_live_edits:
                return True
            reply = QMessageBox.question(
                self, "Discard your edits?",
                "You've hand-edited memory. Loading a file will replace it with "
                "the file's contents.\n\nContinue?",
                QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
            return reply == QMessageBox.Yes

        def _load_clicked(self):
            """Pick a .toys (assembly source) or .toyo (byte listing) file and
            load it into the debugger."""
            if not self._confirm_discard():
                return
            path, _ = QFileDialog.getOpenFileName(
                self, "Load program", "",
                "Toy programs (*.toys *.toyo);;All files (*)")
            if path:
                self._load_path(path)

        def _reload_clicked(self):
            """Re-read the current file (CLI arg or last Load) from disk and
            reload it — so the file can be edited externally and picked up
            without re-browsing. Disabled until a file has been loaded, so
            _current_path is always set when this runs."""
            if not self._current_path:
                return
            if not self._confirm_discard():
                return
            self._load_path(self._current_path)

        def _load_path(self, path):
            """Read `path` from disk, assemble/parse it, and point the debugger
            at it (resetting to step 0). Remembers the path so Reload can re-read
            it. Shared by both the Load and Reload buttons."""
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
                    show_error_dialog(f"Assembly failed: {path}",
                                      "\n".join(errors))
                    return
                self.load_program(mem, listing, syms, data_addrs,
                                  code_guard=None, has_source=True)

            self._current_path = path
            self.btn_reload.setEnabled(True)

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
            # right-click opens the live-edit dialog for that cell; left-click
            # just selects it (highlight in both panels).
            if event.button() == Qt.RightButton:
                if addr is not None:      # ignore right-clicks on header/blank
                    self._edit_cell(addr)
                return
            if addr is not None:
                self.selected_addr = addr
                self.refresh()

        def _edit_cell(self, addr):
            """Live-edit the value of the clicked memory cell. Asks only for the
            value (the address comes from the right-clicked row). The value takes
            the same forms as the assembler (decimal, 0x…, 0b…, 8-bit binary) and
            wraps mod 256, which we point out. The edit is undoable (snapshotted
            like a step) and Reset restores the file."""
            a = addr
            text, ok = QInputDialog.getText(
                self, f"Enter new value for address {a}",
                f"Value (decimal, 0x.., 0b.., or 8-bit binary; "
                f"0–255, wraps mod 256):",
                text=str(self.mem[a]))
            if not ok:
                return
            try:
                raw = parse_val(text)
            except Exception:
                QMessageBox.warning(self, "Invalid value",
                                    f"Could not parse '{text}' as a number.")
                return
            value = raw & 0xFF
            # the whole point of an 8-bit machine: make the wraparound explicit
            if raw != value:
                QMessageBox.information(
                    self, "Value wrapped",
                    f"{raw} doesn't fit in 8 bits — stored as "
                    f"{value} ({raw} mod 256).")

            # snapshot so the edit can be undone with Undo, exactly like a step
            self._push_history()
            self.mem[a] = value
            self.touched.add(a)
            self.visible.add(a)
            self.changed_cell = a       # highlight the edited cell (blue)
            self.acc_written = False
            self.selected_addr = a
            self._has_live_edits = True  # a Load/Reload now warns before discard
            self._mark_dirty()
            self.refresh()

        def refresh(self):
            self._refresh_source()
            self._refresh_memory()

        def _line_changed_bytes(self, addr, blist):
            """Widget wrapper around line_changed_bytes() using the live memory."""
            return line_changed_bytes(self.mem, self.mem_original, addr, blist)

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

                text = f"{marker} {orig.rstrip()}" if orig else marker
                colours = []
                if i == sel_line:  colours.append(HL_SELECTED)
                if i in pc_lines:  colours.append(HL_PC)
                if i == arg_line:  colours.append(HL_ARG)

                # Show how the running program has changed memory vs. the source.
                # A line owns byte `addr` (and addr+1 for a two-byte instruction).
                changed = self._line_changed_bytes(addr, blist)
                if changed:
                    if is_data:
                        # data byte edited at runtime: light red + live value.
                        text = f"{marker} {orig.rstrip()}  # current value: {self.mem[addr]}"
                        colours.append(HL_DATA)
                    else:
                        # code overwritten: strong red, and show the raw byte(s)
                        # now in memory instead of the stale assembly mnemonic
                        # (no disassembly — just the bytes, 1 or 2 of them).
                        raw = " ".join(str(self.mem[addr + k])
                                       for k in range(len(blist)))
                        text = f"{marker} {orig.rstrip()}  # now bytes: {raw}"
                        colours.append(HL_CODE)

                lines.append(highlight_row(text, colours))
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
            acc_text = f"  ACC={self.acc}=b{self.acc:08b}"
            if self.stopped and self.step_count > 0:
                # the program has finished: highlight the final result green
                acc_colours = [HL_ARG]
            elif self.acc_written and self.step_count > 0:
                # a running step just wrote ACC: highlight it blue
                acc_colours = [HL_CHANGE]
            else:
                acc_colours = []
            lines.append(highlight_row(acc_text, acc_colours))
            lines.append(_esc(f"  PC={self.pc}"))
            lines.append(_esc(f"  OP{n}={bs}"))
            lines.append(_esc(f"  EXPLAIN: {desc}"))
            lines.append('')

            # unified memory listing. Each row shows the address -> value mapping
            # as "decimal (binary) -> decimal (binary)", columns aligned to the
            # header. The arrow makes the addr→value lookup explicit.
            self._mem_line_addrs = {}
            lines.append(f'<b>memory:</b>')
            # header, aligned to the same column widths as the rows below
            hdr = f"     {'address (binary)':>19}  ->  {'value (binary)':>19}"
            lines.append(_esc(hdr))
            # Blue (change) only lingers while running, never once stopped.
            changed = self.changed_cell if not self.stopped else None
            for a in sorted(self.visible):
                line_idx = len(lines)
                self._mem_line_addrs[line_idx] = a
                marker = ">>" if a == self.pc else "  "
                v = self.mem[a]
                addr_cell = f"{a:3d} ({a:08b})"
                val_cell = f"{v:3d} ({v:08b})"
                text = f"  {marker} {addr_cell:>19}  ->  {val_cell:>19}"
                # A cell can hold several roles at once; collect all active
                # colours (fixed stripe order) instead of letting one win.
                colours = []
                if a == self.selected_addr: colours.append(HL_SELECTED)
                if a in pc_bytes:           colours.append(HL_PC)
                if a == cur_arg:            colours.append(HL_ARG)
                if a == changed:            colours.append(HL_CHANGE)
                lines.append(highlight_row(text, colours))

            html = '<pre style="margin:0;">' + '\n'.join(lines) + '</pre>'
            self.mem_view.setHtml(html)

    import signal
    signal.signal(signal.SIGINT, signal.SIG_DFL)

    app = QApplication.instance() or QApplication(sys.argv)
    win = ToyDebugger(mem, listing, syms, data_addrs, code_guard, has_source,
                      source_path=source_path)
    win.show()
    app.exec()


def show_error_dialog(title, message):
    """Pop up an error dialog (for assembly failures on GUI startup), then
    return. Used by run.py so a bad file shows a window instead of only printing
    to the terminal. Errors are shown INLINE (not hidden behind 'Show Details')
    so a beginner sees them immediately; long messages get a scrollbar."""
    from PySide6.QtWidgets import (QApplication, QDialog, QVBoxLayout,
                                   QLabel, QTextEdit, QDialogButtonBox)
    from PySide6.QtGui import QFont
    app = QApplication.instance() or QApplication(sys.argv)
    dlg = QDialog()
    dlg.setWindowTitle(title)
    dlg.resize(640, 320)
    layout = QVBoxLayout(dlg)
    layout.addWidget(QLabel("The program could not be assembled:"))
    box = QTextEdit()
    box.setReadOnly(True)
    box.setPlainText(message)          # inline + scrollable when long
    box.setFont(QFont("Menlo, Courier New, monospace"))
    layout.addWidget(box)
    buttons = QDialogButtonBox(QDialogButtonBox.Ok)
    buttons.accepted.connect(dlg.accept)
    layout.addWidget(buttons)
    dlg.exec()


def empty_gui():
    """Open the debugger with an empty, zeroed 256-byte memory and no source,
    so `run.py` with no arguments opens a usable window. The user can then load
    an example via the Load button."""
    mem = [0] * 256
    # show every byte in the memory panel; no source, no symbols
    listing = [(a, [mem[a]], "", True) for a in range(256)]
    gui_main(mem, listing, {}, set(range(256)), code_guard=None,
             has_source=False)
