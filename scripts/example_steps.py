#!/usr/bin/env python3
"""
example_steps.py - run every example headless and check its result and length.

For each example under examples/ (asm, C with every compiler that accepts it,
and the .toyo bytecode listings) this assembles / compiles it, runs it without
the GUI to STOP and prints the final ACC and the number of steps (STOP counts
as a step). The I/O examples (examples/asm/04-io, examples/c/04-io) wait for
input and are skipped.

Each example documents its numbers in its header comment, and this script
checks them:
    asm:         # result: 13   and   # steps: 117
    toyo:        the same lines, in the listing's SOURCE column
    C:           // expect: 13  and   // steps: toycc 255, minicc 180
                 (only the compilers that accept the source are listed)
A missing line is reported as MISSING, a wrong one as MISMATCH.

Usage:  python3 scripts/example_steps.py           # check, exit 1 on problems
        python3 scripts/example_steps.py --table   # just print the numbers
        python3 scripts/example_steps.py --write   # add / update the lines
                                                   # (at the top of the file)
"""
import glob
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from pytoy.assembler import assemble
from pytoy.core import decode, execute_one
from pytoy.simulator import _compile_c, parse_toyo

MAX_STEPS = 1_000_000
COMPILERS = ("toycc", "minicc")

_RESULT_ASM = re.compile(r"^#\s*result:\s*(\d+)", re.IGNORECASE | re.MULTILINE)
_STEPS_ASM = re.compile(r"^#\s*steps:\s*(\d+)", re.IGNORECASE | re.MULTILINE)
_RESULT_TOYO = re.compile(r"^#\s+#\s*result:\s*(\d+)", re.IGNORECASE | re.MULTILINE)
_STEPS_TOYO = re.compile(r"^#\s+#\s*steps:\s*(\d+)", re.IGNORECASE | re.MULTILINE)
_RESULT_C = re.compile(r"//\s*expect:\s*(\d+)", re.IGNORECASE)
_STEPS_C = re.compile(r"//\s*steps:\s*(.+)", re.IGNORECASE)


def run(mem):
    """Run a 256-byte image from PC 0 to STOP. Returns (acc, steps) with STOP
    counted, or (acc, None) if it did not stop within MAX_STEPS."""
    mem = list(mem)
    pc, acc, steps = 0, 0, 0
    while steps < MAX_STEPS:
        instr, _arg, _ = decode(mem, pc)
        steps += 1
        if instr == 0:
            return acc, steps
        pc, acc, _arg, _stopped = execute_one(mem, pc, acc)
    return acc, None


def run_asm(src):
    mem, _listing, _syms, _data, errors, _ds = assemble(src)
    if errors:
        raise ValueError(errors[0])
    return run(mem)


def examples(kind, pattern):
    for path in sorted(glob.glob(os.path.join(ROOT, "examples", kind, pattern), recursive=True)):
        if "04-io" not in path:
            yield path


def set_line(path, src, regex, line):
    """Replace the first line matching [regex] with [line], or put [line] at the
    top (after a leading `// expect:` line in C). Writes the file if changed."""
    lines = src.split("\n")
    for i, l in enumerate(lines):
        if regex.match(l):
            lines[i] = line
            break
    else:
        at = 1 if lines and _RESULT_C.match(lines[0]) else 0
        if line.startswith("# steps"):     # keep `# result` above `# steps`
            at = next((i + 1 for i, l in enumerate(lines) if _RESULT_ASM.match(l)), at)
        lines.insert(at, line)
    new = "\n".join(lines)
    if new != src:
        with open(path, "w") as f:
            f.write(new)
    return new


def main():
    table_only = "--table" in sys.argv
    write = "--write" in sys.argv
    problems = []

    def check(name, label, want, got):
        if table_only:
            return
        if want is None:
            problems.append(f"[MISSING]  {name}: no {label} line (actual {got})")
        elif want != got:
            problems.append(f"[MISMATCH] {name}: {label} says {want}, actual {got}")

    for path in list(examples("asm", "**/*.toys")) + list(examples("toyo", "*.toyo")):
        name = os.path.relpath(path, os.path.join(ROOT, "examples"))
        src = open(path).read()
        try:
            acc, steps = run(parse_toyo(src)) if path.endswith(".toyo") else run_asm(src)
        except ValueError as e:
            problems.append(f"[ERROR]    {name}: {e}")
            continue
        print(f"{name:45} ACC={acc:3}  steps={steps}")
        if path.endswith(".toyo"):
            # a listing carries its source's header lines in the SOURCE column
            # ("#      # result: 13"); regenerate it with run.py asm to update
            m = _RESULT_TOYO.search(src)
            check(name, "result", int(m.group(1)) if m else None, acc)
            m = _STEPS_TOYO.search(src)
            check(name, "steps", int(m.group(1)) if m else None, steps)
            continue
        if write:
            src = set_line(path, src, _RESULT_ASM, f"# result: {acc}")
            src = set_line(path, src, _STEPS_ASM, f"# steps: {steps}")
        m = _RESULT_ASM.search(src)
        check(name, "result", int(m.group(1)) if m else None, acc)
        m = _STEPS_ASM.search(src)
        check(name, "steps", int(m.group(1)) if m else None, steps)

    for path in examples("c", "**/*.toyc"):
        name = os.path.relpath(path, os.path.join(ROOT, "examples"))
        src = open(path).read()
        m = _RESULT_C.search(src)
        want = int(m.group(1)) if m else None
        per = {}
        for compiler in COMPILERS:
            try:
                acc, steps = run_asm(_compile_c(src, compiler, os.path.basename(path)))
            except Exception:
                continue   # this compiler does not accept the source
            per[compiler] = steps
            print(f"{name:45} ACC={acc:3}  steps={steps}  ({compiler})")
            check(f"{name} ({compiler})", "expect", want, acc)
        got = ", ".join(f"{c} {s}" for c, s in per.items())
        if write and per:
            src = set_line(path, src, _STEPS_C, f"// steps: {got}")
        m = _STEPS_C.search(src)
        check(name, "steps", m.group(1).strip() if m else None, got)

    for p in problems:
        print(p)
    if not table_only:
        print(f"\n{len(problems)} problem(s)")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
