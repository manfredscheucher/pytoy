#!/usr/bin/env python3
"""
Toy CPU ISA core: the shared instruction set, decoder, and executor.
Based on https://github.com/freedosproject/toycpu

Both the assembler (toyasm) and the simulator/GUI (toysim) import this so the
CPU's semantics can never drift apart.
"""

# ── Instruction set ────────────────────────────────────────────────────────

OPCODES = {
    'stop':0, 'right':1, 'left':2, 'not':15,
    'and':17, 'or':18, 'xor':19,
    'load':20, 'store':21, 'add':22, 'sub':23,
    'goto':24, 'ifzero':25, 'nop':128,
}
FETCH   = 0x10   # bit 4 → instruction has a 2nd address byte

def has_operand(op): return bool(op & FETCH)

# ── Value parser ───────────────────────────────────────────────────────────

def parse_val(s):
    s = s.strip()
    if len(s) == 8 and all(c in '01' for c in s):
        return int(s, 2)
    return int(s, 0)   # 0b…, 0x…, decimal

# ── Instruction execution (shared by the CLI and GUI engines) ──────────────

def decode(mem, pc):
    """Decode the instruction at pc. Returns (instr, arg_addr, next_pc).
    arg_addr is None for one-byte instructions."""
    instr = mem[pc]
    if has_operand(instr):
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
    # opcode 128 (NOP) and any unrecognized opcode: do nothing, just advance
    return next_pc, acc & 0xFF, arg_addr, stopped

# Opcodes whose execute_one branch assigns to `acc` (RIGHT/LEFT/NOT/AND/OR/XOR/
# LOAD/ADD/SUB). STORE/GOTO/IFZERO/STOP/NOP leave it alone. Kept next to
# execute_one so the two can't drift; the GUI uses it to highlight ACC writes.
# When you add or change an opcode above, update this set too.
WRITES_ACC = frozenset({1, 2, 15, 17, 18, 19, 20, 22, 23})

# Every known opcode must be classified as an ACC-writer or not; guard against
# WRITES_ACC drifting from the instruction set (mirrors the OPCODES/_INSTR assert
# below). NOP (128) is a known opcode that does not write ACC.
assert WRITES_ACC <= set(OPCODES.values()), "WRITES_ACC has an unknown opcode"

def is_code_store(mem, pc, code_guard):
    """True if the instruction at pc is a STORE writing into the code region
    (below code_guard). Used to trigger the overwrite warning before the
    store actually happens. Always False when code_guard is None."""
    if code_guard is None:
        return False
    instr, arg_addr, _ = decode(mem, pc)
    return instr == 21 and arg_addr is not None and arg_addr < code_guard

def _overwrite_msg(pc, acc, arg_addr, code_guard):
    """The shared core of the code-overwrite warning (CLI and GUI). Callers add
    their own trailing prompt."""
    return (f"STORE at PC={pc} writes {acc} into address {arg_addr}, which is "
            f"in the code region (below the data start at {code_guard}) — this "
            f"overwrites program code.")

# opcode -> (mnemonic, operand kind): None = no operand, 'a' = address only,
# 'av' = address plus the value stored there.
_INSTR = {
    0: ("STOP", None), 1: ("RIGHT", None), 2: ("LEFT", None),
    15: ("NOT", None), 128: ("NOP", None),
    17: ("AND", 'av'), 18: ("OR", 'av'), 19: ("XOR", 'av'),
    20: ("LOAD", 'av'), 22: ("ADD", 'av'), 23: ("SUB", 'av'),
    21: ("STORE", 'a'), 24: ("GOTO", 'a'), 25: ("IFZERO", 'a'),
}

# OPCODES (name->number) and _INSTR (number->mnemonic) both list the opcodes;
# guard against the two drifting apart.
assert set(OPCODES.values()) == set(_INSTR), "OPCODES and _INSTR disagree"

def _esc(s):
    """Escape the three HTML-significant characters for the GUI's rich text."""
    return s.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')

def _describe(instr, arg_addr, sym, mem):
    bs = f"b{instr:08b}" + (f" b{arg_addr:08b}" if arg_addr is not None else "")
    # unknown opcodes behave like NOP but are shown as unknown, not "NOP"
    name, kind = _INSTR.get(instr, (f"?? (opcode={instr}, treated as NOP)", None))
    if kind is None:
        return name, bs
    tail = f"(addr:{arg_addr}, val:{mem[arg_addr]})" if kind == 'av' else f"(addr:{arg_addr})"
    return f"{name:<5} {sym(arg_addr)} {tail}", bs
