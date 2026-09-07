<img src="screenshot.png" alt="toyasm" width="100%"/>


# toyasm

Assembler and simulator for the [Toy CPU](https://github.com/freedosproject/toycpu) in Python.

The Toy CPU is a minimal 8-bit processor with 256 bytes of memory, one
accumulator, and a program counter. It was built as a FreeDOS learning tool
with a switch-based interface (like an Altair 8800); toyasm keeps the same CPU
but replaces the binary switch input with readable assembly, a GUI, and a CLI.

## Quick start

```bash
pip install PySide6                          # required for the default GUI
python3 toyasm.py examples/fibonacci.toys    # opens the GUI
python3 toyasm.py examples/fibonacci.toys -c # or run in the terminal (--cli)
```

By default toyasm opens a graphical interface (source + memory panels, with
Step / Run / Reset). Use `-c` / `--cli` to run in the terminal instead — that
mode needs no PySide6. Run `python3 toyasm.py -h` for all options.

## A taste of the syntax

```
        load  a         # acc = a
        add   b         # acc = a + b
        stop
a:      10              # data goes after stop
b:      20
```

See [`examples/`](examples/) for complete programs (Fibonacci, multiply, array
sum/max, …).

## Write it in C instead

toyasm also ships **toycc**, a compiler for a small subset of C that targets the
Toy CPU — often nicer than writing assembly by hand:

```c
int main(void) {
    int a = 7;
    int b = 6;
    return a * b;   // no multiply opcode -> compiled to repeated addition
}
```

```bash
python3 compiler/toycc.py compiler/examples/multiply.toyc --run  # -> ACC = 42
```

See [`compiler/`](compiler/) and the
[compiler pipeline docs](docs/compiler-pipeline.md).

## Documentation

Full docs live in **[`docs/`](docs/)** — written for newcomers with no assembly
background:

- [Concepts](docs/concepts.md) — how a CPU works: memory, accumulator, program
  counter, the fetch–execute cycle.
- [Instruction set](docs/instruction-set.md) — every opcode and how bytes are
  encoded.
- [Assembly syntax](docs/assembly.md) — writing `.toys` programs.
- [Writing programs](docs/writing-programs.md) — worked examples: loops,
  conditionals, self-modifying code.
- [Using toyasm](docs/usage.md) — the GUI and CLI in detail.
- [About the Toy CPU](docs/toycpu.md) — background and origins.

## Credits & license

The Toy CPU instruction set is by Jim Hall (FreeDOS Project), from the
[toycpu](https://github.com/freedosproject/toycpu) project. toyasm's own code
(assembler, GUI, CLI, compiler) is independent.

toyasm is MIT-licensed (see [`LICENSE`](LICENSE)). toycpu is MIT too; its
original notice is reproduced in [`NOTICE`](NOTICE). See
[docs/toycpu.md](docs/toycpu.md) for exactly what was reused vs. written from
scratch.
