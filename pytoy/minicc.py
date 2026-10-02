#!/usr/bin/env python3
"""
minicc - a tiny, readable C-to-Toy-CPU compiler, for learning.

This is the stripped-down sibling of pytoy/compiler.py (toycc). It deliberately
leaves out everything optional so the whole pipeline fits in one short, linear
file you can read top to bottom:

    - multiple NON-RECURSIVE functions (main plus helpers), but NO call stack
      and NO save/restore -- so recursion is impossible and is rejected.
    - no optimizations (no constant folding, no peepholes).
    - scalars, one-dimensional int arrays, if/else, while, return.
    - operators + - * & | ^ ~ << >> and == != < > <= >= .

Everything is 8-bit and wraps mod 256, exactly like the Toy CPU. Comparisons use
the same sign-bit (bit 7) trick as toycc, so they are correct for operands that
differ by less than 128 -- plenty for the teaching examples.

Two simplifications a learner should know about: variable scope is flat (a name
declared inside a `{ }` block stays visible afterwards, unlike real C), and the
bit-7 comparison above is silently wrong for operands 128 or more apart.

It still compiles most of the single-function examples in examples/c/ correctly.
For recursion, pointers and optimizations, use the full toycc
(pytoy/compiler.py).

Pipeline: source text -> tokens (lex) -> AST (Parser) -> assembly (Gen).
"""


class MiniError(Exception):
    """A compile error with a human-readable message."""


# ── 1. Lexer: text -> list of tokens ─────────────────────────────────────────
# A token is a (kind, value) pair. Kinds: 'num', 'id', 'kw', 'op', 'punct'.

KEYWORDS = {'int', 'void', 'return', 'if', 'else', 'while'}

# Multi-character operators must be tried before their single-char prefixes.
OPS = ['<<', '>>', '==', '!=', '<=', '>=', '+', '-', '*', '&', '|', '^',
       '~', '<', '>', '=']
PUNCT = ['(', ')', '{', '}', '[', ']', ';', ',']


def lex(src):
    """Turn source text into a list of (kind, value) tokens, ending with ('eof', '')."""
    # strip // line comments and /* ... */ block comments
    out, i, n = [], 0, len(src)
    while i < n:
        c = src[i]
        if c in ' \t\r\n':
            i += 1
        elif src[i:i + 2] == '//':
            i = src.find('\n', i)
            i = n if i < 0 else i
        elif src[i:i + 2] == '/*':
            end = src.find('*/', i + 2)
            if end < 0:
                raise MiniError("unterminated /* comment")
            i = end + 2
        elif c.isdigit():
            j = i
            if src[i:i + 2] in ('0x', '0X'):      # hex literal
                j = i + 2
                while j < n and src[j] in '0123456789abcdefABCDEF':
                    j += 1
            else:
                while j < n and src[j].isdigit():
                    j += 1
            out.append(('num', int(src[i:j], 0) & 0xFF))
            i = j
        elif c.isalpha() or c == '_':
            j = i
            while j < n and (src[j].isalnum() or src[j] == '_'):
                j += 1
            word = src[i:j]
            out.append(('kw', word) if word in KEYWORDS else ('id', word))
            i = j
        else:
            for op in OPS:
                if src.startswith(op, i):
                    out.append(('op', op))
                    i += len(op)
                    break
            else:
                if c in PUNCT:
                    out.append(('punct', c))
                    i += 1
                else:
                    raise MiniError(f"unexpected character {c!r}")
    out.append(('eof', ''))
    return out


# ── 2. Parser: tokens -> AST ─────────────────────────────────────────────────
# AST node shapes (plain tuples):
#   expressions: ('num', v) ('var', name) ('index', name, idx)
#                ('unop', op, e) ('binop', op, a, b) ('call', name, [args])
#   statements:  ('callstmt', call)                    f(args);  (value discarded)
#                ('decl', name, init_or_None)          int x = e;
#                ('arraydecl', name, size, [inits])     int a[10] = {...};
#                ('assign', name, e)                    x = e;
#                ('store', name, idx, e)                a[i] = e;
#                ('if', cond, then, else_or_None)
#                ('while', cond, body)
#                ('return', e)
#                ('block', [stmts])

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

    def eat(self, kind, value=None):
        t = self.next()
        if t[0] != kind or (value is not None and t[1] != value):
            want = value if value is not None else kind
            raise MiniError(f"expected {want!r}, got {t[1]!r}")
        return t

    def accept(self, kind, value=None):
        t = self.peek()
        if t[0] == kind and (value is None or t[1] == value):
            return self.next()
        return None

    # program ::= function+        (exactly one of them must be `main`)
    # function ::= 'int' name '(' params ')' block
    # params   ::= 'void' | 'int' name (',' 'int' name)*
    def parse_program(self):
        funcs = []
        while self.peek()[0] != 'eof':
            funcs.append(self.parse_func())
        names = [f[1] for f in funcs]
        if 'main' not in names:
            raise MiniError("no `int main(void)` function found")
        return funcs

    def parse_func(self):
        self.eat('kw', 'int')
        name = self.eat('id')[1]
        self.eat('punct', '(')
        params = []
        if not self.accept('kw', 'void'):
            if self.peek() != ('punct', ')'):
                self.eat('kw', 'int')
                params.append(self.eat('id')[1])
                while self.accept('punct', ','):
                    self.eat('kw', 'int')
                    params.append(self.eat('id')[1])
        self.eat('punct', ')')
        body = self.parse_block()
        return ('func', name, params, body)

    def parse_block(self):
        self.eat('punct', '{')
        stmts = []
        while not self.accept('punct', '}'):
            stmts.append(self.parse_stmt())
        return ('block', stmts)

    def parse_stmt(self):
        t = self.peek()
        if t == ('kw', 'int'):
            return self.parse_decl()
        if t == ('kw', 'return'):
            self.next()
            e = self.parse_expr()
            self.eat('punct', ';')
            return ('return', e)
        if t == ('kw', 'if'):
            return self.parse_if()
        if t == ('kw', 'while'):
            return self.parse_while()
        if t[0] == 'punct' and t[1] == '{':
            return self.parse_block()
        # assignment:  name = e;   or   name[idx] = e;
        return self.parse_assign()

    def parse_decl(self):
        self.eat('kw', 'int')
        name = self.eat('id')[1]
        if self.accept('punct', '['):
            size = self.eat('num')[1]
            self.eat('punct', ']')
            inits = []
            if self.accept('op', '='):
                self.eat('punct', '{')
                if not self.accept('punct', '}'):
                    inits.append(self.eat('num')[1])
                    while self.accept('punct', ','):
                        inits.append(self.eat('num')[1])
                    self.eat('punct', '}')
            self.eat('punct', ';')
            return ('arraydecl', name, size, inits)
        init = None
        if self.accept('op', '='):
            init = self.parse_expr()
        self.eat('punct', ';')
        return ('decl', name, init)

    def _eat_assign_op(self):
        """Consume `=`. A compound op like `+=` lexes as `+` then `=`; catch it
        and explain, since minicc has no compound assignment."""
        t = self.peek()
        if t[0] == 'op' and t[1] != '=':
            raise MiniError(
                f"minicc has no compound assignment ({t[1]}=); "
                f"write it out, e.g. `x = x {t[1]} ...`.")
        self.eat('op', '=')

    def parse_assign(self):
        name = self.eat('id')[1]
        if self.peek() == ('punct', '('):      # a bare call statement: f(args);
            call = self.parse_call(name)
            self.eat('punct', ';')
            return ('callstmt', call)
        if self.accept('punct', '['):
            idx = self.parse_expr()
            self.eat('punct', ']')
            self._eat_assign_op()
            e = self.parse_expr()
            self.eat('punct', ';')
            return ('store', name, idx, e)
        self._eat_assign_op()
        e = self.parse_expr()
        self.eat('punct', ';')
        return ('assign', name, e)

    def parse_if(self):
        self.eat('kw', 'if')
        self.eat('punct', '(')
        cond = self.parse_expr()
        self.eat('punct', ')')
        then = self.parse_stmt()
        els = self.parse_stmt() if self.accept('kw', 'else') else None
        return ('if', cond, then, els)

    def parse_while(self):
        self.eat('kw', 'while')
        self.eat('punct', '(')
        cond = self.parse_expr()
        self.eat('punct', ')')
        body = self.parse_stmt()
        return ('while', cond, body)

    # Expression grammar, lowest precedence first. Each level parses the next
    # level up, then folds left-associative runs of its own operators.
    #   expr    ::= cmp
    #   cmp     ::= bitor  ( (== != < > <= >=) bitor )*
    #   bitor   ::= bitxor ( (| ) bitxor )*
    #   bitxor  ::= bitand ( (^ ) bitand )*
    #   bitand  ::= shift  ( (& ) shift )*
    #   shift   ::= add    ( (<< >>) add )*
    #   add     ::= mul    ( (+ -) mul )*
    #   mul     ::= unary  ( (* ) unary )*
    #   unary   ::= (- ~) unary | atom
    #   atom    ::= num | name | name[expr] | ( expr )
    def parse_expr(self):
        return self._binlevel(0)

    _LEVELS = [
        ['==', '!=', '<', '>', '<=', '>='],
        ['|'], ['^'], ['&'], ['<<', '>>'], ['+', '-'], ['*'],
    ]

    def _binlevel(self, lvl):
        if lvl == len(self._LEVELS):
            return self.parse_unary()
        left = self._binlevel(lvl + 1)
        while self.peek()[0] == 'op' and self.peek()[1] in self._LEVELS[lvl]:
            op = self.next()[1]
            right = self._binlevel(lvl + 1)
            left = ('binop', op, left, right)
        return left

    def parse_unary(self):
        t = self.peek()
        if t[0] == 'op' and t[1] in ('-', '~'):
            self.next()
            return ('unop', t[1], self.parse_unary())
        return self.parse_atom()

    def parse_atom(self):
        t = self.next()
        if t[0] == 'num':
            return ('num', t[1])
        if t[0] == 'punct' and t[1] == '(':
            e = self.parse_expr()
            self.eat('punct', ')')
            return e
        if t[0] == 'id':
            if self.peek() == ('punct', '('):
                return self.parse_call(t[1])
            if self.accept('punct', '['):
                idx = self.parse_expr()
                self.eat('punct', ']')
                return ('index', t[1], idx)
            return ('var', t[1])
        raise MiniError(f"unexpected {t[1]!r} in expression")

    def parse_call(self, name):
        self.eat('punct', '(')
        args = []
        if self.peek() != ('punct', ')'):
            args.append(self.parse_expr())
            while self.accept('punct', ','):
                args.append(self.parse_expr())
        self.eat('punct', ')')
        return ('call', name, args)


# ── 3. Code generator: AST -> Toy assembly text ──────────────────────────────
# Layout: all code first, then a data section. Scalars and arrays get fixed data
# bytes; every constant and temporary also lives in a data byte (the Toy CPU has
# only the accumulator, so intermediate values are spilled to memory).

class Gen:
    def __init__(self, funcs=None):
        self.code = []
        self.vars = {}          # name -> data label
        self.consts = {}        # value -> data label (deduplicated)
        self.arrays = {}        # name -> (base_label, size, inits)
        self.temps = []         # temp labels, all initialised to 0
        self.all_vars = []      # every scalar's data label (across all functions)
        self.all_arrays = []    # every array's (base_label, data_label, size, inits)
        self.n_label = 0
        self.n_temp = 0
        # function support (see the marker-dispatch comment block below)
        self.funcs = {f[1]: f for f in (funcs or [])}   # name -> ('func',...)
        self.slots = []         # extra data bytes for f__p_*, f__ret, f__mark
        self.cur_func = None    # name of the function body being generated
        self.sites = {name: 0 for name in self.funcs}   # fname -> next site idx

    def emit(self, line):
        self.code.append(line)

    def const(self, value):
        value &= 0xFF
        if value not in self.consts:
            self.consts[value] = f"c_{value}"
        return self.consts[value]

    def var(self, name):
        if name not in self.vars and name not in self.arrays:
            raise MiniError(f"unknown variable {name!r}")
        if name in self.arrays:
            raise MiniError(f"{name!r} is an array, not a scalar")
        return self.vars[name]

    def new_temp(self):
        self.n_temp += 1
        label = f"t{self.n_temp}"
        self.temps.append(label)
        return label

    def new_label(self, stem):
        self.n_label += 1
        return f"{stem}{self.n_label}"

    # -- expressions: leave the result in the accumulator --------------------
    def gen_expr(self, e):
        kind = e[0]
        if kind == 'num':
            self.emit(f"        load  {self.const(e[1])}")
        elif kind == 'var':
            self.emit(f"        load  {self.var(e[1])}")
        elif kind == 'index':
            self.gen_index_read(e)
        elif kind == 'unop':
            self.gen_unop(e)
        elif kind == 'binop':
            self.gen_binop(e)
        elif kind == 'call':
            self.gen_call(e)
            self.emit(f"        load  {e[1]}__ret")
        else:
            raise MiniError(f"cannot compile expression {e!r}")

    def gen_unop(self, e):
        _, op, operand = e
        self.gen_expr(operand)
        if op == '~':
            self.emit("        not")
        elif op == '-':                 # 0 - operand
            t = self.new_temp()
            self.emit(f"        store {t}")
            self.emit(f"        load  {self.const(0)}")
            self.emit(f"        sub   {t}")

    MEMOP = {'+': 'add', '-': 'sub', '&': 'and', '|': 'or', '^': 'xor'}

    def gen_binop(self, e):
        _, op, left, right = e
        if op in ('==', '!=', '<', '>', '<=', '>='):
            self.gen_compare(op, left, right)
            return
        if op == '*':
            self.gen_multiply(left, right)
            return
        if op in ('<<', '>>'):
            self.gen_shift(op, left, right)
            return
        # +, -, &, |, ^ : evaluate right into a temp, then left, then apply.
        self.gen_expr(right)
        t = self.new_temp()
        self.emit(f"        store {t}")
        self.gen_expr(left)
        self.emit(f"        {self.MEMOP[op]:<5} {t}")

    def gen_shift(self, op, left, right):
        # Only a constant shift amount is supported (keeps it simple): unroll to
        # that many single-bit shifts.
        if right[0] != 'num':
            raise MiniError("minicc supports only a constant shift amount")
        self.gen_expr(left)
        instr = 'left' if op == '<<' else 'right'
        for _ in range(right[1] & 0xFF):
            self.emit(f"        {instr}")

    def gen_multiply(self, left, right):
        # No multiply opcode: loop `right` times, adding `left` each pass.
        a, cnt, res = self.new_temp(), self.new_temp(), self.new_temp()
        self.gen_expr(left)
        self.emit(f"        store {a}")
        self.gen_expr(right)
        self.emit(f"        store {cnt}")
        self.emit(f"        load  {self.const(0)}")
        self.emit(f"        store {res}")
        loop, end = self.new_label("mul"), self.new_label("mulend")
        self.emit(f"{loop}: load  {cnt}")
        self.emit(f"        ifzero {end}")
        self.emit(f"        load  {res}")
        self.emit(f"        add   {a}")
        self.emit(f"        store {res}")
        self.emit(f"        load  {cnt}")
        self.emit(f"        sub   {self.const(1)}")
        self.emit(f"        store {cnt}")
        self.emit(f"        goto  {loop}")
        self.emit(f"{end}: load  {res}")

    def gen_diff(self, left, right):
        """Leave (left - right) in the accumulator."""
        self.gen_expr(right)
        t = self.new_temp()
        self.emit(f"        store {t}")
        self.gen_expr(left)
        self.emit(f"        sub   {t}")

    def gen_compare(self, op, left, right):
        # Produce a 0/1 result. == / != test (left-right) for zero. The
        # relational ops read bit 7 of a difference: for small operands,
        # bit 7 of (a-b) is set exactly when a < b.
        if op in ('==', '!='):
            self.gen_diff(left, right)
            self._bool_from_zero(one_if_zero=(op == '=='))
            return
        # a<b and a>=b read (a-b); a>b and a<=b read (b-a). bit 7 set means the
        # difference went negative, i.e. the first operand was the smaller one.
        if op == '<':
            self.gen_diff(left, right)
            one_if_neg = True
        elif op == '>':
            self.gen_diff(right, left)
            one_if_neg = True
        elif op == '>=':
            self.gen_diff(left, right)
            one_if_neg = False
        else:  # <=
            self.gen_diff(right, left)
            one_if_neg = False
        self.emit(f"        and   {self.const(0x80)}")   # isolate bit 7
        self._bool_from_zero(one_if_zero=not one_if_neg)

    def _bool_from_zero(self, one_if_zero):
        """ACC is 0 or nonzero; replace it with a clean 0/1.
        If one_if_zero, result is 1 when ACC==0 else 0 (and vice versa)."""
        zero = self.new_label("z")
        end = self.new_label("zend")
        self.emit(f"        ifzero {zero}")
        self.emit(f"        load  {self.const(0 if one_if_zero else 1)}")
        self.emit(f"        goto  {end}")
        self.emit(f"{zero}: load  {self.const(1 if one_if_zero else 0)}")
        self.emit(f"{end}: nop")

    # -- array element access via self-modifying code ------------------------
    def gen_element_addr(self, name, idx):
        """Leave (base + idx) -- the element's address -- in the accumulator."""
        if name not in self.arrays:
            raise MiniError(f"{name!r} is not an array")
        base, _size, _inits = self.arrays[name]
        if idx[0] == 'num':
            self.emit(f"        load  {base}")
            if idx[1] & 0xFF:
                self.emit(f"        add   {self.const(idx[1])}")
            return
        self.gen_expr(idx)
        t = self.new_temp()
        self.emit(f"        store {t}")
        self.emit(f"        load  {base}")
        self.emit(f"        add   {t}")

    def gen_index_read(self, e):
        # a[i] : compute the address, patch a raw LOAD's operand byte, run it.
        _, name, idx = e
        addr = self.new_label("iarg")
        self.gen_element_addr(name, idx)
        self.emit(f"        store {addr}")
        self.emit(f"        20               # LOAD opcode")
        self.emit(f"{addr}: 0                # <- a[i]")

    def gen_store_index(self, name, idx, value):
        # a[i] = value : spill value, compute address, patch a raw STORE, run it.
        val = self.new_temp()
        self.gen_expr(value)
        self.emit(f"        store {val}")
        addr = self.new_label("sarg")
        self.gen_element_addr(name, idx)
        self.emit(f"        store {addr}")
        self.emit(f"        load  {val}")
        self.emit(f"        21               # STORE opcode")
        self.emit(f"{addr}: 0                # <- a[i] := acc")

    # -- statements ----------------------------------------------------------
    def gen_stmt(self, s):
        kind = s[0]
        if kind == 'block':
            for st in s[1]:
                self.gen_stmt(st)
        elif kind == 'decl':
            _, name, init = s
            if name in self.vars or name in self.arrays:
                raise MiniError(f"{name!r} already declared")
            label = f"v_{self.cur_func}__{name}"   # per-function: no collisions
            self.vars[name] = label
            self.all_vars.append(label)
            if init is not None:
                self.gen_expr(init)
                self.emit(f"        store {label}")
        elif kind == 'arraydecl':
            _, name, size, inits = s
            if name in self.vars or name in self.arrays:
                raise MiniError(f"{name!r} already declared")
            if len(inits) > size:
                raise MiniError(f"too many initialisers for {name!r}")
            tag = f"{self.cur_func}__{name}"        # per-function: no collisions
            base, data = f"abase_{tag}", f"adata_{tag}"
            self.arrays[name] = (base, size, inits)
            self.all_arrays.append((base, data, size, inits))
        elif kind == 'assign':
            _, name, e = s
            self.gen_expr(e)
            self.emit(f"        store {self.var(name)}")
        elif kind == 'store':
            self.gen_store_index(s[1], s[2], s[3])
        elif kind == 'callstmt':
            self.gen_call(s[1])          # evaluate for effect; discard f__ret
        elif kind == 'return':
            self.gen_expr(s[1])
            if self.cur_func == 'main':
                self.emit("        stop")
            else:
                self.emit(f"        store {self.cur_func}__ret")
                self.emit(f"        goto  {self.cur_func}__dispatch")
        elif kind == 'if':
            self.gen_if(s)
        elif kind == 'while':
            self.gen_while(s)
        else:
            raise MiniError(f"cannot compile statement {s!r}")

    def gen_cond_jump(self, cond, false_label):
        """Evaluate cond; jump to false_label when it is false (0)."""
        self.gen_expr(cond)
        self.emit(f"        ifzero {false_label}")

    def gen_if(self, s):
        _, cond, then, els = s
        if els is None:
            end = self.new_label("endif")
            self.gen_cond_jump(cond, end)
            self.gen_stmt(then)
            self.emit(f"{end}: nop")
        else:
            else_l = self.new_label("else")
            end = self.new_label("endif")
            self.gen_cond_jump(cond, else_l)
            self.gen_stmt(then)
            self.emit(f"        goto  {end}")
            self.emit(f"{else_l}: nop")
            self.gen_stmt(els)
            self.emit(f"{end}: nop")

    def gen_while(self, s):
        _, cond, body = s
        top = self.new_label("while")
        end = self.new_label("endwhile")
        self.emit(f"{top}: nop")
        self.gen_cond_jump(cond, end)
        self.gen_stmt(body)
        self.emit(f"        goto  {top}")
        self.emit(f"{end}: nop")

    # -- functions: global slots + marker-dispatch --------------------------
    # The Toy CPU has no call/return and no stack, so a call cannot push a
    # return address. Instead every function f gets FIXED data bytes and its
    # body is emitted ONCE:
    #     f__p_<param>  one byte per parameter (caller writes the argument here)
    #     f__ret        one byte              (body writes the return value here)
    #     f__mark       one byte              (caller writes which call site called)
    #     f__body:      the single copy of f's body
    #     f__dispatch:  a compare-chain over f__mark that jumps back to the caller
    # A call f(args) at site k: store each arg into f__p_<param>; store k into
    # f__mark; `goto f__body`; f__cont_k: nop. The body's `return e` becomes
    # `eval e; store f__ret; goto f__dispatch`, and the dispatch chain reads
    # f__mark to jump back to f__cont_k. After the call the value is in f__ret.
    # These slots are shared across all activations, so a second (recursive)
    # entry would clobber the caller's — that is why recursion is rejected up
    # front (compile_source builds the call graph and refuses any cycle).

    def gen_call(self, e):
        _, name, args = e
        f = self.funcs[name]            # existence + arg count checked earlier
        params = f[2]
        # Evaluate every argument into a fresh temp FIRST, then copy the temps
        # into the parameter slots. Doing it in one pass would be wrong for a
        # call like f(y, f(x)): evaluating the second argument re-enters f and
        # overwrites f__p_<first> before the jump.
        temps = []
        for arg in args:
            self.gen_expr(arg)
            t = self.new_temp()
            self.emit(f"        store {t}")
            temps.append(t)
        for t, p in zip(temps, params):
            self.emit(f"        load  {t}")
            self.emit(f"        store {name}__p_{p}")
        # Mark which call site we are, so f__dispatch can return here.
        k = self.sites[name]
        self.sites[name] += 1
        self.emit(f"        load  {self.const(k)}")
        self.emit(f"        store {name}__mark")
        self.emit(f"        goto  {name}__body")
        self.emit(f"{name}__cont_{k}: nop        # return lands here; value in {name}__ret")

    def gen_function_body(self, f):
        """Emit one function body. Its dispatch chain is added later, once every
        call site in the whole program has been counted (gen_dispatch)."""
        _, name, params, body = f
        self.cur_func = name
        # Parameters are addressed as the ordinary variable slots f__p_<param>.
        self.vars = {p: f"{name}__p_{p}" for p in params}
        self.arrays = {}
        if name != 'main':      # main is never called, so it needs no slots
            for p in params:
                self.slots.append(f"{name}__p_{p}")
            self.slots.append(f"{name}__ret")
            self.slots.append(f"{name}__mark")
        self.emit("")
        self.emit(f"# function {name}(...) — single body, marker-dispatch return")
        self.emit(f"{name}__body: nop")
        self.gen_stmt(body)
        # main has no dispatch chain (its caller added a stop guard). For a helper,
        # a fall-through with no explicit return still goes to dispatch (f__ret
        # keeps its last value). Skip it if the body already ends that way.
        if name != 'main' and self.code[-1].strip() != f"goto  {name}__dispatch":
            self.emit(f"        goto  {name}__dispatch")
        self.cur_func = None

    def gen_dispatch(self, name):
        """A compare-chain over f__mark: for each call site k, jump back to its
        continuation. Emitted after all bodies, so n_sites is final."""
        self.emit("")
        self.emit(f"{name}__dispatch: nop")
        for k in range(self.sites.get(name, 0)):
            self.emit(f"        load  {name}__mark")
            self.emit(f"        sub   {self.const(k)}")
            self.emit(f"        ifzero {name}__cont_{k}")
        self.emit(f"        stop            # unreachable: bad {name} marker")

    # -- assemble the final .toys text --------------------------------------
    def finish(self, source_name):
        lines = [f"# Generated by minicc from {source_name}",
                 "# Toy CPU assembly. 8-bit values, wrap mod 256.",
                 "# Result ends up in the accumulator at STOP.",
                 ""]
        lines += self.code
        lines.append("")
        lines.append("# data")
        for label in self.all_vars:
            lines.append(f"{label}: 0")
        for slot in self.slots:          # f__p_*, f__ret, f__mark
            lines.append(f"{slot}: 0")
        for t in self.temps:
            lines.append(f"{t}: 0")
        for value, label in sorted(self.consts.items()):
            lines.append(f"{label}: {value}")
        # arrays last: a base byte holding the array address, then its elements.
        # The element block uses a prefixed label (adata_<fn>__<name>), not the
        # bare user name, so an array named like a temp/const (t1, c_5) can't
        # collide, and two functions can each have an array of the same name.
        for base, data, size, inits in self.all_arrays:
            lines.append(f"{base}: {data}")
            cells = list(inits) + [0] * (size - len(inits))
            lines.append(f"{data}: {cells[0]}")
            for v in cells[1:]:
                lines.append(f"        {v}")
        return "\n".join(lines) + "\n"


# ── 4. Whole-program checks and driver ───────────────────────────────────────

def _calls(node):
    """Yield every ('call', name, args) tuple anywhere inside an AST node."""
    if not isinstance(node, tuple):
        return
    if node[0] == 'call':
        yield node
    for part in node[1:]:
        if isinstance(part, tuple):
            yield from _calls(part)
        elif isinstance(part, list):
            for item in part:
                yield from _calls(item)


def check_calls(funcs):
    """Reject undefined calls and wrong argument counts."""
    defined = {f[1]: f[2] for f in funcs}       # name -> params
    for _, _name, _params, body in funcs:
        for _, callee, args in _calls(body):
            if callee not in defined:
                raise MiniError(f"call to undefined function {callee!r}")
            if len(args) != len(defined[callee]):
                raise MiniError(
                    f"{callee}() takes {len(defined[callee])} argument(s), "
                    f"got {len(args)}")


def check_no_recursion(funcs):
    """Build the call graph and reject any cycle: minicc is stackfree, so a
    function cannot call itself directly or indirectly (there is nowhere to save
    the caller's slots). DFS from each function looking for a path back to it."""
    graph = {f[1]: {c[1] for c in _calls(f[3])} for f in funcs}

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

    bad = sorted(name for name in graph if reaches_self(name))
    if bad:
        raise MiniError(
            f"recursion is not supported by minicc (stackfree): "
            f"function(s) {', '.join(bad)} call themselves directly or "
            f"indirectly. Use the full toycc for recursion.")


def compile_source(src, source_name="minicc"):
    """Compile C source text to Toy CPU assembly text."""
    funcs = Parser(lex(src)).parse_program()
    check_calls(funcs)
    check_no_recursion(funcs)
    gen = Gen(funcs)
    # main first (its `return` halts); then each helper body; then every
    # helper's dispatch chain, by which time all call sites have been counted.
    main = next(f for f in funcs if f[1] == 'main')
    if main[2]:                 # main(void) only: main is never called, has no slots
        raise MiniError("main must take no parameters: `int main(void)`")
    helpers = [f for f in funcs if f[1] != 'main']
    gen.gen_function_body(main)
    gen.emit("        stop            # end of main (halt if it falls through)")
    for f in helpers:
        gen.gen_function_body(f)
    for f in helpers:
        gen.gen_dispatch(f[1])
    return gen.finish(source_name)


def compile_file(in_path, out_path=None, run=False):
    """Compile a .toyc file to .toys. Mirrors toycc's CLI shape (minus options)."""
    import os
    import sys
    try:
        src = open(in_path).read()
    except OSError as e:
        sys.exit(f"cannot read {in_path}: {e}")
    try:
        asm = compile_source(src, os.path.basename(in_path))
    except MiniError as e:
        sys.exit(f"compile error: {e}")
    if out_path is None:
        out_path = os.path.splitext(in_path)[0] + ".toys"
    with open(out_path, "w") as f:
        f.write(asm)
    print(f"wrote {out_path}")
    if run:
        from pytoy.assembler import assemble
        from pytoy.simulator import simulate
        mem, listing, syms, data_addrs, errors, _ds = assemble(asm)
        if errors:
            sys.exit(f"assembler errors: {errors}")
        acc = simulate(mem, syms, data_addrs)
        print(f"Result:  ACC = {acc}  ({acc:08b}  0x{acc:02x}  dec {acc})")


if __name__ == "__main__":
    import sys
    if len(sys.argv) < 2:
        sys.exit("usage: python -m pytoy.minicc <file.toyc> [--run]")
    compile_file(sys.argv[1], run="--run" in sys.argv)
