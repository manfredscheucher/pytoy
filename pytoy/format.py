"""
Byte formatting, the memory-mapped I/O map, and source directives.

Pure and Qt-free so the GUI, the Edit dialog, and the tests can all share it.
The Toy CPU core (core.py) is NOT aware of any of this — memory-mapped I/O is
purely an interpretation the GUI puts on a few high memory addresses.

Memory map:
    240..254  io0..io14  — 15 bidirectional I/O registers (input and output)
    255       ready      — a plain register, polled by the program (0 = nothing
                           yet, non-zero = input available / a count)
    0..239    ordinary RAM; the recursion stack starts at 239 and grows down.

I/O is a GUI-only feature; the headless runner treats 240..255 as plain memory.
"""

from pytoy.core import parse_val

# ── Memory map ───────────────────────────────────────────────────────────────
#
#   240..254  io0..io14  — 15 bidirectional I/O registers (input AND output)
#   255       ready      — a plain 8-bit register; by CONVENTION a program uses
#                          it as an input-ready flag (0 = nothing yet, non-zero =
#                          input available) or a counter (e.g. how many io cells
#                          hold input). The CPU only has `ifzero`, so 0 vs
#                          non-zero is the natural signal. Nothing is enforced.
#   0..239    ordinary RAM; the recursion stack starts at 239 and grows down.
#
# These are ordinary memory bytes — the CPU core reads/writes them normally. The
# simulator/GUI just *interpret* this region as the outside world: the I/O widget
# shows io0..io14, and a `load 255` (the program polling for input) is flagged.

IO_BASE   = 240                 # io0 lives here
IO_COUNT  = 15                  # io0..io14  -> 240..254
IO_READY  = 255                 # the ready register
SP_TOP    = 239                 # stack starts here (top reserved for I/O)

# Back-compat aliases (older names) — kept so nothing that imported them breaks.
IO_OUT_BASE  = IO_BASE
IO_OUT_COUNT = IO_COUNT

# address -> label and label -> address, for the assembler/compiler to seed and
# for the GUI to annotate.
IO_CELL_LABELS = {IO_BASE + i: f"io{i}" for i in range(IO_COUNT)}
READY_LABEL    = {IO_READY: "ready"}
IO_LABELS  = {**IO_CELL_LABELS, **READY_LABEL}   # addr -> name
IO_SYMBOLS = {name: addr for addr, name in IO_LABELS.items()}  # name -> addr
# alias retained for existing imports
OUT_LABELS = IO_CELL_LABELS


# ── Byte formatters ──────────────────────────────────────────────────────────

# Active I/O display formats. "7segment" is intentionally DISABLED for now: the
# current implementation shows the low nibble as a hex digit, which is not the
# model we want (each of the 8 bits should drive one segment directly, with bit 7
# as the dot). Until that is reworked it is left out of the active list so it
# never appears in the View menu / directives. The seven_segment() helper and the
# SevenSegDisplay widget are kept (commented as inactive) for a future redo.
FORMATS = ("decimal", "binary", "hex", "ascii")


def fmt_decimal(b):
    return str(b & 0xFF)


def fmt_binary(b):
    return format(b & 0xFF, "08b")


def fmt_hex(b):
    return format(b & 0xFF, "02X")


def fmt_ascii(b):
    # Printable ASCII (32..126) shows as the character itself. Everything else
    # (control codes, 127, high bytes) shows as a middle dot "·", kept distinct
    # from a real "." (code 46) so the two are not confused.
    b &= 0xFF
    return chr(b) if 32 <= b < 127 else "·"


def format_byte(b, fmt="decimal"):
    """Format a byte as a short string for the given mode."""
    b &= 0xFF
    if fmt == "decimal":  return fmt_decimal(b)
    if fmt == "binary":   return fmt_binary(b)
    if fmt == "hex":      return fmt_hex(b)
    if fmt == "ascii":    return fmt_ascii(b)
    # "7segment" is disabled for now (see FORMATS); no text form here.
    raise ValueError(f"unknown format {fmt!r}")


# ── Seven-segment (DISABLED — parked for a future redo) ──────────────────────
# NOTE: this is the OLD, wrong model (low nibble -> hex digit). The intended
# model is different: each of the 8 bits drives one segment directly (7 segments
# a..g + bit 7 = decimal point), i.e. the byte IS the segment pattern, not a
# digit to look up. "7segment" is out of the active FORMATS until this is reworked
# (see format.py:FORMATS). Code kept so the redo has a starting point.
#
# Segment layout:   aaa
#                  f   b
#                  f   b
#                   ggg
#                  e   c
#                  e   c
#                   ddd   . (dot)
#
# _SEG = {
#     0x0: "abcdef",  0x1: "bc",     0x2: "abged",  0x3: "abgcd",
#     0x4: "fgbc",    0x5: "afgcd",  0x6: "afgcde", 0x7: "abc",
#     0x8: "abcdefg", 0x9: "abcfgd", 0xA: "abcefg", 0xB: "fgcde",
#     0xC: "adef",    0xD: "bcgde",  0xE: "adefg",  0xF: "aefg",
# }
#
#
# def seven_segment(b):
#     """Return (segments, dot): segments is a dict a..g -> bool for the low
#     nibble's digit; dot is True when bit 7 is set."""
#     on = set(_SEG[b & 0x0F])
#     segments = {s: (s in on) for s in "abcdefg"}
#     dot = bool(b & 0x80)
#     return segments, dot


# ── Input parsing ────────────────────────────────────────────────────────────

def parse_input(text, fmt="decimal"):
    """Parse a user-typed value in the given mode into a 0..255 byte.
    Reuses core.parse_val for the numeric modes so behaviour matches the
    assembler/edit box; ascii takes the first char's code. ("7segment" is
    disabled for now — see FORMATS.)"""
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
    "output": "decimal",    # io-widget display format: decimal|binary|hex|ascii
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
