# Instruction set

The Toy CPU understands 14 instructions. Each has a numeric **opcode** (the
byte that identifies it). Instructions that reference memory are two bytes
long (opcode + address); the rest are one byte.

| Mnemonic | Opcode (dec) | Opcode (bin) | Bytes | Effect |
|----------|-------------:|--------------|:-----:|--------|
| `stop`   | 0   | `00000000` | 1 | Halt execution |
| `right`  | 1   | `00000001` | 1 | `ACC = ACC >> 1` (shift right) |
| `left`   | 2   | `00000010` | 1 | `ACC = ACC << 1` (shift left) |
| `not`    | 15  | `00001111` | 1 | `ACC = ~ACC` (bitwise NOT) |
| `and`    | 17  | `00010001` | 2 | `ACC = ACC & mem[addr]` |
| `or`     | 18  | `00010010` | 2 | `ACC = ACC | mem[addr]` |
| `xor`    | 19  | `00010011` | 2 | `ACC = ACC ^ mem[addr]` |
| `load`   | 20  | `00010100` | 2 | `ACC = mem[addr]` |
| `store`  | 21  | `00010101` | 2 | `mem[addr] = ACC` |
| `add`    | 22  | `00010110` | 2 | `ACC = ACC + mem[addr]` |
| `sub`    | 23  | `00010111` | 2 | `ACC = ACC - mem[addr]` |
| `goto`   | 24  | `00011000` | 2 | `PC = addr` (jump) |
| `ifzero` | 25  | `00011001` | 2 | if `ACC == 0`: `PC = addr` |
| `nop`    | 128 | `10000000` | 1 | Do nothing |

Any opcode not in this table is treated as `nop`.

## How the CPU knows the length

Look at **bit 4** (value `0x10`, the `1` in `000` `1` `0000`). If it is set,
the instruction reads a second byte as its address. This is called the
*fetch bit*:

- `load` = `00010100` → bit 4 set → two bytes.
- `right` = `00000001` → bit 4 clear → one byte.

You never set this bit yourself — it's baked into the opcodes. It's just how
the CPU decides whether to read an address after the opcode.

## Notes on individual instructions

- **Arithmetic wraps modulo 256.** `255 + 1 = 0`, `0 - 1 = 255`. There is no
  overflow flag. If a result must fit, keep values small.
- **`right` / `left`** shift the bits by one position, filling with `0`.
  `left` is a quick multiply-by-2; `right` is a divide-by-2 (dropping the low
  bit). Bits shifted off the end are lost.
- **`ifzero`** is the only conditional. Every "if" and every loop exit you
  write is ultimately built from `ifzero`.
- **`goto`** is an unconditional jump — used to loop back or skip ahead.
- **`store`** is how results leave the accumulator and become data in memory.

## Building bigger operations

The Toy CPU has no multiply, divide, or compare instruction. You build them:

- **Multiply** → repeated `add`, or doubling with `left` (see the
  `sevenfold.toy` and `multiply.toy` examples).
- **Compare for equality** → `xor` two values; the result is `0` exactly when
  they're equal, so follow it with `ifzero`.
- **Loop N times** → keep a counter in memory, `sub` one each pass, and
  `ifzero` to exit.

See **[writing-programs.md](writing-programs.md)** for these patterns in full.
