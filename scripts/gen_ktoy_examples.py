#!/usr/bin/env python3
"""
Generate ktoy's ExampleSources.kt from the pytoy example programs.

The Kotlin app has no filesystem access to pytoy's examples/, so the bundled
programs are embedded as Kotlin strings. This regenerates that file from the
canonical .toys / .toyo sources, so the two never drift.

Run from the pytoy repo root:
    python3 scripts/gen_ktoy_examples.py

Writes:
    ~/github/ktoy/composeApp/src/commonMain/kotlin/dev/scheucher/ktoy/core/ExampleSources.kt
"""

import os

PYTOY = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ASM_DIR = os.path.join(PYTOY, "examples", "asm")
TOYO_DIR = os.path.join(PYTOY, "examples", "toyo")
OUT = os.path.expanduser(
    "~/github/ktoy/composeApp/src/commonMain/kotlin/dev/scheucher/ktoy/core/"
    "ExampleSources.kt")


def kotlin_triple_string(s):
    """Embed s in a Kotlin raw (triple-quote) string. Raw strings can't contain
    a literal triple-quote or a $ (interpolation), so guard against both — the
    current examples have neither, but fail loudly if that ever changes."""
    if '"""' in s:
        raise ValueError("example contains a triple-quote; can't embed raw")
    if '$' in s:
        raise ValueError("example contains '$'; would break Kotlin interpolation")
    return f'"""{s}"""'


def main():
    lines = [
        "package dev.scheucher.ktoy.core",
        "",
        "/**",
        " * The bundled example programs, embedded as strings so they ship inside",
        " * the app (and the tests) with no filesystem access.",
        " *",
        " * GENERATED from pytoy examples/ by scripts/gen_ktoy_examples.py — do not",
        " * edit by hand; regenerate when the .toys / .toyo sources change.",
        " */",
        "",
        "data class Example(val name: String, val kind: ExampleKind, val source: String)",
        "",
        "enum class ExampleKind { ASM, TOYO }",
        "",
        "val EXAMPLES: List<Example> = listOf(",
    ]
    for f in sorted(os.listdir(ASM_DIR)):
        if not f.endswith(".toys"):
            continue
        name = f[:-5]
        src = open(os.path.join(ASM_DIR, f)).read()
        lines.append(f'    Example("{name}", ExampleKind.ASM, '
                     f'{kotlin_triple_string(src)}),')
    for f in sorted(os.listdir(TOYO_DIR)):
        if not f.endswith(".toyo"):
            continue
        name = f[:-5]
        src = open(os.path.join(TOYO_DIR, f)).read()
        lines.append(f'    Example("{name} (bytecode)", ExampleKind.TOYO, '
                     f'{kotlin_triple_string(src)}),')
    lines.append(")")
    lines.append("")

    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "w") as fh:
        fh.write("\n".join(lines))
    print(f"wrote {OUT} ({len(lines)} lines, "
          f"{sum(1 for l in lines if l.startswith('    Example'))} examples)")


if __name__ == "__main__":
    main()
