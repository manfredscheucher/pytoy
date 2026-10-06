#!/usr/bin/env python3
"""Headless check of the output-only I/O examples in examples/asm/04-io/.

Assembles each program, runs it to STOP on the shared CPU core, and prints the
final values of the memory-mapped I/O region (io0..io14 = 240..254, ready = 255)
so we can verify the STOREs land in the right cells and nothing spills past io14
into the ready register (255).
"""
import os
import sys

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO_ROOT)

from pytoy.assembler import assemble            # noqa: E402
from scripts.gen_golden import run_program      # noqa: E402

IO_DIR = os.path.join(REPO_ROOT, "examples", "asm", "04-io")


def check(name):
    path = os.path.join(IO_DIR, name + ".toys")
    with open(path) as f:
        src = f.read()
    mem, listing, syms, data_addrs, errors, data_start = assemble(src)
    if errors:
        print(f"{name}: ASSEMBLE ERRORS: {list(errors)}")
        return
    acc, steps, touched, final_mem, hit_cap = run_program(mem, data_addrs)
    io = [final_mem[240 + i] & 0xFF for i in range(15)]
    ready = final_mem[255] & 0xFF
    print(f"=== {name} (steps={steps} hit_cap={hit_cap} acc={acc}) ===")
    print(f"  io0..io14 (240..254): {io}")
    print(f"  ready (255):          {ready}")


if __name__ == "__main__":
    for n in ("numbers", "hello_world", "fibonacci", "countdown"):
        check(n)
