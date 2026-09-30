# Spec: example programs, organised in three tiers

## What Manfred asked for

Small, loadable, runnable example programs that let you *see what each thing
does*. Three tiers, from single opcodes up to full programs. The `01-basics/`
and `02-extended/` files must be as short as possible with minimal inline
comments — self-explanatory from the code where feasible; the longer
explanation lives here in `doc/`.

## Folder layout (under `examples/asm/`)

- **`01-basics/`** — one file per Toy CPU opcode, `00_stop` … `13_nop` (14
  files). Each isolates a single instruction and ends in a state that shows its
  effect: usually `ACC` (result line / CPU panel), except `STORE` (shown via a
  memory cell 0 → 42) and `NOP` (the point is "no change"). Jumps use a skipped
  `load y` (99) vs. taken `load x` (42) so the branch shows in the final ACC.
- **`02-extended/`** — small *concept* demos above the single-opcode level, but
  still minimal (see below).
- **`03-programs/`** — the full worked programs (fibonacci, multiply, the
  array sum/max/sort, recursive fibonacci, …). Previously the top level of
  `examples/asm/`.

## The extended concepts

This machine has **no indexed addressing and no compare instruction**. The
extended demos show the standard ways around that.

- **`load_indirect.toys`** — read `data[i]`. Compute the address `data + i`,
  patch it into the address byte of a raw `LOAD` (opcode 20), then run that
  LOAD. `stop` immediately after, or execution runs into the data. Uses the 10
  digits of pi as the array; `i=5` → ACC = 9.
- **`store_indirect.toys`** — the write counterpart: patch the address byte of a
  raw `STORE` (opcode 21). `i=3`, `val=42` → `data[3]` goes 0 → 42.
- **`compare.toys`** — `a < b` without a compare opcode: compute `a - b` (wraps
  mod 256); if bit 7 is set the subtraction underflowed, so `a < b`. `AND 128`
  isolates that bit, `IFZERO` branches on it. `a=3, b=5` → ACC = 1.
- **`negate.toys`** — two's complement: `0 - x`. `x=5` → 251 (= −5 mod 256).
- **`bit_set_clear_toggle.toys`** — one-bit masking: `OR mask` sets bit 3,
  `XOR mask` toggles it, `AND (NOT mask)` clears it. Results in `r_set`,
  `r_toggle`, `r_clear`.

The self-modifying trick (patch an instruction's operand byte, then execute it)
is exactly what the `03-programs/` array examples and the C compiler's arrays
use — the extended demos just isolate it.

## ktoy embedding

Only `03-programs/` is embedded into the ktoy app (`gen_ktoy_examples.py` reads
that folder). `01-basics/` and `02-extended/` stay out, so the app's example
list stays lean.

## Verified

All `01-basics/` (14) and `02-extended/` (5) assemble and run
(`run.py sim … --cli --run`) with the expected ACC / memory result. The
`03-programs/` move keeps `test_toyasm.py` green (paths updated) and the ktoy
embedded list unchanged.

`scripts/gen_golden.py` now recurses into the three tier folders, so the golden
table (`tests/golden/asm_golden.json`, checked by `test_golden.py`) covers all
29 examples, not just the 10 programs. Full suite: 242 passed.
