"""
Byte formatting, the memory-mapped I/O map, and source directives.

Pure and Qt-free so the GUI, the Edit dialog, and the tests can all share it.
The Toy CPU core (core.py) is NOT aware of any of this — memory-mapped I/O is
purely an interpretation the GUI puts on a few high memory addresses.

Memory map:
    240..254  io0..io14  — 15 bidirectional I/O registers (input and output)
    255       ready      — a plain register; by convention the program polls it
                           (0 = nothing yet, non-zero = input available / a count)
    0..239    ordinary RAM; the recursion stack starts at 239 and grows down.

I/O is a GUI-only feature; the headless runner treats 240..255 as plain memory.
"""

from pytoy.core import parse_val

IO_BASE   = 240                 # io0 lives here
IO_COUNT  = 15                  # io0..io14  -> 240..254
IO_READY  = 255                 # the ready register
SP_TOP    = 239                 # stack starts here (top reserved for I/O)

# address -> label and label -> address, for the assembler/compiler to seed and
# for the GUI to annotate.
IO_CELL_LABELS = {IO_BASE + i: f"io{i}" for i in range(IO_COUNT)}
READY_LABEL    = {IO_READY: "ready"}
IO_LABELS  = {**IO_CELL_LABELS, **READY_LABEL}   # addr -> name
IO_SYMBOLS = {name: addr for addr, name in IO_LABELS.items()}  # name -> addr


# ── Byte formatters ──────────────────────────────────────────────────────────

# Active I/O display formats.
FORMATS = ("decimal", "binary", "hex", "ascii")


def format_byte(b, fmt="decimal"):
    """Format a byte as a short string for the given mode."""
    b &= 0xFF
    if fmt == "decimal":  return str(b)
    if fmt == "binary":   return format(b, "08b")
    if fmt == "hex":      return format(b, "02X")
    if fmt == "ascii":
        # Printable ASCII shows as the character; everything else as a middle dot
        # "·", kept distinct from a real "." (code 46).
        return chr(b) if 32 <= b < 127 else "·"
    raise ValueError(f"unknown format {fmt!r}")


# ── Input parsing ────────────────────────────────────────────────────────────

def parse_input(text, fmt="decimal"):
    """Parse a user-typed value in the given mode into a 0..255 byte.
    Reuses core.parse_val for the numeric modes so behaviour matches the
    assembler/edit box; ascii takes the first char's code."""
    text = text.strip()
    if fmt == "ascii":
        if not text:
            raise ValueError("empty input")
        return ord(text[0]) & 0xFF
    if fmt == "hex":
        return int(text, 16) & 0xFF           # bare "FF" (no 0x needed here)
    if fmt == "binary":
        return int(text, 2) & 0xFF            # bare "1010"
    # decimal (and the general grammar: 0x.., 0b.., 8-char binary)
    return parse_val(text) & 0xFF


# ── Source directives (# pytoy: key=value  /  // pytoy: key=value) ────────────

_DEFAULTS = {
    # io-widget display format: decimal|binary|hex|ascii. ascii by default so a
    # program with no `output=` directive shows its I/O as characters (the most
    # legible for the typical print/greet examples); an explicit directive wins.
    "output": "ascii",
}

_OUTPUT_OK = set(FORMATS)


def parse_directives(src, comment_prefix="#"):
    """Scan source text for `<prefix> pytoy: key=value` lines and return a
    validated config dict (filled with defaults). `comment_prefix` is "#" for
    assembly and "//" for C. The only directive is `output` (the I/O widget's
    display format)."""
    cfg = dict(_DEFAULTS)
    marker = comment_prefix + " pytoy:"
    alt = comment_prefix + "pytoy:"            # tolerate no space after prefix
    for line in src.splitlines():
        s = line.strip()
        body = None
        if s.startswith(marker):
            body = s[len(marker):]
        elif s.startswith(alt):
            body = s[len(alt):]
        if body is None:
            continue
        for part in body.split(","):           # allow key=v, key=v on one line
            if "=" not in part:
                continue
            key, val = part.split("=", 1)
            key, val = key.strip(), val.strip()
            if key == "output" and val in _OUTPUT_OK:
                cfg["output"] = val
    return cfg
