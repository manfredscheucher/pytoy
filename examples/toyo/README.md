# Compiled `.toyo` examples

These are **compiled byte-listing** programs for the Toy CPU — the assembled
output of the matching `.toys` sources in [`../asm/`](../asm/). A `.toyo` has no
re-runnable source; loading one shows only the memory panel.

Run one in the GUI or the terminal:

```bash
python3 run.py sim examples/toyo/sum3.toyo          # GUI (memory panel only)
python3 run.py sim examples/toyo/sum3.toyo --run    # terminal, -> ACC = 8
```

## How these were generated

Each file was produced by assembling its `.toys` source with `run.py asm`:

```bash
python3 run.py asm examples/asm/03-programs/sum3.toys      -o examples/toyo/sum3.toyo
python3 run.py asm examples/asm/03-programs/fibonacci_iter.toys -o examples/toyo/fibonacci.toyo
```

To regenerate after changing the source, re-run the same commands.

`invalid_opcode.toyo` has no `.toys` under `../asm/` (it is not a program to
learn from, it only shows what an invalid opcode does). Its source is the
SOURCE column of the listing itself; to rebuild it, copy that column into a
`.toys` file and run `run.py asm` on it.

| file             | source                                   | result (final ACC) |
|------------------|------------------------------------------|--------------------|
| `sum3.toyo`      | `../asm/03-programs/sum3.toys`           | 8  (3 + 1 + 4)     |
| `fibonacci.toyo` | `../asm/03-programs/fibonacci_iter.toys` | 13 (fib for n=7)   |
| `invalid_opcode.toyo` | its own listing (see above)          | 42 (the invalid byte is a NOP) |

> Note: `.toyo` files are normally git-ignored (they are build artifacts). These
> are checked in on purpose as examples, via an exception in `.gitignore`.
