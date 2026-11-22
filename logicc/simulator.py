"""
PHASE 7 — EXECUTION & VERIFICATION
==================================

Runs the generated target code on the virtual machine for every one of the
2^n input combinations and prints the truth table. Each row is also checked
against a direct evaluation of the source AST (a reference interpreter), so
we *prove* that phases 4-6 (ICG, optimisation, code generation) preserved
the meaning of the program.
"""

from itertools import product

from .ast_nodes import Assignment, BinaryOp, UnaryOp, Identifier, Constant
from .codegen import VirtualMachine
from .icg import eval_gate
from . import ui

MAX_INPUTS = 12


def eval_expr(e, env):
    if isinstance(e, Identifier):
        return env[e.name]
    if isinstance(e, Constant):
        return e.value
    if isinstance(e, UnaryOp):
        return 1 - eval_expr(e.operand, env)
    return eval_gate(e.op, eval_expr(e.left, env), eval_expr(e.right, env))


def reference_eval(program, env):
    env = dict(env)
    for s in program.statements:
        if isinstance(s, Assignment):
            env[s.target] = eval_expr(s.expr, env)
    return env


def simulate(program, code, inputs, outputs):
    """Returns (rows, mismatches). rows = [(input_bits, output_bits)]."""
    if len(inputs) > MAX_INPUTS:
        raise ValueError(f"too many inputs for a truth table ({len(inputs)} > {MAX_INPUTS})")
    vm = VirtualMachine()
    rows, mismatches = [], []
    for bits in product((0, 1), repeat=len(inputs)):
        env = dict(zip(inputs, bits))
        mem = vm.run(code, env)
        ref = reference_eval(program, env)
        got = tuple(mem[o] for o in outputs)
        exp = tuple(ref[o] for o in outputs)
        rows.append((bits, got))
        if got != exp:
            mismatches.append((bits, got, exp))
    return rows, mismatches


def format_truth_table(rows, inputs, outputs):
    headers = list(inputs) + ["||"] + list(outputs)
    body = [list(i) + ["||"] + list(o) for i, o in rows]
    return ui.table(headers, body)


def minterms(rows, outputs):
    """Canonical sum-of-minterms form for every output, e.g. sum = Σm(1,2,4,7)."""
    result = {}
    for k, name in enumerate(outputs):
        ms = [idx for idx, (_, out) in enumerate(rows) if out[k] == 1]
        result[name] = ms
    return result
