# Design: recursion via uniform save/restore (with an opt-out flag)

Working design note (spec + derivation), written before the code. Establishes
how `toycc` compiles function calls so that recursion works, using ONE uniform
mechanism.

## Decisions (from Manfred)

- **Uniform save/restore, no call-graph needed for correctness.** Every function
  keeps its fixed global slots (params, locals, return value, return marker),
  exactly like the current non-recursive scheme. Recursion-safety comes from
  *saving and restoring the caller's live slots around every call*. Because
  save/restore is always correct (just sometimes unnecessary), we do it for
  *every* call by default and drop the separate recursive/non-recursive code
  paths. Recursion then works for free.
- **Real stack, growing downward from the top.** Code+data occupy low memory
  from 0 up (PC starts at 0); the stack lives at the top and grows down. `sp`
  starts high and decreases on push. They meet in the middle; overflow = they
  collide (no hardware check).
- **Optimisation flag `-O` / `--optimize-save-restore`, default OFF.** When set,
  the compiler builds the call graph and *omits* save/restore around calls to
  functions that are not recursive (directly or mutually) — those calls can't
  re-enter the caller, so the caller's slots can't be clobbered. This is a pure
  optimisation: it only removes provably-unnecessary save/restore, never changes
  results. Default off keeps the compiler behaviour simple and uniform; the call
  graph becomes an optimisation input, not a correctness prerequisite.

## Trade-off (recorded honestly)

Uniform save/restore makes the compiler simpler (one path, no recursion
rejection) but the emitted assembly larger (push/pop brackets around every
call, even where unnecessary). On a 256-byte machine that matters, which is why
`-O` exists. Neither choice is strictly "better"; default = simple, `-O` = lean.

## Stack primitives

One byte `sp` = current top of stack. push decreases `sp`, pop increases it.
Indirect access via self-modifying code (patch a raw load/store's address byte
from `sp` before each access — re-patched every time because `sp` moves), the
same technique as `examples/asm/sum_array.toys`. push/pop are short inline sequences, no subroutine.

## A call, compiled (default: always save/restore)

At a call site inside function `C` (the caller) calling `f`:

1. **Save**: push every live slot of the CALLER `C` — all of `C`'s param slots,
   local slots, and `C__mark`. (Not the callee's slots. For direct self-
   recursion caller==callee so it's the same set; for mutual recursion they
   differ — the rule is always *the caller's* live slots. This was the subtle
   point flagged in the earlier draft and is now fixed.)
2. **Set up**: evaluate arguments into `f`'s parameter slots, set `f__mark` to a
   fresh call-site marker, `goto f__body`.
3. **Result**: on return the value is in `f__ret`; copy it into a fresh temp
   immediately.
4. **Restore**: pop the saved slots in reverse order, restoring `C`'s own
   params/locals/marker exactly as before the call.
5. The call's value is the temp from step 3.

Between save and restore the callee may clobber any shared slots (including by
recursing); the caller's values are safe on the stack. This generalises exactly
what `examples/asm/fibonacci_rec.toys` does by hand.

Why save the *caller's* slots and not the callee's: the danger is that the
callee (or something it calls, transitively) re-enters `C` and overwrites `C`'s
shared slots while `C` is mid-computation. Saving `C`'s slots before the call
and restoring after makes `C` immune to that, whoever it calls.

## Return: marker dispatch (unchanged)

`return e` -> `store f__ret; goto f__dispatch`; `f__dispatch` is a compare-chain
on `f__mark` back to the right call site. `f__mark` is saved/restored around
calls, so an outer activation's marker survives inner calls.

## The `-O` optimisation

With `-O`, build the call graph and compute the set of recursive functions
(functions on a cycle). At a call site in caller `C`:
- if `C` is NOT recursive, the call can never re-enter `C`, so *skip the entire
  save/restore*. (A non-recursive `C` has at most one activation live at a time.)
- if `C` IS recursive, keep save/restore.

That's the whole optimisation: recursive callers keep their brackets,
non-recursive callers lose them. Provably safe; only removes dead save/restore.

## What must be saved — the live-across set (LIVENESS IS REQUIRED)

**Correction after review — the naive "save all named slots" rule is WRONG.** It
miscompiles `fib(4)` (computes 2 instead of 3), because it forgets the anonymous
compiler *temps* that hold live intermediate values.

Concrete failure: `return fib(n-1) + fib(n-2);` compiles to: call fib(n-1),
capture its result into a shared `callret` byte, call fib(n-2), add. But there is
ONE body copy of fib, so `callret` for site 0 is a single fixed byte. When
fib(n-2) runs, it internally re-executes site 0 and **overwrites that byte** —
destroying fib(n-1)'s saved result. So the result of the first call, held in a
temp across the second call, MUST be saved/restored too.

The correct rule: at a call site in caller `C`, save exactly `C`'s slots that are
**live across this call** = written before the call and used after it. That set
is:

- real C locals `C__l_<local>` that are live across the call,
- compiler temps holding still-needed values (a sibling call's result, an
  argument being assembled) that are live across the call,
- `C__mark` (needed for `C`'s own eventual dispatch).

It does NOT include:

- `f__ret` (an output, written by the callee),
- **the temp that captures THIS call's return value** — by construction it is
  written *after* the call, so it is not live *before* the call and is never in
  the live-across set. This is what makes it safe: capture `f__ret` into that
  temp after the call, and restore (which only pops the saved live-across set)
  cannot overwrite it.

Implementation: a live-variable analysis over the lifted per-function body gives
this set directly (the capture temp falls out automatically as not-live-before).
This is more work than "save everything," but it is required for correctness —
there is no shortcut that ships a correct `fib`.

## Ordering invariant (must not be reordered)

1. Save pushes `C__mark` (and the live set) BEFORE set-up overwrites `f__mark`.
2. Restore pops `C__mark` BEFORE this activation reaches its own
   `goto f__dispatch`.

The step order (save → set-up/setmark → goto → capture ret → restore, with
dispatch later in the body) satisfies both. The outermost marker is main's
call-site marker, so the final dispatch returns into main (top-level
termination), like the `top:`/marker-0 convention in `examples/asm/fibonacci_rec.toys`.

## sp convention (fixed)

`sp` points at the last-pushed byte; the stack grows DOWN from the top:

- push v: `sp := sp - 1; mem[sp] := v`
- pop -> v: `v := mem[sp]; sp := sp + 1`

Exact inverses. `sp` starts one past the top usable byte. (Note: the hand-written
`examples/asm/fibonacci_rec.toys` uses the opposite — sp=next-free growing UP — so its push/pop
must be inverted here, not copied.) Overflow (sp reaching the data region) is
unchecked; document a depth cap.

## Budget

Each save/restore pushes (caller's params + locals + 1 marker) bytes per call,
per recursion level. With 256 bytes shared, depth is limited; document the
rough cap. No hardware overflow check.

## Resolved by review

An architecture review hand-traced `fib(3)`, `fib(4)`, and `is_even(2)` and
confirmed:

- **Caller-save is correct** for both self- and mutual recursion. When a callee
  clobbers the caller's shared slots (directly or via a recursive re-entry), the
  caller has already pushed them.
- **Marker routing is correct across functions.** Continuation labels
  (`f__cont_k`) live physically at the caller's site but are keyed by the callee
  and a globally-unique site index, so dispatch returns to the right place even
  in mutual recursion.
- **`-O` skip is airtight**: skip iff the CALLER is non-recursive (on no cycle),
  because there are no shared mutable globals beyond per-function slots, so a
  non-recursive caller's slots can never be clobbered.
- **The one real bug** in the first draft was the save set: it must be the
  live-across set (locals + live temps + mark), NOT "all named slots." Fixed
  above — this is the crux of a correct implementation.
