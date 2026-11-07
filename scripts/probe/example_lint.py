"""Checks the example header format and banned phrases (style: example/description/steps/result)."""
import glob, os, re, sys
ROOT = os.path.join(os.path.dirname(__file__), "..", "..", "examples")
files = sorted(glob.glob(ROOT + "/asm/**/*.toys", recursive=True) + glob.glob(ROOT + "/c/**/*.toyc", recursive=True))
BAD = [r"—", r"\bpytoy\b(?!:)", r"\bktoy\b", r"toycpu", r"acc stays", r"as expected", r"of course", r"\bsimply\b", r"note that", r"\bGUI\b", r"\bpanel\b", r"\bslides?\b"]
problems = 0
def report(path, msg):
    global problems
    problems += 1
    print(os.path.relpath(path, ROOT), "::", msg)
for path in files:
    p = "//" if path.endswith(".toyc") else "#"
    lines = open(path).read().split("\n")
    keys = []
    for l in lines:
        m = re.match(re.escape(p) + r" (example|description|steps|result|expect): ", l)
        if m:
            keys.append(m[1])
        elif re.match(re.escape(p) + r" {3,}", l) and keys and keys[-1] == "description":
            continue
        elif keys:
            break
    io = "04-io" in path
    if lines[0].split(":")[0] != p + " example":
        report(path, "first line is not the example line: " + lines[0][:50])
    want = ["example", "description"] if io else ["example", "description", "steps", "result"]
    if keys[:len(want)] != want and keys != ["example", "description", "steps", "result"]:
        report(path, f"header keys {keys}")
    for i, l in enumerate(lines, 1):
        c = l.split(p, 1)[1] if p in l else ""
        for b in BAD:
            if re.search(b, c):
                report(path, f"line {i}: banned '{b}': {l.strip()[:70]}")
        if re.search(r"\bbit 7\b", c) and any("MSB" in x for x in lines):
            report(path, f"line {i}: mixes bit 7 and MSB")
        if "MSB" in c and "most significant bit" not in "\n".join(lines[:i]):
            report(path, f"line {i}: MSB before it is explained")
        if "LSB" in c and "least significant bit" not in "\n".join(lines[:i]):
            report(path, f"line {i}: LSB before it is explained")
    d = next((l for l in lines if l.startswith(p + " description: ")), "")
    if len(d) > 100:
        report(path, f"long description line ({len(d)})")
print(len(files), "files,", problems, "problems")
