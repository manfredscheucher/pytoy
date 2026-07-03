# Writing programs

This page builds up from a straight-line program to loops, conditionals, and
a couple of advanced tricks. Each example is in the
[`examples/`](../examples/) folder — run them and watch them step (see
[usage.md](usage.md)).

Before starting, make sure you're comfortable with the
[concepts](concepts.md): memory boxes, the accumulator, the program counter,
and that every calculation flows through the accumulator.

## 1. Straight-line: `a + b + c`

The simplest programs just do one thing after another. Load a value, combine
in more values, stop. `sevenfold.toy` computes `7 * a` with only adds:

```
        load  a         # acc = a
        add   a         # acc = 2a
        store b         # b = 2a
        load  b
        add   b         # acc = 4a
        store c         # c = 4a
        load  a
        add   b
        add   c         # acc = a + 2a + 4a = 7a
        stop

a:      4
b:      0
c:      0
```

The pattern to internalize: **`load` to start a calculation, `add`/`sub` to
build it up, `store` to save an intermediate, `stop` when done.** Notice the
data (`a`, `b`, `c`) sits after `stop` so it's never executed.

## 2. Loops and counters: multiply by repeated addition

The Toy CPU has no multiply instruction, so you build it. Keep a counter in
memory, do work each pass, decrement the counter, and jump back until it hits
zero. `multiply.toy` computes `a * b`:

```
        load  a         # acc = a  (used as loop counter)
loop:   ifzero done     # counter == 0 -> exit the loop
        load  sum
        add   b         # sum += b
        store sum
        load  a
        sub   one       # a--
        store a
        goto  loop      # back to the top

done:   load  sum       # result in accumulator
        stop

a:      7
b:      6
sum:    0
one:    1
```

The loop skeleton here is worth memorizing — nearly every Toy CPU loop looks
like it:

1. `ifzero` at the top checks the exit condition.
2. The body does the work.
3. A counter is decremented with `sub one`.
4. `goto` jumps back to the top.

## 3. Conditionals from `ifzero` + `xor`

`ifzero` is the *only* branch instruction, so every decision is phrased as
"is this value zero?". Two useful reductions:

- **Equality:** `xor` two values. The result is `0` exactly when they're
  equal. Follow with `ifzero` to branch on "equal".
- **Countdown to a condition:** `sub` until you reach `0`, then `ifzero`.

`fibonacci.toy` uses the countdown form to run its loop `n` times:

```
        load  n
loop:   ifzero end      # done after n iterations
        ...             # (compute next Fibonacci number)
        load  n
        sub   one
        store n         # n--
        goto  loop
end:    load  a
        stop
```

## 4. Advanced: self-modifying code for arrays

The Toy CPU has no index register, so to walk through an array you modify the
program itself while it runs — because code and data are the same memory,
you can `store` a new address into an instruction's operand byte.

`sum.toy` and `max.toy` do this. The key trick is writing a `load` as two raw
bytes so the address byte is a normal, patchable memory box:

```
iop:    20                # LOAD opcode, as a raw data byte
iarg:   0                 # ← the address byte, overwritten each pass
        add   result
```

Each iteration, the program does `load iarg; add one; store iarg` to bump
`iarg` to the next array element. It's a genuine machine-language technique
(and a good demonstration of *why* code and data sharing memory is powerful —
and dangerous). Read the comments in those files for the full walkthrough.

## Tips for writing your own

- **Sketch on paper first.** Decide your variables and the loop shape before
  writing instructions — the original Toy CPU author recommends the same.
- **Put all data after a `stop` or `goto`** so it's never executed.
- **Watch for wraparound.** Values are mod 256; `fib(14) = 377` overflows, so
  `fibonacci.toy` only works up to `n = 13`.
- **Step through in the GUI** when something's wrong — watching the PC move
  and the accumulator change makes bugs obvious.

Next: **[using pytoy](usage.md)**.
