"""minisim and the plain bytecode files: the step and dump output, the loader,
the export, and that minisim agrees with the real CPU core on the examples.

Run: python3 -m pytest tests/test_minisim.py -q
"""

import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))
import example_steps  # noqa: E402
from pytoy.assembler import bytecode_text  # noqa: E402
from pytoy.minisim import load, run  # noqa: E402
from pytoy.simulator import parse_toyo  # noqa: E402

PROGRAM = "20\n6\n3\n22\n6\n0\n21\n"   # load x, invalid opcode, add x, stop, x: 21

FIXTURE = os.path.join(os.path.dirname(__file__), "fixtures", "fibonacci.txt")


def test_step_lines_and_result(capsys):
    assert run(load(PROGRAM)) == (42, 4)
    assert capsys.readouterr().out == (
        "step=1 acc=0 pc=0 op=20\n"
        "step=2 acc=21 pc=2 op=3\n"
        "step=3 acc=21 pc=3 op=22\n"
        "step=4 acc=42 pc=5 op=0\n"
        "stopped after 4 steps, acc=42\n"
    )


def test_one_step_is_singular(capsys):
    assert run(load("")) == (0, 1)
    assert capsys.readouterr().out.endswith("stopped after 1 step, acc=0\n")


def test_verbose_dumps_16_rows_and_marks_the_pc(capsys):
    run(load(PROGRAM), verbose=True)
    lines = capsys.readouterr().out.splitlines()
    assert lines[1] == "x_000...x_015:  20*  6   3  22   6   0  21 " + "  0 " * 9
    assert lines[16] == "x_240...x_255: " + "  0 " * 16
    assert all(len(l) == 79 for l in lines[1:17])
    assert lines[17].startswith("step=2 ")
    assert lines[18] == "x_000...x_015:  20   6   3* 22   6   0  21 " + "  0 " * 9


def test_load_allows_comments_and_fills_with_zeros():
    mem = load("# a program\n20 # load\n6\n\n")
    assert mem[:2] == [20, 6] and len(mem) == 256 and not any(mem[2:])


@pytest.mark.parametrize("bad", ["1\n" * 257, "256\n", "-1\n", "abc\n", "20 6\n"])
def test_load_rejects_bad_files(bad):
    with pytest.raises(ValueError):
        load(bad)


def test_fixture_runs():
    assert run(load(open(FIXTURE).read()))[0] == 13


def test_bytecode_text_stops_at_the_last_non_zero_cell():
    mem = [0] * 256
    mem[:7] = [1, 0, 3, 0, 5, 0, 7]
    assert bytecode_text(mem) == "1\n0\n3\n0\n5\n0\n7\n"
    assert bytecode_text([0] * 256) == ""
    assert bytecode_text([9] * 256).count("\n") == 256


def test_parse_toyo_reads_bytecode_with_comments():
    mem = parse_toyo("# hi\n20  # load\n6\n")
    assert mem[:2] == [20, 6] and len(mem) == 256 and not any(mem[2:])


@pytest.mark.parametrize("bad", ["1\n" * 257, "300\n"])
def test_parse_toyo_rejects_bad_bytecode(bad):
    with pytest.raises(ValueError):
        parse_toyo(bad)


def test_agrees_with_the_cpu_core_on_all_examples(capsys):
    paths = list(example_steps.examples("asm", "**/*.toys")) + list(example_steps.examples("toyo", "*.toyo"))
    assert len(paths) > 10
    for path in paths:
        src = open(path).read()
        if path.endswith(".toyo"):
            image = parse_toyo(src)
            core = example_steps.run(image)
        else:
            from pytoy.assembler import assemble
            image = assemble(src)[0]
            core = example_steps.run(image)
        assert run(load(bytecode_text(image))) == core, path
    capsys.readouterr()
