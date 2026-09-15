#!/usr/bin/env python3
"""
Toy CPU Assembler
Based on https://github.com/freedosproject/toycpu

Parses .toys assembly into a 256-byte memory image (two-pass), plus the
assembly listing and .toyo export. The ISA core (opcodes, decode/execute)
lives in pytoy.core; the runnable simulator/GUI lives in pytoy.simulator.
"""

import re

from .core import OPCODES, has_operand, parse_val, _describe

# ── Source parser ──────────────────────────────────────────────────────────

def parse_source(src):
    rows = []
    for lineno, line in enumerate(src.splitlines(), start=1):
        orig = line
        if '#' in line:
            line = line[:line.index('#')]
        line = line.strip()
        label = None
        if ':' in line:
            i = line.index(':')
            label = line[:i].strip().lower()
            line  = line[i+1:].strip()
        if not line:
            rows.append((label, None, None, orig, lineno)); continue
        tok = line.split()
        rows.append((label, tok[0].lower(), tok[1] if len(tok)>1 else None,
                     orig, lineno))
    return rows

# ── Assembler (two-pass) ───────────────────────────────────────────────────

# The canonical "start of data" marker. Tools that generate assembly (toycc)
# should emit exactly this so --detect-code-overwrite works on their output.
DATA_MARKER = "# data"

# A data-marker line is a comment whose only word is "data": '#' then optional
# whitespace/punctuation, then "data", then optional ':' — e.g. "# data",
# "#data", "#  data:". This is lenient enough to also accept a decorated header
# like "# ── data ──". It must NOT match a comment that merely contains the word
# data (e.g. "# a raw data byte"), so "data" must be the whole payload.
_DATA_MARKER_RE = re.compile(r'^#\W*data\W*$', re.IGNORECASE)

def _is_data_marker(orig):
    """True if a source line is the '# data' region marker (see DATA_MARKER)."""
    return bool(_DATA_MARKER_RE.match(orig.strip()))

def assemble(src):
    """
    Returns (mem[256], listing, syms, data_addrs, errors, data_start)
    data_addrs: set of addresses that hold data (not code)
    data_start: address of the first data byte, from the '# data' marker, or
                None if the program has no such marker
    """
    parsed = parse_source(src)

    # pass 1 – addresses + symbols, and total size check
    syms, addr = {}, 0
    for label, mn, _, _, _ in parsed:
        if label is not None:
            syms[label] = addr
        if mn is None: continue
        addr += (2 if (mn in OPCODES and has_operand(OPCODES[mn])) else 1)

    # The Toy CPU has exactly 256 bytes. Report an overflow as a normal error
    # instead of letting pass 2 crash with an IndexError.
    if addr > 256:
        errors = [f"Program is too big: it needs {addr} bytes, but the Toy CPU "
                  f"has only 256. Remove instructions or data."]
        return [0]*256, [], syms, set(), errors, None

    # pass 2 – emit
    mem, listing, errors, data_addrs = [0]*256, [], [], set()
    data_start = None
    addr = 0
    for label, mn, op, orig, lineno in parsed:
        if data_start is None and _is_data_marker(orig):
            data_start = addr
        if mn is None:
            listing.append((None, [], orig, False)); continue

        if mn in OPCODES:
            opc = OPCODES[mn]
            if has_operand(opc):
                v = _resolve(op, syms, mn, errors, lineno)
                mem[addr] = opc; mem[addr+1] = v & 0xFF
                listing.append((addr, [opc, v & 0xFF], orig, False))
                addr += 2
            else:
                mem[addr] = opc
                listing.append((addr, [opc], orig, False))
                addr += 1
        else:
            # data byte (or label used as address constant)
            if mn in syms:
                v = syms[mn] & 0xFF
            else:
                try:    v = parse_val(mn) & 0xFF
                except:
                    errors.append(f"line {lineno}: bad value or unknown "
                                  f"instruction '{mn}'"); v = 0
            mem[addr] = v
            data_addrs.add(addr)
            listing.append((addr, [v], orig, True))
            addr += 1

    return mem, listing, syms, data_addrs, errors, data_start

def _resolve(op, syms, ctx, errors, lineno):
    if op is None:
        errors.append(f"line {lineno}: '{ctx}' needs an operand"); return 0
    k = op.lower()
    if k in syms: return syms[k]
    try:    return parse_val(op)
    except:
        errors.append(f"line {lineno}: unknown label '{op}' for '{ctx}'")
        return 0

# ── Assembly listing (interactive) ────────────────────────────────────────

def show_assembly(listing, syms, mem):
    """Walk through each source line and show original + compiled bytes."""
    rsym = {v: k for k, v in syms.items()}
    def sym(a): return rsym.get(a, str(a))

    print("assembly:\n")
    for addr, blist, orig, is_data in listing:
        if addr is None:
            # comment-only or blank line
            stripped = orig.rstrip()
            if stripped:
                print(f"  {stripped}")
            continue

        # source line
        src_line = orig.rstrip()
        print(f"  {src_line}")

        # indent -> line to match source indentation (min 6 to stay readable)
        indent = max(6, len(src_line) - len(src_line.lstrip()) + 2)  # +2 for outer indent

        # compiled translation
        if is_data:
            label = rsym.get(addr, '')
            lbl = f"{label} = " if label else ""
            v = blist[0]
            print(f"{' '*indent}-> {lbl}{v} ({v:08b}) at addr {addr}")
        else:
            opc = blist[0]
            desc, _ = _describe(opc,
                                blist[1] if len(blist) > 1 else None,
                                sym, mem)
            bs = "  ".join(f"{b:08b}" for b in blist)
            print(f"{' '*indent}-> [{bs}] at addr {addr}  =  {desc}")

    # symbols table
    print(f"\nsymbols:")
    for name, a in sorted(syms.items(), key=lambda x: x[1]):
        print(f"  {name:<12} = {a:3d} ({a:08b})")
    print()

# ── Export ─────────────────────────────────────────────────────────────────

def export(listing, syms, mem, path):
    """Write compiled listing to file + print interactive assembly walk-through."""
    rsym = {v: k for k, v in syms.items()}
    out  = ["# Toy CPU – compiled listing", "#",
            f"# {'ADDR':>4}  {'BYTES':<22}  SOURCE", "# " + "─"*56]
    for addr, blist, orig, is_data in listing:
        if addr is None:
            out.append(f"#        {'':22}  {orig.rstrip()}")
        else:
            bs  = "  ".join(f"{b:08b}" for b in blist)
            out.append(f"  {addr:4d}   {bs:<22}  {orig.rstrip()}")
    out += ["", "# SYMBOLS"]
    for name, addr in sorted(syms.items(), key=lambda x: x[1]):
        out.append(f"#   {name:<15} = {addr:3d}  ({addr:08b})")
    with open(path, 'w') as f:
        f.write("\n".join(out) + "\n")
    print(f"exported → {path}\n")
