"""Probe which compilers (minicc / toycc) accept each candidate .toyc example,
and whether the compiled result assembles within the 256-byte memory. Used to
pick fixtures for the Part-3 compiler-switch tests (a both-accept example for the
success case, a minicc-rejects / minicc-overflows example for the rollback case).

Run: QT_QPA_PLATFORM=offscreen python3 scripts/probe_compiler_accept.py
"""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from pytoy.examples_index import _detect_compilers
from pytoy.simulator import _compile_c
from pytoy.assembler import assemble

CANDIDATES = [
    "examples/c/03-programs/sum3.toyc",
    "examples/c/02-extended/multiply_operator.toyc",
    "examples/c/03-programs/fibonacci_rec.toyc",
    "examples/c/03-programs/bigint_add.toyc",
    "examples/c/03-programs/sort_array_inline.toyc",
    "examples/c/03-programs/count_iter.toyc",
]


def _assembles(src, compiler, path):
    try:
        asm = _compile_c(src, compiler, path, annotate_c_lines=True)
    except Exception as e:
        return f"compile-fail ({type(e).__name__})"
    _, _, _, _, errors, _ = assemble(asm)
    return "OK" if not errors else f"assemble-fail ({len(errors)} err)"


def main():
    root = os.path.join(os.path.dirname(__file__), "..")
    for rel in CANDIDATES:
        path = os.path.join(root, rel)
        accepted = _detect_compilers(path)
        src = open(path).read()
        both = {c: _assembles(src, c, path) for c in ("minicc", "toycc")}
        print(f"{rel}\n  detect={accepted}  minicc={both['minicc']}  "
              f"toycc={both['toycc']}")


if __name__ == "__main__":
    main()
