"""
PHASE 6 — TARGET CODE GENERATION
================================

Translates optimised TAC into assembly for a simple register machine
("LGM" - Logic Gate Machine) with K registers R0..R(K-1).

Instruction set
---------------
  LOAD   Rd, var        Rd <- memory[var]
  LOADI  Rd, 0|1        Rd <- constant
  MOV    Rd, Rs         Rd <- Rs
  NOT    Rd, Rs         Rd <- NOT Rs
  AND    Rd, Ra, Rb     Rd <- Ra AND Rb      (also OR XOR NAND NOR XNOR)
  STORE  var, Rs        memory[var] <- Rs
  HALT

Register allocation uses the textbook *simple code generator* idea with a
register descriptor (what each register holds) and an address descriptor
(where each value lives: register and/or memory), plus next-use information:
  1. reuse a register that already holds the operand;
  2. otherwise take a free register, or one whose value is dead,
     or one whose value is already safe in memory;
  3. otherwise SPILL the value with the farthest next use (STORE it first).
Temporaries stay in registers; named signals are stored to memory.
"""

from .icg import BINARY_OPS, is_const


class Instr:
    def __init__(self, op, args, comment=""):
        self.op = op
        self.args = args
        self.comment = comment

    def __str__(self):
        text = f"    {self.op:<6} {', '.join(str(a) for a in self.args)}"
        if self.comment:
            text = f"{text:<30}; {self.comment}"
        return text


class CodeGenerator:
    def __init__(self, quads, inputs, temps, num_regs=4):
        if num_regs < 3:
            raise ValueError("the target machine needs at least 3 registers")
        self.quads = quads
        self.temps = set(temps)
        self.k = num_regs
        self.reg = [None] * num_regs        # register descriptor
        self.loc = {}                       # address descriptor: name -> register
        self.in_mem = set(inputs)           # names whose current value is in memory
        self.code = []
        self.spills = 0
        self.cur = 0
        self.uses = {}
        for i, q in enumerate(quads):
            for a in q.args():
                if isinstance(a, str):
                    self.uses.setdefault(a, []).append(i)

    # -- helpers ---------------------------------------------------------------
    def emit(self, op, *args, comment=""):
        self.code.append(Instr(op, list(args), comment))

    def next_use(self, name, include_current=True):
        """Index of the next instruction reading `name` (the current one counts by default)."""
        for i in self.uses.get(name, []):
            if i > self.cur or (include_current and i == self.cur):
                return i
        return None

    def dies_here(self, x):
        return is_const(x) or self.next_use(x, include_current=False) is None

    def _free(self, r):
        old = self.reg[r]
        if old is not None and self.loc.get(old) == r:
            del self.loc[old]
        self.reg[r] = None

    def bind(self, r, name):
        self._free(r)
        if name in self.loc:
            self._free(self.loc[name])
        self.reg[r] = name
        self.loc[name] = r

    def alloc(self, avoid):
        cands = [r for r in range(self.k) if r not in avoid]
        for r in cands:                                           # free register
            if self.reg[r] is None or self.reg[r].startswith("#"):
                return r
        for r in cands:                                           # value is dead
            if self.next_use(self.reg[r]) is None:
                self._free(r)
                return r
        for r in cands:                                           # value safe in memory
            if self.reg[r] in self.in_mem:
                self._free(r)
                return r
        r = max(cands, key=lambda c: self.next_use(self.reg[c]))  # spill
        name = self.reg[r]
        self.emit("STORE", name, f"R{r}", comment=f"spill {name} (register pressure)")
        self.in_mem.add(name)
        self.spills += 1
        self._free(r)
        return r

    def operand(self, x, avoid):
        if is_const(x):
            r = self.alloc(avoid)
            self.emit("LOADI", f"R{r}", x)
            self._free(r)
            self.reg[r] = f"#{x}"
            return r
        if x in self.loc:
            return self.loc[x]
        r = self.alloc(avoid)
        self.emit("LOAD", f"R{r}", x)
        self.bind(r, x)
        return r

    # -- main ------------------------------------------------------------------
    def generate(self):
        for i, q in enumerate(self.quads):
            self.cur = i
            start = len(self.code)
            if q.op == "COPY" and q.result not in self.temps:
                rs = self.operand(q.arg1, set())     # named signal: just store it
                self.emit("STORE", q.result, f"R{rs}")
                self.in_mem.add(q.result)
                self.code[start].comment = (self.code[start].comment + " | " if self.code[start].comment else "") + str(q)
                continue
            if q.op == "COPY":
                rs = self.operand(q.arg1, set())
                if self.dies_here(q.arg1):
                    rd = rs
                else:
                    rd = self.alloc({rs})
                    self.emit("MOV", f"R{rd}", f"R{rs}")
            elif q.op == "NOT":
                rs = self.operand(q.arg1, set())
                rd = rs if self.dies_here(q.arg1) else self.alloc({rs})
                self.emit("NOT", f"R{rd}", f"R{rs}")
            else:
                ra = self.operand(q.arg1, set())
                rb = self.operand(q.arg2, {ra})
                if self.dies_here(q.arg1):
                    rd = ra
                elif self.dies_here(q.arg2):
                    rd = rb
                else:
                    rd = self.alloc({ra, rb})
                self.emit(q.op, f"R{rd}", f"R{ra}", f"R{rb}")
            self.bind(rd, q.result)
            if q.result not in self.temps:
                self.emit("STORE", q.result, f"R{rd}")
                self.in_mem.add(q.result)
            if len(self.code) > start:
                self.code[start].comment = (self.code[start].comment + " | " if self.code[start].comment else "") + str(q)
        self.emit("HALT")
        return self.code


def generate(quads, inputs, temps, num_regs=4):
    gen = CodeGenerator(quads, inputs, temps, num_regs)
    code = gen.generate()
    return code, gen.spills


def format_asm(code):
    return "\n".join(str(i) for i in code)


# ---------------------------------------------------------------------------
class VirtualMachine:
    """Executes LGM assembly - used to test that the generated code is correct."""

    def run(self, code, memory):
        mem = dict(memory)
        R = {}
        for ins in code:
            op, a = ins.op, ins.args
            if op == "LOAD":
                R[a[0]] = mem[a[1]]
            elif op == "LOADI":
                R[a[0]] = int(a[1])
            elif op == "MOV":
                R[a[0]] = R[a[1]]
            elif op == "NOT":
                R[a[0]] = 1 - R[a[1]]
            elif op in BINARY_OPS:
                x, y = R[a[1]], R[a[2]]
                R[a[0]] = {"AND": x & y, "OR": x | y, "XOR": x ^ y, "NAND": 1 - (x & y),
                           "NOR": 1 - (x | y), "XNOR": 1 - (x ^ y)}[op]
            elif op == "STORE":
                mem[a[0]] = R[a[1]]
            elif op == "HALT":
                break
            else:
                raise RuntimeError(f"unknown instruction {op}")
        return mem
