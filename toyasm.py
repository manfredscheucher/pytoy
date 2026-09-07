#!/usr/bin/env python3
"""
Toy CPU Assembler + Simulator
Based on https://github.com/freedosproject/toycpu

Usage:  python toyasm.py prog.toys [options]
"""

import sys, argparse

# ── Instruction set ────────────────────────────────────────────────────────

OPCODES = {
    'stop':0, 'right':1, 'left':2, 'not':15,
    'and':17, 'or':18, 'xor':19,
    'load':20, 'store':21, 'add':22, 'sub':23,
    'goto':24, 'ifzero':25, 'nop':128,
}
OPNAMES = {v: k.upper() for k, v in OPCODES.items()}
FETCH   = 0x10   # bit 4 → instruction has a 2nd address byte

def has_operand(op): return bool(op & FETCH)

# ── Value parser ───────────────────────────────────────────────────────────

def parse_val(s):
    s = s.strip()
    if len(s) == 8 and all(c in '01' for c in s):
        return int(s, 2)
    return int(s, 0)   # 0b…, 0x…, decimal

# ── Source parser ──────────────────────────────────────────────────────────

def parse_source(src):
    rows = []
    for line in src.splitlines():
        orig = line
        if '#' in line:
            line = line[:line.index('#')]
        line = line.strip()
        label = None
        if ':' in line:
            i = line.index(':')
            label = line[:i].strip().lower()
            line  = line[i+1:].strip()
        if not line:
            rows.append((label, None, None, orig)); continue
        tok = line.split()
        rows.append((label, tok[0].lower(), tok[1] if len(tok)>1 else None, orig))
    return rows

# ── Assembler (two-pass) ───────────────────────────────────────────────────

def _is_data_marker(orig):
    """A line whose only content is the comment '# data' marks the start of the
    data region (used by --detect-code-overwrite). Matched leniently."""
    return orig.strip().lower().replace(' ', '') in ('#data', '#data:')

def assemble(src):
    """
    Returns (mem[256], listing, syms, data_addrs, errors, data_start)
    data_addrs: set of addresses that hold data (not code)
    data_start: address of the first data byte, from the '# data' marker, or
                None if the program has no such marker
    """
    parsed = parse_source(src)

    # pass 1 – addresses + symbols, and total size check
    syms, addr = {}, 0
    for label, mn, _, _ in parsed:
        if label is not None:
            syms[label] = addr
        if mn is None: continue
        addr += (2 if (mn in OPCODES and has_operand(OPCODES[mn])) else 1)

    # The Toy CPU has exactly 256 bytes. Report an overflow as a normal error
    # instead of letting pass 2 crash with an IndexError.
    if addr > 256:
        errors = [f"Program is too big: it needs {addr} bytes, but the Toy CPU "
                  f"has only 256. Remove instructions or data."]
        return [0]*256, [], syms, set(), errors, None

    # pass 2 – emit
    mem, listing, errors, data_addrs = [0]*256, [], [], set()
    data_start = None
    addr = 0
    for label, mn, op, orig in parsed:
        if data_start is None and _is_data_marker(orig):
            data_start = addr
        if mn is None:
            listing.append((None, [], orig, False)); continue

        if mn in OPCODES:
            opc = OPCODES[mn]
            if has_operand(opc):
                v = _resolve(op, syms, mn, errors)
                mem[addr] = opc; mem[addr+1] = v & 0xFF
                listing.append((addr, [opc, v & 0xFF], orig, False))
                addr += 2
            else:
                mem[addr] = opc
                listing.append((addr, [opc], orig, False))
                addr += 1
        else:
            # data byte (or label used as address constant)
            if mn in syms:
                v = syms[mn] & 0xFF
            else:
                try:    v = parse_val(mn) & 0xFF
                except: errors.append(f"Bad value/mnemonic: '{mn}'"); v = 0
            mem[addr] = v
            data_addrs.add(addr)
            listing.append((addr, [v], orig, True))
            addr += 1

    return mem, listing, syms, data_addrs, errors, data_start

def _resolve(op, syms, ctx, errors):
    if op is None:
        errors.append(f"'{ctx}' needs an operand"); return 0
    k = op.lower()
    if k in syms: return syms[k]
    try:    return parse_val(op)
    except: errors.append(f"Unknown label '{op}' for '{ctx}'"); return 0

# ── Instruction execution (shared by the CLI and GUI engines) ──────────────

def decode(mem, pc):
    """Decode the instruction at pc. Returns (instr, arg_addr, next_pc).
    arg_addr is None for one-byte instructions."""
    instr = mem[pc]
    if instr & FETCH:
        return instr, mem[(pc + 1) % 256], (pc + 2) % 256
    return instr, None, (pc + 1) % 256

def execute_one(mem, pc, acc):
    """Run one instruction. Mutates mem on STORE. Returns
    (next_pc, acc, arg_addr, stopped). acc is masked to 8 bits.

    The single source of truth for the CPU's semantics — both the CLI
    simulator and the GUI debugger call this so they can never drift apart.
    STORE writes unconditionally here; callers that want the code-overwrite
    guard check is_code_store() *before* calling this and handle the prompt."""
    instr, arg_addr, next_pc = decode(mem, pc)
    stopped = False
    if   instr == 0:  stopped = True
    elif instr == 1:  acc >>= 1
    elif instr == 2:  acc <<= 1
    elif instr == 15: acc = ~acc
    elif instr == 17: acc &= mem[arg_addr]
    elif instr == 18: acc |= mem[arg_addr]
    elif instr == 19: acc ^= mem[arg_addr]
    elif instr == 20: acc = mem[arg_addr]
    elif instr == 21: mem[arg_addr] = acc
    elif instr == 22: acc += mem[arg_addr]
    elif instr == 23: acc -= mem[arg_addr]
    elif instr == 24: next_pc = arg_addr
    elif instr == 25:
        if acc == 0: next_pc = arg_addr
    return next_pc, acc & 0xFF, arg_addr, stopped

def is_code_store(mem, pc, code_guard):
    """True if the instruction at pc is a STORE writing into the code region
    (below code_guard). Used to trigger the overwrite warning before the
    store actually happens. Always False when code_guard is None."""
    if code_guard is None:
        return False
    instr, arg_addr, _ = decode(mem, pc)
    return instr == 21 and arg_addr is not None and arg_addr < code_guard


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

    # show initial state before first instruction
    if verbose:
        # peek at first instruction for description
        _instr = mem[pc]
        _arg = mem[(pc+1) % 256] if _instr & FETCH else None
        _desc, _bs = _describe(_instr, _arg, sym, mem)
        print(vertical_mem(pc, acc, step_num=step_num, cmd_desc=_desc, cmd_bytes=_bs, cur_arg=_arg, dump=show_mem))
        print()
        if step:
            try: input("[Enter] > ")
            except EOFError: pass

    while True:
        instr, arg_addr, _ = decode(mem, pc)

        desc, bytes_str = _describe(instr, arg_addr, sym, mem)

        if not verbose:
            line = f"PC={pc:3d}  ACC={acc:3d}  {desc}"

        if step and not verbose:
            print(f"\n{line}")
            if show_mem: print(mem_dump())
            try: input("       [Enter] > ")
            except EOFError: pass

        if instr == 0:  # STOP
            break

        # guard: ask before a STORE overwrites code
        if is_code_store(mem, pc, code_guard):
            msg = (f"store at PC={pc} writes {acc} into address {arg_addr}, "
                   f"which is in the code region (below the data start at "
                   f"{code_guard}) — this overwrites program code.")
            if not _warn_continue(msg):
                print("Aborted.", file=sys.stderr)
                return acc

        next_pc, acc, arg_addr, _ = execute_one(mem, pc, acc)
        if instr == 21:  # STORE wrote memory
            touched.add(arg_addr)

        step_num += 1

        # add runtime-written addresses to visible set
        if verbose:
            visible.update(touched)

        if verbose:
            # describe the next instruction at next_pc
            _ninstr = mem[next_pc]
            _narg = mem[(next_pc+1) % 256] if _ninstr & FETCH else None
            _ndesc, _nbs = _describe(_ninstr, _narg, sym, mem)
            print(vertical_mem(next_pc, acc, step_num=step_num, cmd_desc=_ndesc, cmd_bytes=_nbs, cur_arg=_narg, dump=show_mem))
            print()
            if step:
                try: input("[Enter] > ")
                except EOFError: pass
        elif not step:
            print(line)
            if show_mem: print(mem_dump())

        pc = next_pc

    # STOP
    if verbose:
        print(vertical_mem(pc, acc, step_num=step_num, cmd_bytes="b00000000", stopped=True, dump=show_mem))
    else:
        print(f"\nPC={pc:3d}  ACC={acc:3d}  STOP")
        if show_mem: print(mem_dump())
    return acc

# opcode -> (mnemonic, operand kind): None = no operand, 'a' = address only,
# 'av' = address plus the value stored there.
_INSTR = {
    0: ("STOP", None), 1: ("RIGHT", None), 2: ("LEFT", None),
    15: ("NOT", None), 128: ("NOP", None),
    17: ("AND", 'av'), 18: ("OR", 'av'), 19: ("XOR", 'av'),
    20: ("LOAD", 'av'), 22: ("ADD", 'av'), 23: ("SUB", 'av'),
    21: ("STORE", 'a'), 24: ("GOTO", 'a'), 25: ("IFZERO", 'a'),
}

def _describe(instr, arg_addr, sym, mem):
    bs = f"b{instr:08b}" + (f" b{arg_addr:08b}" if arg_addr is not None else "")
    name, kind = _INSTR.get(instr, (f"NOP (opcode={instr})", None))
    if kind is None:
        return name, bs
    tail = f"(addr:{arg_addr}, val:{mem[arg_addr]})" if kind == 'av' else f"(addr:{arg_addr})"
    return f"{name:<5} {sym(arg_addr)} {tail}", bs

# ── Assembly listing (interactive) ────────────────────────────────────────

def show_assembly(listing, syms, mem):
    """Walk through each source line and show original + compiled bytes."""
    rsym = {v: k for k, v in syms.items()}
    def sym(a): return rsym.get(a, str(a))

    print("assembly:\n")
    for addr, blist, orig, is_data in listing:
        if addr is None:
            # comment-only or blank line
            stripped = orig.rstrip()
            if stripped:
                print(f"  {stripped}")
            continue

        # source line
        src_line = orig.rstrip()
        print(f"  {src_line}")

        # indent -> line to match source indentation (min 6 to stay readable)
        indent = max(6, len(src_line) - len(src_line.lstrip()) + 2)  # +2 for outer indent

        # compiled translation
        if is_data:
            label = rsym.get(addr, '')
            lbl = f"{label} = " if label else ""
            v = blist[0]
            print(f"{' '*indent}-> {lbl}{v} ({v:08b}) at addr {addr}")
        else:
            opc = blist[0]
            desc, _ = _describe(opc,
                                blist[1] if len(blist) > 1 else None,
                                sym, mem)
            bs = "  ".join(f"{b:08b}" for b in blist)
            print(f"{' '*indent}-> [{bs}] at addr {addr}  =  {desc}")

    # symbols table
    print(f"\nsymbols:")
    for name, a in sorted(syms.items(), key=lambda x: x[1]):
        print(f"  {name:<12} = {a:3d} ({a:08b})")
    print()

# ── Export ─────────────────────────────────────────────────────────────────

def export(listing, syms, mem, path):
    """Write compiled listing to file + print interactive assembly walk-through."""
    rsym = {v: k for k, v in syms.items()}
    out  = ["# Toy CPU – compiled listing", "#",
            f"# {'ADDR':>4}  {'BYTES':<22}  SOURCE", "# " + "─"*56]
    for addr, blist, orig, is_data in listing:
        if addr is None:
            out.append(f"#        {'':22}  {orig.rstrip()}")
        else:
            bs  = "  ".join(f"{b:08b}" for b in blist)
            out.append(f"  {addr:4d}   {bs:<22}  {orig.rstrip()}")
    out += ["", "# SYMBOLS"]
    for name, addr in sorted(syms.items(), key=lambda x: x[1]):
        out.append(f"#   {name:<15} = {addr:3d}  ({addr:08b})")
    with open(path, 'w') as f:
        f.write("\n".join(out) + "\n")
    print(f"exported → {path}\n")

# ── GUI Debugger ──────────────────────────────────────────────────────────

def gui_main(mem, listing, syms, data_addrs, code_guard=None):
    """Launch PySide6 graphical debugger."""
    from PySide6.QtWidgets import (QApplication, QMainWindow, QWidget,
                                   QHBoxLayout, QVBoxLayout, QTextEdit,
                                   QPushButton, QSplitter, QMessageBox)
    from PySide6.QtCore import Qt, QTimer
    from PySide6.QtGui import QFont, QTextCursor, QShortcut, QKeySequence

    class ToyDebugger(QMainWindow):
        def __init__(self, mem_original, listing, syms, data_addrs, code_guard):
            super().__init__()
            self.setWindowTitle("toyasm")
            self.resize(1000, 700)

            self.mem_original = list(mem_original)
            self.listing = listing
            self.syms = syms
            self.data_addrs = set(data_addrs)
            self.code_guard = code_guard   # data-region start, or None
            self.rsym = {v: k for k, v in syms.items()}

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

            self._build_ui()
            self._setup_shortcuts()
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

            bottom.addStretch(1)

            self.btn_step = QPushButton("Step")
            self.btn_run = QPushButton("Run")
            self.btn_reset = QPushButton("Reset")
            for btn in (self.btn_step, self.btn_run, self.btn_reset):
                btn.setFont(mono)
                bottom.addWidget(btn)

            self.btn_step.clicked.connect(self.step)
            self.btn_run.clicked.connect(self.run)
            self.btn_reset.clicked.connect(self.reset)

            self.timer = QTimer()
            self.timer.timeout.connect(self._run_tick)

        def _setup_shortcuts(self):
            QShortcut(QKeySequence(Qt.Key_Space), self, self.step)
            QShortcut(QKeySequence(Qt.Key_Return), self, self.step)
            QShortcut(QKeySequence(Qt.Key_R), self, self.run)
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
            self._mem_line_addrs = {}
            self.timer.stop()
            self.btn_step.setEnabled(True)
            self.btn_run.setEnabled(True)
            self.refresh()

        def _sym(self, a):
            return self.rsym.get(a, str(a))

        def _halt(self):
            """Stop execution: freeze the machine and disable Step/Run."""
            self.stopped = True
            self.timer.stop()
            self.btn_step.setEnabled(False)
            self.btn_run.setEnabled(False)
            self.refresh()

        def step(self):
            if self.stopped:
                return

            instr, arg_addr, _ = decode(self.mem, self.pc)

            if instr == 0:  # STOP
                self._halt()
                return

            # guard: ask before a STORE overwrites code
            if is_code_store(self.mem, self.pc, self.code_guard):
                self.timer.stop()   # pause auto-run while asking
                msg = (f"STORE at PC={self.pc} writes {self.acc} into "
                       f"address {arg_addr}, which is in the code region "
                       f"(below the data start at {self.code_guard}).\n\n"
                       f"This overwrites program code. Continue anyway?")
                reply = QMessageBox.warning(
                    self, "Code overwrite detected", msg,
                    QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
                if reply != QMessageBox.Yes:
                    self._halt()
                    return

            self.pc, self.acc, arg_addr, _ = execute_one(self.mem, self.pc, self.acc)
            if instr == 21:  # STORE wrote memory
                self.touched.add(arg_addr)
            self.step_count += 1
            self.selected_addr = None
            self.arg_addr = arg_addr
            self.visible.update(self.touched)
            self.refresh()

        def run(self):
            if self.stopped:
                return
            self.timer.start(100)

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
            instr = self.mem[self.pc]
            cur_arg = self.mem[(self.pc + 1) % 256] if instr & FETCH else None
            arg_line = self.addr_to_line.get(cur_arg) if cur_arg is not None else None
            for i, (addr, blist, orig, is_data) in enumerate(self.listing):
                if i == pc_line:
                    marker = ">>"
                elif i == arg_line:
                    marker = "**"
                else:
                    marker = "  "
                text = orig.rstrip() if orig else ""
                escaped = text.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')
                if i == sel_line:
                    lines.append(f'<span style="background-color:#ffcc66;">{marker} {escaped}</span>')
                elif i == pc_line:
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
            def _esc(s):
                return s.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')

            lines = []

            # status info on top
            instr = self.mem[self.pc]
            arg = self.mem[(self.pc + 1) % 256] if instr & FETCH else None
            desc, bs = _describe(instr, arg, self._sym, self.mem)
            n = len(bs.split())
            if self.stopped:
                lines.append(f'<b>Stopped after {self.step_count} steps.</b>')
            else:
                lines.append(f'<b>Step #{self.step_count}:</b>')
            lines.append(_esc(f"  ACC={self.acc}=b{self.acc:08b}"))
            lines.append(_esc(f"  PC={self.pc}"))
            lines.append(_esc(f"  OP{n}={bs}"))
            lines.append(_esc(f"  EXPLAIN: {desc}"))
            lines.append('')

            # determine which address the current instruction references
            cur_arg = None
            if instr & FETCH:
                cur_arg = self.mem[(self.pc + 1) % 256]

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
                if a == self.selected_addr:
                    lines.append(f'<span style="background-color:#ffcc66;">{escaped}</span>')
                elif a == self.pc:
                    lines.append(f'<span style="background-color:#ffffaa;">{escaped}</span>')
                elif a == cur_arg:
                    lines.append(f'<span style="background-color:#aaffaa;">{escaped}</span>')
                else:
                    lines.append(escaped)

            html = '<pre style="margin:0;">' + '\n'.join(lines) + '</pre>'
            self.mem_view.setHtml(html)

    import signal
    signal.signal(signal.SIGINT, signal.SIG_DFL)

    app = QApplication.instance() or QApplication(sys.argv)
    win = ToyDebugger(mem, listing, syms, data_addrs, code_guard)
    win.show()
    app.exec()


# ── CLI ────────────────────────────────────────────────────────────────────

def main():
    ap = argparse.ArgumentParser(description="Toy CPU Assembler + Simulator")
    ap.add_argument('file')
    ap.add_argument('-r', '--run',     action='store_true', help='run all steps without pausing')
    ap.add_argument('-q', '--quiet',   action='store_true', help='compact one-line-per-step output')
    ap.add_argument('-x', '--export',  action='store_true', help='export compiled listing to .toyo')
    ap.add_argument('-c', '--cli',     action='store_true', help='run in the terminal instead of the graphical interface')
    ap.add_argument('-d', '--detect-code-overwrite', action='store_true',
                    help='warn when a store writes into the code region (below the "# data" marker)')
    args = ap.parse_args()

    try:    src = open(args.file).read()
    except: sys.exit(f"File not found: {args.file}")

    mem, listing, syms, data_addrs, errors, data_start = assemble(src)
    if errors:
        for e in errors: print(f"ERROR: {e}", file=sys.stderr)
        sys.exit(1)

    guard = data_start if args.detect_code_overwrite else None
    if args.detect_code_overwrite and data_start is None:
        print("WARNING: --detect-code-overwrite is on but the program has no "
              "'# data' marker; code-overwrite detection is disabled.",
              file=sys.stderr)

    # graphical interface is the default; --cli opts into terminal mode
    if not args.cli:
        gui_main(mem, listing, syms, data_addrs, guard)
        return

    if args.export:
        print("─"*62)
        show_assembly(listing, syms, mem)
        export(listing, syms, mem, args.file.rsplit('.', 1)[0] + '.toyo')

    # build addr→original source map for verbose mode
    addr_orig = {}
    if not args.quiet:
        for addr, blist, orig, is_data in listing:
            if addr is None:
                continue
            addr_orig[addr] = orig.rstrip()
            if len(blist) == 2:
                addr_orig[addr + 1] = ''

    print("─"*62)
    if args.export:
        print("execution:\n")
    acc = simulate(mem, syms, data_addrs, step=not args.run, show_mem=not args.quiet,
                   verbose=not args.quiet, addr_orig=addr_orig, code_guard=guard)
    print("─"*62)
    print(f"Result:  ACC = {acc}  ({acc:08b}  0x{acc:02x}  dec {acc})")

if __name__ == '__main__':
    main()
