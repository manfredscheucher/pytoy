# minicc — the minimal didactic compiler

## What Manfred asked for

A separate, standalone compiler written for readability: everything optional
stripped out, no stack, no recursion, no folding or other clever passes. The
point is that the code is minimal, overseeable and well-readable, yet still
translates most of the simple examples to correct assembly.

## What it is

`pytoy/minicc.py` — a single short file, read top to bottom: lexer, parser, code
generator. It is the teaching sibling of the full `toycc` (`pytoy/compiler.py`),
which stays as the feature-complete compiler.

Deliberately left out (use toycc for these):
- functions other than `main` → no call stack, no save/restore, no recursion
- all optimizations (no constant folding, no peepholes)
- pointers, `&`, compound assignment (`+=`), `for`, `?:`, `switch`
- variable (runtime) shift amounts — only constant shifts

Supported: scalars, 1-D int arrays (with `{...}` initialisers), `if`/`else`,
`while`, `return`, the operators `+ - * & | ^ ~ << >>` and the comparisons
`== != < > <= >=`, decimal and hex (`0x..`) literals.

Comparisons use the same bit-7 sign trick as toycc (correct for operands that
differ by less than 128) — kept identical so behaviour is consistent between the
two compilers.

## Scope vs. the examples

minicc targets the single-function examples in `examples/c/`. It compiles these
correctly: `ifelse`, `sum_array`, `max_array`, `multiply`, `sevenfold`,
`bitops`, `fibonacci_array`, `msb_shift_vs_mask`.

Known, intended non-fits (not bugs):
- `countdown` uses `+=` / `for` (syntax sugar minicc omits).
- `sort_array_inline` (259 bytes) and `bigint_add` (373) overflow the 256-byte
  machine because minicc does not optimize. toycc with `-O` fits them.

## Usage

    python3 -m pytoy.minicc examples/c/sum_array.toyc --run

Tested in `tests/test_minicc.py` (core language + the examples above + the
deliberate-limit rejections).
