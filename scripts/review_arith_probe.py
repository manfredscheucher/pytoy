#!/usr/bin/env python3
"""Fresh-eyes probe of the new arithmetic examples.

Patches the data bytes (a/b) of the 02-extended arithmetic examples and the
03-programs/gcd example, runs them through the real pipeline
(assemble -> simulate), and checks ACC against hand-computed values.

Each example runs in a subprocess with a short timeout so a non-terminating
loop shows up as TIMEOUT instead of hanging the probe.

Run: python3 scripts/review_arith_probe.py
"""
import io
import os
import re
import sys
import contextlib

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)

from pytoy.assembler import assemble
from pytoy.simulator import simulate


def patch(src, overrides):
    """Replace the integer value of `label:  <int>` data lines."""
    out = []
    for ln in src.splitlines(keepends=True):
        m = re.match(r'^(\w+):(\s+)(-?\d+)(.*)$', ln)
        if m and m.group(1) in overrides:
            out.append(f"{m.group(1)}:{m.group(2)}{overrides[m.group(1)]}{m.group(4)}\n")
        else:
            out.append(ln)
    return "".join(out)


def _once(src, box):
    mem, listing, syms, data_addrs, errors, _ds = assemble(src)
    if errors:
        box["r"] = f"ERR:{errors}"
        return
    with contextlib.redirect_stdout(io.StringIO()):
        acc = simulate(mem, syms, data_addrs)
    box["r"] = acc


def run(path, overrides, timeout=5):
    """Run in a daemon thread; if it doesn't finish, report TIMEOUT.

    The simulator has no step cap, so a non-terminating loop would hang.
    A daemon thread that overruns is simply abandoned (left spinning) — fine
    for a probe since the process exits at the end.
    """
    import threading
    with open(path) as f:
        src = patch(f.read(), overrides)
    box = {}
    t = threading.Thread(target=_once, args=(src, box), daemon=True)
    t.start()
    t.join(timeout)
    if t.is_alive():
        return "TIMEOUT"
    return box.get("r")


EXT = os.path.join(ROOT, "examples/asm/02-extended")
PROG = os.path.join(ROOT, "examples/asm/03-programs")

fails = []

def check(label, got, exp):
    ok = (got == exp)
    if not ok:
        fails.append(label)
    print(f"  [{'OK ' if ok else 'XX '}] {label}: got={got!s:>8} exp={exp}")


DEGEN_ONLY = "--degenerate" in sys.argv

def run_subproc(path, overrides, timeout=4):
    """Run via run.py in a real subprocess; kill on timeout (clean, no GIL spin)."""
    import subprocess, tempfile
    with open(path) as f:
        src = patch(f.read(), overrides)
    fd, tmp = tempfile.mkstemp(suffix=".toys", dir=ROOT)
    with os.fdopen(fd, "w") as f:
        f.write(src)
    try:
        r = subprocess.run([sys.executable, "run.py", "sim", tmp, "--cli", "--run"],
                           cwd=ROOT, capture_output=True, text=True, timeout=timeout)
        m = re.search(r'ACC = (\d+)', r.stdout)
        return int(m.group(1)) if m else "(no ACC)"
    except subprocess.TimeoutExpired:
        return "TIMEOUT (infinite loop)"
    finally:
        os.unlink(tmp)


if DEGEN_ONLY:
    print("=== degenerate / termination probes (expect TIMEOUT where a loop can't end) ===")
    print("  divide a=20 b=0 ->", run_subproc(f"{EXT}/divide.toys", {'a':20,'b':0}))
    print("  modulo a=20 b=0 ->", run_subproc(f"{EXT}/modulo.toys", {'a':20,'b':0}))
    print("  gcd    a=0  b=5 ->", run_subproc(f"{PROG}/gcd.toys", {'a':0,'b':5}))
    print("  gcd    a=5  b=0 ->", run_subproc(f"{PROG}/gcd.toys", {'a':5,'b':0}))
    sys.exit(0)

print("=== multiply vs multiply_fast (expect (a*b) mod 256) ===")
for a, b in [(6,7),(0,5),(5,0),(0,0),(1,1),(15,8),(12,12),(20,10),(16,16),
             (100,3),(255,1),(1,255),(17,15),(200,2)]:
    m1 = run(f"{EXT}/multiply.toys", {'a':a,'b':b})
    m2 = run(f"{EXT}/multiply_fast.toys", {'a':a,'b':b})
    exp = (a*b) % 256
    note = "  <<OVERFLOW a*b>255>>" if a*b > 255 else ""
    agree = "" if m1 == m2 else "  <<DISAGREE>>"
    if m1 != exp or m2 != exp or m1 != m2:
        fails.append(f"mul a={a} b={b}")
    print(f"  a={a:3} b={b:3}  mul={m1!s:>6} fast={m2!s:>6} exp(mod256)={exp:3}{agree}{note}")

print("\n=== divide (a/b) & modulo (a%b), check q*b+r==a ===")
for a, b in [(20,6),(6,6),(6,20),(0,6),(0,1),(7,7),(100,10),(49,7),(50,7),
             (127,1),(127,2),(127,126),(13,1),(1,1)]:
    q = run(f"{EXT}/divide.toys", {'a':a,'b':b})
    r = run(f"{EXT}/modulo.toys", {'a':a,'b':b})
    eq, er = a // b, a % b
    ok = (q == eq and r == er)
    if not ok:
        fails.append(f"div/mod a={a} b={b}")
    ident = ""
    if isinstance(q,int) and isinstance(r,int):
        ident = f"  q*b+r={q*b+r}"
    print(f"  [{'OK ' if ok else 'XX '}] a={a:3} b={b:3}  q={q!s:>6}(exp {eq:3}) r={r!s:>6}(exp {er:3}){ident}")

print("\n=== divide/modulo boundary: large a (doc says valid 0..127) ===")
for a, b in [(126,6),(127,6),(128,6),(129,6),(130,6),
             (200,3),(250,7),(255,100),(180,7),(160,3),(129,1),(200,1)]:
    q = run(f"{EXT}/divide.toys", {'a':a,'b':b})
    r = run(f"{EXT}/modulo.toys", {'a':a,'b':b})
    eq, er = a // b, a % b
    tag = "ok" if (q==eq and r==er) else "WRONG"
    print(f"  a={a:3} b={b:3}  q={q!s:>10}(true {eq}) r={r!s:>10}(true {er})  -> {tag}")
print("\n=== gcd ===")
import math
for a, b in [(48,36),(36,48),(17,5),(12,12),(100,10),(7,13),(81,27)]:
    g = run(f"{PROG}/gcd.toys", {'a':a,'b':b})
    print(f"  a={a:3} b={b:3}  gcd={g!s:>8}  math.gcd={math.gcd(a,b)}")
    check(f"gcd({a},{b})", g, math.gcd(a,b))

print("\n=== degenerate / termination probes (these may hang -> TIMEOUT) ===")
# b=0 in divide/modulo: a-b never goes negative -> infinite loop expected
print("  divide a=20 b=0 ->", run(f"{EXT}/divide.toys", {'a':20,'b':0}, timeout=3))
print("  modulo a=20 b=0 ->", run(f"{EXT}/modulo.toys", {'a':20,'b':0}, timeout=3))
# gcd with a 0 operand: a-b never zero if other nonzero -> watch for hang
print("  gcd    a=0  b=5 ->", run(f"{PROG}/gcd.toys", {'a':0,'b':5}, timeout=3))
print("  gcd    a=5  b=0 ->", run(f"{PROG}/gcd.toys", {'a':5,'b':0}, timeout=3))

print("\n" + ("ALL PASS" if not fails else f"FAILURES ({len(fails)}): " + ", ".join(fails)))
