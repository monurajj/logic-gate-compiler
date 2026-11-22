"""
PHASE 3 — SEMANTIC ANALYSIS
===========================

The parser only checks *form*. This phase checks *meaning* and fills the
symbol table. Rules for a combinational logic circuit:

Errors
  1. A name may be declared only once.
  2. A name cannot be both `input` and `output`.
  3. An `input` cannot be assigned (it is driven from outside).
  4. Every signal is driven exactly once (no multiple drivers).
  5. A signal must be defined before it is used (input, or assigned earlier).
  6. A signal cannot be used in its own definition (combinational loop).
  7. Every declared `output` must be assigned.

Warnings
  - an input that is never used
  - an internal wire that is assigned but never used (dead code)

Convenience mode: if the program declares *no* inputs at all (e.g. the
single line `x = a AND b;`), unknown names are treated as implicit inputs.
If it declares no outputs, every assigned signal becomes an output.
"""

from .ast_nodes import Declaration, Assignment, BinaryOp, UnaryOp, Identifier
from .symbol_table import SymbolTable


class SemanticResult:
    def __init__(self, symtab, inputs, outputs):
        self.symtab = symtab
        self.inputs = inputs      # list of names, in order
        self.outputs = outputs    # list of names, in order


class SemanticAnalyzer:
    PHASE = "Semantic"

    def __init__(self, errors):
        self.errors = errors
        self.symtab = SymbolTable()
        self.implicit_inputs = False

    def analyze(self, program):
        decls = [s for s in program.statements if isinstance(s, Declaration)]
        assigns = [s for s in program.statements if isinstance(s, Assignment)]
        self.implicit_inputs = not any(d.kind == "input" for d in decls)

        # Pass 1 — declarations
        for d in decls:
            for name, line, col in d.names:
                old = self.symtab.lookup(name)
                if old is None:
                    self.symtab.insert(name, d.kind, line)
                elif old.kind != d.kind:
                    self.errors.error(self.PHASE, f"'{name}' is declared as both {old.kind} "
                                      f"(line {old.declared}) and {d.kind}", line, col)
                else:
                    self.errors.error(self.PHASE, f"redeclaration of {d.kind} '{name}' "
                                      f"(first declared at line {old.declared})", line, col)

        # Pass 2 — assignments, in program order
        for a in assigns:
            self._check_expr(a.expr, a.target)
            sym = self.symtab.lookup(a.target)
            if sym is None:
                sym = self.symtab.insert(a.target, "wire", a.line)
                sym.assigned = a.line
            elif sym.kind == "input":
                self.errors.error(self.PHASE, f"cannot assign to input '{a.target}' "
                                  f"(inputs are driven from outside the circuit)", a.line, a.col)
            elif sym.assigned is not None:
                self.errors.error(self.PHASE, f"'{a.target}' is already assigned at line {sym.assigned} "
                                  f"(a signal can have only one driver)", a.line, a.col)
            else:
                sym.assigned = a.line

        # Pass 3 — whole-program checks
        outputs = [s for s in self.symtab if s.kind == "output"]
        for s in outputs:
            if s.assigned is None:
                self.errors.error(self.PHASE, f"output '{s.name}' is declared but never assigned", s.declared)
        if not outputs:
            for s in self.symtab.by_kind("wire"):
                s.is_output = True
            if self.symtab.by_kind("wire"):
                self.errors.note(self.PHASE, "no 'output' declared - every assigned signal is treated as an output")

        for s in self.symtab:
            if s.kind == "input" and s.uses == 0:
                self.errors.warning(self.PHASE, f"input '{s.name}' is never used", s.declared)
            if s.kind == "wire" and not s.is_output and s.uses == 0:
                self.errors.warning(self.PHASE, f"wire '{s.name}' is assigned but never used "
                                    f"(it will be removed as dead code)", s.declared)

        inputs = [s.name for s in self.symtab if s.kind == "input"]
        outs = [s.name for s in self.symtab if s.is_output]
        return SemanticResult(self.symtab, inputs, outs)

    def _check_expr(self, e, target):
        if isinstance(e, BinaryOp):
            self._check_expr(e.left, target)
            self._check_expr(e.right, target)
        elif isinstance(e, UnaryOp):
            self._check_expr(e.operand, target)
        elif isinstance(e, Identifier):
            sym = self.symtab.lookup(e.name)
            if e.name == target and (sym is None or sym.kind != "input"):
                self.errors.error(self.PHASE, f"combinational loop: '{e.name}' is used in its own definition",
                                  e.line, e.col)
            elif sym is None:
                if self.implicit_inputs:
                    sym = self.symtab.insert(e.name, "input", e.line, implicit=True)
                    self.errors.note(self.PHASE, f"'{e.name}' is not declared - treating it as an implicit input",
                                     e.line, e.col)
                else:
                    self.errors.error(self.PHASE, f"undefined signal '{e.name}' (not an input and not "
                                      f"assigned before this line)", e.line, e.col)
            elif sym.kind == "output" and sym.assigned is None:
                self.errors.error(self.PHASE, f"output '{e.name}' is used before it is assigned", e.line, e.col)
            if sym is not None:
                sym.uses += 1


def analyze(program, errors):
    return SemanticAnalyzer(errors).analyze(program)
