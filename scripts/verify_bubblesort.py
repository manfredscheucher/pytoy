#!/usr/bin/env python3
"""
Durable verification harness for examples/bubblesort.toys.

Assembles the program, runs the real fetch/execute loop (toyasm.execute_one)
to STOP, then reads the sorted array straight out of the simulator's memory
image and asserts it equals [1, 1, 2, 3, 3, 4, 5, 5, 6, 9].

Run:  python3 scripts/verify_bubblesort.py
Exit code 0 on success, 1 on failure.
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)

import toyasm
import toycpu

TOYS = os.path.join(ROOT, "examples", "bubblesort.toys")
EXPECTED = [1, 1, 2, 3, 3, 4, 5, 5, 6, 9]
N = len(EXPECTED)
MAX_STEPS = 1_000_000  # safety cap; the program halts well before this


def run(mem_in):
    """Run the machine to STOP on a copy of mem. Returns (final_mem, acc, steps)."""
    mem = list(mem_in)
    acc, pc, steps = 0, 0, 0
    while steps < MAX_STEPS:
        instr = mem[pc]
        if instr == 0:  # STOP
            break
        pc, acc, _arg, _stopped = toycpu.execute_one(mem, pc, acc)
        steps += 1
    else:
        raise RuntimeError(f"did not halt within {MAX_STEPS} steps")
    return mem, acc, steps


def main():
    src = open(TOYS).read()
    mem, listing, syms, data_addrs, errors, data_start = toyasm.assemble(src)
    if errors:
        print("ASSEMBLE ERRORS:")
        for e in errors:
            print("  " + e)
        return 1

    # program byte size = highest used address + 1 (assemble packs from addr 0)
    used = max(syms.values())  # last label addr
    # array end:
    arr_addr = syms["arr"]
    size = arr_addr + N  # arr is the final block, so this is the total footprint
    fits = size <= 256

    final_mem, acc, steps = run(mem)
    arr = [final_mem[arr_addr + i] for i in range(N)]

    print(f"file          : {TOYS}")
    print(f"array address : {arr_addr}")
    print(f"byte size     : {size}  (fits in 256: {fits})")
    print(f"steps to halt : {steps}")
    print(f"ACC at STOP   : {acc}  (arr[0], expected 1)")
    print(f"initial array : [3, 1, 4, 1, 5, 9, 2, 6, 5, 3]")
    print(f"sorted array  : {arr}")
    print(f"expected      : {EXPECTED}")

    ok = arr == EXPECTED and acc == EXPECTED[0] and fits
    print("RESULT        : " + ("PASS" if ok else "FAIL"))
    if arr != EXPECTED:
        print("  !! array does not match expected sorted order")
    if acc != EXPECTED[0]:
        print(f"  !! ACC={acc} but expected arr[0]={EXPECTED[0]}")
    if not fits:
        print(f"  !! program is {size} bytes, exceeds 256")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
