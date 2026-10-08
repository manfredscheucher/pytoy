#!/usr/bin/env python3
"""Dump reference toycc assembly for a set of example C programs.

Used to cross-check the Kotlin port (ktoy) against the Python compiler oracle.
Run from the pytoy repo root:  python3 scripts/oracle_dump.py
"""
import os
import sys

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, HERE)

from pytoy.compiler import compile_source, Opts

EXAMPLES = [
    ("examples/c/02-extended/multiply_operator.toyc", Opts()),
    ("examples/c/02-extended/bit_operators.toyc", Opts()),
    ("examples/c/02-extended/if_then_else.toyc", Opts()),
    ("examples/c/03-programs/max3.toyc", Opts()),
    ("examples/c/03-programs/gcd_iter.toyc", Opts()),
    ("examples/c/03-programs/fibonacci_rec.toyc", Opts()),
    ("examples/c/03-programs/sum_array.toyc", Opts()),
    ("examples/c/03-programs/sort_array_fn.toyc", Opts()),
]


def main():
    for path, opts in EXAMPLES:
        full = os.path.join(HERE, path)
        with open(full) as f:
            src = f.read()
        print("=" * 70)
        print("FILE:", path)
        print("=" * 70)
        print(compile_source(src, os.path.basename(path), opts=opts))


if __name__ == "__main__":
    main()
