= A stack, and recursion

The Toy CPU has no stack pointer, no call/return instruction, and no index
register. It is tempting to conclude that recursion is impossible on it. It is
not --- you can build a real call stack by hand, and this chapter shows how.
The worked result is `examples/fibonacci_rec.toys`, which computes Fibonacci
*recursively*.

== The one primitive you need: indirect access

The trick is *self-modifying code*, the same technique the `sum` and `max`
examples use. A two-byte instruction like `load` is an opcode byte followed by
an address byte. If you write those two bytes as data,

```
iop:    20        # LOAD opcode, as a raw byte
iarg:   0         # ← address byte, patched at runtime
```

then storing a value into `iarg` and executing the `iop/iarg` pair loads from
*that* address. That is `*p` --- indirect read. Indirect write works the same
with the STORE opcode. Indirect access is all a stack needs.

== The stack

Reserve a block of memory for the stack and keep one byte, `sp`, holding the
address of the next free slot.

- *push v*: write `v` to `mem[sp]` (an indirect store through `sp`), then
  `sp = sp + 1`.
- *pop*: `sp = sp - 1`, then read `mem[sp]` (an indirect load through `sp`).

The one subtlety: `sp` changes on every push and pop, so the indirect
instruction's address byte must be *re-patched from the current `sp` before
each access*. (This is different from `sum_array.toys`, which patches its pointer once
and then walks it.)

The stack grows upward; there is no hardware bounds check, so a program must
stay within a sensible depth. `--detect-code-overwrite` does not help here (it
watches for stores *below* the data region, but this stack grows up), so the
safe budget is simply: max depth × frame size ≤ free bytes.

== Calling convention

Each call pushes a frame `[return-marker][argument]`. Crucially the return
marker lives *on the stack*, one per activation --- so a recursive call cannot
clobber the outer call's marker. The shared function body:

+ reads its argument from the frame,
+ does its work, pushing and popping its own temporaries (so a recursive call
  gets its own copies --- this is what makes recursion correct),
+ leaves the result in the accumulator,
+ pops the frame and *dispatches* on the return marker: a compare-chain
  (`load marker; ifzero site0; sub 1; ifzero site1; …`) jumps back to whichever
  call site invoked it.

== Recursive Fibonacci

`fib(n) = n` if `n < 2`, else `fib(n-1) + fib(n-2)`, all mod 256. The recursive
body, for the non-base case:

+ compute `n-1` and `n-2` up front (later recursive calls bury the frame, so
  don't rely on `n` staying reachable);
+ push a return marker and `n-1`, jump to `fib`; on return the accumulator holds
  `fib(n-1)`. *Push it onto the stack to save it* --- the next call must not
  destroy it;
+ push a return marker and `n-2`, jump to `fib`; on return the accumulator holds
  `fib(n-2)`;
+ store `fib(n-2)` into a scratch byte (there is only one accumulator), pop the
  saved `fib(n-1)`, and add the scratch --- giving `fib(n-1) + fib(n-2)`;
+ return: pop the frame and dispatch on the marker.

The subtle point --- pointed out during design and confirmed by hand-tracing
`fib(3) = 2` --- is that you must compute and *stash* `fib(n-1)` on the stack
before starting `fib(n-2)`, because both use the same shared body and the same
stack. `examples/fibonacci_rec.toys` is verified against `fib(0..13)`.

== The compiler emits this automatically

This hand-written program was the proof of concept; the C compiler `toycc` now
generates the same kind of stack machinery on its own. It uses a slightly
different but equivalent scheme --- instead of hand-picking what to stack, it
saves the caller's live values around each call and restores them after (see the
recursion section of the previous chapter) --- but the core idea is identical:
a self-modifying-code stack gives each activation its own copies, so recursion
works. `examples/fibonacci_rec.toyc` is the C version of this very program,
compiled and run through the same pipeline.
