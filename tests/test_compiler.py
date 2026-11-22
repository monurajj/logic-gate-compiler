"""Unit + end-to-end tests.   Run:  python3 -m unittest discover -s tests -v"""

import os
import random
import sys
import unittest
from itertools import product

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from logicc.compiler import compile_source
from logicc.errors import ErrorHandler
from logicc.lexer import tokenize
from logicc.icg import eval_gate
from logicc.optimizer import gate_count
from logicc.simulator import simulate
from logicc.main import main

EXAMPLES = os.path.join(os.path.dirname(__file__), "..", "examples")


def messages(res):
    return [d.message for d in res.errors.errors]


def truth(src, **kw):
    res = compile_source(src, **kw)
    assert res.ok, res.errors.report()
    rows, bad = simulate(res.ast, res.asm, res.sem.inputs, res.sem.outputs)
    assert not bad, bad
    return res, rows


class TestLexer(unittest.TestCase):
    def test_tokens(self):
        e = ErrorHandler()
        toks = tokenize("input a;\nx = a and !b | 1; // c", e)
        types = [t.type for t in toks]
        self.assertEqual(types, ["INPUT", "IDENT", "SEMI", "IDENT", "ASSIGN", "IDENT", "OP", "OP",
                                 "IDENT", "OP", "CONST", "SEMI", "EOF"])
        self.assertEqual([t.value for t in toks if t.type == "OP"], ["AND", "NOT", "OR"])
        self.assertEqual((toks[3].line, toks[3].col), (2, 1))
        self.assertFalse(e.has_errors())

    def test_lexical_errors(self):
        e = ErrorHandler()
        tokenize("x = a $ 2; 3y = b; /* open", e)
        msgs = " | ".join(d.message for d in e.errors)
        self.assertIn("unexpected character '$'", msgs)
        self.assertIn("invalid constant '2'", msgs)
        self.assertIn("invalid identifier '3y'", msgs)
        self.assertIn("unterminated block comment", msgs)


class TestParser(unittest.TestCase):
    def test_precedence(self):
        # NOT > AND > XOR > OR :  a OR b AND NOT c  ==  a OR (b AND (NOT c))
        _, rows = truth("input a,b,c; output y; y = a OR b AND NOT c;")
        for (a, b, c), (y,) in rows:
            self.assertEqual(y, a | (b & (1 - c)))

    def test_left_associative(self):
        _, rows = truth("input a,b,c; output y; y = a NAND b NAND c;")
        for (a, b, c), (y,) in rows:
            self.assertEqual(y, eval_gate("NAND", eval_gate("NAND", a, b), c))

    def test_panic_mode_reports_multiple_errors(self):
        res = compile_source("input a; output y; y = a AND ; z = (a; w = a b;")
        self.assertEqual(len(res.errors.errors), 3)
        self.assertEqual(res.stopped_at, "parse")


class TestSemantic(unittest.TestCase):
    def test_errors(self):
        src = """input a, b, a; input c; output y, z, v;
                 y = a AND d; b = a OR c; z = z XOR a; y = a;"""
        msgs = " | ".join(messages(compile_source(src)))
        for expected in ["redeclaration of input 'a'", "undefined signal 'd'", "cannot assign to input 'b'",
                         "combinational loop", "already assigned", "output 'v' is declared but never assigned"]:
            self.assertIn(expected, msgs)

    def test_input_and_output(self):
        msgs = messages(compile_source("input a; output a;"))
        self.assertTrue(any("both input" in m for m in msgs))

    def test_implicit_mode(self):
        res, rows = truth("x = a AND b;")
        self.assertEqual(res.sem.inputs, ["a", "b"])
        self.assertEqual(res.sem.outputs, ["x"])
        self.assertEqual([o for _, o in rows], [(0,), (0,), (0,), (1,)])

    def test_unused_warning(self):
        res = compile_source("input a, b, c; output y; w = a OR b; y = a AND b;")
        warns = " | ".join(d.message for d in res.errors.warnings)
        self.assertIn("input 'c' is never used", warns)
        self.assertIn("wire 'w'", warns)


class TestOptimizer(unittest.TestCase):
    def opt(self, src):
        res = compile_source(src)
        self.assertTrue(res.ok, res.errors.report())
        return [str(q) for q in res.optimized]

    def test_constant_folding(self):
        self.assertEqual(self.opt("output y; y = 1 AND 0 OR 1;"), ["y = 1"])

    def test_algebraic(self):
        self.assertEqual(self.opt("input a; output y; y = a AND 1;"), ["y = a"])
        self.assertEqual(self.opt("input a; output y; y = a XOR a;"), ["y = 0"])
        self.assertEqual(self.opt("input a; output y; y = a OR NOT a;"), ["y = 1"])
        self.assertEqual(self.opt("input a; output y; y = a XOR 1;"), ["y = NOT a"])

    def test_double_negation(self):
        self.assertEqual(self.opt("input a; output y; y = NOT NOT a;"), ["y = a"])

    def test_cse(self):
        code = self.opt("input a,b,c; output y; y = (a AND b) OR (c XOR (b AND a));")
        self.assertEqual(len([c for c in code if "AND" in c]), 1)

    def test_dead_code(self):
        self.assertEqual(self.opt("input a,b; output y; w = a NOR b; y = a;"), ["y = a"])

    def test_optimizer_demo_shrinks(self):
        with open(os.path.join(EXAMPLES, "optimize_demo.lg")) as f:
            res = compile_source(f.read())
        self.assertEqual(gate_count(res.tac), 12)
        self.assertEqual(gate_count(res.optimized), 1)


class TestEndToEnd(unittest.TestCase):
    def test_full_adder(self):
        with open(os.path.join(EXAMPLES, "full_adder.lg")) as f:
            _, rows = truth(f.read())
        for (a, b, c), (s, cout) in rows:
            self.assertEqual(a + b + c, s + 2 * cout)

    def test_all_examples_run(self):
        for name in sorted(os.listdir(EXAMPLES)):
            path = os.path.join(EXAMPLES, name)
            with open(os.devnull, "w") as devnull:
                old, sys.stdout = sys.stdout, devnull
                try:
                    code = main([path, "--no-color"])
                finally:
                    sys.stdout = old
            self.assertEqual(code, 1 if "error" in name else 0, name)

    def test_register_spilling(self):
        # many live values + only 3 registers forces spills, result must stay correct
        src = ("input a,b,c,d; output y;"
               "y = ((a AND b) OR (c AND d)) XOR ((a OR c) AND (b OR d)) XOR ((a XOR d) NAND (b XOR c));")
        res, _ = truth(src, num_regs=3)
        self.assertGreater(res.spills, 0)

    def test_random_programs(self):
        """Fuzz test: random circuits, with and without optimisation, 3-6 registers."""
        rng = random.Random(2023)
        ops = ["AND", "OR", "XOR", "NAND", "NOR", "XNOR"]

        def rand_expr(names, depth):
            if depth == 0 or rng.random() < 0.25:
                return rng.choice(names + ["0", "1"]) if rng.random() < 0.9 else rng.choice(names)
            if rng.random() < 0.2:
                return f"NOT {rand_expr(names, depth - 1)}"
            return f"({rand_expr(names, depth - 1)} {rng.choice(ops)} {rand_expr(names, depth - 1)})"

        for _ in range(300):
            names = ["a", "b", "c", "d"][: rng.randint(1, 4)]
            lines = [f"input {', '.join(names)};"]
            avail = list(names)
            outs = []
            for k in range(rng.randint(1, 5)):
                w = f"w{k}"
                lines.append(f"{w} = {rand_expr(avail, 4)};")
                avail.append(w)
                if rng.random() < 0.6:
                    outs.append(w)
            outs = outs or [avail[-1]]
            src = f"output {', '.join(outs)};\n" + "\n".join(lines)
            for optimize in (True, False):
                res = compile_source(src, optimize=optimize, num_regs=rng.randint(3, 6))
                self.assertTrue(res.ok, src + "\n" + res.errors.report())
                rows, bad = simulate(res.ast, res.asm, res.sem.inputs, res.sem.outputs)
                self.assertFalse(bad, src)


class TestWebAPI(unittest.TestCase):
    def test_compile_to_json(self):
        from logicc.web import compile_to_json, load_examples
        d = compile_to_json("input a, b; output y; y = a NAND b;")
        self.assertTrue(d["ok"])
        self.assertEqual([p["status"] for p in d["phases"]], ["ok"] * 7)
        self.assertTrue(d["truth"]["verified"])
        self.assertEqual(d["truth"]["minterms"]["y"], [0, 1, 2])
        d = compile_to_json("input a; output y; y = a AND ;")
        self.assertFalse(d["ok"])
        self.assertEqual(d["phases"][1]["status"], "error")
        self.assertEqual(d["phases"][2]["status"], "skipped")
        self.assertGreaterEqual(len(load_examples()), 8)


if __name__ == "__main__":
    unittest.main()
