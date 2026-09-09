#!/usr/bin/env python3
"""
toycc - a tiny C-to-assembly compiler for the toyasm "Toy CPU".

It compiles a small, standard-looking subset of C into a .toys assembly file
that the toysim simulator (../toysim.py) can run.

Target machine (see ../doc-typst/):
  - 256 bytes of memory total; code and data share the address space.
  - One 8-bit accumulator (ACC). All arithmetic wraps modulo 256.
  - The only conditional instruction is `ifzero`; the only jump is `goto`.
  - There is no multiply/divide/compare/index register.

Because the machine is 8-bit, every C `int` here is an unsigned 8-bit value
(0..255) that wraps modulo 256. This is documented in the README.

Usage:
    python3 toycc.py program.toyc              # writes program.toys
    python3 toycc.py program.toyc -o out.toys  # custom output path
    python3 toycc.py program.toyc --run        # compile, then run via toysim CLI

Design: hand-written lexer + recursive-descent parser + a straightforward
code generator that emits Toy assembly text. Standard library only.
"""

import sys
import os
import argparse
import subprocess

# toycc reuses the assembler for the shared 256-byte limit and the canonical
# data-region marker, so the two tools can't drift apart. toyasm.py sits in the
# repo root, one level above this compiler/ directory.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from toyasm import assemble, DATA_MARKER


# ── Lexer ──────────────────────────────────────────────────────────────────

KEYWORDS = {'int', 'void', 'return', 'while', 'if', 'else', 'for'}

# Multi-character operators must be tried before single-character ones.
MULTI_OPS = [
    '<<=', '>>=',
    '==', '!=', '<=', '>=', '<<', '>>',
    '+=', '-=', '*=', '&=', '|=', '^=',
    '&&', '||',
]
SINGLE_OPS = set('+-*&|^~<>=(){};,![]')


class Token:
    def __init__(self, kind, value, pos, line):
        self.kind = kind      # 'int_lit', 'ident', 'kw', 'op', 'eof'
        self.value = value
        self.pos = pos
        self.line = line

    def __repr__(self):
        return f"Token({self.kind!r}, {self.value!r})"


def lex(src):
    toks = []
    i = 0
    n = len(src)
    line = 1
    while i < n:
        c = src[i]
        # whitespace
        if c in ' \t\r':
            i += 1
            continue
        if c == '\n':
            line += 1
            i += 1
            continue
        # line comment //
        if c == '/' and i + 1 < n and src[i + 1] == '/':
            while i < n and src[i] != '\n':
                i += 1
            continue
        # block comment /* ... */
        if c == '/' and i + 1 < n and src[i + 1] == '*':
            i += 2
            while i + 1 < n and not (src[i] == '*' and src[i + 1] == '/'):
                if src[i] == '\n':
                    line += 1
                i += 1
            i += 2
            continue
        # numbers (decimal or hex 0x..)
        if c.isdigit():
            start = i
            if c == '0' and i + 1 < n and src[i + 1] in 'xX':
                i += 2
                while i < n and (src[i] in '0123456789abcdefABCDEF'):
                    i += 1
                val = int(src[start:i], 16)
            else:
                while i < n and src[i].isdigit():
                    i += 1
                val = int(src[start:i], 10)
            toks.append(Token('int_lit', val, start, line))
            continue
        # identifiers / keywords
        if c.isalpha() or c == '_':
            start = i
            while i < n and (src[i].isalnum() or src[i] == '_'):
                i += 1
            word = src[start:i]
            if word in KEYWORDS:
                toks.append(Token('kw', word, start, line))
            else:
                toks.append(Token('ident', word, start, line))
            continue
        # operators
        matched = None
        for op in MULTI_OPS:
            if src.startswith(op, i):
                matched = op
                break
        if matched:
            toks.append(Token('op', matched, i, line))
            i += len(matched)
            continue
        if c in SINGLE_OPS:
            toks.append(Token('op', c, i, line))
            i += 1
            continue
        raise CompileError(f"line {line}: unexpected character {c!r}")
    toks.append(Token('eof', None, n, line))
    return toks


class CompileError(Exception):
    pass


# ── AST nodes ──────────────────────────────────────────────────────────────
# Represented as plain tuples/dicts for brevity.
#
#   ('num', value)
#   ('var', name)
#   ('unop', op, expr)                 op in {'-', '~', '!'}
#   ('binop', op, left, right)         op in {+,-,*,&,|,^,<<,>>,==,!=,<,>,<=,>=}
#
#   ('decl', name, init_or_None)
#   ('assign', name, expr)
#   ('if', cond, then_body, else_body_or_None)
#   ('while', cond, body)
#   ('return', expr)
#   ('block', [stmts])


# ── Parser (recursive descent) ─────────────────────────────────────────────

class Parser:
    def __init__(self, toks):
        self.toks = toks
        self.i = 0

    def peek(self):
        return self.toks[self.i]

    def next(self):
        t = self.toks[self.i]
        self.i += 1
        return t

    def at(self, kind, value=None):
        t = self.peek()
        if t.kind != kind:
            return False
        if value is not None and t.value != value:
            return False
        return True

    def eat(self, kind, value=None):
        t = self.peek()
        if t.kind != kind or (value is not None and t.value != value):
            want = value if value is not None else kind
            raise CompileError(
                f"line {t.line}: expected {want!r}, got {t.value!r}")
        return self.next()

    # program  := func_def+
    # func_def := ('int'|'void') NAME '(' params ')' block
    # params   := 'void' | 'int' NAME (',' 'int' NAME)* | (empty)
    # Returns ('program', [func, ...]); exactly one function must be 'main'.
    def parse_program(self):
        funcs = []
        while not self.at('eof'):
            funcs.append(self.parse_func())
        names = [f[1] for f in funcs]
        if 'main' not in names:
            raise CompileError("no 'main' function found")
        for n in names:
            if names.count(n) > 1:
                raise CompileError(f"function {n!r} defined more than once")
        return ('program', funcs)

    def parse_func(self):
        # return type: 'int' or 'void'
        if self.at('kw', 'int'):
            self.next()
        elif self.at('kw', 'void'):
            self.next()
        else:
            t = self.peek()
            raise CompileError(f"line {t.line}: expected 'int' or 'void', "
                               f"got {t.value!r}")
        name = self.eat('ident').value
        self.eat('op', '(')
        params = self.parse_params()
        self.eat('op', ')')
        body = self.parse_block()
        # ('func', name, params, body)
        return ('func', name, params, body)

    def parse_params(self):
        # 'void' or empty -> no params
        if self.at('op', ')'):
            return []
        if self.at('kw', 'void'):
            self.next()
            return []
        params = []
        while True:
            self.eat('kw', 'int')
            # A pointer parameter `int *p` or an array parameter `int a[]` both
            # decay to a plain one-byte scalar that holds an address; only the
            # name matters for codegen, so the `*` / `[]` are just consumed.
            if self.at('op', '*'):
                self.next()
            name = self.eat('ident').value
            if self.at('op', '['):
                self.next()
                self.eat('op', ']')
            params.append(name)
            if self.at('op', ','):
                self.next()
                continue
            break
        return params

    def parse_block(self):
        self.eat('op', '{')
        stmts = []
        while not self.at('op', '}'):
            stmts.append(self.parse_statement())
        self.eat('op', '}')
        return ('block', stmts)

    def parse_statement(self):
        t = self.peek()
        if t.kind == 'op' and t.value == '{':
            return self.parse_block()
        if t.kind == 'kw' and t.value == 'int':
            return self.parse_decl()
        if t.kind == 'kw' and t.value == 'return':
            self.next()
            expr = self.parse_expr()
            self.eat('op', ';')
            return ('return', expr)
        if t.kind == 'kw' and t.value == 'if':
            return self.parse_if()
        if t.kind == 'kw' and t.value == 'while':
            return self.parse_while()
        if t.kind == 'kw' and t.value == 'for':
            return self.parse_for()
        # deref assignment:  *p = expr;  (or a compound form *p += expr;)
        if t.kind == 'op' and t.value == '*':
            return self.parse_deref_assign_stmt()
        # bare call statement:  f(args);  (the result is discarded)
        if (t.kind == 'ident' and self.toks[self.i + 1].kind == 'op'
                and self.toks[self.i + 1].value == '('):
            name = self.eat('ident').value
            self.eat('op', '(')
            args = self.parse_args()
            self.eat('op', ')')
            self.eat('op', ';')
            return ('exprstmt', ('call', name, args))
        # else: assignment (possibly compound)
        return self.parse_assign_stmt()

    def parse_decl(self):
        self.eat('kw', 'int')
        # pointer declaration:  int *p;  or  int *p = expr;
        # A pointer is an ordinary one-byte scalar that holds an address, so it
        # reuses the plain ('decl', ...) node — the star only affects parsing.
        if self.at('op', '*'):
            self.next()
            name = self.eat('ident').value
            init = None
            if self.at('op', '='):
                self.next()
                init = self.parse_expr()
            self.eat('op', ';')
            return ('decl', name, init)
        name = self.eat('ident').value
        # array declaration:  int a[N];  or  int a[N] = {e0, e1, ...};
        if self.at('op', '['):
            self.next()
            size_expr = self.parse_expr()
            self.eat('op', ']')
            size = self._const_size(size_expr)
            init = None
            if self.at('op', '='):
                self.next()
                self.eat('op', '{')
                init = []
                if not self.at('op', '}'):
                    init.append(self.parse_expr())
                    while self.at('op', ','):
                        self.next()
                        init.append(self.parse_expr())
                self.eat('op', '}')
                if len(init) > size:
                    raise CompileError(
                        f"array {name!r} has {len(init)} initializers "
                        f"but size {size}")
            self.eat('op', ';')
            return ('arraydecl', name, size, init)
        init = None
        if self.at('op', '='):
            self.next()
            init = self.parse_expr()
        self.eat('op', ';')
        return ('decl', name, init)

    def _const_size(self, expr):
        """Array size must be a compile-time constant."""
        if expr[0] == 'num':
            if expr[1] == 0:
                raise CompileError("array size must be non-zero")
            return expr[1]
        raise CompileError("array size must be a constant")

    def parse_assign_stmt(self):
        name = self.eat('ident').value
        compound = {'+=': '+', '-=': '-', '*=': '*',
                    '&=': '&', '|=': '|', '^=': '^',
                    '<<=': '<<', '>>=': '>>'}
        # indexed assignment:  a[idx] = expr;  (or a compound-assign form)
        if self.at('op', '['):
            self.next()
            idx = self.parse_expr()
            self.eat('op', ']')
            op = self.eat('op').value
            if op == '=':
                expr = self.parse_expr()
            elif op in compound:
                rhs = self.parse_expr()
                expr = ('binop', compound[op], ('index', name, idx), rhs)
            else:
                raise CompileError(
                    f"expected assignment operator, got {op!r}")
            self.eat('op', ';')
            return ('idxassign', name, idx, expr)
        op = self.eat('op').value
        if op == '=':
            expr = self.parse_expr()
        elif op in compound:
            rhs = self.parse_expr()
            expr = ('binop', compound[op], ('var', name), rhs)
        else:
            raise CompileError(
                f"expected assignment operator, got {op!r}")
        self.eat('op', ';')
        return ('assign', name, expr)

    def parse_deref_assign_stmt(self):
        # *p = expr;  or  *p OP= expr;   (p is any expression yielding an address)
        self.eat('op', '*')
        ptr = self.parse_unary()
        compound = {'+=': '+', '-=': '-', '*=': '*',
                    '&=': '&', '|=': '|', '^=': '^',
                    '<<=': '<<', '>>=': '>>'}
        op = self.eat('op').value
        if op == '=':
            expr = self.parse_expr()
        elif op in compound:
            rhs = self.parse_expr()
            expr = ('binop', compound[op], ('deref', ptr), rhs)
        else:
            raise CompileError(f"expected assignment operator, got {op!r}")
        self.eat('op', ';')
        return ('deref_assign', ptr, expr)

    def parse_if(self):
        self.eat('kw', 'if')
        self.eat('op', '(')
        cond = self.parse_expr()
        self.eat('op', ')')
        then_body = self.parse_statement()
        else_body = None
        if self.at('kw', 'else'):
            self.next()
            else_body = self.parse_statement()
        return ('if', cond, then_body, else_body)

    def parse_while(self):
        self.eat('kw', 'while')
        self.eat('op', '(')
        cond = self.parse_expr()
        self.eat('op', ')')
        body = self.parse_statement()
        return ('while', cond, body)

    def parse_for(self):
        # for (init; cond; post) body   ->   { init; while (cond) { body; post } }
        self.eat('kw', 'for')
        self.eat('op', '(')
        if self.at('op', ';'):
            init = None
            self.next()
        else:
            init = self.parse_assign_or_decl_no_semi()
            self.eat('op', ';')
        if self.at('op', ';'):
            cond = ('num', 1)
        else:
            cond = self.parse_expr()
        self.eat('op', ';')
        if self.at('op', ')'):
            post = None
        else:
            post = self.parse_assign_no_semi()
        self.eat('op', ')')
        body = self.parse_statement()
        inner = [body]
        if post is not None:
            inner.append(post)
        loop = ('while', cond, ('block', inner))
        outer = []
        if init is not None:
            outer.append(init)
        outer.append(loop)
        return ('block', outer)

    def parse_assign_or_decl_no_semi(self):
        if self.at('kw', 'int'):
            self.eat('kw', 'int')
            name = self.eat('ident').value
            init = None
            if self.at('op', '='):
                self.next()
                init = self.parse_expr()
            return ('decl', name, init)
        return self.parse_assign_no_semi()

    def parse_assign_no_semi(self):
        name = self.eat('ident').value
        compound = {'+=': '+', '-=': '-', '*=': '*',
                    '&=': '&', '|=': '|', '^=': '^',
                    '<<=': '<<', '>>=': '>>'}
        if self.at('op', '['):
            self.next()
            idx = self.parse_expr()
            self.eat('op', ']')
            op = self.eat('op').value
            if op == '=':
                expr = self.parse_expr()
            elif op in compound:
                rhs = self.parse_expr()
                expr = ('binop', compound[op], ('index', name, idx), rhs)
            else:
                raise CompileError(f"expected assignment operator, got {op!r}")
            return ('idxassign', name, idx, expr)
        op = self.eat('op').value
        if op == '=':
            expr = self.parse_expr()
        elif op in compound:
            rhs = self.parse_expr()
            expr = ('binop', compound[op], ('var', name), rhs)
        else:
            raise CompileError(f"expected assignment operator, got {op!r}")
        return ('assign', name, expr)

    # ── expression grammar (precedence climbing) ──
    # expr        := equality
    # equality    := relational (('=='|'!=') relational)*
    # relational  := bitor (('<'|'>'|'<='|'>=') bitor)*
    # bitor       := bitxor ('|' bitxor)*
    # bitxor      := bitand ('^' bitand)*
    # bitand      := shift ('&' shift)*
    # shift       := additive (('<<'|'>>') additive)*
    # additive    := multiplicative (('+'|'-') multiplicative)*
    # multiplicative := unary ('*' unary)*
    # unary       := ('-'|'~'|'!') unary | primary
    # primary     := int_lit | ident | '(' expr ')'

    def parse_expr(self):
        return self.parse_equality()

    def _left_assoc(self, sub, ops):
        left = sub()
        while self.at('op') and self.peek().value in ops:
            op = self.next().value
            right = sub()
            left = ('binop', op, left, right)
        return left

    def parse_equality(self):
        return self._left_assoc(self.parse_relational, {'==', '!='})

    def parse_relational(self):
        return self._left_assoc(self.parse_bitor, {'<', '>', '<=', '>='})

    def parse_bitor(self):
        return self._left_assoc(self.parse_bitxor, {'|'})

    def parse_bitxor(self):
        return self._left_assoc(self.parse_bitand, {'^'})

    def parse_bitand(self):
        return self._left_assoc(self.parse_shift, {'&'})

    def parse_shift(self):
        return self._left_assoc(self.parse_additive, {'<<', '>>'})

    def parse_additive(self):
        return self._left_assoc(self.parse_multiplicative, {'+', '-'})

    def parse_multiplicative(self):
        return self._left_assoc(self.parse_unary, {'*'})

    def parse_unary(self):
        if self.at('op') and self.peek().value in ('-', '~', '!'):
            op = self.next().value
            operand = self.parse_unary()
            return ('unop', op, operand)
        if self.at('op', '&'):
            # &x  -> address of a variable ; &a[i] -> address of an element.
            self.next()
            name = self.eat('ident').value
            if self.at('op', '['):
                self.next()
                idx = self.parse_expr()
                self.eat('op', ']')
                return ('addrof_index', name, idx)
            return ('addrof', name)
        if self.at('op', '*'):
            # *p  -> dereference (read through a pointer).
            self.next()
            operand = self.parse_unary()
            return ('deref', operand)
        return self.parse_primary()

    def parse_primary(self):
        t = self.peek()
        if t.kind == 'int_lit':
            self.next()
            return ('num', t.value & 0xFF)
        if t.kind == 'ident':
            self.next()
            if self.at('op', '('):      # a call: NAME(args...)
                self.next()
                args = self.parse_args()
                self.eat('op', ')')
                return ('call', t.value, args)
            if self.at('op', '['):      # an indexed read: NAME[expr]
                self.next()
                idx = self.parse_expr()
                self.eat('op', ']')
                return ('index', t.value, idx)
            return ('var', t.value)
        if t.kind == 'op' and t.value == '(':
            self.next()
            e = self.parse_expr()
            self.eat('op', ')')
            return e
        raise CompileError(f"line {t.line}: unexpected token {t.value!r}")

    def parse_args(self):
        if self.at('op', ')'):
            return []
        args = [self.parse_expr()]
        while self.at('op', ','):
            self.next()
            args.append(self.parse_expr())
        return args


# ── Code generator ─────────────────────────────────────────────────────────
#
# Strategy: expressions are evaluated into the accumulator. When an operation
# needs both operands, the left operand is spilled to a temporary data byte
# and the right operand is (re)loaded from there. Every C variable and every
# temporary is a named data byte placed after the code.

class CodeGen:
    def __init__(self):
        self.code = []          # list of instruction/comment lines (strings)
        self.vars = {}          # C variable name -> data label
        self.consts = {}        # constant value -> data label (dedup)
        self.temps = []         # list of temp data labels (name, initial)
        self.extra_data = []    # (label, value, comment) for constants
        self.label_n = 0
        self.temp_n = 0
        self.declared_order = []  # variable labels in declaration order
        # Arrays: name -> (data_label, base_label, size). Laid out as a
        # contiguous block of data bytes after the scalar variables. `base_label`
        # is a data byte initialised to the array's address (like `arrptr: arr`
        # in bubblesort.toys), so codegen can load the base as a runtime value
        # and add the index for self-modifying element access.
        self.arrays = {}
        self.array_data = []      # (data_label, [init bytes], base_label) in order
        # Extra data bytes for the global-slots call scheme (param/return/marker
        # slots). Kept separate from user variables so `declare()` stays a plain
        # "did the user declare this twice?" check. Each entry is (label, init).
        self.global_slots = []
        # &x needs a data byte initialised to the address of x's slot (like an
        # array's arrbase byte). One byte per distinct variable taken address-of;
        # deduped. Maps a variable's slot label -> its addrof byte label.
        self.addrof_slots = {}

    # -- emission helpers --
    def emit(self, text):
        self.code.append(text)

    def comment(self, text):
        self.code.append(f"        # {text}")

    def new_label(self, base):
        self.label_n += 1
        return f"L{self.label_n}_{base}"

    def var_label(self, name):
        if name not in self.vars:
            raise CompileError(f"use of undeclared variable {name!r}")
        return self.vars[name]

    def declare(self, name):
        if name in self.vars or name in self.arrays:
            raise CompileError(f"variable {name!r} declared twice")
        label = f"v_{name}"
        self.vars[name] = label
        self.declared_order.append(label)
        return label

    def declare_array(self, name, size, init_bytes):
        """Register a fixed-size array. `init_bytes` is a list of already-
        evaluated constant bytes (or None). Reserves `size` contiguous data
        bytes plus one base-pointer byte holding the array's address."""
        if name in self.arrays or name in self.vars:
            raise CompileError(f"variable {name!r} declared twice")
        data_label = f"arr_{name}"
        base_label = f"arrbase_{name}"
        vals = list(init_bytes) if init_bytes else []
        vals += [0] * (size - len(vals))
        self.arrays[name] = (data_label, base_label, size)
        self.array_data.append((data_label, vals, base_label))
        return data_label

    def array_info(self, name):
        if name not in self.arrays:
            raise CompileError(f"use of undeclared array {name!r}")
        return self.arrays[name]

    def add_global_slot(self, label, init=0):
        """Register a fixed data byte for the global-slots call scheme (param,
        return-value or marker slot). Its variable name maps to itself, so the
        normal ('var'/'assign', label) codegen path reaches it directly."""
        if label not in self.vars:
            self.vars[label] = label
            self.global_slots.append((label, init))
        return label

    def addrof_label(self, name):
        """Return the label of a data byte initialised to the ADDRESS of variable
        `name`'s slot (for &name). Deduped: one byte per distinct variable. The
        byte is emitted as `addrof_<slot>: <slot>`, and the assembler resolves
        the slot symbol to its address — exactly how an array's arrbase works."""
        slot = self.var_label(name)
        if slot not in self.addrof_slots:
            self.addrof_slots[slot] = f"addrof_{slot}"
        return self.addrof_slots[slot]

    def const_label(self, value):
        value &= 0xFF
        if value not in self.consts:
            label = f"c_{value}"
            self.consts[value] = label
        return self.consts[value]

    def new_temp(self):
        self.temp_n += 1
        label = f"t{self.temp_n}"
        self.temps.append(label)
        return label

    def shared_index_temp(self):
        """One reused temp byte for element-address index spills. Safe because
        such a spill is consumed two instructions later and never stays live
        across another element access (even nested `a[b[i]]` finishes the inner
        spill before the outer one starts)."""
        if not hasattr(self, '_ixtmp'):
            self._ixtmp = self.new_temp()
        return self._ixtmp

    # -- stack primitives (self-modifying indirect load/store) --
    # One byte `sp` points at the last-pushed byte; the stack grows DOWN from the
    # top of memory. push: sp-=1, mem[sp]=slot;  pop: slot=mem[sp], sp+=1.
    # The address byte of a raw load/store is re-patched from `sp` on every
    # access, because sp moves — the same trick as sum.toys.
    def gen_push(self, slot):
        addr = self.new_label("push_addr")
        self.emit(f"        load  sp         # push {slot}")
        self.emit(f"        sub   {self.const_label(1)}")
        self.emit(f"        store sp         # sp -= 1")
        self.emit(f"        store {addr}       # patch store-address to sp")
        self.emit(f"        load  {slot}")
        self.emit(f"        21               # STORE opcode (raw)")
        self.emit(f"{addr}: 0                # <- mem[sp] := {slot}")

    def gen_pop(self, slot):
        addr = self.new_label("pop_addr")
        self.emit(f"        load  sp         # pop -> {slot}")
        self.emit(f"        store {addr}       # patch load-address to sp")
        self.emit(f"        20               # LOAD opcode (raw)")
        self.emit(f"{addr}: 0                # <- acc := mem[sp]")
        self.emit(f"        store {slot}")
        self.emit(f"        load  sp")
        self.emit(f"        add   {self.const_label(1)}")
        self.emit(f"        store sp         # sp += 1")

    # -- expression code generation: result left in ACC --
    def gen_expr(self, e):
        kind = e[0]
        if kind == 'num':
            self.emit(f"        load  {self.const_label(e[1])}")
            return
        if kind == 'var':
            name = e[1]
            # An array name used as a value (not indexed) decays to its base
            # address — e.g. passing `a` to a function taking `int a[]`.
            if name in self.arrays:
                _data, base, _size = self.arrays[name]
                self.emit(f"        load  {base}")
            else:
                self.emit(f"        load  {self.var_label(name)}")
            return
        if kind == 'unop':
            self.gen_unop(e)
            return
        if kind == 'binop':
            self.gen_binop(e)
            return
        if kind == 'index':
            self.gen_index_read(e)
            return
        if kind == 'addrof':
            # &x : load the data byte that holds x's address (a constant).
            self.emit(f"        load  {self.addrof_label(e[1])}")
            return
        if kind == 'addrof_index':
            # &a[i] == base(a) + i  (same address computation as an element read,
            # but we KEEP the address in ACC instead of loading through it).
            _, name, idx = e
            self._gen_element_addr(self._index_base_label(name), idx)
            return
        if kind == 'deref':
            self.gen_deref_read(e)
            return
        raise CompileError(f"cannot generate expression {e!r}")

    def _gen_element_addr(self, base_label, idx_expr):
        """Leave (base_label + idx) in ACC — the address of element idx.
        `base_label` is a data byte holding the array's base address."""
        # Fast path: constant index folds into a single add against the base.
        if idx_expr[0] == 'num':
            self.emit(f"        load  {base_label}")
            if idx_expr[1] & 0xFF:
                self.emit(f"        add   {self.const_label(idx_expr[1])}")
            return
        # General: evaluate the index into ACC, spill it, then add the base.
        # (add is commutative, so base + idx == idx + base.) The spill uses one
        # shared temp: an element-address computation never nests inside another
        # (the index is consumed two instructions later), so a single reused byte
        # is safe and saves one data byte per element access — this is what makes
        # the array-parameter bubble sort fit the 256-byte machine.
        self.gen_expr(idx_expr)
        t = self.shared_index_temp()
        self.emit(f"        store {t}")
        self.emit(f"        load  {base_label}")
        self.emit(f"        add   {t}")

    def _index_base_label(self, name):
        """The data byte whose VALUE is the base address for `name[idx]`.
        a[i] == *(a + i): `a` must evaluate to an address. A real local array's
        name evaluates to its base address (the arrbase byte). A pointer variable
        (including an array-decayed function parameter) evaluates to its stored
        value, so the base is just the variable's own slot."""
        if name in self.arrays:
            _data, base, _size = self.arrays[name]
            return base
        # a pointer/param scalar: its byte already holds the address
        return self.var_label(name)

    def gen_index_read(self, e):
        # a[idx] : compute element address, patch a raw LOAD's address byte,
        # then execute that LOAD to bring a[idx] into ACC (self-modifying code,
        # exactly the sum.toys / bubblesort.toys trick).
        _, name, idx = e
        base = self._index_base_label(name)
        addr = self.new_label("iload_arg")
        self._gen_element_addr(base, idx)
        self.emit(f"        store {addr}       # patch LOAD address to &{name}[idx]")
        self.emit(f"        20               # LOAD opcode (raw)")
        self.emit(f"{addr}: 0                # <- acc := {name}[idx]")

    def gen_deref_read(self, e):
        # *p : evaluate p (an address) into ACC, patch a raw LOAD's address byte,
        # then execute it to bring mem[p] into ACC. Like gen_index_read, but the
        # address comes from an arbitrary expression instead of base+idx.
        _, ptr = e
        addr = self.new_label("dload_arg")
        self.gen_expr(ptr)
        self.emit(f"        store {addr}       # patch LOAD address to *p")
        self.emit(f"        20               # LOAD opcode (raw)")
        self.emit(f"{addr}: 0                # <- acc := *p")

    def gen_deref_write(self, s):
        # *p = expr : evaluate expr into a temp, evaluate p (address) and patch a
        # raw STORE's address byte, then load the value and run the STORE.
        _, ptr, expr = s
        self.comment("*p = ...")
        val = self.new_temp()
        self.gen_expr(expr)
        self.emit(f"        store {val}")
        addr = self.new_label("dstore_arg")
        self.gen_expr(ptr)
        self.emit(f"        store {addr}       # patch STORE address to *p")
        self.emit(f"        load  {val}")
        self.emit(f"        21               # STORE opcode (raw)")
        self.emit(f"{addr}: 0                # <- *p := acc")

    def gen_unop(self, e):
        _, op, operand = e
        if op == '-':
            # 0 - operand  (mod 256)
            self.gen_expr(operand)
            t = self.new_temp()
            self.emit(f"        store {t}")
            self.emit(f"        load  {self.const_label(0)}")
            self.emit(f"        sub   {t}")
            return
        if op == '~':
            self.gen_expr(operand)
            self.emit("        not")
            return
        if op == '!':
            # logical NOT: result is 1 if operand==0 else 0
            self.gen_expr(operand)
            l_zero = self.new_label("not_zero")
            l_end = self.new_label("not_end")
            self.emit(f"        ifzero {l_zero}")
            self.emit(f"        load  {self.const_label(0)}")
            self.emit(f"        goto  {l_end}")
            self.emit(f"{l_zero}: load  {self.const_label(1)}")
            self.emit(f"{l_end}: nop")
            return
        raise CompileError(f"unknown unary op {op!r}")

    def gen_binop(self, e):
        _, op, left, right = e

        # Comparisons produce a 0/1 boolean in ACC.
        if op in ('==', '!=', '<', '>', '<=', '>='):
            self.gen_comparison(op, left, right)
            return

        if op == '*':
            self.gen_multiply(left, right)
            return

        mem_op = {'+': 'add', '-': 'sub', '&': 'and', '|': 'or', '^': 'xor'}

        # Fast path: when the right operand is a constant or a plain variable it
        # already lives in a fixed data byte, so we can evaluate the left operand
        # into ACC and apply the op against that byte directly — no spill temp.
        # This saves a `store` (and a data byte) per such op; on the 256-byte
        # machine that adds up (e.g. every `n-1` in a recursive body).
        if op in mem_op and right[0] in ('num', 'var'):
            self.gen_expr(left)
            slot = (self.const_label(right[1]) if right[0] == 'num'
                    else self.var_label(right[1]))
            self.emit(f"        {mem_op[op]:<5} {slot}")
            return

        # Arithmetic / bitwise: evaluate right first, spill it, then left,
        # then apply the op against the spilled right operand.
        self.gen_expr(right)
        t = self.new_temp()
        self.emit(f"        store {t}")
        self.gen_expr(left)

        if op in mem_op:
            self.emit(f"        {mem_op[op]:<5} {t}")
        elif op in ('<<', '>>'):
            self.gen_shift(op, right, t)
        else:
            raise CompileError(f"unknown binary op {op!r}")

    def gen_shift(self, op, right, spilled_right):
        # ACC currently holds the left operand; spilled_right holds the shift
        # amount. If the shift amount is a compile-time constant we can unroll
        # into that many left/right instructions. Otherwise we build a small
        # runtime loop that shifts ACC one bit at a time.
        instr = 'left' if op == '<<' else 'right'
        if right[0] == 'num':
            for _ in range(right[1] & 0xFF):
                self.emit(f"        {instr}")
            return
        # runtime variable shift amount
        acc_tmp = self.new_temp()
        cnt_tmp = self.new_temp()
        l_loop = self.new_label("shift_loop")
        l_end = self.new_label("shift_end")
        self.emit(f"        store {acc_tmp}       # value to shift")
        self.emit(f"        load  {spilled_right}")
        self.emit(f"        store {cnt_tmp}       # shift count")
        self.emit(f"{l_loop}: load  {cnt_tmp}")
        self.emit(f"        ifzero {l_end}")
        self.emit(f"        load  {acc_tmp}")
        self.emit(f"        {instr}")
        self.emit(f"        store {acc_tmp}")
        self.emit(f"        load  {cnt_tmp}")
        self.emit(f"        sub   {self.const_label(1)}")
        self.emit(f"        store {cnt_tmp}")
        self.emit(f"        goto  {l_loop}")
        self.emit(f"{l_end}: load  {acc_tmp}")

    def gen_multiply(self, left, right):
        # result = left * right via repeated addition (loop `right` times,
        # adding `left` each pass). Both operands wrap mod 256; the product
        # is taken mod 256 as well.
        self.comment("multiply via repeated addition")
        a_tmp = self.new_temp()       # the value being added (left)
        cnt_tmp = self.new_temp()     # loop counter (right)
        res_tmp = self.new_temp()     # accumulating result
        self.gen_expr(left)
        self.emit(f"        store {a_tmp}")
        self.gen_expr(right)
        self.emit(f"        store {cnt_tmp}")
        self.emit(f"        load  {self.const_label(0)}")
        self.emit(f"        store {res_tmp}")
        l_loop = self.new_label("mul_loop")
        l_end = self.new_label("mul_end")
        self.emit(f"{l_loop}: load  {cnt_tmp}")
        self.emit(f"        ifzero {l_end}")
        self.emit(f"        load  {res_tmp}")
        self.emit(f"        add   {a_tmp}")
        self.emit(f"        store {res_tmp}")
        self.emit(f"        load  {cnt_tmp}")
        self.emit(f"        sub   {self.const_label(1)}")
        self.emit(f"        store {cnt_tmp}")
        self.emit(f"        goto  {l_loop}")
        self.emit(f"{l_end}: load  {res_tmp}")

    # Produce (left - right) in ACC, used by comparisons. Leaves difference.
    def _gen_diff(self, left, right):
        # If right is already a fixed data byte (constant or variable), subtract
        # it directly — no spill temp (same saving as gen_binop's fast path).
        if right[0] in ('num', 'var'):
            self.gen_expr(left)
            slot = (self.const_label(right[1]) if right[0] == 'num'
                    else self.var_label(right[1]))
            self.emit(f"        sub   {slot}")
            return
        self.gen_expr(right)
        t = self.new_temp()
        self.emit(f"        store {t}")
        self.gen_expr(left)
        self.emit(f"        sub   {t}")

    def gen_comparison(self, op, left, right):
        # All comparisons boil down to producing a 0/1 result in ACC.
        # == / != : test whether (left - right) is zero.
        # < / > / <= / >= : use the sign bit (bit 7) of (left - right).
        #   For unsigned 8-bit a,b with the mod-256 subtraction:
        #     bit7 of (a-b) is set  <=>  a < b   (this is the max.toys trick,
        #     valid when a and b differ by less than 128, which holds for the
        #     small values this compiler targets).
        if op in ('==', '!='):
            self._gen_diff(left, right)
            l_eq = self.new_label("eq")
            l_end = self.new_label("eq_end")
            self.emit(f"        ifzero {l_eq}")
            # not equal
            self.emit(f"        load  {self.const_label(1 if op == '!=' else 0)}")
            self.emit(f"        goto  {l_end}")
            self.emit(f"{l_eq}: load  {self.const_label(0 if op == '!=' else 1)}")
            self.emit(f"{l_end}: nop")
            return

        # relational: compute sign bit of a difference
        if op == '<':
            self._gen_diff(left, right)      # a - b ; bit7 set  <=> a < b
            want_neg = True
        elif op == '>':
            self._gen_diff(right, left)      # b - a ; bit7 set  <=> b < a  <=> a > b
            want_neg = True
        elif op == '>=':
            self._gen_diff(left, right)      # a - b ; bit7 clear <=> a >= b
            want_neg = False
        elif op == '<=':
            self._gen_diff(right, left)      # b - a ; bit7 clear <=> a <= b
            want_neg = False
        else:
            raise CompileError(f"unknown comparison {op!r}")

        # isolate bit 7
        self.emit(f"        and   {self.const_label(0x80)}")
        # ACC is now 0 (bit7 clear) or 128 (bit7 set)
        l_neg = self.new_label("cmp_neg")
        l_end = self.new_label("cmp_end")
        self.emit(f"        ifzero {l_neg}")
        # bit7 was set
        self.emit(f"        load  {self.const_label(1 if want_neg else 0)}")
        self.emit(f"        goto  {l_end}")
        self.emit(f"{l_neg}: load  {self.const_label(0 if want_neg else 1)}")
        self.emit(f"{l_end}: nop")

    # -- condition for if/while: jump to `false_label` when cond is false --
    def gen_cond_branch(self, cond, false_label):
        # Fast paths that avoid materializing a 0/1 boolean.
        if cond[0] == 'binop' and cond[1] in ('==', '!='):
            _, op, left, right = cond
            self._gen_diff(left, right)
            if op == '==':
                # cond true when diff==0; jump away when diff!=0
                l_true = self.new_label("cond_true")
                self.emit(f"        ifzero {l_true}")
                self.emit(f"        goto  {false_label}")
                self.emit(f"{l_true}: nop")
            else:  # !=
                # cond true when diff!=0; jump away when diff==0
                self.emit(f"        ifzero {false_label}")
            return
        # Relational fast path: branch straight off the sign bit of a difference,
        # skipping the 0/1 materialisation (saves several bytes per branch — this
        # matters on the 256-byte machine, and every if/while uses it).
        if cond[0] == 'binop' and cond[1] in ('<', '>', '<=', '>='):
            _, op, left, right = cond
            # bit7 of (a-b) is set  <=>  a < b  (valid for the small values this
            # compiler targets; same trick as gen_comparison / max.toys).
            if op == '<':       self._gen_diff(left, right);  true_if_neg = True
            elif op == '>':     self._gen_diff(right, left);  true_if_neg = True
            elif op == '>=':    self._gen_diff(left, right);  true_if_neg = False
            else:               self._gen_diff(right, left);  true_if_neg = False
            self.emit(f"        and   {self.const_label(0x80)}")
            if true_if_neg:
                # true when bit7 set (ACC!=0); jump to false when ACC==0.
                self.emit(f"        ifzero {false_label}")
            else:
                # true when bit7 clear (ACC==0); jump to false when ACC!=0.
                l_true = self.new_label("cond_true")
                self.emit(f"        ifzero {l_true}")
                self.emit(f"        goto  {false_label}")
                self.emit(f"{l_true}: nop")
            return
        # General path: evaluate to boolean, branch when zero (false).
        self.gen_expr(cond)
        self.emit(f"        ifzero {false_label}")

    # -- statements --
    def gen_stmt(self, s):
        kind = s[0]
        if kind == 'block':
            for st in s[1]:
                self.gen_stmt(st)
            return
        if kind == 'decl':
            _, name, init = s
            label = self.declare(name)
            self.comment(f"int {name}" + (" = ..." if init is not None else ""))
            if init is not None:
                self.gen_expr(init)
                self.emit(f"        store {label}")
            return
        if kind == 'assign':
            _, name, expr = s
            self.comment(f"{name} = ...")
            self.gen_expr(expr)
            self.emit(f"        store {self.var_label(name)}")
            return
        if kind == 'arraydecl':
            _, name, size, init = s
            # Array initializers must be compile-time constants (like the size):
            # they become the array's initial data bytes. Runtime-computed
            # element initializers are not supported.
            self.comment(f"int {name}[{size}]" + (" = {...}" if init else ""))
            init_bytes = None
            if init is not None:
                init_bytes = []
                for x in init:
                    if x[0] != 'num':
                        raise CompileError(
                            f"array {name!r} initializers must be constants")
                    init_bytes.append(x[1] & 0xFF)
            self.declare_array(name, size, init_bytes)
            return
        if kind == 'idxassign':
            self.gen_index_write(s)
            return
        if kind == 'deref_assign':
            self.gen_deref_write(s)
            return
        if kind == 'return':
            _, expr = s
            self.comment("return")
            self.gen_expr(expr)
            self.emit("        stop")
            return
        if kind == 'if':
            self.gen_if(s)
            return
        if kind == 'while':
            self.gen_while(s)
            return
        if kind == 'label':
            # A jump target. The Toy CPU has no bare label, so we anchor it on a
            # nop. Introduced by the CallLifter (e.g. a while-end target, or a
            # call-site continuation) so a `goto` has a place to land.
            _, name = s
            self.emit(f"{name}: nop")
            return
        if kind == 'goto':
            _, name = s
            self.emit(f"        goto  {name}")
            return
        if kind == 'setmark':
            # Write this call site's marker constant into the callee's marker
            # slot, so f__dispatch can return control to the right continuation.
            _, fname, k = s
            self.emit(f"        load  {self.const_label(k)}")
            self.emit(f"        store {fname}__mark")
            return
        if kind == 'call_jump':
            # Jump into the callee's single body copy, then land the return here.
            _, fname, cont = s
            self.emit(f"        goto  {fname}__body")
            self.emit(f"{cont}: nop")
            return
        if kind == 'push':
            self.gen_push(self.var_label(s[1]))
            return
        if kind == 'pop':
            self.gen_pop(self.var_label(s[1]))
            return
        raise CompileError(f"cannot generate statement {s!r}")

    def gen_index_write(self, s):
        # a[idx] = expr : evaluate expr into a temp, compute the element address
        # and patch a raw STORE's address byte, then load the value and run the
        # STORE (self-modifying code, mirroring gen_index_read).
        _, name, idx, expr = s
        base = self._index_base_label(name)
        self.comment(f"{name}[idx] = ...")
        val = self.new_temp()
        self.gen_expr(expr)
        self.emit(f"        store {val}")
        addr = self.new_label("istore_arg")
        self._gen_element_addr(base, idx)
        self.emit(f"        store {addr}       # patch STORE address to &{name}[idx]")
        self.emit(f"        load  {val}")
        self.emit(f"        21               # STORE opcode (raw)")
        self.emit(f"{addr}: 0                # <- {name}[idx] := acc")

    def gen_if(self, s):
        _, cond, then_body, else_body = s
        self.comment("if")
        if else_body is None:
            l_end = self.new_label("if_end")
            self.gen_cond_branch(cond, l_end)
            self.gen_stmt(then_body)
            self.emit(f"{l_end}: nop")
        else:
            l_else = self.new_label("else")
            l_end = self.new_label("if_end")
            self.gen_cond_branch(cond, l_else)
            self.gen_stmt(then_body)
            self.emit(f"        goto  {l_end}")
            self.emit(f"{l_else}: nop")
            self.gen_stmt(else_body)
            self.emit(f"{l_end}: nop")

    def gen_while(self, s):
        _, cond, body = s
        l_top = self.new_label("while_top")
        l_end = self.new_label("while_end")
        self.comment("while")
        self.emit(f"{l_top}: nop")
        self.gen_cond_branch(cond, l_end)
        self.gen_stmt(body)
        self.emit(f"        goto  {l_top}")
        self.emit(f"{l_end}: nop")

    def register_slots(self, name, params):
        # The fixed global slots this function owns: one per parameter, a
        # return-value slot and a marker slot. Registering them as variables lets
        # the body read params (('var', f__p_a)) and the callers write them
        # (('assign', f__p_a, ...)) through the ordinary codegen path. Must happen
        # before ANY code is generated, since main references these slots.
        for p in params:
            self.add_global_slot(f"{name}__p_{p}")
        self.add_global_slot(f"{name}__ret")
        self.add_global_slot(f"{name}__mark")

    # -- one function body block + its marker-dispatch return chain --
    def gen_function(self, name, params, body_block, n_sites):
        self.emit("")
        self.comment(f"function {name}(...) — single body, marker-dispatch return")
        self.emit(f"{name}__body: nop")
        self.gen_stmt(body_block)
        # If control falls off the end without an explicit return, still go to
        # the dispatch chain (f__ret keeps whatever value it had, default 0).
        # Skip it when the body already ends by jumping to dispatch (every path
        # returned) — that goto would be dead code, and on a 256-byte machine
        # those 2 bytes matter.
        if self.code[-1].strip() != f"goto  {name}__dispatch":
            self.emit(f"        goto  {name}__dispatch")

        # Dispatch: compare the marker slot against each call site's constant and
        # jump back to that site's continuation. Loaded fresh each compare for
        # simplicity (this is a teaching tool, not optimised).
        self.emit(f"{name}__dispatch: nop")
        for k in range(n_sites):
            self.emit(f"        load  {name}__mark")
            if k != 0:
                self.emit(f"        sub   {self.const_label(k)}")
            # k==0: marker 0 means ACC is already 0, so `ifzero` matches directly
            # (skipping a `sub 0` no-op saves 2 bytes on the tight budget).
            self.emit(f"        ifzero {name}__cont_{k}")
        # No marker matched (shouldn't happen). Halt rather than run into data.
        self.emit(f"        stop            # unreachable: bad {name} marker")

    def _peephole(self, code):
        """Drop a `load X` that immediately follows `store X` on the next line:
        `store` leaves ACC unchanged, so ACC already holds mem[X] and the reload
        is redundant. Only safe when the `load` line carries NO label (it must
        not be a jump target). Small but the 256-byte budget is tight."""
        def parts(line):
            body = line.split('#', 1)[0].strip()
            label = None
            if ':' in body:
                label, body = body.split(':', 1)
                label = label.strip()
                body = body.strip()
            toks = body.split()
            return label, (toks[0] if toks else None), (toks[1] if len(toks) > 1 else None)
        def next_code(j):
            """Index of the next real instruction line at/after j (skip blank
            and comment-only lines), or None."""
            while j < len(code):
                _, mn, _ = parts(code[j])
                if mn is not None:
                    return j
                j += 1
            return None
        out = []
        i = 0
        while i < len(code):
            line = code[i]
            _, mn, arg = parts(line)
            if mn == 'store' and arg is not None:
                j = next_code(i + 1)
                if j is not None:
                    lbl2, mn2, arg2 = parts(code[j])
                    if mn2 == 'load' and arg2 == arg and lbl2 is None:
                        # emit everything up to (but not incl.) the redundant load,
                        # then skip that load line.
                        out.extend(code[i:j])
                        i = j + 1
                        continue
            out.append(line)
            i += 1
        return out

    # -- assemble the whole .toys file --
    def generate(self, main_body, bodies, source_name):
        # `main_body` is main's ('block', [...]); `bodies` is the list of
        # (name, params, body_block, n_sites) for every called non-main function
        # (from CallLifter). Recursion works: each call is bracketed by
        # save/restore of the caller's live-across slots on the stack.
        # Register every function's global slots up front, because main's code
        # (generated first) already reads/writes them.
        for name, params, _body, _n in bodies:
            self.register_slots(name, params)

        # The call stack lives at the very top of memory and grows DOWN. `sp`
        # points at the last-pushed byte and starts at 255 (byte 255 is left
        # unused; the first push writes to 254). Overflow into the data region
        # is unchecked — depth is bounded by the free bytes between end-of-data
        # and the stack top (see doc-typst/design/recursion-codegen.md).
        self.add_global_slot("sp", 255)

        self.gen_stmt(main_body)
        # Safety net: if control falls off the end of main without a return,
        # halt anyway (returning whatever is in ACC).
        self.emit("        stop            # fallthrough halt")

        # Emit each function's single body + its dispatch chain after main. main
        # never falls into them (it always ends in `stop`).
        for name, params, body_block, n_sites in bodies:
            self.gen_function(name, params, body_block, n_sites)

        lines = []
        lines.append(f"# Generated by toycc from {source_name}")
        lines.append("# Toy CPU assembly. 8-bit values, wraps mod 256.")
        lines.append("# The return value ends up in ACC when the program stops.")
        lines.append("")
        lines.extend(self._peephole(self.code))
        lines.append("")
        lines.append(DATA_MARKER)   # canonical marker so --detect-code-overwrite works
        # C variables (declared but possibly with runtime init; give initial 0)
        for label in self.declared_order:
            lines.append(f"{label}: 0")
        # global call slots (param / return-value / marker bytes)
        for label, init in self.global_slots:
            lines.append(f"{label}: {init}")
        # temporaries
        for label in self.temps:
            lines.append(f"{label}: 0")
        # constants
        for value, label in sorted(self.consts.items()):
            lines.append(f"{label}: {value}")
        # arrays: one base-pointer byte (address constant) then the contiguous
        # element block. Emitting the base right before its data keeps the two
        # together and readable; the assembler resolves `arr_x` to its address.
        for data_label, vals, base_label in self.array_data:
            lines.append(f"{base_label}: {data_label}   # address of {data_label}[0]")
            lines.append(f"{data_label}: {vals[0]}")
            for v in vals[1:]:
                lines.append(f"        {v}")
        # &x address-constant bytes: each holds the address of variable x's slot.
        for slot, alabel in self.addrof_slots.items():
            lines.append(f"{alabel}: {slot}   # address of {slot}")
        return "\n".join(lines) + "\n"


# ── Call-graph analysis ─────────────────────────────────────────────────────

def _calls_in(node):
    """Yield the names of every function called anywhere inside an AST node."""
    if not isinstance(node, tuple):
        return
    if node[0] == 'call':
        yield node[1]
    for child in node[1:]:
        if isinstance(child, tuple):
            yield from _calls_in(child)
        elif isinstance(child, list):
            for c in child:
                yield from _calls_in(c)

def _declares_array(node):
    """True if the AST subtree declares a local array anywhere."""
    if not isinstance(node, tuple):
        return False
    if node[0] == 'arraydecl':
        return True
    for child in node[1:]:
        if isinstance(child, tuple):
            if _declares_array(child):
                return True
        elif isinstance(child, list):
            if any(_declares_array(c) for c in child):
                return True
    return False

def _takes_address(node):
    """True if the AST subtree takes the address of anything (&x or &a[i])."""
    if not isinstance(node, tuple):
        return False
    if node[0] in ('addrof', 'addrof_index'):
        return True
    for child in node[1:]:
        if isinstance(child, tuple):
            if _takes_address(child):
                return True
        elif isinstance(child, list):
            if any(_takes_address(c) for c in child):
                return True
    return False

def build_call_graph(funcs):
    """funcs: list of ('func', name, params, body).
    Returns {name: set(callee names)} restricted to defined functions."""
    defined = {f[1] for f in funcs}
    graph = {}
    for _, name, _params, body in funcs:
        graph[name] = {c for c in _calls_in(body) if c in defined}
    return graph

def find_recursive(graph):
    """Return the set of functions that are part of a cycle in the call graph
    (self-recursive or mutually recursive). A function is recursive iff it can
    reach itself by following calls — a plain reachability check via DFS."""
    def reaches_self(start):
        seen, stack = set(), list(graph.get(start, ()))
        while stack:
            n = stack.pop()
            if n == start:
                return True
            if n not in seen:
                seen.add(n)
                stack.extend(graph.get(n, ()))
        return False
    return {name for name in graph if reaches_self(name)}


# ── Global-slots + marker-dispatch call scheme, made recursion-safe ─────────
#
# The Toy CPU has no call/return, no stack, no indirect jump. To support real
# (non-inlined) functions we give each function `f` FIXED global data bytes and
# emit its body EXACTLY ONCE:
#
#   f__p_<param>  one byte per parameter   (caller writes the argument here)
#   f__ret        one byte                 (body writes the return value here)
#   f__mark       one byte                 (caller writes which call site called)
#   f__body:      the single copy of f's body
#   f__dispatch:  a compare-chain over f__mark that jumps back to the caller
#
# A CALL f(args) at call site k (0,1,2,…) becomes:
#   store each arg into f__p_<param>;  set f__mark := k;  goto f__body;
#   f__cont_k: nop                     ← body returns HERE via the dispatch chain
# and the call's value is then sitting in f__ret.
#
# f__dispatch is: for each site k, `load f__mark; sub k; ifzero f__cont_k`. The
# body's `return e` becomes `eval e; store f__ret; goto f__dispatch`.
#
# RECURSION. Those global slots are shared across all activations of f, so a
# recursive re-entry would clobber the caller's. We make it safe by SAVING the
# caller's live-across slots on a real stack before the jump and RESTORING them
# after (uniform save/restore — see doc-typst/design/recursion-codegen.md). The
# stack grows down from the top of memory via self-modifying indirect push/pop
# (CodeGen.gen_push/gen_pop). The save set is the caller's slots LIVE ACROSS the
# call, computed by a live-variable analysis (CallLifter.insert_save_restore);
# "save everything" would be wrong (it re-saves the temp holding THIS call's
# result and miscompiles fib(4) to 2). The `-O` flag skips save/restore around
# calls whose caller is provably non-recursive — a pure size optimisation.
#
# A pure AST-to-AST pass (CallLifter) does the rewrite. It turns each function
# body into a call-free block using ('label',n)/('goto',n) plus small new
# statement nodes the codegen understands:
#   ('setmark', fname, k)        -> load k; store f__mark
#   ('call_jump', fname, cont)   -> goto f__body; cont: nop
#   ('push', slot) / ('pop', slot) -> indirect stack save/restore
# A call in EXPRESSION position (y = f(a)+1) is lifted: the call statements run
# first, then the sub-expression is replaced by ('var', capture-temp).

class CallLifter:
    def __init__(self, funcs, recursive, optimize=False):
        self.funcs = {f[1]: f for f in funcs}
        self.recursive = set(recursive)
        self.optimize = optimize  # -O: skip save/restore when caller not recursive
        self.call_counts = {}     # fname -> number of call sites seen so far
        self.uid = 0              # unique suffix for local-variable renaming
        self.cur_caller = None    # name of the function currently being lifted

    def next_site(self, fname):
        k = self.call_counts.get(fname, 0)
        self.call_counts[fname] = k + 1
        return k

    def fresh(self, base):
        self.uid += 1
        return f"{base}__u{self.uid}"

    # -- main entry --
    # Returns (main_block, bodies) where:
    #   main_block : ('block', [...]) — main's body, call-free
    #   bodies     : list of (fname, params, body_block, n_sites) in definition
    #                order (only functions that are actually reachable/emitted)
    def run(self):
        main = self.funcs['main']
        _, _name, params, body = main
        if params:
            raise CompileError("main must take no parameters (or void)")
        # Rewrite main. Any call inside gets lifted, which also records call
        # sites on the callees. main's own `return` stays a real return (halts).
        self.cur_caller = 'main'
        main_out = []
        self.lift_stmt(body, main_out, ret_slot=None)
        main_out = self.insert_save_restore('main', main_out)
        main_block = ('block', main_out)

        # Rewrite every non-main function that gets called (transitively). A
        # called function may itself call others that main never mentions, so
        # we process a worklist: lifting a body can reveal new callees, which
        # we then lift too, until no new function appears.
        lifted = {}                            # name -> (params, block)
        pending = [n for n in self.call_counts if n != 'main']
        while pending:
            name = pending.pop()
            if name in lifted:
                continue
            _, _n, fparams, fbody = self.funcs[name]
            # Flat per-function namespace: params map to the fixed parameter
            # slots (f__p_<param>); locals get a unique per-function prefix.
            rename = {p: f"{name}__p_{p}" for p in fparams}
            for local in self._declared_names(fbody):
                if local not in rename:
                    rename[local] = f"{name}__l_{local}"
            fbody2 = self._rename(fbody, rename)
            self.cur_caller = name
            out = []
            self.lift_stmt(fbody2, out, ret_slot=f"{name}__ret")
            out = self.insert_save_restore(name, out)
            lifted[name] = (list(fparams), ('block', out))
            # Lifting may have discovered calls to not-yet-lifted functions.
            pending.extend(n for n in self.call_counts
                           if n != 'main' and n not in lifted)

        bodies = [(name, params, block, self.call_counts[name])
                  for name, (params, block) in lifted.items()]
        return main_block, bodies

    # -- helpers: gather declared names, and rename variables in a subtree --
    def _declared_names(self, node):
        names = set()
        def walk(n):
            if not isinstance(n, tuple):
                return
            if n[0] in ('decl', 'arraydecl'):
                names.add(n[1])
            for child in n[1:]:
                if isinstance(child, tuple):
                    walk(child)
                elif isinstance(child, list):
                    for c in child:
                        walk(c)
        walk(node)
        return names

    def _rename(self, node, rename):
        """Copy `node`, remapping 'var'/'assign'/'decl' names through `rename`
        (unknown names left as-is). Calls are kept intact for later lifting."""
        if not isinstance(node, tuple):
            return node
        tag = node[0]
        if tag == 'var':
            return ('var', rename.get(node[1], node[1]))
        if tag == 'decl':
            _, nm, init = node
            return ('decl', rename.get(nm, nm),
                    None if init is None else self._rename(init, rename))
        if tag == 'assign':
            _, nm, expr = node
            return ('assign', rename.get(nm, nm), self._rename(expr, rename))
        if tag == 'arraydecl':
            _, nm, size, init = node
            init2 = (None if init is None
                     else [self._rename(x, rename) for x in init])
            return ('arraydecl', rename.get(nm, nm), size, init2)
        if tag == 'index':
            _, nm, idx = node
            return ('index', rename.get(nm, nm), self._rename(idx, rename))
        if tag == 'idxassign':
            _, nm, idx, expr = node
            return ('idxassign', rename.get(nm, nm),
                    self._rename(idx, rename), self._rename(expr, rename))
        if tag == 'addrof':
            return ('addrof', rename.get(node[1], node[1]))
        if tag == 'addrof_index':
            _, nm, idx = node
            return ('addrof_index', rename.get(nm, nm), self._rename(idx, rename))
        if tag == 'deref_assign':
            _, ptr, expr = node
            return ('deref_assign', self._rename(ptr, rename),
                    self._rename(expr, rename))
        parts = [tag]
        for child in node[1:]:
            if isinstance(child, tuple):
                parts.append(self._rename(child, rename))
            elif isinstance(child, list):
                parts.append([self._rename(c, rename) for c in child])
            else:
                parts.append(child)
        return tuple(parts)

    # ── statement pass ──────────────────────────────────────────────────────
    # Append the call-free translation of `s` to `out`. `ret_slot` is None in
    # main (a `return` really halts) or 'f__ret' inside f's body (a `return e`
    # becomes: store e to f__ret; goto f__dispatch).
    def lift_stmt(self, s, out, ret_slot):
        kind = s[0]

        if kind == 'block':
            for st in s[1]:
                self.lift_stmt(st, out, ret_slot)
            return

        if kind == 'decl':
            _, name, init = s
            init2 = None if init is None else self.lift_calls(init, out)
            out.append(('decl', name, init2))
            return

        if kind == 'arraydecl':
            _, name, size, init = s
            init2 = (None if init is None
                     else [self.lift_calls(x, out) for x in init])
            out.append(('arraydecl', name, size, init2))
            return

        if kind == 'assign':
            _, name, expr = s
            out.append(('assign', name, self.lift_calls(expr, out)))
            return

        if kind == 'idxassign':
            _, name, idx, expr = s
            idx2 = self.lift_calls(idx, out)
            expr2 = self.lift_calls(expr, out)
            out.append(('idxassign', name, idx2, expr2))
            return

        if kind == 'deref_assign':
            _, ptr, expr = s
            ptr2 = self.lift_calls(ptr, out)
            expr2 = self.lift_calls(expr, out)
            out.append(('deref_assign', ptr2, expr2))
            return

        if kind == 'exprstmt':
            # A bare expression statement (e.g. a call whose result is unused):
            # lift any calls it contains; the resulting value is discarded.
            self.lift_calls(s[1], out)
            return

        if kind == 'return':
            _, expr = s
            expr2 = self.lift_calls(expr, out)
            if ret_slot is None:
                out.append(('return', expr2))          # main: really halt
            else:
                out.append(('assign', ret_slot, expr2))  # store to f__ret
                out.append(('goto', f"{ret_slot[:-5]}__dispatch"))
            return

        if kind == 'if':
            _, cond, then_body, else_body = s
            cond2 = self.lift_calls(cond, out)     # cond evaluated before branch
            then2 = self.block_of(then_body, ret_slot)
            else2 = None if else_body is None else self.block_of(else_body, ret_slot)
            out.append(('if', cond2, then2, else2))
            return

        if kind == 'while':
            # The condition is re-evaluated every iteration, so a call inside it
            # must be re-run each pass. Rewrite
            #   while (cond) { body }
            # into
            #   while (1) { <lift cond>; if (!cond) goto end; body }  end:
            _, cond, body = s
            # If the condition has no call, keep a plain `while (cond) body`: the
            # code generator's gen_cond_branch handles it with a single cheap
            # branch (no boolean materialisation). Only conditions containing a
            # call need the `while(1){ lift-cond; if(!cond) goto end; body }`
            # rewrite (the call must be re-evaluated each iteration). Keeping the
            # plain form is a big size win — it's what lets the array-parameter
            # bubble sort fit the 256-byte machine.
            if not any(True for _ in _calls_in(cond)):
                body_out = []
                self.lift_stmt(body, body_out, ret_slot)
                out.append(('while', cond, ('block', body_out)))
                return
            end = self.fresh('while_end')
            inner = []
            cond2 = self.lift_calls(cond, inner)
            inner.append(('if', ('unop', '!', cond2), ('goto', end), None))
            self.lift_stmt(body, inner, ret_slot)
            out.append(('while', ('num', 1), ('block', inner)))
            out.append(('label', end))
            return

        if kind in ('label', 'goto'):
            out.append(s)
            return

        raise CompileError(f"cannot compile statement {s!r}")

    def block_of(self, s, ret_slot):
        inner = []
        self.lift_stmt(s, inner, ret_slot)
        return ('block', inner)

    # ── save/restore insertion (live-variable analysis) ──────────────────────
    # After a function body has been lifted to a call-free tree of
    # blocks/ifs/whiles/gotos plus ('call_site', ...) nodes, wrap every call
    # with push/pop of the CALLER's slots that are LIVE ACROSS the call.
    #
    # Why liveness (not "save everything"): every named byte (locals, params,
    # mark, compiler temps) is a single GLOBAL byte shared by all activations, so
    # a recursive re-entry clobbers all of them. We must restore exactly those
    # whose value is still needed after the call. "Save all" wrongly re-saves the
    # capture temp holding THIS call's result and can miscompile fib(4) to 2; the
    # correct set excludes it because it is written by the call, not before it.
    #
    # Save set at a call site = live-out(node) ∩ caller-owned slots − {capture}.
    # (The capture temp is a DEF at the node, so standard liveness drops it.)

    def insert_save_restore(self, caller, stmts):
        # -O optimisation: a non-recursive caller can never be re-entered, so no
        # call from it can clobber its slots — skip save/restore entirely.
        skip = self.optimize and caller not in self.recursive
        live_at_label = {}   # label name -> set of vars live just before it
        caller_slots = self._caller_slots(caller, stmts)

        # Iterate to a fixpoint because gotos create back-edges (loops). Each
        # pass recomputes label live-in from the current estimates until stable.
        for _ in range(100):
            changed = [False]
            self._live_block(stmts, set(), live_at_label, caller_slots,
                             changed, record=False)
            if not changed[0]:
                break
        # Final pass with recording: expand call_site nodes using stable liveness.
        result, _live = self._live_block(stmts, set(), live_at_label, caller_slots,
                                         [False], record=True, caller=caller,
                                         skip=skip)
        return result

    def _caller_slots(self, caller, stmts):
        """The caller-owned bytes that may need saving: its params, locals, mark,
        and every compiler temp declared in its body. (Callee slots and shared
        return slots are never in this set, so they are never saved.)

        A variable whose address is taken (`&x`) is EXCLUDED: its home is its
        memory slot, and a callee may write it indirectly through the pointer, so
        saving/restoring its value would undo that write. (Taking a local's
        address inside a RECURSIVE function is rejected earlier in compile_source,
        because a pointer to the single global slot can't follow the save/restore
        stack — so here the caller is always non-recursive w.r.t. address-taken
        locals.)"""
        slots = {f"{caller}__mark"}
        addr_taken = set()
        _, _n, params, _body = self.funcs[caller]
        for p in params:
            slots.add(f"{caller}__p_{p}")
        def walk(node):
            if not isinstance(node, tuple):
                return
            if node[0] == 'decl':
                slots.add(node[1])
            if node[0] in ('addrof', 'addrof_index'):
                addr_taken.add(node[1])
            if node[0] == 'call_site':
                # The capture temp is declared later (during expansion) but is a
                # caller-owned byte holding a call result; a sibling call may need
                # it saved across it, so it must be a candidate for the save set.
                slots.add(node[5])
            for c in node[1:]:
                if isinstance(c, tuple):
                    walk(c)
                elif isinstance(c, list):
                    for x in c:
                        walk(x)
        for s in stmts:
            walk(s)
        return slots - addr_taken

    def _as_stmt(self, x):
        """Normalise a liveness-pass result (a stmt, a list of stmts, or None)
        into a single statement: a list becomes a ('block', ...)."""
        if x is None:
            return None
        if isinstance(x, list):
            return ('block', x)
        return x

    def _expr_uses(self, e, acc):
        if not isinstance(e, tuple):
            return
        if e[0] == 'var':
            acc.add(e[1])
            return
        if e[0] == 'index':
            # a[idx]: the index expression's variables are used. So is `a` itself
            # when it is a pointer/param (its value is the base address); a real
            # array name is not a tracked scalar slot, so marking it is harmless.
            self._expr_uses(e[2], acc)
            acc.add(e[1])
            return
        if e[0] == 'addrof':
            # &x: conservatively treat x as used so its slot is kept live.
            acc.add(e[1])
            return
        if e[0] == 'addrof_index':
            self._expr_uses(e[2], acc)
            acc.add(e[1])
            return
        for c in e[1:]:
            if isinstance(c, tuple):
                self._expr_uses(c, acc)

    # Backward pass over a statement list. `live` is live-out of the list; return
    # (new_stmts, live-in). When record is True, call_site nodes are expanded
    # with push/pop; otherwise the tree is only traversed to update label live-in.
    def _live_block(self, stmts, live, live_at_label, caller_slots,
                    changed, record, caller=None, skip=False):
        live = set(live)
        out_rev = []
        for s in reversed(stmts):
            new_s, live = self._live_stmt(s, live, live_at_label, caller_slots,
                                          changed, record, caller, skip)
            out_rev.extend(reversed(new_s) if isinstance(new_s, list) else [new_s])
        result = list(reversed(out_rev))
        return (result, live) if record else (None, live)

    def _live_stmt(self, s, live, live_at_label, caller_slots,
                   changed, record, caller, skip):
        """Return (replacement, live-in). replacement is a stmt or a list."""
        live = set(live)
        kind = s[0]

        if kind == 'block':
            new, live = self._live_block(s[1], live, live_at_label, caller_slots,
                                         changed, record, caller, skip)
            return (('block', new) if record else s), live

        if kind == 'decl':
            _, name, init = s
            live.discard(name)          # defined here
            if init is not None:
                self._expr_uses(init, live)
            return s, live

        if kind == 'assign':
            _, name, expr = s
            live.discard(name)
            self._expr_uses(expr, live)
            return s, live

        if kind == 'arraydecl':
            # The array is not a saveable scalar slot; only its constant/expr
            # initializers use variables.
            _, _name, _size, init = s
            if init:
                for x in init:
                    self._expr_uses(x, live)
            return s, live

        if kind == 'idxassign':
            # a[idx] = expr : both idx and expr are USES (the array byte written
            # is not a tracked scalar slot, so nothing is killed here). `a` itself
            # is used too when it is a pointer/param base.
            _, name, idx, expr = s
            self._expr_uses(idx, live)
            self._expr_uses(expr, live)
            live.add(name)
            return s, live

        if kind == 'deref_assign':
            # *p = expr : the target byte is reached indirectly (not a tracked
            # scalar slot), so nothing is killed; both p and expr are uses.
            _, ptr, expr = s
            self._expr_uses(ptr, live)
            self._expr_uses(expr, live)
            return s, live

        if kind == 'return':
            self._expr_uses(s[1], live)
            return s, live

        if kind == 'if':
            # then/else may be any statement (block, goto, return, ...), so run
            # the single-statement pass on each rather than assuming a block.
            _, cond, then_b, else_b = s
            new_then, live_then = self._live_stmt(
                then_b, live, live_at_label, caller_slots, changed, record,
                caller, skip)
            if else_b is None:
                live_else = set(live)
                new_else = None
            else:
                new_else, live_else = self._live_stmt(
                    else_b, live, live_at_label, caller_slots, changed, record,
                    caller, skip)
            live = live_then | live_else
            self._expr_uses(cond, live)
            if record:
                s = ('if', cond, self._as_stmt(new_then), self._as_stmt(new_else))
            return s, live

        if kind == 'while':
            # while(cond){body}: body's live-out is body's own live-in plus the
            # condition's uses (both are re-evaluated each iteration). Fixpoint
            # the body until its live-in stops growing. `cond` is ('num',1) for a
            # lifted call-condition loop and a real expression for a plain loop.
            _, _cond, body = s
            body_live_out = set(live)
            self._expr_uses(_cond, body_live_out)
            for _ in range(100):
                _, live_in = self._live_block(body[1], body_live_out, live_at_label,
                                              caller_slots, changed, False,
                                              caller, skip)
                self._expr_uses(_cond, live_in)
                if live_in <= body_live_out:
                    break
                body_live_out |= live_in
            if record:
                new_body, _ = self._live_block(body[1], body_live_out, live_at_label,
                                               caller_slots, changed, True,
                                               caller, skip)
                s = ('while', _cond, ('block', new_body))
            return s, body_live_out

        if kind == 'label':
            name = s[1]
            old = live_at_label.get(name, set())
            if not (live <= old):
                live_at_label[name] = old | live
                changed[0] = True
            return s, set(live_at_label.get(name, live))

        if kind == 'goto':
            # control transfers to the label; live-in = live-in recorded there.
            return s, set(live_at_label.get(s[1], set()))

        if kind == 'call_site':
            return self._expand_call(s, live, caller_slots, record, caller, skip)

        # setmark / call_jump / push / pop don't appear before this pass runs.
        raise CompileError(f"liveness: unexpected stmt {s!r}")

    def _expand_call(self, s, live, caller_slots, record, caller, skip):
        _, name, param_pairs, k, cont, cap, arg_temps = s
        # live-out of the whole call site is `live`. The capture temp is DEFINED
        # here, so it is not live before the call. Save set = the caller slots
        # live across the call (live-out minus the capture temp).
        live_across = (live & caller_slots) - {cap}
        # The caller's marker is ALWAYS live across a call: the callee clobbers
        # C__mark (its setup does setmark), and the caller needs its own marker
        # later for C__dispatch — which lives OUTSIDE this analysed body, so the
        # liveness pass can't see that use. main has no dispatch (it halts), so
        # its non-existent mark is never forced in.
        if caller != 'main':
            live_across.add(f"{caller}__mark")
        save = sorted(live_across)

        # live-in: after the call the value in `cap` came from the call, so cap
        # is no longer live before it. The param slots are the callee's (not in
        # caller_slots). The setup USES the arg temps and reads caller state.
        live = set(live)
        live.discard(cap)
        for pslot, tmp in param_pairs:
            live.add(tmp)              # arg temps are used by the param assigns
        live |= set(save)              # saved slots must be live before the call

        if not record:
            return s, live

        # Expand: [push saves] param-assigns setmark call_jump capture [pop rev]
        do_save = save and not skip
        stmts = []
        if do_save:
            for slot in save:
                stmts.append(('push', slot))
        for pslot, tmp in param_pairs:
            stmts.append(('assign', pslot, ('var', tmp)))
        stmts.append(('setmark', name, k))
        stmts.append(('call_jump', name, cont))
        stmts.append(('decl', cap, ('var', f"{name}__ret")))
        if do_save:
            for slot in reversed(save):
                stmts.append(('pop', slot))
        return stmts, live

    # ── expression pass ─────────────────────────────────────────────────────
    # Return a call-free copy of `e`; every call is emitted into `out` (in eval
    # order) as a global-slot call sequence and replaced by ('var', 'f__ret').
    def lift_calls(self, e, out):
        kind = e[0]
        if kind in ('num', 'var'):
            return e
        if kind == 'unop':
            _, op, operand = e
            return ('unop', op, self.lift_calls(operand, out))
        if kind == 'binop':
            _, op, l, r = e
            l2 = self.lift_calls(l, out)
            r2 = self.lift_calls(r, out)
            return ('binop', op, l2, r2)
        if kind == 'index':
            _, name, idx = e
            return ('index', name, self.lift_calls(idx, out))
        if kind == 'addrof':
            return e
        if kind == 'addrof_index':
            _, name, idx = e
            return ('addrof_index', name, self.lift_calls(idx, out))
        if kind == 'deref':
            return ('deref', self.lift_calls(e[1], out))
        if kind == 'call':
            return self.lift_call(e, out)
        raise CompileError(f"cannot compile expression {e!r}")

    # Emit one call's sequence into `out`; return ('var', 'f__ret'-capture-temp).
    def lift_call(self, call, out):
        _, name, args = call
        if name not in self.funcs:
            raise CompileError(f"call to undefined function {name!r}")

        _, _n, params, _body = self.funcs[name]
        if len(args) != len(params):
            raise CompileError(
                f"call to {name!r} passes {len(args)} args, expects {len(params)}")

        # Evaluate ALL arguments into fresh temps FIRST, then store into the
        # parameter slots. Doing it in two phases is essential: a nested call to
        # the SAME function (e.g. f(1, f(2,3))) would otherwise overwrite this
        # call's own param slots while evaluating a later argument, before we
        # jump. Materialising every argument first makes that safe.
        arg_temps = []
        for arg in args:
            arg2 = self.lift_calls(arg, out)
            tmp = self.fresh('arg')
            out.append(('decl', tmp, arg2))
            arg_temps.append(tmp)
        param_pairs = [(f"{name}__p_{pname}", tmp)
                       for pname, tmp in zip(params, arg_temps)]

        k = self.next_site(name)
        cont = f"{name}__cont_{k}"
        # f__ret is a SHARED slot — the next call overwrites it. The capture temp
        # holds this call's result; it is written AFTER the call, so it is never
        # in the live-across set and restore can't clobber it (design note).
        cap = self.fresh('callret')
        # A single structured node marks the call boundary. The save/restore
        # liveness pass expands it into: [push saves] param-assigns setmark
        # call_jump capture [pop restores].  arg_temps is recorded so the pass
        # knows those temps die inside the setup (they are consumed by the
        # param assigns before the jump) and are therefore never live-across.
        out.append(('call_site', name, param_pairs, k, cont, cap, arg_temps))
        return ('var', cap)


def lift_functions(funcs, recursive, optimize=False):
    """Return (main_block, bodies) with all calls rewritten to the global-slots
    + marker-dispatch scheme, each call bracketed by save/restore of the
    caller's live-across slots. See CallLifter for details."""
    return CallLifter(funcs, recursive, optimize).run()


def compile_source(src, source_name, optimize=False):
    toks = lex(src)
    funcs = Parser(toks).parse_program()[1]

    # Validate calls: every callee must be a defined function.
    defined = {f[1] for f in funcs}
    for _, name, _params, body in funcs:
        for callee in _calls_in(body):
            if callee not in defined:
                raise CompileError(f"call to undefined function {callee!r}")

    graph = build_call_graph(funcs)
    recursive = find_recursive(graph)

    # Arrays are fixed global bytes and are NOT saved/restored across calls, so
    # a recursive function that declares an array would silently clobber it on
    # re-entry. Reject that instead of miscompiling (scalars ARE saved, so this
    # is the one place arrays and recursion don't mix). See the compiler README.
    for _, name, _params, body in funcs:
        if name in recursive and _declares_array(body):
            raise CompileError(
                f"function {name!r} is recursive and declares a local array; "
                f"arrays are not saved across recursive calls (hoist the array "
                f"out of the recursion, or make the function non-recursive)")

    # Taking a local's address (&x, &a[i]) inside a recursive function can't work:
    # &x is the address of the single GLOBAL slot for x, but the save/restore
    # recursion stack keeps each activation's value on a separate stack byte, so a
    # pointer can't follow it. Reject instead of silently miscompiling (the same
    # spirit as the recursive-array rejection above).
    for _, name, _params, body in funcs:
        if name in recursive and _takes_address(body):
            raise CompileError(
                f"function {name!r} is recursive and takes the address of a "
                f"local (&x or &a[i]); a pointer to the single global slot can't "
                f"follow the recursion save/restore stack (take the address in a "
                f"non-recursive function, or pass the value instead)")

    main_block, bodies = lift_functions(funcs, recursive, optimize)

    gen = CodeGen()
    return gen.generate(main_block, bodies, source_name)


# ── CLI ────────────────────────────────────────────────────────────────────

def main():
    ap = argparse.ArgumentParser(
        description="toycc - compile a C subset to Toy CPU assembly (.toys)")
    ap.add_argument('file', help='input C file (.toyc)')
    ap.add_argument('-o', '--output', help='output .toys path')
    ap.add_argument('-r', '--run', action='store_true',
                    help='after compiling, run the .toys through toysim (CLI)')
    ap.add_argument('-O', '--optimize-save-restore', action='store_true',
                    dest='optimize',
                    help='skip save/restore at call sites whose caller is not '
                         'recursive (smaller code, same results; default off)')
    args = ap.parse_args()

    try:
        with open(args.file) as f:
            src = f.read()
    except OSError as e:
        sys.exit(f"cannot read {args.file}: {e}")

    try:
        asm = compile_source(src, os.path.basename(args.file), args.optimize)
    except CompileError as e:
        sys.exit(f"compile error: {e}")

    # Check the generated program actually fits the 256-byte machine, using
    # the assembler as the single source of truth for sizing. Report the same
    # kind of clean error the assembler would, instead of writing a .toys that
    # only fails later.
    _, listing, _, _, errors, _ = assemble(asm)
    size_errors = [e for e in errors if "too big" in e]
    if size_errors:
        sys.exit(f"compile error: {size_errors[0]}")

    # The recursion stack grows DOWN from address 255 into the free space above
    # the program. There is no hardware bounds check: if recursion goes deeper
    # than the free space allows, the stack silently overwrites data and the
    # program computes wrong answers. Warn when a recursive program leaves
    # little stack room, so the failure is visible rather than silent.
    funcs = Parser(lex(src)).parse_program()[1]
    if find_recursive(build_call_graph(funcs)):
        top = max((a for a, *_ in listing if a is not None), default=0)
        free = 255 - top
        if free < 32:
            print(f"WARNING: only {free} bytes of stack space (data ends at "
                  f"{top}, stack grows down from 255). Deep recursion will "
                  f"overflow into data and give wrong results — reduce the "
                  f"input, or pass -O to shrink the code.", file=sys.stderr)

    out_path = args.output
    if out_path is None:
        base = args.file
        if base.endswith('.toyc'):
            base = base[:-5]
        out_path = base + '.toys'

    with open(out_path, 'w') as f:
        f.write(asm)
    print(f"wrote {out_path}")

    if args.run:
        toysim = os.path.join(os.path.dirname(os.path.dirname(
            os.path.abspath(__file__))), 'toysim.py')
        cmd = [sys.executable, toysim, out_path, '--cli', '--run', '--quiet']
        print(f"running: {' '.join(cmd)}")
        subprocess.run(cmd)


if __name__ == '__main__':
    main()
