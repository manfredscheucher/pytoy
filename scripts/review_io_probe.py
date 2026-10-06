#!/usr/bin/env python3
"""Ad-hoc probes used during the I/O/compiler review. Checks the ascii_X
case-collision, the sign-bit copy-loop for large/zero counts, and a few
compile paths for the new builtins and && / ||."""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from pytoy.compiler import compile_source, _const_name
from pytoy.assembler import assemble


def probe(title, src):
    print("=" * 70)
    print(title)
    print("-" * 70)
    try:
        asm = compile_source(src, "probe")
    except Exception as e:
        print("COMPILE ERROR:", type(e).__name__, e)
        return None
    mem, listing, syms, data_addrs, errors, data_start = assemble(asm)
    if errors:
        print("ASM ERRORS:", errors)
    return asm, syms


# 1) ascii_X case collision: 'H'=72 and 'h'=104 both -> ascii_h after the
#    assembler lowercases labels.
print("_const_name(72)=", _const_name(72), " _const_name(104)=", _const_name(104))

r = probe("H vs h both used", """
int main() {
    int a;
    int b;
    a = 'H';
    b = 'h';
    return a;
}
""")
if r:
    asm, syms = r
    print("ascii_h symbol value:", syms.get("ascii_h"))
    # show the two const definitions in the asm
    for ln in asm.splitlines():
        if "ascii_h" in ln.lower():
            print("  DEF/USE:", ln)

# 2) sign-bit copy loop: build a program that does write(buf, k) and inspect
#    nothing at runtime here (headless), just confirm it compiles for k large.
probe("write with k as literal 200 (>127)", """
int main() {
    int buf[3];
    buf[0] = 1;
    write(buf, 200);
    return 0;
}
""")

probe("write(buf, 0)", """
int main() {
    int buf[3];
    write(buf, 0);
    return 0;
}
""")

# 3) read in a while condition (re-eval each iteration)
probe("while(read(buf)) {}", """
int main() {
    int buf[3];
    while (read(buf)) {
        buf[0] = buf[0];
    }
    return 0;
}
""")

# 4) builtin inside recursive function
probe("read inside recursive fn", """
int f(int n) {
    int buf[2];
    if (n == 0) { return 0; }
    read(buf);
    return f(n - 1);
}
int main() {
    return f(3);
}
""")

# 5) && with calls rejected (both operands, nested)
probe("call inside && (should reject)", """
int g() { return 1; }
int main() {
    int x;
    x = 1 && g();
    return x;
}
""")

# 6) &a[const] addrof still works
probe("&a[2] addrof", """
int main() {
    int a[5];
    int *p;
    p = &a[2];
    return 0;
}
""")

# 7) char literal edge cases
for lit in ["''", "'ab'", "'\\q'"]:
    probe(f"char literal {lit}", f"""
int main() {{
    int a;
    a = {lit};
    return a;
}}
""")
