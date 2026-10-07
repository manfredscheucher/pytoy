#!/usr/bin/env python3
"""One-shot example renamer (C + asm), aligning names between the two sets and
replacing vague/misleading names with clearer ones. Run once from the repo root:

    python3 scripts/rename_examples.py            # dry run (prints the plan)
    python3 scripts/rename_examples.py --apply    # actually `git mv` the files

Kept as a durable record of the rename (per the project's durable-scripts rule).
The naming convention it encodes:
  - same concept -> same base name in C and asm; variants via explicit suffix
    (_iter/_rec, _array, _inline/_fn, _operator/_doubling/_repeated, _io, _hex/_ascii)
  - clear over cute; plain name reserved for the canonical form
After running, fix references (test globs are already recursive) and regenerate
the snapshot table + ktoy ExampleSources if needed.
"""
import os
import subprocess
import sys

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# (relative path from repo root) old -> new, basename only (same folder).
# Only files that CHANGE are listed.
RENAMES = {
    # ── asm 02-extended ──
    "examples/asm/02-extended/multiply.toys":      "multiply_repeated.toys",
    "examples/asm/02-extended/multiply_fast.toys": "multiply_doubling.toys",
    "examples/asm/02-extended/sevenfold.toys":     "times7_doubling.toys",
    "examples/asm/02-extended/compare.toys":       "compare_less.toys",
    # ── asm 03-programs ──
    "examples/asm/03-programs/fibonacci.toys":   "fibonacci_iter.toys",
    "examples/asm/03-programs/gcd.toys":         "gcd_iter.toys",
    "examples/asm/03-programs/sevenfold.toys":   "times7_doubling.toys",
    "examples/asm/03-programs/sort_array.toys":  "sort_array_inline.toys",
    # ── asm 04-io ──
    "examples/asm/04-io/fibonacci.toys": "fibonacci_io.toys",
    "examples/asm/04-io/sort.toys":      "sort_array_io.toys",
    # ── C 02-extended ──
    "examples/c/02-extended/bitops.toyc":     "bit_operators.toyc",
    "examples/c/02-extended/ifelse.toyc":     "if_then_else.toyc",
    "examples/c/02-extended/sevenfold.toyc":  "times7_operator.toyc",
    # multiply_operator.toyc keeps its name (part of the decided trio)
    # ── C 03-programs ──
    "examples/c/03-programs/countdown.toyc":            "sum_countdown.toyc",
    "examples/c/03-programs/functions.toyc":            "sum_of_squares.toyc",
    "examples/c/03-programs/sort_array_function.toyc":  "sort_array_fn.toyc",
    # sort_array_inline.toyc (C) keeps its name (option B: both explicit)
}


def main():
    apply = "--apply" in sys.argv
    for rel, newbase in RENAMES.items():
        src = os.path.join(REPO, rel)
        dst = os.path.join(os.path.dirname(src), newbase)
        if not os.path.exists(src):
            print(f"  SKIP (missing): {rel}")
            continue
        print(f"  {rel}  ->  {newbase}")
        if apply:
            subprocess.run(["git", "mv", src, dst], cwd=REPO, check=True)
    print("\n(applied)" if apply else "\n(dry run — pass --apply to rename)")


if __name__ == "__main__":
    main()
