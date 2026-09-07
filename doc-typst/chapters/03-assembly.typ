= Assembly syntax

Programming the original Toy CPU meant flipping switches to enter raw binary
(see the Toy CPU chapter). toyasm lets you write the same programs as readable
text in a `.toys` file, and it does the tedious part --- turning mnemonics and
labels into the right bytes at the right addresses.

== The shape of a program

```
# comments start with # and run to end of line
label:  load  var       # an instruction, optionally with a label
        add   other
        goto  label

# data usually goes at the end
var:    42              # decimal
flags:  0b00001111      # binary (0b prefix)
mask:   0xFF            # hexadecimal (0x prefix)
bits:   00001111        # bare 8-bit binary is also accepted
```

== Elements

*Instructions* are a mnemonic from the instruction set, optionally followed by
an operand. Two-byte instructions (`load`, `add`, `goto`, …) take one operand
--- a label naming a memory box. One-byte instructions (`stop`, `right`, `not`,
…) take none.

*Labels* name a memory address. Write `name:` before an instruction or a data
value, then use the name anywhere an address is needed:

```
loop:   sub   one       # "loop" names this instruction's address
        ifzero end      # "end" and "one" are labels defined elsewhere
        goto  loop
```

A label is just a human-friendly name for a number. toyasm figures out the
actual address and substitutes it, so you never count bytes by hand.

*Data* is a label followed by a value; it reserves one byte holding that value.
Because code and data share memory, put your data _after_ the `stop` (or after
a `goto`) so the CPU never tries to execute it as an instruction.

== Number formats

#table(
  columns: (auto, auto, 1fr),
  align: (left, left, left),
  stroke: 0.5pt + luma(200),
  table.header([*Form*], [*Example*], [*Meaning*]),
  [Decimal],     [`42`],         [Base 10],
  [Hexadecimal], [`0xFF`],       [`0x` prefix],
  [Binary],      [`0b00001111`], [`0b` prefix],
  [Bare 8-bit],  [`00001111`],   [Exactly 8 `0`/`1` digits, read as binary],
)

All values must fit in one byte (`0`--`255`).

== How toyasm lays it out in memory

Lines are placed into memory top to bottom, starting at address 0: a one-byte
instruction takes one address; a two-byte instruction takes two (opcode, then
the resolved address); a data line takes one address holding its value. So this
source:

```
        load  a     # addr 0-1
        add   b     # addr 2-3
        stop        # addr 4
a:      10          # addr 5
b:      20          # addr 6
```

compiles to the bytes `20, 5, 22, 6, 0, 10, 20` at addresses 0--6. The label
`a` resolves to `5` and `b` to `6`, which is why `load a` becomes `20, 5`.

You can see this layout for any program with the CLI's export option
(`--cli --export`) or in the GUI's memory panel.
