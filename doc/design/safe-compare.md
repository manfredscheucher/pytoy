# Spec: `--safe-compare` (full unsigned comparison)

## The problem

toycc's ordering comparisons (`<`, `>`, `<=`, `>=`) use the compact bit-7 trick:
bit 7 of the mod-256 difference `a - b` is read as "a < b". This is correct only
when the operands differ by less than 128. For far-apart unsigned bytes it is
silently wrong — e.g. `10 < 200` yields 0.

A fresh review surfaced this while checking the constant-folding pass: folding a
constant comparison gives the mathematically correct answer, which then disagreed
with the (wrong) runtime path. The bug is in the runtime comparison, pre-dating
the fold work.

## Why not just fix it always

A full unsigned comparison needs ~30 more bytes per compare than the bit-7 trick.
Measured on the tight examples: `sort_array_function` (230 bytes, ~4 compares),
`bigint_add` (237, ~3), `sort3` (129, ~9) would all blow past the 256-byte
machine if every comparison were made correct. The bit-7 trick exists precisely
so these fit.

## Decision

Add it as an opt-in flag, `--safe-compare` (Opts.safe_compare), default OFF.

- OFF (default): the compact bit-7 compare. Examples keep fitting; correct for
  operands < 128 apart.
- ON: a full unsigned compare — bit 7 of the borrow from `a - b`, computed as
  `(~a & b) | (~(a ^ b) & (a - b))`. Correct over all 0..255. Larger code.

It is a correctness/size trade-off, not an optimization, so `-O` / `Opts.all_on()`
does **not** enable it (that would silently grow comparison-heavy programs).

The single helper `CodeGen._gen_cmp_sign(x, y)` leaves a value whose bit 7 is set
iff `x < y`; both comparison call sites (`gen_comparison` value context and
`gen_cond_branch` if/while) then `and 0x80` and branch as before, so only one
place changes behaviour with the flag.

## Verified

`--safe-compare` makes all six relational ops correct for far-apart operands
(e.g. `10 < 200` -> 1) and still agrees with the default for close operands. All
23 C examples still build at default. Tests in `tests/test_toycc.py`
(`test_safe_compare_*`); full suite green.
