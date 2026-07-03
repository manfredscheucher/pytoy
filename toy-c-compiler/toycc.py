#!/usr/bin/env python3
"""
toycc - a tiny C-to-assembly compiler for the pytoy "Toy CPU".

It compiles a small, standard-looking subset of C into a .toy assembly file
that the pytoy assembler/simulator (../pytoy.py) can run.

Target machine (see ../docs/):
  - 256 bytes of memory total; code and data share the address space.
  - One 8-bit accumulator (ACC). All arithmetic wraps modulo 256.
  - The only conditional instruction is `ifzero`; the only jump is `goto`.
  - There is no multiply/divide/compare/index register.

Because the machine is 8-bit, every C `int` here is an unsigned 8-bit value
(0..255) that wraps modulo 256. This is documented in the README.

Usage:
    python3 toycc.py program.c                 # writes program.toy
    python3 toycc.py program.c -o out.toy      # custom output path
    python3 toycc.py program.c --run           # compile, then run via pytoy CLI

Design: hand-written lexer + recursive-descent parser + a straightforward
code generator that emits Toy assembly text. Standard library only.
"""

import sys
import os
import argparse
import subprocess


# ── Lexer ──────────────────────────────────────────────────────────────────

KEYWORDS = {'int', 'void', 'return', 'while', 'if', 'else', 'for'}

# Multi-character operators must be tried before single-character ones.
MULTI_OPS = [
    '<<=', '>>=',
    '==', '!=', '<=', '>=', '<<', '>>',
    '+=', '-=', '*=', '&=', '|=', '^=',
    '&&', '||',
]
SINGLE_OPS = set('+-*&|^~<>=(){};,!')


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

    # program := 'int' 'main' '(' ('void')? ')' block
    def parse_program(self):
        self.eat('kw', 'int')
        name = self.eat('ident')
        if name.value != 'main':
            raise CompileError(
                f"line {name.line}: only a single 'int main' function is "
                f"supported, found {name.value!r}")
        self.eat('op', '(')
        if self.at('kw', 'void'):
            self.next()
        self.eat('op', ')')
        body = self.parse_block()
        self.eat('eof')
        return body

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
        # else: assignment (possibly compound)
        return self.parse_assign_stmt()

    def parse_decl(self):
        self.eat('kw', 'int')
        name = self.eat('ident').value
        init = None
        if self.at('op', '='):
            self.next()
            init = self.parse_expr()
        self.eat('op', ';')
        return ('decl', name, init)

    def parse_assign_stmt(self):
        name = self.eat('ident').value
        op = self.eat('op').value
        compound = {'+=': '+', '-=': '-', '*=': '*',
                    '&=': '&', '|=': '|', '^=': '^',
                    '<<=': '<<', '>>=': '>>'}
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
        op = self.eat('op').value
        compound = {'+=': '+', '-=': '-', '*=': '*',
                    '&=': '&', '|=': '|', '^=': '^',
                    '<<=': '<<', '>>=': '>>'}
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
        return self.parse_primary()

    def parse_primary(self):
        t = self.peek()
        if t.kind == 'int_lit':
            self.next()
            return ('num', t.value & 0xFF)
        if t.kind == 'ident':
            self.next()
            return ('var', t.value)
        if t.kind == 'op' and t.value == '(':
            self.next()
            e = self.parse_expr()
            self.eat('op', ')')
            return e
        raise CompileError(f"line {t.line}: unexpected token {t.value!r}")


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
        if name in self.vars:
            raise CompileError(f"variable {name!r} declared twice")
        label = f"v_{name}"
        self.vars[name] = label
        self.declared_order.append(label)
        return label

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

    # -- expression code generation: result left in ACC --
    def gen_expr(self, e):
        kind = e[0]
        if kind == 'num':
            self.emit(f"        load  {self.const_label(e[1])}")
            return
        if kind == 'var':
            self.emit(f"        load  {self.var_label(e[1])}")
            return
        if kind == 'unop':
            self.gen_unop(e)
            return
        if kind == 'binop':
            self.gen_binop(e)
            return
        raise CompileError(f"cannot generate expression {e!r}")

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

        # Arithmetic / bitwise: evaluate right first, spill it, then left,
        # then apply the op against the spilled right operand.
        self.gen_expr(right)
        t = self.new_temp()
        self.emit(f"        store {t}")
        self.gen_expr(left)

        if op == '+':
            self.emit(f"        add   {t}")
        elif op == '-':
            self.emit(f"        sub   {t}")
        elif op == '&':
            self.emit(f"        and   {t}")
        elif op == '|':
            self.emit(f"        or    {t}")
        elif op == '^':
            self.emit(f"        xor   {t}")
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
        #     bit7 of (a-b) is set  <=>  a < b   (this is the max.toy trick,
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
        raise CompileError(f"cannot generate statement {s!r}")

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

    # -- assemble the whole .toy file --
    def generate(self, ast, source_name):
        # main body
        self.gen_stmt(ast)
        # Safety net: if control falls off the end of main without a return,
        # halt anyway (returning whatever is in ACC).
        self.emit("        stop            # fallthrough halt")

        lines = []
        lines.append(f"# Generated by toycc from {source_name}")
        lines.append("# Toy CPU assembly. 8-bit values, wraps mod 256.")
        lines.append("# The return value ends up in ACC when the program stops.")
        lines.append("")
        lines.extend(self.code)
        lines.append("")
        lines.append("# ── data ──")
        # C variables (declared but possibly with runtime init; give initial 0)
        for label in self.declared_order:
            lines.append(f"{label}: 0")
        # temporaries
        for label in self.temps:
            lines.append(f"{label}: 0")
        # constants
        for value, label in sorted(self.consts.items()):
            lines.append(f"{label}: {value}")
        return "\n".join(lines) + "\n"


def compile_source(src, source_name):
    toks = lex(src)
    ast = Parser(toks).parse_program()
    gen = CodeGen()
    return gen.generate(ast, source_name)


# ── CLI ────────────────────────────────────────────────────────────────────

def main():
    ap = argparse.ArgumentParser(
        description="toycc - compile a C subset to Toy CPU assembly (.toy)")
    ap.add_argument('file', help='input C file (.c)')
    ap.add_argument('-o', '--output', help='output .toy path')
    ap.add_argument('-r', '--run', action='store_true',
                    help='after compiling, run the .toy through pytoy (CLI)')
    args = ap.parse_args()

    try:
        with open(args.file) as f:
            src = f.read()
    except OSError as e:
        sys.exit(f"cannot read {args.file}: {e}")

    try:
        asm = compile_source(src, os.path.basename(args.file))
    except CompileError as e:
        sys.exit(f"compile error: {e}")

    out_path = args.output
    if out_path is None:
        base = args.file
        if base.endswith('.c'):
            base = base[:-2]
        out_path = base + '.toy'

    with open(out_path, 'w') as f:
        f.write(asm)
    print(f"wrote {out_path}")

    if args.run:
        pytoy = os.path.join(os.path.dirname(os.path.dirname(
            os.path.abspath(__file__))), 'pytoy.py')
        cmd = [sys.executable, pytoy, out_path, '--cli', '--run', '--quiet']
        print(f"running: {' '.join(cmd)}")
        subprocess.run(cmd)


if __name__ == '__main__':
    main()
