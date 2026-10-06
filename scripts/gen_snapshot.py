#!/usr/bin/env python3
"""
Generate a "snapshot" behaviour table for pytoy's example assembly programs.

For every examples/asm/**/*.toys this assembles the source in-process (same
pytoy.assembler.assemble the CLI uses), runs it on the same CPU core
(pytoy.core.execute_one / decode — the single source of truth), and records the
final ACC, the number of steps executed, whether a max-step cap was hit, and the
final values of every data/touched memory address.

The result is written as deterministic, sorted JSON to
tests/snapshot/asm_snapshot.json so it diffs cleanly and can be committed. A later
Kotlin port (ktoy) can be checked against the exact same numbers.

Run it as:
    python3 scripts/gen_snapshot.py
    .venv/bin/python scripts/gen_snapshot.py

stdlib + pytoy only, no PySide6.
"""

import os
import sys
import glob
import json

# Make the pytoy package importable regardless of cwd (mirrors run.py).
REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO_ROOT)

from pytoy.assembler import assemble  # noqa: E402
from pytoy.core import decode, execute_one  # noqa: E402

ASM_DIR = os.path.join(REPO_ROOT, "examples", "asm")
OUT_PATH = os.path.join(REPO_ROOT, "tests", "snapshot", "asm_snapshot.json")

# Guard against non-terminating programs. These examples are tiny (256-byte
# programs), so anything past this cap is a runaway loop, not real work.
MAX_STEPS = 100_000


def run_program(mem_in, data_addrs, max_steps=MAX_STEPS):
    """Run a 256-byte program to STOP (or the step cap) on the shared CPU core.

    A thin re-implementation of the run loop in simulator.simulate() that also
    returns the step count and final memory. It uses core.decode / execute_one
    directly, so the semantics are identical. STORE writes (opcode 21) mark their
    target address as touched, matching simulate().

    Memory-mapped I/O is a GUI-only feature, so this headless runner treats
    240..255 as ordinary memory. Input-driven I/O examples (which poll for a
    value that never arrives here) are excluded from the snapshot table instead.

    Returns (final_acc, steps, touched_addrs, final_mem, hit_cap).
    """
    mem = list(mem_in)
    acc, pc, steps = 0, 0, 0
    touched = set(data_addrs)
    hit_cap = False

    while True:
        instr, arg_addr, _ = decode(mem, pc)
        if instr == 0:  # STOP
            break
        if steps >= max_steps:
            hit_cap = True
            break
        next_pc, acc, arg_addr, _stopped = execute_one(mem, pc, acc)
        if instr == 21:  # STORE wrote memory
            touched.add(arg_addr)
        pc = next_pc
        steps += 1

    return acc, steps, touched, mem, hit_cap


def snapshot_for_file(path):
    """Assemble and run one .toys file. Returns the snapshot dict entry."""
    with open(path) as f:
        src = f.read()

    mem, listing, syms, data_addrs, errors, data_start = assemble(src)
    if errors:
        return {"assembled": False, "errors": list(errors)}

    # Memory-mapped I/O is GUI-only; this headless runner treats 240..255 as
    # ordinary memory, so no directives/input injection are needed here.
    acc, steps, touched, final_mem, hit_cap = run_program(mem, data_addrs)

    # Build a readable memory map. Prefer the symbol name for an address; fall
    # back to the plain decimal address (as a string, so the JSON key set is
    # stable regardless of whether a label exists). Only include addresses that
    # are data or were written to, sorted by address for deterministic output.
    rsym = {v: k for k, v in syms.items()}
    memory = {}
    for a in sorted(touched):
        key = rsym.get(a, str(a))
        memory[key] = final_mem[a]

    return {
        "assembled": True,
        "final_acc": acc,
        "steps": steps,
        "hit_cap": hit_cap,
        "memory": memory,
    }


def build_snapshot():
    """Build the full snapshot table for every examples/asm/**/*.toys (sorted).

    Keyed by the path RELATIVE to examples/asm/ without the .toys extension
    (e.g. "03-programs/fibonacci"), so two files with the same basename in
    different tier folders (03-programs/fibonacci vs 04-io/fibonacci) each get
    their own entry instead of one silently overwriting the other."""
    # These are GUI-only busy-wait demos: they poll `ready` and, with no input
    # (ready stays 0 headless), spin to the step cap by design, so they have no
    # meaningful headless result. Exclude them — the GUI drives them live by
    # letting the user set `ready`.
    SKIP = {"poll_demo", "greet_name", "sort", "pin_check"}
    table = {}
    for path in sorted(glob.glob(os.path.join(ASM_DIR, "**", "*.toys"),
                                 recursive=True)):
        rel = os.path.relpath(path, ASM_DIR)
        key = os.path.splitext(rel)[0]               # e.g. "03-programs/fibonacci"
        if os.path.basename(key) in SKIP:
            continue
        table[key] = snapshot_for_file(path)
    return table


def write_snapshot(table, out_path=OUT_PATH):
    """Write the table as deterministic JSON (sorted keys, indent=2)."""
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    with open(out_path, "w") as f:
        json.dump(table, f, sort_keys=True, indent=2)
        f.write("\n")


def print_summary(table):
    for name in sorted(table):
        e = table[name]
        if not e.get("assembled", False):
            print(f"{name:16s} -> ASSEMBLY ERROR: {e.get('errors')}")
            continue
        cap = "  [HIT CAP]" if e.get("hit_cap") else ""
        print(f"{name:16s} -> acc={e['final_acc']:4d}  steps={e['steps']}{cap}")


def main():
    table = build_snapshot()
    write_snapshot(table)
    print_summary(table)
    print(f"\nWrote {OUT_PATH}")


if __name__ == "__main__":
    main()
