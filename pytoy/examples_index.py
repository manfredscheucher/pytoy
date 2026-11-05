"""Runtime enumeration of the examples/ folder, so a GUI can render a grouped
"Examples" browser without hard-coding any example.

Three categories (see `Example.category`):

  - "asm"  — assembly sources (*.toys) by subfolder. To load: assemble.
  - "c"    — C sources (*.toyc) by subfolder. To load: compile with one of
             `compilers`, then assemble.
  - "toyo" — pre-compiled bytecode listings (*.toyo). To load: parse directly.

Which compilers accept a C example is detected by actually compiling it. That is
lazy and cached per source text, so listing examples stays cheap.
"""

import os
from dataclasses import dataclass


# examples/ sits at the repo root, a sibling of the pytoy/ package directory.
_PACKAGE_DIR = os.path.dirname(os.path.abspath(__file__))
EXAMPLES_ROOT = os.path.normpath(os.path.join(_PACKAGE_DIR, os.pardir, "examples"))


@dataclass
class Example:
    """One example the GUI can offer.

      path         absolute path to the source/listing file on disk
      display_name the file's base name, no extension
      category     "asm" | "c" | "toyo"
      subfolder    the grouping bucket, e.g. "01-basics" (asm/c) or "" (toyo)
    """

    path: str
    display_name: str
    category: str
    subfolder: str = ""

    @property
    def compilers(self):
        """For C examples: the compilers that accept this source, a subset of
        ("minicc", "toycc") in that order. Empty for asm/toyo examples."""
        return list(_detect_compilers(self.path)) if self.category == "c" else []


# ── compiler probing (lazy, cached by source text) ───────────────────────────

_compiler_cache: "dict[str, list[str]]" = {}


def _accepts(compile_source, src):
    """Compiling is not enough: minicc inlines everything and can overflow the
    240-byte program region, so the assembler must accept the result too."""
    from pytoy.assembler import assemble
    try:
        errors = assemble(compile_source(src, "probe"))[4]
    except Exception:
        return False
    return not errors


def _detect_compilers(path):
    """The compilers that accept the source at `path`, minicc first."""
    from pytoy import compiler, minicc
    try:
        with open(path, "r") as f:
            src = f.read()
    except OSError:
        return []
    if src not in _compiler_cache:
        _compiler_cache[src] = [name for name, mod in (("minicc", minicc), ("toycc", compiler))
                                if _accepts(mod.compile_source, src)]
    return _compiler_cache[src]


# ── scanning ──────────────────────────────────────────────────────────────────

def _scan(category, ext, subfolders):
    """The `ext` files of examples/<category>/, per subfolder (sorted), or
    directly in it without `subfolders`. Loose .toys files in examples/c/ are
    compiled outputs and so never picked up."""
    base = os.path.join(EXAMPLES_ROOT, category)
    if not os.path.isdir(base):
        return []
    subs = [""]
    if subfolders:
        subs = sorted(d for d in os.listdir(base) if os.path.isdir(os.path.join(base, d)))
    return [Example(path=os.path.join(base, sub, name),
                    display_name=os.path.splitext(name)[0],
                    category=category, subfolder=sub)
            for sub in subs
            for name in sorted(os.listdir(os.path.join(base, sub)))
            if name.endswith(ext)]


def list_examples():
    """Every example on disk, in display order: asm, then C, then toyo."""
    return _scan("asm", ".toys", True) + _scan("c", ".toyc", True) + _scan("toyo", ".toyo", False)


def grouped_examples():
    """The examples as { category: { subfolder: [Example, ...] } }, in display
    order. The toyo category has the one subfolder ""."""
    out = {"asm": {}, "c": {}, "toyo": {}}
    for ex in list_examples():
        out[ex.category].setdefault(ex.subfolder, []).append(ex)
    return out
