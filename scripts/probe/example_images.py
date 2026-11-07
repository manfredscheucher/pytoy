"""Guard for comment-only edits of the examples: the bytes every example builds to.

  python3.14 scripts/probe/example_images.py save          store the baseline
  python3.14 scripts/probe/example_images.py check [dir]   compare (optional: only paths containing dir)
"""
import glob, json, os, sys
ROOT = os.path.join(os.path.dirname(__file__), "..", "..")
sys.path.insert(0, ROOT)
from pytoy.assembler import assemble
from pytoy.compiler import compile_source as toycc
from pytoy.minicc import compile_source as minicc

BASE = os.path.join(os.path.dirname(__file__), "example_images.json")

def image(asm_text):
    return list(assemble(asm_text)[0])

def build(path):
    src = open(path).read()
    if path.endswith(".toys"):
        try:
            return {"asm": image(src)}
        except Exception as e:
            return {"asm": "error: " + type(e).__name__}
    out = {}
    for name, cc in (("toycc", toycc), ("minicc", minicc)):
        try:
            out[name] = image(cc(src, os.path.basename(path)))
        except Exception as e:
            out[name] = "error: " + type(e).__name__
    return out

def all_images():
    files = glob.glob(os.path.join(ROOT, "examples", "**", "*.toys"), recursive=True) + \
            glob.glob(os.path.join(ROOT, "examples", "**", "*.toyc"), recursive=True)
    return {os.path.relpath(f, os.path.join(ROOT, "examples")): build(f) for f in sorted(files)}

if sys.argv[1] == "save":
    json.dump(all_images(), open(BASE, "w"))
    print("saved", len(json.load(open(BASE))), "examples")
else:
    where = sys.argv[2] if len(sys.argv) > 2 else ""
    base = json.load(open(BASE))
    now = all_images()
    bad = [k for k in sorted(set(base) | set(now)) if where in k and base.get(k) != now.get(k)]
    print("changed:" if bad else "all bytes identical", *bad, sep="\n  " if bad else "")
    sys.exit(1 if bad else 0)
