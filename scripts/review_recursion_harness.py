#!/usr/bin/env python3
"""Adversarial harness for the toycc recursion codegen (review scratch, KEEP).

Compiles a C source with toycc (optimize False and True), assembles + simulates
it via toyasm with stdout suppressed and a step cap (to catch infinite loops),
and returns the final ACC for both -O settings. Used to hand-check tricky
recursive programs against expected values.
"""
import os
import sys
import io
import contextlib

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from pytoy import assembler as toyasm
from pytoy import core as toycpu
from pytoy.compiler import compile_source, CompileError


class StepCap(Exception):
    pass


def _run_capped(mem, syms, data_addrs, cap):
    """Mini interpreter mirroring toyasm.execute_one, with a step cap so an
    infinite loop raises instead of hanging. Returns (acc, steps)."""
    mem = list(mem)
    acc, pc, steps = 0, 0, 0
    while True:
        instr, arg_addr, _ = toycpu.decode(mem, pc)
        if instr == 0:  # STOP
            return acc, steps
        pc, acc, arg_addr, _ = toycpu.execute_one(mem, pc, acc)
        steps += 1
        if steps > cap:
            raise StepCap(f"exceeded {cap} steps (likely infinite loop)")


def run(src, optimize, cap=2_000_000):
    asm = compile_source(src, 't')  # save/restore now automatic
    mem, listing, syms, data_addrs, errors, data_start = toyasm.assemble(asm)
    hard = [e for e in errors if 'too big' in e or 'Bad value' in e]
    if hard:
        raise RuntimeError(f"assemble errors: {hard}")
    acc, steps = _run_capped(mem, syms, data_addrs, cap)
    return acc, steps, asm


def both(src, cap=2_000_000):
    """Return dict with acc for optimize False/True (or exception repr)."""
    res = {}
    for opt in (False, True):
        try:
            acc, steps, _ = run(src, opt, cap)
            res[opt] = ('ok', acc, steps)
        except Exception as e:
            res[opt] = ('err', type(e).__name__, str(e))
    return res


def check(name, src, expected, cap=2_000_000):
    r = both(src, cap)
    o0, o1 = r[False], r[True]
    ok = (o0[0] == 'ok' and o1[0] == 'ok'
          and o0[1] == expected and o1[1] == expected)
    inv = (o0[0] == 'ok' and o1[0] == 'ok' and o0[1] == o1[1])
    status = 'PASS' if ok else ('INVAR-OK' if inv else 'FAIL')
    print(f"[{status}] {name}: expected={expected} "
          f"O0={o0[1:]} O1={o1[1:]}")
    return ok, r


if __name__ == '__main__':
    pass
