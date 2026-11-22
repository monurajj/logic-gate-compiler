"""
PHASE 5 — CODE OPTIMIZATION (machine-independent, on Three-Address Code)
========================================================================

Passes run repeatedly until nothing changes (a fixed point):

 1. Constant folding         t1 = 1 AND 0        ->  t1 = 0
 2. Algebraic simplification (Boolean algebra laws)
       x AND 1 = x      x AND 0 = 0      x OR 0 = x       x OR 1 = 1
       x XOR 0 = x      x XOR 1 = NOT x  x AND x = x      x XOR x = 0
       x AND NOT x = 0  x OR NOT x = 1   x NAND x = NOT x ...
 3. Double negation          NOT (NOT x) = x
 4. Common sub-expression elimination (CSE)
       t1 = a AND b ... t5 = b AND a   ->  t5 = t1   (AND is commutative)
 5. Copy / constant propagation
       t1 = a ; t2 = t1 OR c           ->  t2 = a OR c
 6. Copy coalescing           t3 = a XOR b ; s = t3  ->  s = a XOR b
 7. Dead code elimination     drop instructions whose result never reaches an output

Every pass is safe because the semantic phase guarantees each signal is
assigned exactly once and before use (the code is effectively in SSA form).
"""

from .icg import Quad, BINARY_OPS, is_const, eval_gate

# (op, constant) -> result, where "x" = the other operand, "not" = NOT x
CONST_RULES = {
    ("AND", 0): 0, ("AND", 1): "x",
    ("OR", 0): "x", ("OR", 1): 1,
    ("XOR", 0): "x", ("XOR", 1): "not",
    ("NAND", 0): 1, ("NAND", 1): "not",
    ("NOR", 0): "not", ("NOR", 1): 0,
    ("XNOR", 0): "not", ("XNOR", 1): "x",
}
SAME_OPERAND = {"AND": "x", "OR": "x", "XOR": 0, "XNOR": 1, "NAND": "not", "NOR": "not"}
COMPLEMENT = {"AND": 0, "OR": 1, "XOR": 1, "XNOR": 0, "NAND": 1, "NOR": 0}   # x op NOT x


class Optimizer:
    def __init__(self, quads, outputs, temps):
        self.quads = [q.copy() for q in quads]
        self.outputs = list(outputs)
        self.temps = set(temps)
        self.log = []           # (round, pass name, message)
        self.round = 0

    def is_temp(self, x):
        return isinstance(x, str) and x in self.temps

    def _log(self, name, msg):
        self.log.append((self.round, name, msg))

    def optimize(self, max_rounds=50):
        for r in range(1, max_rounds + 1):
            self.round = r
            before = len(self.log)
            self.algebraic()
            self.cse()
            self.propagate()
            self.coalesce()
            self.dead_code()
            if len(self.log) == before:
                break
        return self.quads

    # -- 1, 2, 3 --------------------------------------------------------------
    def algebraic(self):
        defs = {q.result: q for q in self.quads}

        def neg_of(x):
            q = defs.get(x) if isinstance(x, str) else None
            return q.arg1 if q is not None and q.op == "NOT" else None

        for i, q in enumerate(self.quads):
            new, name = self._simplify(q, neg_of)
            if new is not None:
                self._log(name, f"{q}   =>   {new}")
                self.quads[i] = new
                defs[new.result] = new

    @staticmethod
    def _make(rule, x, r):
        if rule == "x":
            return Quad("COPY", x, None, r)
        if rule == "not":
            return Quad("NOT", x, None, r)
        return Quad("COPY", rule, None, r)

    def _simplify(self, q, neg_of):
        op, a, b, r = q.op, q.arg1, q.arg2, q.result
        if op == "COPY":
            return None, None
        if op == "NOT":
            if is_const(a):
                return Quad("COPY", 1 - a, None, r), "Constant folding"
            inner = neg_of(a)
            if inner is not None:
                return Quad("COPY", inner, None, r), "Double negation"
            return None, None
        if is_const(a) and is_const(b):
            return Quad("COPY", eval_gate(op, a, b), None, r), "Constant folding"
        if is_const(a):
            a, b = b, a
        if is_const(b):
            return self._make(CONST_RULES[(op, b)], a, r), "Algebraic simplification"
        if a == b:
            return self._make(SAME_OPERAND[op], a, r), "Algebraic simplification"
        if neg_of(a) == b or neg_of(b) == a:
            return self._make(COMPLEMENT[op], a, r), "Algebraic simplification"
        return None, None

    # -- 4 ---------------------------------------------------------------------
    def cse(self):
        seen = {}
        for i, q in enumerate(self.quads):
            if q.op == "COPY":
                continue
            if q.op == "NOT":
                key = ("NOT", q.arg1)
            else:
                key = (q.op,) + tuple(sorted((q.arg1, q.arg2), key=repr))
            if key in seen:
                new = Quad("COPY", seen[key], None, q.result)
                self._log("Common subexpression elimination", f"{q}   =>   {new}")
                self.quads[i] = new
            else:
                seen[key] = q.result

    # -- 5 ---------------------------------------------------------------------
    def propagate(self):
        copies = {}
        for q in self.quads:
            if q.op == "COPY" and (self.is_temp(q.result) or not self.is_temp(q.arg1)):
                copies[q.result] = q.arg1

        def resolve(x):
            seen = set()
            while isinstance(x, str) and x in copies and x not in seen:
                seen.add(x)
                x = copies[x]
            return x

        for i, q in enumerate(self.quads):
            a1, a2 = resolve(q.arg1), resolve(q.arg2) if q.arg2 is not None else None
            if a1 != q.arg1 or a2 != q.arg2:
                new = Quad(q.op, a1, a2, q.result)
                kind = "Constant propagation" if is_const(a1) or is_const(a2) else "Copy propagation"
                self._log(kind, f"{q}   =>   {new}")
                self.quads[i] = new

    # -- 6 ---------------------------------------------------------------------
    def coalesce(self):
        uses = {}
        for q in self.quads:
            for a in q.args():
                if isinstance(a, str):
                    uses[a] = uses.get(a, 0) + 1
        def_at = {q.result: i for i, q in enumerate(self.quads)}
        remove = set()
        for i, q in enumerate(self.quads):
            t = q.arg1
            if q.op == "COPY" and self.is_temp(t) and uses.get(t) == 1 and t in def_at:
                j = def_at[t]
                old = str(self.quads[j])
                self.quads[j].result = q.result
                self._log("Copy coalescing", f"{old} ; {q}   =>   {self.quads[j]}")
                remove.add(i)
        self.quads = [q for i, q in enumerate(self.quads) if i not in remove]

    # -- 7 ---------------------------------------------------------------------
    def dead_code(self):
        needed = set(self.outputs)
        kept = []
        for q in reversed(self.quads):
            if q.result in needed:
                kept.append(q)
                needed.update(a for a in q.args() if isinstance(a, str))
            else:
                self._log("Dead code elimination", f"removed  {q}")
        self.quads = list(reversed(kept))


def optimize(quads, outputs, temps):
    opt = Optimizer(quads, outputs, temps)
    result = opt.optimize()
    return result, opt.log


def gate_count(quads):
    return sum(1 for q in quads if q.op != "COPY")
