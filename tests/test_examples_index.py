"""Tests for pytoy.examples_index — runtime enumeration of examples/.

Verifies the scanner finds the known example files on disk, categorises them
correctly, groups asm/c by subfolder, and that the per-example compiler
compatibility for C examples is accurate (minicc rejects recursion, accepts a
simple non-recursive one).
"""

import os

from pytoy import examples_index as ei


def _by_name(examples):
    """Map display_name -> Example (names are unique within our test lookups)."""
    out = {}
    for e in examples:
        out.setdefault((e.category, e.subfolder, e.display_name), e)
    return out


def test_examples_root_resolves_to_repo_examples():
    assert os.path.isdir(ei.EXAMPLES_ROOT)
    assert os.path.basename(ei.EXAMPLES_ROOT) == "examples"
    # independent of cwd: it is relative to the package, not os.getcwd()
    assert os.path.isabs(ei.EXAMPLES_ROOT)


def test_lists_known_files_and_categories():
    examples = ei.list_examples()

    asm = [e for e in examples if e.category == "asm"]
    c = [e for e in examples if e.category == "c"]
    toyo = [e for e in examples if e.category == "toyo"]
    assert asm and c and toyo

    # known asm I/O example
    hello = [e for e in asm if e.display_name == "hello_world"]
    assert hello, "expected asm/.../hello_world.toys"
    assert hello[0].subfolder == "04-io"
    assert hello[0].path.endswith(os.path.join("asm", "04-io", "hello_world.toys"))

    # known C program example
    fib = [e for e in c if e.display_name == "fibonacci_rec"]
    assert fib, "expected c/03-programs/fibonacci_rec.toyc"
    assert fib[0].subfolder == "03-programs"
    assert fib[0].path.endswith(".toyc")

    # known toyo listing
    assert any(e.display_name == "fibonacci" for e in toyo)


def test_asm_grouped_by_subfolder():
    grouped = ei.grouped_examples()
    asm_groups = grouped["asm"]
    # all four teaching subfolders present and non-empty
    for sub in ("01-basics", "02-extended", "03-programs", "04-io"):
        assert sub in asm_groups and asm_groups[sub], f"missing asm/{sub}"
    # every example in a bucket actually carries that subfolder
    for sub, items in asm_groups.items():
        assert all(e.subfolder == sub and e.category == "asm" for e in items)


def test_c_examples_ignore_loose_toys_outputs():
    # examples/c/ has loose compiled .toys files that must NOT be listed as C
    # examples (only .toyc under the numbered subfolders count).
    c = [e for e in ei.list_examples() if e.category == "c"]
    for e in c:
        assert e.path.endswith(".toyc")
        assert e.subfolder in ("01-basics", "02-extended", "03-programs", "04-io")


def test_toyo_examples_have_no_compilers():
    toyo = [e for e in ei.list_examples() if e.category == "toyo"]
    assert toyo
    for e in toyo:
        assert e.compilers == []


def test_compiler_detection_rejects_recursion_for_minicc():
    c = [e for e in ei.list_examples() if e.category == "c"]
    fib_rec = next(e for e in c if e.display_name == "fibonacci_rec")
    # recursion: toycc compiles it, minicc rejects it
    assert fib_rec.compilers == ["toycc"], fib_rec.compilers


def test_compiler_detection_accepts_simple_for_both():
    c = [e for e in ei.list_examples() if e.category == "c"]
    sum3 = next(e for e in c if e.display_name == "sum3")
    # sum3 is a simple non-recursive multi-function example: both accept it.
    assert sum3.compilers == ["minicc", "toycc"], sum3.compilers


def test_compilers_cached_by_source_text():
    ei._compiler_cache.clear()
    c = [e for e in ei.list_examples() if e.category == "c"]
    sum3 = next(e for e in c if e.display_name == "sum3")
    first = sum3.compilers
    # cache now populated; a fresh Example for the same file reuses it
    assert ei._compiler_cache, "expected the probe result to be cached"
    again = ei.Example(path=sum3.path, display_name="sum3", category="c",
                       subfolder=sum3.subfolder)
    assert again.compilers == first
