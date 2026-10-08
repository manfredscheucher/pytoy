#!/usr/bin/env python3
"""Compile+assemble+run every C example in 02-extended/03-programs with toycc
and check the final ACC against its `// expect: N` marker. Ground truth for
ktoy's ExampleCatalogTest.everyCExampleCompilesAssemblesAndRunsToExpected.
"""
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
PYTOY = os.path.dirname(HERE)
sys.path.insert(0, PYTOY)

from pytoy.compiler import compile_source  # noqa: E402
from pytoy.assembler import assemble  # noqa: E402
from pytoy.simulator import simulate  # noqa: E402

EXPECT = re.compile(r"//\s*expect:\s*(\d+)", re.IGNORECASE)


def main():
    bad = 0
    for sub in ["02-extended", "03-programs"]:
        folder = os.path.join(PYTOY, "examples", "c", sub)
        for f in sorted(os.listdir(folder)):
            if not f.endswith(".toyc"):
                continue
            src = open(os.path.join(folder, f)).read()
            exp = EXPECT.search(src)
            if not exp:
                print(f"{f}: NO EXPECT MARKER")
                bad += 1
                continue
            asm = compile_source(src, f)
            mem, listing, syms, data_addrs, errors, _ds = assemble(asm)
            if errors:
                print(f"{f}: ASSEMBLE ERRORS {errors}")
                bad += 1
                continue
            acc = simulate(mem, syms, data_addrs)
            ok = acc == int(exp.group(1))
            print(f"{f}: acc={acc} expect={exp.group(1)} {'OK' if ok else 'MISMATCH'}")
            if not ok:
                bad += 1
    print(f"\n{bad} problem(s)")


if __name__ == "__main__":
    main()
