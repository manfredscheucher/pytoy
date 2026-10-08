#!/usr/bin/env python3
"""Probe which of minicc/toycc accept each C example (ground truth for ktoy's
ExampleSources compiler tags). Prints `<name>: [compilers]` for every .toyc in
examples/c/02-extended and 03-programs.
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
PYTOY = os.path.dirname(HERE)
sys.path.insert(0, PYTOY)


def minicc_accepts(src):
    from pytoy.minicc import compile_source, MiniError
    try:
        compile_source(src, "probe")
        return True
    except MiniError:
        return False
    except Exception:
        return False


def toycc_accepts(src):
    from pytoy.compiler import compile_source, CompileError
    try:
        compile_source(src, "probe")
        return True
    except CompileError:
        return False
    except Exception:
        return False


def main():
    for sub in ["02-extended", "03-programs"]:
        folder = os.path.join(PYTOY, "examples", "c", sub)
        for f in sorted(os.listdir(folder)):
            if not f.endswith(".toyc"):
                continue
            src = open(os.path.join(folder, f)).read()
            comps = []
            if minicc_accepts(src):
                comps.append("minicc")
            if toycc_accepts(src):
                comps.append("toycc")
            print(f"{f}: {comps}")


if __name__ == "__main__":
    main()
