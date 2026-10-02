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


def run(src, cap=2_000_000):
    # Save/restore is automatic now (only for recursive callers), so there is a
    # single compile path — the old optimize on/off comparison no longer applies.
    asm = compile_source(src, 't')
    mem, listing, syms, data_addrs, errors, data_start = toyasm.assemble(asm)
    hard = [e for e in errors if 'too big' in e or 'Bad value' in e]
    if hard:
        raise RuntimeError(f"assemble errors: {hard}")
    acc, steps = _run_capped(mem, syms, data_addrs, cap)
    return acc, steps, asm


def check(name, src, expected, cap=2_000_000):
    try:
        acc, steps, _ = run(src, cap)
    except Exception as e:
        print(f"[FAIL] {name}: expected={expected} err={type(e).__name__}: {e}")
        return False, None
    ok = acc == expected
    print(f"[{'PASS' if ok else 'FAIL'}] {name}: expected={expected} "
          f"got={acc} steps={steps}")
    return ok, acc


if __name__ == '__main__':
    pass
