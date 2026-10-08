# Design: PIN security teaching example

A design note for the security-basics material built around the `pin_check`
example. It records what Manfred asked for, the decisions taken, and how the
pieces (examples, simulator features, slides) fit together, so the whole thing
can be checked against the intent.

The goal is a small, concrete story: a 4-digit PIN guards a secret, and we walk
through how an attacker beats a naive check — brute force, reading the bytecode,
side channels, fault injection — and what each countermeasure does and does not
buy. The Toy CPU is simple enough that every attack is demonstrable live in the
simulator.

## The running example

`pin_check` checks a 4-digit PIN against **1337**. Right PIN reveals the secret
**42** (the Answer to Life, the Universe and Everything, Hitchhiker's Guide):
the accumulator holds 42 at STOP, and the io cells spell `succ`. Wrong PIN
returns 0 and spells `fail`.

- `examples/asm/04-io/pin_check.toys` — assembly, runs end to end.
- `examples/c/04-io/pin_check.toyc` — the C source it mirrors.

Input is ASCII: the user types `1`,`3`,`3`,`7` into io0..io3 and sets `ready`
to submit. The expected digits live in memory as the ASCII codes 49,51,51,55.

The naive check compares one digit at a time and **bails on the first
mismatch**:

```
        load  io0
        sub   pin0
        ifzero ok0         # matched -> check next digit
        goto  fail         # mismatched -> fail
ok0:    load  io1
        ...
```

That early-out is the vulnerability the story turns on.

## The attacks, in order (and why this order)

Manfred asked for this ordering: brute force, then reading the bytecode, then
**side channels**, then **fault injection last**. The reasoning: side channels
are exploitable **remotely** (just measure timing or power), while fault
injection **requires physical hardware access** and usually a more expensive
setup. So side channels are the cheaper, more broadly applicable class and come
first; fault injection, needing a lab, comes last. Countermeasures against the
side channels sit between the two.

### 1. Brute force

An n-digit PIN has `10^n` possibilities. n=4 → 10000. On average you find it
after half the attempts, but a factor of 2 is not real protection — it is still
`10^n / 2`. The cost is linear in the number of PINs and exponential in the
number of digits. This is the baseline every smarter attack improves on.

### 2. Reading the bytecode (obfuscation)

If the attacker can read the program's bytes, the PIN is simply there: the
`pin0..pin3` cells literally hold 49,51,51,55. No work required.

Countermeasure direction: do not store the PIN in the clear. **Compute** each
expected digit at runtime from other values, so no memory cell ever literally
contains the digit codes — split a digit across cells, derive it by arithmetic,
reconstruct it only during the compare. This is obfuscation, a large topic of
its own ("blow up" the code so the constant never appears). Be honest about the
limit: obfuscation raises the bar, it does not make extraction impossible — the
computation that reconstructs the PIN is still there to be traced.

### 3. Side channels (remote)

**Timing.** Because the naive check bails at the first wrong digit, a wrong
first digit stops sooner than a wrong last digit. Run time (in pytoy, the step
count) leaks **where** the first mismatch is. That collapses brute force into a
digit-by-digit attack:

- First round: run with `0000`, `1000`, `2000`, …, `9000` and record steps-to-
  stop. The input that runs **longest** got past digit 0, so its first digit is
  correct. Keep it.
- Repeat per digit. Total ≈ `n * 10` = 40 runs instead of `10^4`.

Illustrative pytoy step counts for the naive asm: a wrong first digit halts
around 16 steps; a guess that gets the first digit right (wrong later) runs
further, ~25 steps. The exact numbers do not matter — **more steps means you got
further**, and that is the leak. (`tests/test_pin_examples.py` asserts the naive
version's step count differs by first-mismatch position, and that the hardened
version's does not.)

**Power.** Different inputs can draw different power, which also leaks. pytoy can
**fake** a power measurement: count the 1-bits across all machine state (256
memory bytes + ACC + PC = 258 bytes × 8 bits) and report that count as "power".
If the bit-count trajectory differs by input, that is a leak. (Simulated power,
for teaching — see the "Extra info" panel below.)

**Cache / memory-access timing.** On real machines, instructions differ in cycle
count; cached data is fast, memory/disk slow; lazy/on-demand computation is
efficient but its timing reveals what was or was not needed; branch prediction,
pipelining and prefetch make the predicted branch faster, so a mispredicted
branch (condition not as predicted, other branch not prefetched) runs slower and
leaks which branch was taken. pytoy simulates direct-mapped caches of size
8/16/32/64 and counts hits: different data → different hit counts → different
timing in a real machine.

### Countermeasures (timing / side channels)

Make the check **constant-time**: never branch on a single digit. Compute
`(entered XOR expected)` for **every** digit — 0 iff that digit matches — and OR
them all together:

```
diff = (io0 ^ pin0) | (io1 ^ pin1) | (io2 ^ pin2) | (io3 ^ pin3)
```

`diff == 0` if and only if all four digits are correct. Which digit is wrong is
irrelevant to control flow; the only fact used is `diff == 0` at the end. Then a
**single** final conditional: `if diff == 0: return 42 else return 0`. Every run
executes the same instructions in the same order, so timing no longer depends on
the input.

This is `pin_check_hardened` (`examples/asm/04-io/pin_check_hardened.toys` and
`examples/c/04-io/pin_check_hardened.toyc`). The C version writes it as one
expression and unrolls the compare by hand (no `pin[]` array, no `for`) to fit
the 240-byte machine.

Faking/masking power (equalizing work so draw does not track the data) is harder;
defeating real power analysis is non-trivial. State the limit honestly:
countermeasures against **all** fault attacks and side channels are non-trivial.

### 4. Fault injection (needs hardware access — last)

Equality on the Toy CPU is `x - y` then `IFZERO`. If the attacker can poke the
hardware and force **ACC = 0** just before the `IFZERO`, the comparison sees 0
instead of the real difference, so the check passes for **any** input.

Live demo in pytoy: step up to the `IFZERO`, right-click the accumulator, Edit it
to 0, and the wrong PIN is accepted. (PC can likewise be edited to jump straight
past the check.) This is what the ACC/PC-edit simulator feature below is for.

Connection to hardening: constant-time killed the timing leak but concentrated
the decision into a **single** final `diff == 0` check — now the one spot a
one-shot fault targets. In the naive version, four separate compares meant a
fault attack had to skip all four (≈4 injections); the hardened version has one.
So hardening against timing can make the fault-injection target easier. Trade-
offs everywhere.

### Closing

The whole system is only secure if **both** software and hardware are secure.
The most secure software is useless if the hardware leaks via timing, power, or
faults; the most secure hardware is useless if the software leaks the secret.
Both must hold.

## Simulator features this material needs

These are specified for the pytoy/ktoy code in `TODO-security-extras.md` (a
separate agent implements them). Recorded here so the spec lives with the rest:

1. **Right-click edit of ACC and PC.** Memory cells are already right-click
   editable; ACC and PC are not. Making them editable (reusing the existing
   `ValueDialog`, undoable like a step) powers the fault-injection demo. Editing
   PC must re-home the PC highlight (the yellow current-instruction bytes and the
   `>>` marker).

2. **Optional "Extra info" panel** (View menu toggle, off by default, shown below
   the I/O panel):
   - `steps` — total steps.
   - `steps1` / `steps2` — count of 1-byte / 2-byte instructions (`steps1 +
     steps2 == steps`).
   - `jumps` — taken jumps: every `goto`, plus every `ifzero` that actually
     branched (ACC==0); a fallen-through `ifzero` does not count.
   - `cachehits` — `{8, 16, 32, 64}` hit counts from the cache simulator.
   Counters update every step (cheap); only the widget render is gated on
   visibility, so there is no cost when hidden.

3. **Cache simulator** (`Cache` class, direct-mapped, keyed by `addr % size`,
   counts hits only). Four instances for sizes 8/16/32/64. On each executed
   instruction it is fed the touched addresses in execution order: the opcode
   byte at PC, the operand byte at PC+1 (two-byte instructions), then the data
   address for instructions that dereference it (`load/store/add/sub/and/or/xor`;
   `goto`/`ifzero` use their operand as a jump target, not a RAM access, so they
   do not feed the data address). Data is fed last, so on a slot collision with
   PC/PC+1 the data access wins the slot. This models how data-dependent access
   patterns become a timing side channel.

## Verified

- `tests/test_pin_examples.py`:
  - naive asm `pin_check` returns 42 for 1337, 0 for wrong PINs.
  - C `pin_check` compiles and loads the secret 42 (the C `read()` clears
    `ready` before polling, so it cannot run headless — busy-poll only works in
    the GUI; the asm test covers the identical compare logic end to end).
  - hardened asm `pin_check_hardened` returns 42 / 0 correctly **and** is
    constant-time: all wrong PINs take the same step count, while the naive
    version's step count varies with the first-mismatch position.
  - hardened C compiles within the 240-byte budget.
- All four examples are picked up by `pytoy/examples_index.py` under `04-io`.
