"""
Symbol Table (cross-cutting component of the compiler)
======================================================

Stores one entry per signal name, filled in by the semantic analyser and
read by intermediate-code generation, optimisation and code generation.

  kind     : input | output | wire     (wire = internal signal)
  type     : always `bit` (1-bit boolean) in this language
  declared : line where the name was declared / first defined
  assigned : line where the signal is driven (None for inputs)
  uses     : how many times the signal is read
"""

from collections import OrderedDict
from . import ui


class Symbol:
    def __init__(self, name, kind, line, implicit=False):
        self.name = name
        self.kind = kind
        self.type = "bit"
        self.declared = line
        self.assigned = None
        self.uses = 0
        self.implicit = implicit
        self.is_output = kind == "output"


class SymbolTable:
    def __init__(self):
        self._table = OrderedDict()

    def insert(self, name, kind, line, implicit=False):
        sym = Symbol(name, kind, line, implicit)
        self._table[name] = sym
        return sym

    def lookup(self, name):
        return self._table.get(name)

    def __contains__(self, name):
        return name in self._table

    def __iter__(self):
        return iter(self._table.values())

    def by_kind(self, kind):
        return [s for s in self if s.kind == kind]

    def format(self):
        rows = []
        for i, s in enumerate(self, 1):
            kind = s.kind + (" (implicit)" if s.implicit else "")
            if s.kind == "wire" and s.is_output:
                kind = "output (implicit)"
            rows.append([i, s.name, kind, s.type, s.declared,
                         s.assigned if s.assigned else "-", s.uses])
        return ui.table(["#", "Name", "Kind", "Type", "Declared@", "Assigned@", "Uses"], rows)
