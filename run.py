#!/usr/bin/env python3
"""
pytoy — single entry point.

Subcommands:
    sim <file> [--cli --run --quiet -x -d]   simulate a .toys/.toyo (GUI default)
    asm <file.toys> [-o out.toyo]            assemble to a .toyo object file
    cc  <file.toyc> [-o out.toys] [--run] [-O]   compile C to assembly

With no subcommand (or `sim` with no file), the GUI opens empty so you can load
an example via the Load button.

Examples:
    python3 run.py                               # open the GUI, empty
    python3 run.py sim examples/asm/multiply.toys
    python3 run.py sim examples/asm/fibonacci.toys --cli --run --quiet
    python3 run.py asm examples/asm/multiply.toys -o /tmp/m.toyo
    python3 run.py cc  examples/c/multiply.toyc --run
"""

import os
import sys
import argparse

# Make the pytoy package importable when run from anywhere.
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))


# ── sim ──────────────────────────────────────────────────────────────────────

def cmd_sim(args):
    from pytoy.assembler import assemble, show_assembly, export
    from pytoy.simulator import simulate, parse_toyo, gui_main, empty_gui

    # No file: open the GUI empty so a newcomer can just load an example.
    if not args.file:
        empty_gui()
        return

    try:
        src = open(args.file).read()
    except OSError:
        sys.exit(f"File not found: {args.file}")

    is_toyo = args.file.lower().endswith('.toyo')

    # The GUI is the default. --cli forces the terminal; --run/--quiet also
    # imply the terminal (you asked to run it, not to open a window). Decide
    # this from what the USER passed, before any .toyo-specific tweaks below.
    use_gui = not (args.cli or args.run or args.quiet)

    if is_toyo:
        # A .toyo is a compiled byte listing with no re-runnable source: load the
        # memory image directly and skip assembly. Mirror the GUI's .toyo Load
        # branch so CLI and GUI behave the same.
        try:
            mem = parse_toyo(src)
        except Exception as e:
            sys.exit(f"cannot parse {args.file}: {e}")
        listing = [(a, [mem[a]], "", True) for a in range(256)]
        syms = {}
        data_addrs = set(range(256))
        data_start = None
        # verbose/step output and --export need source we don't have here.
        if args.export:
            print("NOTE: nothing to export from a .toyo (no source); "
                  "skipping --export.", file=sys.stderr)
            args.export = False
        # In the terminal there is no per-line source to explain, so force the
        # compact output. (Only affects CLI mode; the GUI is unaffected.)
        if not use_gui:
            args.quiet = True

    if not is_toyo and errors:
        # Assembly failed: in the GUI show a scrollable dialog; on the terminal
        # print each error. Either way, don't try to run a broken program.
        if use_gui:
            from pytoy.simulator import show_error_dialog
            show_error_dialog(f"Assembly failed: {args.file}", "\n".join(errors))
        else:
            for e in errors:
                print(f"ERROR: {e}", file=sys.stderr)
        sys.exit(1)

    guard = data_start if args.detect_code_overwrite else None
    if args.detect_code_overwrite and data_start is None:
        print("WARNING: --detect-code-overwrite is on but the program has no "
              "'# data' marker; code-overwrite detection is disabled.",
              file=sys.stderr)

    if use_gui:
        if is_toyo:
            gui_main(mem, listing, syms, data_addrs, guard, has_source=False,
                     source_path=args.file)
        else:
            gui_main(mem, listing, syms, data_addrs, guard,
                     source_path=args.file)
        return

    if args.export:
        print("─" * 62)
        show_assembly(listing, syms, mem)
        export(listing, syms, mem, args.file.rsplit('.', 1)[0] + '.toyo')

    # build addr→original source map for verbose mode
    addr_orig = {}
    if not args.quiet:
        for addr, blist, orig, is_data in listing:
            if addr is None:
                continue
            addr_orig[addr] = orig.rstrip()
            if len(blist) == 2:
                addr_orig[addr + 1] = ''

    print("─" * 62)
    if args.export:
        print("execution:\n")
    acc = simulate(mem, syms, data_addrs, step=not args.run,
                   show_mem=not args.quiet, verbose=not args.quiet,
                   addr_orig=addr_orig, code_guard=guard)
    print("─" * 62)
    print(f"Result:  ACC = {acc}  ({acc:08b}  0x{acc:02x}  dec {acc})")


# ── asm ──────────────────────────────────────────────────────────────────────

def cmd_asm(args):
    from pytoy.assembler import assemble, export

    if args.file.lower().endswith('.toyo'):
        sys.exit(f"{args.file} is already a compiled .toyo object; asm "
                 f"assembles .toys source. To run it: run.py sim "
                 f"{args.file} --run")

    try:
        with open(args.file) as f:
            src = f.read()
    except OSError as e:
        sys.exit(f"cannot read {args.file}: {e}")

    mem, listing, syms, _data_addrs, errors, _data_start = assemble(src)
    if errors:
        for e in errors:
            print(f"ERROR: {e}", file=sys.stderr)
        sys.exit(1)

    out_path = args.output or (os.path.splitext(args.file)[0] + '.toyo')
    export(listing, syms, mem, out_path)


# ── cc ───────────────────────────────────────────────────────────────────────

def cmd_cc(args):
    from pytoy.compiler import compile_file
    compile_file(args.file, out_path=args.output, optimize=args.optimize,
                 run=args.run)


# ── argument parsing ──────────────────────────────────────────────────────────

def build_parser():
    ap = argparse.ArgumentParser(
        prog='run.py',
        description="pytoy — Toy CPU tools. With no subcommand, opens the GUI "
                    "empty so you can load an example via the Load button.",
        formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest='command')

    p_sim = sub.add_parser(
        'sim', help='simulate a .toys/.toyo program (GUI by default)')
    p_sim.add_argument('file', nargs='?',
                       help='a .toys assembly or .toyo object file '
                            '(omit to open the GUI empty)')
    p_sim.add_argument('-r', '--run', action='store_true',
                       help='run to the end in the terminal (implies --cli)')
    p_sim.add_argument('-q', '--quiet', action='store_true',
                       help='compact one-line-per-step output (implies --cli)')
    p_sim.add_argument('-x', '--export', action='store_true',
                       help='export compiled listing to .toyo')
    p_sim.add_argument('-c', '--cli', action='store_true',
                       help='run in the terminal instead of the GUI')
    p_sim.add_argument('-d', '--detect-code-overwrite', action='store_true',
                       help='warn when a store writes into the code region '
                            '(below the "# data" marker)')
    p_sim.set_defaults(func=cmd_sim)

    p_asm = sub.add_parser(
        'asm', help='assemble .toys source into a .toyo object file')
    p_asm.add_argument('file', help='input assembly file (.toys)')
    p_asm.add_argument('-o', '--output', help='output .toyo path')
    p_asm.set_defaults(func=cmd_asm)

    p_cc = sub.add_parser(
        'cc', help='compile a C subset (.toyc) to Toy CPU assembly (.toys)')
    p_cc.add_argument('file', help='input C file (.toyc)')
    p_cc.add_argument('-o', '--output', help='output .toys path')
    p_cc.add_argument('-r', '--run', action='store_true',
                      help='after compiling, run the program (in-process)')
    p_cc.add_argument('-O', '--optimize-save-restore', action='store_true',
                      dest='optimize',
                      help='skip save/restore at call sites whose caller is '
                           'not recursive (smaller code, same results)')
    p_cc.set_defaults(func=cmd_cc)

    return ap


def main():
    ap = build_parser()
    args = ap.parse_args()

    # No subcommand at all -> open the GUI empty.
    if args.command is None:
        from pytoy.simulator import empty_gui
        empty_gui()
        return

    args.func(args)


if __name__ == '__main__':
    main()
