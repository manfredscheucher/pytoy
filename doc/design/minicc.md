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
- recursion → there is no stack, so a function cannot call itself directly or
  indirectly; minicc builds the call graph and rejects any cycle
- all optimizations (no constant folding, no peepholes)
- pointers, `&`, compound assignment (`+=`), `for`, `?:`, `switch`, array params
- variable (runtime) shift amounts — only constant shifts

Supported: multiple non-recursive functions (`main` plus helpers, with `int`
parameters and a return value), scalars, 1-D int arrays (with `{...}`
initialisers), `if`/`else`, `while`, `return`, the operators `+ - * & | ^ ~ <<
>>` and the comparisons `== != < > <= >=`, decimal and hex (`0x..`) literals.

Comparisons use the same bit-7 sign trick as toycc (correct for operands that
differ by less than 128) — kept identical so behaviour is consistent between the
two compilers.

## Functions: global slots + marker dispatch

The Toy CPU has no call/return and no stack. minicc uses the same scheme as
toycc but WITHOUT save/restore (which is why recursion is impossible). Each
function `f` gets fixed data bytes and its body is emitted once:

- `f__p_<param>` — one byte per parameter (the caller writes the argument here)
- `f__ret` — one byte (the body writes the return value here)
- `f__mark` — one byte (the caller writes which call-site index called)
- `f__body:` — the single copy of the body
- `f__dispatch:` — a compare-chain over `f__mark` that jumps back to the caller

A call `f(args)` at site `k` stores each arg into its param slot, sets
`f__mark := k`, `goto f__body`, and `f__cont_k: nop` is where control returns;
the value is then in `f__ret`. A `return e` in a helper becomes `eval e; store
f__ret; goto f__dispatch`; in `main` it stays a plain `stop`. Because the slots
are shared across all activations, a recursive re-entry would clobber the
caller's — hence the up-front cycle check.

Local variables and arrays are prefixed per function (`v_<fn>__<name>`,
`adata_<fn>__<name>`) so two functions can reuse the same local name.

## Scope vs. the examples

Main-only examples it compiles correctly: `ifelse`, `sum_array`, `max_array`,
`multiply`, `sevenfold`, `bitops`, `fibonacci_array`, `msb_shift_vs_mask`.

Non-recursive function examples it compiles correctly: `sum3`, `max3`,
`gcd_iter`, `functions`. `fibonacci_iter` and `popcount` also work but land at
exactly 256 bytes (they just fit, since minicc does not optimize).

Known, intended non-fits (not bugs):
- `countdown`, `factorial_iter` use `+=` / `for` (syntax sugar minicc omits).
- `sort_array_function` uses array parameters (`int a[]`), unsupported.
- the recursive `factorial_rec`, `fibonacci_rec`, `gcd_rec` are rejected with a
  clear "recursion is not supported (stackfree)" error — use toycc.
- `sort_array_inline` (259 bytes) and `bigint_add` (373) overflow the 256-byte
  machine because minicc does not optimize. toycc with `-O` fits them.

## Usage

    python3 -m pytoy.minicc examples/c/sum_array.toyc --run

Tested in `tests/test_minicc.py` (core language + the examples above + the
deliberate-limit rejections).
