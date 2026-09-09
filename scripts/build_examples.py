#!/usr/bin/env python3
"""
build_examples.py - compile every compiler/examples/*.toyc to its .toys.

The generated .toys files are build artifacts (not tracked in git); run this to
(re)create them all from the C sources. Each example carries a `// expect: N`
header; this script also runs each result and reports OK/MISMATCH so a broken
compiler is obvious.

Usage:  python3 scripts/build_examples.py
"""
import io
import os
import re
import sys
import glob
import contextlib

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "compiler"))

from toycc import compile_source, CompileError
from toyasm import assemble
from toysim import simulate

EXAMPLES = os.path.join(ROOT, "compiler", "examples")
_EXPECT = re.compile(r"//\s*expect:\s*(\d+)", re.IGNORECASE)


def run_acc(asm):
    mem, listing, syms, data_addrs, errors, _ds = assemble(asm)
    if errors:
        return None, errors
    with contextlib.redirect_stdout(io.StringIO()):
        return simulate(mem, syms, data_addrs), None


def main():
    fails = 0
    for path in sorted(glob.glob(os.path.join(EXAMPLES, "*.toyc"))):
        name = os.path.basename(path)
        with open(path) as f:
            src = f.read()
        m = _EXPECT.search(src)
        want = int(m.group(1)) if m else None
        try:
            asm = compile_source(src, name)
        except CompileError as e:
            print(f"[COMPILE-ERR] {name}: {e}")
            fails += 1
            continue
        out = path[:-5] + ".toys"          # strip .toyc, add .toys
        with open(out, "w") as f:
            f.write(asm)
        acc, errors = run_acc(asm)
        if errors:
            print(f"[ASM-ERR] {name}: {errors[0]}")
            fails += 1
        elif want is not None and acc != want:
            print(f"[MISMATCH] {name}: got {acc}, expected {want}")
            fails += 1
        else:
            print(f"[ok] {name} -> {os.path.basename(out)}  (ACC={acc})")
    total = len(glob.glob(os.path.join(EXAMPLES, "*.toyc")))
    print(f"\n{total - fails}/{total} examples built and verified.")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
