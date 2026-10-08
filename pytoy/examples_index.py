"""Runtime enumeration of the examples/ folder.

Scans the on-disk examples/ directory and returns a structured list of the
available examples, so a GUI can render a grouped "Examples" browser without
any example being hard-coded. New files on disk appear automatically.

Three separate categories (see `Example.category`):

  - "asm"  — assembly sources (*.toys), grouped by their subfolder
             (01-basics, 02-extended, 03-programs, 04-io). To load: assemble.
  - "c"    — C sources (*.toyc). To load they must be COMPILED first. Each C
             example records which compiler(s) accept it in `compilers`
             ("minicc" and/or "toycc"); minicc rejects recursion and other
             syntax it does not support. To load: compile with a chosen
             compiler, then assemble.
  - "toyo" — pre-compiled bytecode listings (*.toyo). To load: parse directly.

Compiler compatibility for C examples is detected by ACTUALLY trying to compile
the source with each compiler and catching its error (accurate, not a
heuristic). It is lazy and cached per source text, so merely listing examples
is cheap — compilation only happens the first time `compilers` is needed.
"""

import os
from dataclasses import dataclass, field


# ── locating the examples/ root ──────────────────────────────────────────────
# examples/ sits at the repo root, a sibling of the pytoy/ package directory.
# Resolve it relative to this file so it is found no matter the cwd.

_PACKAGE_DIR = os.path.dirname(os.path.abspath(__file__))
EXAMPLES_ROOT = os.path.normpath(os.path.join(_PACKAGE_DIR, os.pardir, "examples"))

# Known asm subfolders, in teaching order. Any other subfolder found on disk is
# appended after these (sorted), so new groups still show up automatically.
_ASM_SUBFOLDER_ORDER = ["01-basics", "02-extended", "03-programs", "04-io"]

# The C sources live under these subfolders. We deliberately ignore loose .toys
# files sitting directly in examples/c/ (those are compiled outputs, not C).
_C_SUBFOLDER_ORDER = ["01-basics", "02-extended", "03-programs", "04-io"]

ALL_COMPILERS = ("minicc", "toycc")


@dataclass
class Example:
    """One example the GUI can offer.

    Fields a GUI needs to render a menu entry and act on a selection:

      path         absolute path to the source/listing file on disk
      display_name human-friendly name (the file's base name, no extension)
      category     "asm" | "c" | "toyo" — decides how to LOAD it:
                     asm  -> assemble(source)
                     c    -> compile(source, compiler) then assemble
                     toyo -> parse_toyo(listing)
      subfolder    the grouping bucket, e.g. "01-basics" (asm/c) or "" (toyo)

    C-only (empty/ignored for asm and toyo):
      _source      lazily-read source text, used to probe compilers
      _compilers   cached result of probing; None until first asked
    """

    path: str
    display_name: str
    category: str
    subfolder: str = ""
    _source: "str | None" = field(default=None, repr=False)
    _compilers: "list[str] | None" = field(default=None, repr=False)

    @property
    def compilers(self):
        """For C examples: the compilers that accept this source, a subset of
        ("minicc", "toycc") in that order. Empty for asm/toyo examples.

        Lazily probed on first access and cached, so enumerating examples does
        not pay the compile cost until the GUI actually needs it.
        """
        if self.category != "c":
            return []
        if self._compilers is None:
            self._compilers = _detect_compilers(self.path)
        return list(self._compilers)


# ── compiler probing (lazy, cached) ──────────────────────────────────────────
# Cache keyed by the source TEXT, so two files with identical content (or the
# same file probed twice) share one result.

_compiler_cache: "dict[str, list[str]]" = {}


def _minicc_accepts(src):
    from pytoy.minicc import compile_source, MiniError
    try:
        compile_source(src, "probe")
        return True
    except MiniError:
        return False
    except Exception:
        # Any other failure means the source is not usable with minicc.
        return False


def _toycc_accepts(src):
    from pytoy.compiler import compile_source, CompileError
    try:
        compile_source(src, "probe")
        return True
    except CompileError:
        return False
    except Exception:
        return False


def _detect_compilers(path):
    """Return the list of compilers that successfully compile `path`, trying
    minicc first then toycc. Cached by source text."""
    try:
        with open(path, "r") as f:
            src = f.read()
    except OSError:
        return []
    if src in _compiler_cache:
        return _compiler_cache[src]
    result = []
    if _minicc_accepts(src):
        result.append("minicc")
    if _toycc_accepts(src):
        result.append("toycc")
    _compiler_cache[src] = result
    return result


# ── scanning ──────────────────────────────────────────────────────────────────

def _ordered_subfolders(base, order):
    """Subfolders of `base` that exist on disk, the known ones in `order` first,
    then any extras sorted alphabetically (so new groups appear automatically)."""
    if not os.path.isdir(base):
        return []
    present = {d for d in os.listdir(base)
               if os.path.isdir(os.path.join(base, d))}
    known = [d for d in order if d in present]
    extra = sorted(present - set(order))
    return known + extra


def _files_with_ext(folder, ext):
    if not os.path.isdir(folder):
        return []
    names = [n for n in os.listdir(folder) if n.endswith(ext)]
    return [os.path.join(folder, n) for n in sorted(names)]


def _base_name(path):
    return os.path.splitext(os.path.basename(path))[0]


def scan_asm(root=None):
    """All .toys examples under examples/asm/, grouped by subfolder."""
    root = root or EXAMPLES_ROOT
    base = os.path.join(root, "asm")
    out = []
    for sub in _ordered_subfolders(base, _ASM_SUBFOLDER_ORDER):
        for p in _files_with_ext(os.path.join(base, sub), ".toys"):
            out.append(Example(path=p, display_name=_base_name(p),
                               category="asm", subfolder=sub))
    return out


def scan_c(root=None):
    """All .toyc examples under examples/c/<subfolder>/, grouped by subfolder.

    Loose .toys files directly in examples/c/ are compiled outputs and ignored.
    """
    root = root or EXAMPLES_ROOT
    base = os.path.join(root, "c")
    out = []
    for sub in _ordered_subfolders(base, _C_SUBFOLDER_ORDER):
        for p in _files_with_ext(os.path.join(base, sub), ".toyc"):
            out.append(Example(path=p, display_name=_base_name(p),
                               category="c", subfolder=sub))
    return out


def scan_toyo(root=None):
    """All .toyo pre-compiled listings under examples/toyo/."""
    root = root or EXAMPLES_ROOT
    base = os.path.join(root, "toyo")
    out = []
    for p in _files_with_ext(base, ".toyo"):
        out.append(Example(path=p, display_name=_base_name(p),
                           category="toyo", subfolder=""))
    return out


def list_examples(root=None):
    """Enumerate every example on disk, in display order (asm, then C, then
    toyo). Returns a flat list of `Example` records; group by `.category` and
    `.subfolder` for a menu. Compiler compatibility for C examples is NOT
    computed here — access `Example.compilers` to probe it lazily.
    """
    root = root or EXAMPLES_ROOT
    return scan_asm(root) + scan_c(root) + scan_toyo(root)


def grouped_examples(root=None):
    """Convenience view for a GUI: a nested dict

        { "asm":  { "01-basics": [Example, ...], ... },
          "c":    { "02-extended": [...], ... },
          "toyo": { "": [Example, ...] } }

    preserving the display order of categories and subfolders.
    """
    out = {"asm": {}, "c": {}, "toyo": {}}
    for ex in list_examples(root):
        out[ex.category].setdefault(ex.subfolder, []).append(ex)
    return out
