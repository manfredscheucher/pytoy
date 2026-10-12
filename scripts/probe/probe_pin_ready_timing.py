#!/usr/bin/env python3
"""
Diagnose the pin_check .toyc-vs-.toys divergence.

Repro: user types '1','3','3','7' into io0..io3 and sets ready=4 BEFORE running.
The hand-written .toys busy-polls `ready` WITHOUT clearing it, so it sees ready=4
immediately and succeeds. The compiled .toyc read() CLEARS ready to 0 first, then
busy-polls — so after the clear, ready is 0 forever (nobody sets it again during
a single headless run), and the program spins forever (or, with a step cap, never
copies io0..io3 into data[], so the compare fails).

This script seeds memory exactly as the GUI would (io cells + ready pre-set),
runs each program headless, and reports the result.
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.abspath(os.path.join(HERE, "..", ".."))
sys.path.insert(0, REPO)

from pytoy.assembler import assemble
from pytoy.compiler import compile_source
from pytoy.core import execute_one, is_code_store  # noqa: F401 (import check)
from pytoy.format import IO_BASE, IO_READY


def run_headless(mem, max_steps=100000):
    """Run from pc=0 until STOP or the step cap. Returns (acc, steps, stopped)."""
    mem = list(mem)
    pc, acc = 0, 0
    for step in range(max_steps):
        pc, acc, _arg, stopped = execute_one(mem, pc, acc)
        if stopped:
            return acc, step + 1, True, mem
    return acc, max_steps, False, mem


def seed_input(mem):
    """Seed memory as the GUI would when the user pre-types the PIN + ready."""
    mem = list(mem)
    mem[IO_BASE + 0] = ord('1')   # 49
    mem[IO_BASE + 1] = ord('3')   # 51
    mem[IO_BASE + 2] = ord('3')   # 51
    mem[IO_BASE + 3] = ord('7')   # 55
    mem[IO_READY] = 4             # user submits with ready=4
    return mem


def assemble_file(path):
    with open(path) as f:
        src = f.read()
    mem, listing, syms, data_addrs, errors, data_start = assemble(src)
    assert not errors, errors
    return mem


def compile_and_assemble(path):
    with open(path) as f:
        csrc = f.read()
    asm = compile_source(csrc, os.path.basename(path))
    mem, listing, syms, data_addrs, errors, data_start = assemble(asm)
    assert not errors, errors
    return mem, asm


def main():
    asm_toys = os.path.join(REPO, "examples/asm/04-io/pin_check.toys")
    c_toyc = os.path.join(REPO, "examples/c/04-io/pin_check.toyc")

    print("=== .toys (hand-written, does NOT clear ready) ===")
    mem = seed_input(assemble_file(asm_toys))
    acc, steps, stopped, out = run_headless(mem)
    print(f"  stopped={stopped} steps={steps} acc={acc} "
          f"(42=success, 0=fail)")
    print(f"  io0..3 after = {[out[IO_BASE+i] for i in range(4)]} "
          f"({''.join(chr(out[IO_BASE+i]) for i in range(4))!r})")

    print("\n=== .toyc (compiled, read() CLEARS ready, then polls) ===")
    mem_c, asm = compile_and_assemble(c_toyc)
    mem_c = seed_input(mem_c)
    acc, steps, stopped, out = run_headless(mem_c)
    print(f"  stopped={stopped} steps={steps} acc={acc} "
          f"(42=success, 0=fail)")
    print(f"  ready after = {out[IO_READY]}")
    print(f"  io0..3 after = {[out[IO_BASE+i] for i in range(4)]} "
          f"({''.join(chr(out[IO_BASE+i]) for i in range(4))!r})")

    print("\n=== control: .toyc WITHOUT the ready-clear (hypothetical fix) ===")
    # Rebuild the .toyc image but neutralise the `store ready` (255) that clears
    # ready. We find the first `load 0; store ready` in the compiled asm's image
    # by patching the mem: replace the STORE-to-255 of the read() clear with NOPs.
    mem_c2, _ = compile_and_assemble(c_toyc)
    # locate the clear: scan for opcode 20 (load) of a byte holding 0 followed by
    # opcode 21 (store) to address 255. Simplest: find a `21,255` (store ready).
    for i in range(254):
        if mem_c2[i] == 21 and mem_c2[i + 1] == IO_READY:
            # was this preceded by a load-of-const-0? neutralise just this store
            mem_c2[i] = 128      # nop
            mem_c2[i + 1] = 128  # nop (the operand byte becomes a standalone nop)
            print(f"  patched store-ready at addr {i} -> nop,nop")
            break
    mem_c2 = seed_input(mem_c2)
    acc, steps, stopped, out = run_headless(mem_c2)
    print(f"  stopped={stopped} steps={steps} acc={acc}")
    print(f"  io0..3 after = {[out[IO_BASE+i] for i in range(4)]} "
          f"({''.join(chr(out[IO_BASE+i]) for i in range(4))!r})")


if __name__ == "__main__":
    main()
