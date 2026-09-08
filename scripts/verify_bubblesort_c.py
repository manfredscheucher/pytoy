#!/usr/bin/env python3
"""
Durable verification harness for compiler/examples/bubblesort.toyc.

Compiles the C bubble sort with toycc, assembles it, runs the real
fetch/execute loop (toyasm.execute_one) to STOP, then reads the sorted array
straight out of the simulator's memory image and asserts it equals
[1, 1, 2, 3, 3, 4, 5, 5, 6, 9].

Run:  python3 scripts/verify_bubblesort_c.py
Exit code 0 on success, 1 on failure.
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "compiler"))

import toyasm
from toycc import compile_source

TOYC = os.path.join(ROOT, "compiler", "examples", "bubblesort.toyc")
EXPECTED = [1, 1, 2, 3, 3, 4, 5, 5, 6, 9]
N = len(EXPECTED)
MAX_STEPS = 1_000_000  # safety cap; the program halts well before this


def run(mem_in):
    """Run the machine to STOP on a copy of mem. Returns (final_mem, acc, steps)."""
    mem = list(mem_in)
    acc, pc, steps = 0, 0, 0
    while steps < MAX_STEPS:
        if mem[pc] == 0:  # STOP
            break
        pc, acc, _arg, _stopped = toyasm.execute_one(mem, pc, acc)
        steps += 1
    else:
        raise RuntimeError(f"did not halt within {MAX_STEPS} steps")
    return mem, acc, steps


def main():
    src = open(TOYC).read()
    asm = compile_source(src, "bubblesort.toyc")
    mem, listing, syms, data_addrs, errors, _ds = toyasm.assemble(asm)
    if errors:
        print("ASSEMBLE ERRORS:")
        for e in errors:
            print("  " + e)
        return 1

    size = max(a for a, *_ in listing if a is not None) + 1
    fits = size <= 256
    arr_addr = syms["arr_a"]

    final_mem, acc, steps = run(mem)
    arr = [final_mem[arr_addr + i] for i in range(N)]

    print(f"file          : {TOYC}")
    print(f"array address : {arr_addr}")
    print(f"byte size     : {size}  (fits in 256: {fits})")
    print(f"steps to halt : {steps}")
    print(f"ACC at STOP   : {acc}  (arr[0], expected 1)")
    print(f"initial array : [3, 1, 4, 1, 5, 9, 2, 6, 5, 3]")
    print(f"sorted array  : {arr}")
    print(f"expected      : {EXPECTED}")

    ok = arr == EXPECTED and acc == EXPECTED[0] and fits
    print("RESULT        : " + ("PASS" if ok else "FAIL"))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
