#!/usr/bin/env python3
"""Adversarial review harness for the C-source-line annotation feature.

For several programs and option sets, this checks that:
  - the default (annotate_c_lines=False) output has no `@c:` marker;
  - the annotated output assembles to the IDENTICAL memory image;
  - the annotated output is line-for-line the plain output with only a trailing
    `# @c:N` (or ` @c:N` appended to an existing comment) added;
  - it prints, for the recursive toycc case, every code-section instruction line
    and whether it carries a marker (to spot missing/wrong tags by eye).

Run: python3 scripts/review_c_annotation.py
"""
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from pytoy import compiler as toycc
from pytoy import minicc
from pytoy.assembler import assemble, DATA_MARKER


def mem(asm):
    m, _, _, _, errs, _ = assemble(asm)
    assert errs == [], errs
    return m


def strip_marker(a):
    # Two cases _annotate() produces: a fresh "  # @c:N" comment on a line that
    # had none, or " @c:N" appended inside an existing comment. Try the fresh
    # form first (it ends in "  # @c:N"); otherwise strip the appended form.
    if re.search(r"  # @c:\d+$", a):
        return re.sub(r"  # @c:\d+$", "", a)
    return re.sub(r" @c:\d+$", "", a)


PROGS = {
    "nested": """int main(void) {
    int a[3] = {1,2,3};
    int i = 0;
    while (i < 3) {
        if (a[i] > 1) {
            a[i] = a[i] - 1;
        } else {
            a[i] = 0;
        }
        i = i + 1;
    }
    return a[0];
}
""",
    "for_loop": """int main(void) {
    int s = 0;
    for (int i = 0; i < 4; i = i + 1) {
        s = s + i;
    }
    return s;
}
""",
    "recursion": """int f(int n) {
    if (n == 0) return 0;
    return f(n - 1) + n;
}
int main(void) {
    return f(4);
}
""",
}


def check(compile_fn, src, opts_variants, label):
    for opts, olabel in opts_variants:
        kw = {} if opts is None else {"opts": opts}
        plain = compile_fn(src, "t", **kw)
        ann = compile_fn(src, "t", annotate_c_lines=True, **kw)
        assert "@c:" not in plain, (label, olabel)
        assert mem(plain) == mem(ann), f"IMAGE DIFF {label} {olabel}"
        pl, al = plain.splitlines(), ann.splitlines()
        assert len(pl) == len(al), f"LINE COUNT DIFF {label} {olabel}"
        for p, a in zip(pl, al):
            assert strip_marker(a) == p, (
                f"MISMATCH {label} {olabel}\n  plain={p!r}\n  ann  ={a!r}")
        print(f"OK {label} {olabel}")


def main():
    for name, src in PROGS.items():
        check(toycc.compile_source, src,
              [(None, "plain"), (toycc.Opts.all_on(), "allon")],
              f"toycc {name}")
    # minicc: no recursion, no for-loop, no compound assign. Use a program it
    # can actually compile that still exercises while/if/else + arrays.
    mini_src = """int main(void) {
    int a[3] = {1,2,3};
    int i = 0;
    while (i < 3) {
        if (a[i] > 1) {
            a[i] = a[i] - 1;
        } else {
            a[i] = 0;
        }
        i = i + 1;
    }
    return a[0];
}
"""
    check(minicc.compile_source, mini_src, [(None, "plain")], "minicc nested")

    print("--- missing-marker scan (toycc recursion, annotated) ---")
    ann = toycc.compile_source(PROGS["recursion"], "t", annotate_c_lines=True)
    code_part = ann.split(DATA_MARKER)[0].splitlines()
    for ln in code_part:
        body = ln.split('#', 1)[0].strip()
        if not body:
            continue
        has = "@c:" in ln
        print(f"{'   ' if has else 'NO '} {ln}")


def check_directive_passthrough():
    """`// pytoy:` directives are passed through by rewriting the whole asm
    text; make sure that doesn't strip or corrupt @c markers."""
    src = ("// pytoy: out=dec\n"
           "int main(void) {\n"
           "    int x = 5;\n"
           "    return x;\n"
           "}\n")
    ann = toycc.compile_source(src, "t", annotate_c_lines=True)
    assert "# pytoy: out=dec" in ann, "directive lost"
    assert "@c:" in ann, "markers lost after directive passthrough"
    plain = toycc.compile_source(src, "t")
    assert mem(plain) == mem(ann), "directive+annotation changed image"
    print("OK toycc directive-passthrough + annotation")


def check_id_collision_stress():
    """Stress the id()-keyed carry: force GC between compiles and verify every
    annotated line ends in a well-formed `@c:<digits>` and the image is
    unchanged. A mis-tag from id() reuse wouldn't change the image (comments are
    inert), but a freed-and-reused id could attach a marker to a line that has
    no C origin, or a garbled one -- which this would surface."""
    import gc
    bad = 0
    for _ in range(300):
        gc.collect()
        for _name, src in PROGS.items():
            for opts in (None, toycc.Opts.all_on()):
                kw = {} if opts is None else {"opts": opts}
                plain = toycc.compile_source(src, "t", **kw)
                ann = toycc.compile_source(src, "t", annotate_c_lines=True, **kw)
                if mem(plain) != mem(ann):
                    bad += 1
                for a in ann.splitlines():
                    if "@c:" in a and not re.search(r"@c:\d+$", a):
                        print("GARBLED:", repr(a))
                        bad += 1
    print(f"OK id-collision stress ({'clean' if bad == 0 else f'{bad} FAIL'})")


if __name__ == "__main__":
    main()
    check_directive_passthrough()
    check_id_collision_stress()
