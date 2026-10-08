#!/usr/bin/env python3
"""Review probe: for each minicc-accepted non-io C example, compile with minicc,
assemble, simulate, and check the result matches the `// expect: N` marker.
Confirms didactic correctness of the 18 embedded goldens (pytoy side)."""
import sys
import os
import re
import glob
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from pytoy.minicc import compile_source as mini, MiniError
from pytoy.assembler import assemble
from pytoy.simulator import simulate

EXPECT = re.compile(r"//\s*expect:\s*(\d+)", re.I)
for path in sorted(glob.glob(os.path.join(ROOT, "examples", "c", "**", "*.toyc"),
                             recursive=True)):
    if os.sep + "04-io" + os.sep in path:
        continue
    name = os.path.basename(path)
    src = open(path).read()
    try:
        asm = mini(src, name)
        mem, _, syms, data_addrs, errs, _ = assemble(asm)
        if errs:
            continue
    except MiniError:
        continue
    m = EXPECT.search(src)
    exp = int(m.group(1)) if m else None
    acc = simulate(mem, syms, data_addrs)
    ok = "OK" if exp == acc else "MISMATCH"
    print(f"{name:30s} expect={exp} acc={acc} {ok}")
