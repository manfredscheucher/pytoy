# Design: a call stack (and recursion) on the Toy CPU

This is a working design note (spec + derivation), written before the code.
The claim it establishes: **the Toy CPU can support a real call stack, and
therefore recursion**, despite having no stack pointer register, no
call/return instruction, and no index register. It costs self-modifying code,
but it is genuinely possible — not a fake.

## Why this is possible at all

The one primitive we need is **indirect memory access** (load/store through an
address held in a variable). The machine has no index register, but it has
self-modifying code, and the existing `sum_array.toys` / `max_array.toys` examples already
use exactly this:

```
iop:    20        # LOAD opcode as a raw byte
iarg:   0         # ← address byte, patched at runtime with `store iarg`
```

To read `mem[p]`: `load p; store iarg;` then execute the `iop/iarg` pair — it
now loads from address `p`. Storing indirectly works the same way with opcode
21 (STORE). This gives us `*p` (read) and `*p = acc` (write). With indirect
access plus one ordinary byte used as a **stack pointer (SP)**, a stack is just
convention.

## The stack

- Reserve a block of memory for the stack (say addresses `S .. S+N`).
- One byte `sp` holds the address of the next free slot. Initialise `sp = S`.
- **push v**: `mem[sp] = v; sp = sp + 1` — an indirect store through `sp`, then
  increment `sp`.
- **pop -> acc**: `sp = sp - 1; acc = mem[sp]` — decrement `sp`, then an
  indirect load through `sp`.

**Critical (fix 1): the operand byte must be re-patched from the current `sp`
on every push and every pop.** Unlike `sum_array.toys`, which patches its pointer once
and then walks it, `sp` changes on every stack operation, so each access must do
`load sp; store <indirect_op_arg>` immediately before executing the indirect
load/store pair. Patching once at init would read/write a fixed slot and corrupt
the stack.

The stack grows upward. **There is no hardware bounds check.** Note that
`--detect-code-overwrite` does NOT protect this: it only fires on a store *below*
the data region (into code), but this stack grows upward and, on overflow, runs
off the top and wraps mod 256 — it is already corrupting memory before the guard
would notice. So the design must instead reserve a concrete **stack budget**:
`max_depth × frame_size ≤ free bytes`. With 256 bytes shared by code+data, deep
recursion is genuinely limited; document the cap rather than relying on the
overwrite detector.

## Calling convention (no call/return instruction)

The hard part is *return*: a callee must jump back to whichever caller invoked
it, and callers differ. Two honest options:

### Option A — inline expansion (the `inline` keyword)

If a function is marked `inline`, every call site is replaced by a fresh copy
of the body, with its labels and locals renamed per call site. No stack frame,
no return address — the "call" vanishes at compile time. This cannot express
recursion (a body can't inline itself forever), which is the correct and
intuitive limitation of `inline`. Cheap and simple; costs code size.

### Option B — a real stack frame (default functions, incl. recursion)

Non-inline functions get one shared body and a stack frame per call:

1. **Caller**, before jumping in:
   - pushes its **return marker** (a small integer identifying this call site),
   - pushes the **arguments**.
2. **Callee** runs on a fresh frame:
   - reads its parameters from the frame,
   - for its own locals and temporaries, pushes/pops on the stack (so a
     recursive call gets its own copies — this is what makes recursion correct),
   - leaves its result in ACC.
3. **Return**: the callee pops its frame, reads the return marker, and must jump
   back to the right call site.

The return jump is the crux. The machine has no computed goto, so we implement
it as a **return dispatch**: a fixed compare-chain at the end of the callee that
does `load marker; sub K; ifzero ret_site_K; ...` for each call site K, jumping
to a per-call-site continuation label. This is O(number of call sites) code, but
it is static and needs no self-modifying code for the jump itself (only the
stack uses SMC). Each distinct call site gets a distinct marker constant at
compile time.

Recursion works because every activation's data (args, locals, return marker)
lives in its own stack frame, pushed before the recursive call and popped after.
The compare-chain return target is the *call site*, not the activation, so a
function that calls itself twice (like Fibonacci) has two call sites and two
markers, and each returns to the correct continuation.

## Worked example: recursive Fibonacci (the asm proof)

`fib(n) = n if n < 2 else fib(n-1) + fib(n-2)`, all mod 256.

Frame layout per call (pushed by caller, in order): `[return_marker][n]`.
The callee:

1. reads `n` from its frame.
2. if `n < 2`: result = n, go to return.
3. else (compute `n-1` and `n-2` up front — fix 3: after entry, don't assume
   `n` stays reachable, since inner calls bury the frame; derive both values
   before any recursive call):
   - push return_marker=1, push `n-1`; goto fib. On return, ACC = fib(n-1).
     Save it: **push it onto the stack** (it must survive the second call).
   - push return_marker=2, push `n-2`; goto fib. On return, ACC = fib(n-2).
   - **store fib(n-2) into a scratch byte (fix 2: there is only ONE
     accumulator).** Then pop the saved fib(n-1) into ACC, and
     `add scratch` → ACC = fib(n-1) + fib(n-2). A single global scratch byte is
     safe here because no call happens between the pop and the add. General
     rule: any temporary that must survive a recursive call lives on the stack;
     only a truly transient value (no intervening call) may use a global scratch.
4. return: pop the frame, dispatch on the outer return marker back to the caller
   (call site 1, call site 2, or the top-level entry).

The subtlety the user pointed out: **you must compute and stash fib(n-1) before
starting fib(n-2)**, because both use the same shared body and the same stack.
Pushing fib(n-1) onto the stack before the second call is what preserves it —
the second call's frames sit *above* it and are gone by the time we pop it back.
Verified by hand-tracing fib(3) = 2 (fib(1)=1, fib(0)=0 → fib(2)=1; fib(1)=1 →
1 + 1 = 2).

This is the hand-written `fibonacci_rec.toys` we build first, as the concrete
proof that the mechanism works, before teaching the compiler to emit it.

## What the compiler will do

- `inline` functions -> Option A (expand at call sites).
- ordinary functions -> Option B (shared body, stack frames, marker dispatch).
- Recursion is allowed for Option B and rejected for `inline`.
- The stack region is emitted after the `# data` marker so
  `--detect-code-overwrite` guards it.

## Open questions to resolve while building

- Exact frame layout and whether callee-saved temporaries also go on the stack
  (they must, for recursion).
- Stack size default and how to detect overflow gracefully.
- Whether `void` functions are allowed (no return value) — probably yes, they
  just don't leave ACC meaningful.
