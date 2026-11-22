"""
Abstract Syntax Tree (AST) node definitions + a pretty printer.

The parser (Phase 2) builds this tree; every later phase walks it.
"""

from dataclasses import dataclass
from typing import List, Tuple


@dataclass
class Program:
    statements: list


@dataclass
class Declaration:
    kind: str                             # "input" | "output"
    names: List[Tuple[str, int, int]]     # (name, line, col)
    line: int
    col: int


@dataclass
class Assignment:
    target: str
    expr: object
    line: int
    col: int


@dataclass
class BinaryOp:
    op: str
    left: object
    right: object
    line: int
    col: int


@dataclass
class UnaryOp:
    op: str
    operand: object
    line: int
    col: int


@dataclass
class Identifier:
    name: str
    line: int
    col: int


@dataclass
class Constant:
    value: int
    line: int
    col: int


# ---------------------------------------------------------------------------
def expr_to_str(e):
    """Fully parenthesised infix form of an expression."""
    if isinstance(e, Identifier):
        return e.name
    if isinstance(e, Constant):
        return str(e.value)
    if isinstance(e, UnaryOp):
        return f"NOT {expr_to_str(e.operand)}"
    return f"({expr_to_str(e.left)} {e.op} {expr_to_str(e.right)})"


def _label(n):
    if isinstance(n, Program):
        return "Program"
    if isinstance(n, Declaration):
        return f"Declaration [{n.kind}]: " + ", ".join(x[0] for x in n.names)
    if isinstance(n, Assignment):
        return f"Assign  {n.target} ="
    if isinstance(n, BinaryOp):
        return f"Gate {n.op}"
    if isinstance(n, UnaryOp):
        return "Gate NOT"
    if isinstance(n, Identifier):
        return f"Var {n.name}"
    if isinstance(n, Constant):
        return f"Const {n.value}"
    return type(n).__name__


def _children(n):
    if isinstance(n, Program):
        return n.statements
    if isinstance(n, Assignment):
        return [n.expr]
    if isinstance(n, BinaryOp):
        return [n.left, n.right]
    if isinstance(n, UnaryOp):
        return [n.operand]
    return []


def format_ast(node, prefix="", is_last=True, is_root=True):
    lines = []
    if is_root:
        lines.append(_label(node))
        child_prefix = ""
    else:
        lines.append(prefix + ("└── " if is_last else "├── ") + _label(node))
        child_prefix = prefix + ("    " if is_last else "│   ")
    kids = _children(node)
    for i, k in enumerate(kids):
        lines.extend(format_ast(k, child_prefix, i == len(kids) - 1, False))
    return lines
