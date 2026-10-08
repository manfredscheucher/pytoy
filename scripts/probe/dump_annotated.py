#!/usr/bin/env python3
"""Dump pytoy's C-line-annotated assembly for a set of example programs.

Used to cross-check ktoy's annotateCLines=true output against pytoy's
annotate_c_lines=True (the reference). Prints, per example, each emitted asm
line that carries a `# @c:N` marker as `<N>\t<line>` so the markers can be
diffed line-for-line against ktoy.
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
PYTOY = os.path.dirname(HERE)
sys.path.insert(0, PYTOY)

from pytoy.compiler import compile_source  # noqa: E402

EXAMPLES = [
    "examples/c/03-programs/fibonacci_iter.toyc",
    "examples/c/03-programs/sum3.toyc",
    "examples/c/03-programs/count_rec.toyc",
    "examples/c/02-extended/if_then_else.toyc",
]


def main():
    for rel in EXAMPLES:
        path = os.path.join(PYTOY, rel)
        src = open(path).read()
        name = os.path.basename(path)
        asm = compile_source(src, name, annotate_c_lines=True)
        print(f"### {name}")
        for ln in asm.splitlines():
            if "@c:" in ln:
                # extract marker
                import re
                m = re.search(r"@c:(\d+)", ln)
                print(f"{m.group(1)}\t{ln.strip()}")
        print()


if __name__ == "__main__":
    main()
