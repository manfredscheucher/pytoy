"""Report loads overwritten by the next load and data cells that are only ever written."""
import re
from pathlib import Path

OVERWRITE = {"load"}
for f in sorted(Path("examples/asm").rglob("*.toys")):
    toks = []
    for n, raw in enumerate(f.read_text().splitlines(), 1):
        s = raw.split("#")[0].strip()
        if not s:
            continue
        m = re.match(r"(\w+):\s*(.*)", s)
        toks.append((n, m.group(1) if m else None, (m.group(2) if m else s).split()))
    out = []
    for a, b in zip(toks, toks[1:]):
        if not a[2] or not b[2]:
            continue
        # load followed by another full acc overwrite, also through a raw load opcode
        if a[2][0] == "load" and b[2][0] in ("load", "20"):
            out.append(f"  L{a[0]}: {' '.join(a[2])} overwritten by L{b[0]}: {' '.join(b[2])}")
    for i, t in enumerate(toks):
        if not t[1] or not t[2] or not re.fullmatch(r"-?\d+", t[2][0]):
            continue
        if i and toks[i - 1][2] and toks[i - 1][2][0] in ("20", "21"):
            continue  # patched operand
        uses = [p[0] for x in toks for p in [x[2]] if len(p) > 1 and p[1] == t[1]]
        bare = [x for x in toks if x[2] and x[2][0] == t[1]]
        if uses and not bare and all(u == "store" for u in uses):
            out.append(f"  L{t[0]}: {t[1]} only written")
    if out:
        print(f"{f}:"); print("\n".join(out))
