"""Report unused labels and code unreachable from the entry in examples/asm/**/*.toys."""
import re, subprocess, sys
from pathlib import Path

OPS1 = {"right", "left", "not", "stop", "nop"}
OPS2 = {"and", "or", "xor", "load", "store", "add", "sub", "goto", "ifzero", "dec", "inc"}

def main():
    for f in sorted(Path("examples/asm").rglob("*.toys")):
        lines = f.read_text().splitlines()
        toks = []
        for n, raw in enumerate(lines, 1):
            s = raw.split("#")[0].strip()
            if not s:
                continue
            m = re.match(r"(\w+):\s*(.*)", s)
            label = m.group(1) if m else None
            rest = m.group(2) if m else s
            toks.append((n, label, rest.split()))
        labels = {t[1]: i for i, t in enumerate(toks) if t[1]}
        used = set()
        for _, _, parts in toks:
            for w in parts[1:] if parts and parts[0] in OPS2 else parts:
                if w in labels:
                    used.add(w)
        unused = [l for l in labels if l not in used]
        # data starts at first non-instruction line
        seen, work = set(), [0]
        while work:
            i = work.pop()
            if i in seen or i >= len(toks):
                continue
            seen.add(i)
            parts = toks[i][2]
            if not parts:
                work.append(i + 1); continue
            op = parts[0]
            if op == "stop":
                continue
            if op == "goto":
                work.append(labels.get(parts[1], i + 1)); continue
            if op == "ifzero":
                work.append(labels.get(parts[1], i + 1))
            work.append(i + 1)
        dead = [toks[i] for i in range(len(toks)) if i not in seen and toks[i][2] and toks[i][2][0] in OPS1 | OPS2]
        # stores never read: variables only written
        if unused or dead:
            print(f"{f}:")
            if unused: print("  unused labels:", ", ".join(unused))
            for n, _, parts in dead: print(f"  unreachable L{n}: {' '.join(parts)}")

main()
