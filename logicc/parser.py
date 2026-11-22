"""
PHASE 2 — SYNTAX ANALYSIS (Parser)
==================================

A hand-written *recursive-descent* (top-down, LL(1)) parser that checks the
token stream against the grammar and builds an Abstract Syntax Tree.

Grammar (EBNF) — one level per precedence, lowest first
--------------------------------------------------------
  program     → statement* EOF
  statement   → declaration | assignment
  declaration → ("input" | "output") IDENT ("," IDENT)* ";"
  assignment  → IDENT "=" expr ";"
  expr        → or_expr
  or_expr     → xor_expr  (("OR"  | "NOR")  xor_expr)*
  xor_expr    → and_expr  (("XOR" | "XNOR") and_expr)*
  and_expr    → unary     (("AND" | "NAND") unary)*
  unary       → "NOT" unary | primary
  primary     → IDENT | CONST | "(" expr ")"

Precedence: NOT  >  AND/NAND  >  XOR/XNOR  >  OR/NOR   (all binary ops are
left-associative). The left recursion of the textbook grammar
(E → E OR T | T) has been removed using the `( ... )*` loops above.

Error recovery: *panic mode*. On a syntax error we record it, skip tokens
until a synchronising token (';' or the start of a new statement), and keep
parsing — so several syntax errors are reported in one run.
"""

from .ast_nodes import Program, Declaration, Assignment, BinaryOp, UnaryOp, Identifier, Constant


class ParseError(Exception):
    pass


class Parser:
    PHASE = "Syntax"

    def __init__(self, tokens, errors):
        self.tokens = tokens
        self.errors = errors
        self.pos = 0

    # -- token helpers -------------------------------------------------------
    def peek(self, k=0):
        return self.tokens[min(self.pos + k, len(self.tokens) - 1)]

    def advance(self):
        tok = self.peek()
        if tok.type != "EOF":
            self.pos += 1
        return tok

    def check(self, ttype, *values):
        tok = self.peek()
        return tok.type == ttype and (not values or tok.value in values)

    def expect(self, ttype, message):
        if self.check(ttype):
            return self.advance()
        self.fail(message)

    def fail(self, message):
        tok = self.peek()
        self.errors.error(self.PHASE, f"{message}, but found {tok.describe()}", tok.line, tok.col)
        raise ParseError()

    def synchronize(self, stmt_start):
        if self.pos == stmt_start:          # guarantee progress
            self.advance()
        while not self.check("EOF"):
            tok = self.peek()
            if tok.type in ("INPUT", "OUTPUT"):
                return
            if tok.type == "IDENT" and self.peek(1).type == "ASSIGN":
                return
            self.advance()
            if tok.type == "SEMI":
                return

    # -- grammar rules -------------------------------------------------------
    def parse(self):
        statements = []
        while not self.check("EOF"):
            start = self.pos
            try:
                statements.append(self.statement())
            except ParseError:
                self.synchronize(start)
        return Program(statements)

    def statement(self):
        tok = self.peek()
        if tok.type in ("INPUT", "OUTPUT"):
            return self.declaration()
        if tok.type == "IDENT":
            return self.assignment()
        self.fail("expected a declaration ('input'/'output') or an assignment")

    def declaration(self):
        kw = self.advance()
        names = []
        ident = self.expect("IDENT", f"expected an identifier after '{kw.lexeme}'")
        names.append((ident.value, ident.line, ident.col))
        while self.check("COMMA"):
            self.advance()
            ident = self.expect("IDENT", "expected an identifier after ','")
            names.append((ident.value, ident.line, ident.col))
        self.expect("SEMI", "expected ';' at the end of the declaration")
        return Declaration(kw.value, names, kw.line, kw.col)

    def assignment(self):
        ident = self.advance()
        self.expect("ASSIGN", f"expected '=' after '{ident.lexeme}'")
        expr = self.expression()
        self.expect("SEMI", "expected ';' after the expression")
        return Assignment(ident.value, expr, ident.line, ident.col)

    def expression(self):
        return self._binary(0)

    LEVELS = [("OR", "NOR"), ("XOR", "XNOR"), ("AND", "NAND")]

    def _binary(self, level):
        if level == len(self.LEVELS):
            return self.unary()
        left = self._binary(level + 1)
        while self.check("OP", *self.LEVELS[level]):
            op = self.advance()
            right = self._binary(level + 1)
            left = BinaryOp(op.value, left, right, op.line, op.col)
        return left

    def unary(self):
        if self.check("OP", "NOT"):
            op = self.advance()
            return UnaryOp("NOT", self.unary(), op.line, op.col)
        return self.primary()

    def primary(self):
        tok = self.peek()
        if tok.type == "IDENT":
            self.advance()
            return Identifier(tok.value, tok.line, tok.col)
        if tok.type == "CONST":
            self.advance()
            return Constant(tok.value, tok.line, tok.col)
        if tok.type == "LPAREN":
            self.advance()
            e = self.expression()
            self.expect("RPAREN", "expected ')' to close '('")
            return e
        if tok.type == "OP":
            self.fail(f"operator '{tok.lexeme}' is missing its left operand")
        self.fail("expected an operand (variable, 0/1 or '(')")


def parse(tokens, errors):
    return Parser(tokens, errors).parse()
