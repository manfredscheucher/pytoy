"""Run old (HEAD) and new versions of the cleaned examples and compare acc and io cells."""
import subprocess, sys
sys.path.insert(0, ".")
from pytoy.assembler import assemble
from pytoy.core import execute_one

def run(src, pokes=None, sym_pokes=None, cap=200000):
    mem, _, syms, _, errs, _ = assemble(src)
    assert not errs, errs
    mem = list(mem)
    for a, v in (pokes or {}).items():
        mem[a] = v
    for s, v in (sym_pokes or {}).items():
        mem[syms[s]] = v
    pc = acc = n = 0
    while n < cap:
        n += 1
        pc, acc, _, stopped = execute_one(mem, pc, acc)
        if stopped:
            return acc, mem[240:256], n
    raise RuntimeError("cap")

def old(p):
    return subprocess.check_output(["git", "show", f"HEAD:{p}"], text=True)

def io(values):
    d = {240 + i: v for i, v in enumerate(values)}
    d[255] = len(values)
    return d

A = "examples/asm/"
cases = [(A + "04-io/fibonacci_io.toys", {}, {}), (A + "04-io/countdown.toys", {}, {}),
         (A + "03-programs/sum_array.toys", {}, {}), (A + "02-extended/load_indirect.toys", {}, {}),
         (A + "02-extended/store_indirect.toys", {}, {})]
cases += [(A + "03-programs/fibonacci_rec.toys", {}, {"input": n}) for n in range(0, 12)]
cases += [(A + "04-io/greet_name.toys", io(list(name.encode())), {}) for name in ["Al", "Manfred", "Annaluis"]]
cases += [(A + "04-io/sort_array_io.toys", io(v), {}) for v in ([5], [3, 1, 2], [9, 8, 7, 6, 5, 4, 3, 2, 1, 0, 10, 20, 15, 12, 11])]
bad = 0
for p, pk, sp in cases:
    a, b = run(old(p), pk, sp), run(open(p).read(), pk, sp)
    same = a[:2] == b[:2]
    bad += not same
    print("ok " if same else "DIFF", p.split("/")[-1], list(sp.values()) or "", "acc", b[0], "steps", a[2], "->", b[2])
    if "greet" in p or "sort" in p:
        print("    io:", bytes(c for c in b[1][:15] if c).decode("latin1") if "greet" in p else b[1][:15])
print("differences:", bad)
