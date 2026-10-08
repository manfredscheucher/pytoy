#!/usr/bin/env python3
"""Review probe: for every examples/c/**/*.toyc, report which compilers
examples_index detects, and whether minicc compiles-but-overflows (the fit
gate). Confirms the intended exclusions (bigint_add, sort_array_inline lose
minicc; recursive stay out)."""
import sys
import os
import glob
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from pytoy.minicc import compile_source as mini, MiniError
from pytoy.compiler import compile_source as toy, CompileError
from pytoy.assembler import assemble

for path in sorted(glob.glob(os.path.join(ROOT, "examples", "c", "**", "*.toyc"),
                             recursive=True)):
    name = os.path.relpath(path, ROOT)
    src = open(path).read()
    tags = []
    # minicc
    note = ""
    try:
        asm = mini(src, "probe")
        _, _, _, _, errs, _ = assemble(asm)
        if errs:
            note = f"minicc-compiles-but-{'overflow' if 'too big' in errs[0] else 'asmerr'}"
        else:
            tags.append("minicc")
    except MiniError:
        pass
    except Exception as e:
        note = f"minicc-{type(e).__name__}"
    # toycc
    try:
        asm = toy(src, "probe")
        _, _, _, _, errs, _ = assemble(asm)
        if not errs:
            tags.append("toycc")
    except Exception:
        pass
    print(f"{name:45s} {','.join(tags) or '-':14s} {note}")
