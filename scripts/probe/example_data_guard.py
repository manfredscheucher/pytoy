"""Assembly examples: code/data split and directives unchanged against git HEAD (comments can carry them)."""
import glob, os, re, subprocess, sys
ROOT = os.path.join(os.path.dirname(__file__), "..", "..")
sys.path.insert(0, ROOT)
from pytoy.assembler import assemble
bad = 0
for f in sorted(glob.glob(os.path.join(ROOT, "examples/asm/**/*.toys"), recursive=True)):
    rel = os.path.relpath(f, ROOT)
    old = subprocess.run(["git", "-C", ROOT, "show", "HEAD:" + rel], capture_output=True, text=True).stdout
    new = open(f).read()
    def info(src):
        r = assemble(src)
        return r[1:] if isinstance(r, tuple) else r
    def strip(res):
        out = []
        for x in res:
            out.append(x if isinstance(x, (int, set, frozenset)) or x is None else None)
        return out
    a, b = strip(info(old)), strip(info(new))
    da = re.findall(r"(?m)^\s*#\s*pytoy:.*$", old); db = re.findall(r"(?m)^\s*#\s*pytoy:.*$", new)
    if a != b or da != db:
        bad += 1
        print(rel, "DIFF", a, b, da, db)
print("differences:", bad)
