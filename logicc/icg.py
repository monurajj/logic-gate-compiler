"""
PHASE 4 — INTERMEDIATE CODE GENERATION
======================================

Translates the AST into *Three-Address Code* (TAC): every instruction has at
most one operator and three addresses (two operands + one result). Each
gate in an expression gets a fresh temporary t1, t2, ...

    sum = (a XOR b) XOR cin;        t1 = a XOR b
                                    t2 = t1 XOR cin
                                    sum = t2

The same code is shown in the two classic representations:
  * Quadruples : (op, arg1, arg2, result)
  * Triples    : (op, arg1, arg2)  -- results referred to by position (i)
"""

from .ast_nodes import Assignment, BinaryOp, UnaryOp, Identifier, Constant
from . import ui

BINARY_OPS = ("AND", "OR", "XOR", "NAND", "NOR", "XNOR")


def is_const(x):
    return isinstance(x, int)


def eval_gate(op, a, b=None):
    if op == "NOT":
        return 1 - a
    if op == "COPY":
        return a
    return {
        "AND": a & b, "OR": a | b, "XOR": a ^ b,
        "NAND": 1 - (a & b), "NOR": 1 - (a | b), "XNOR": 1 - (a ^ b),
    }[op]


class Quad:
    """One three-address instruction:  result = arg1 op arg2."""

    def __init__(self, op, arg1, arg2, result):
        self.op = op          # AND OR XOR NAND NOR XNOR | NOT | COPY
        self.arg1 = arg1      # str (name) or int (constant 0/1)
        self.arg2 = arg2
        self.result = result

    def args(self):
        return [a for a in (self.arg1, self.arg2) if a is not None]

    def copy(self):
        return Quad(self.op, self.arg1, self.arg2, self.result)

    def __str__(self):
        if self.op == "COPY":
            return f"{self.result} = {self.arg1}"
        if self.op == "NOT":
            return f"{self.result} = NOT {self.arg1}"
        return f"{self.result} = {self.arg1} {self.op} {self.arg2}"

    def __eq__(self, other):
        return isinstance(other, Quad) and str(self) == str(other)

    def __repr__(self):
        return f"Quad({self})"


class ICGenerator:
    def __init__(self, symtab):
        self.symtab = symtab
        self.quads = []
        self.temps = []
        self._n = 0

    def new_temp(self):
        while True:
            self._n += 1
            name = f"t{self._n}"
            if name not in self.symtab:       # never clash with a user signal
                self.temps.append(name)
                return name

    def emit(self, op, a1, a2, res):
        self.quads.append(Quad(op, a1, a2, res))

    def generate(self, program):
        for s in program.statements:
            if isinstance(s, Assignment):
                addr = self.gen_expr(s.expr)
                self.emit("COPY", addr, None, s.target)
        return self.quads

    def gen_expr(self, e):
        if isinstance(e, Identifier):
            return e.name
        if isinstance(e, Constant):
            return e.value
        if isinstance(e, UnaryOp):
            a = self.gen_expr(e.operand)
            t = self.new_temp()
            self.emit("NOT", a, None, t)
            return t
        if isinstance(e, BinaryOp):
            left = self.gen_expr(e.left)
            right = self.gen_expr(e.right)
            t = self.new_temp()
            self.emit(e.op, left, right, t)
            return t
        raise TypeError(e)


def generate(program, symtab):
    gen = ICGenerator(symtab)
    quads = gen.generate(program)
    return quads, gen.temps


# -- pretty printers ---------------------------------------------------------
def _s(x):
    return "" if x is None else str(x)


def format_tac(quads):
    return "\n".join(f"  {i:>3}:  {q}" for i, q in enumerate(quads))


def format_quadruples(quads):
    rows = [[i, "=" if q.op == "COPY" else q.op, _s(q.arg1), _s(q.arg2), q.result]
            for i, q in enumerate(quads)]
    return ui.table(["#", "op", "arg1", "arg2", "result"], rows)


def format_triples(quads, temps):
    return ui.table(["#", "op", "arg1", "arg2"], triples_rows(quads, temps))


def triples_rows(quads, temps):
    temps = set(temps)
    where = {}
    rows = []
    for i, q in enumerate(quads):
        ref = lambda x: f"({where[x]})" if isinstance(x, str) and x in where else _s(x)
        if q.op == "COPY":
            rows.append([f"({i})", "=", q.result, ref(q.arg1)])
        else:
            rows.append([f"({i})", q.op, ref(q.arg1), ref(q.arg2)])
        if q.result in temps:
            where[q.result] = i
    return rows
