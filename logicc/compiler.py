"""Compiler driver: runs the phases in order and collects every artefact."""

from .errors import ErrorHandler
from . import lexer, parser, semantic, icg, optimizer, codegen

PHASES = ["lex", "parse", "semantic", "icg", "opt", "codegen", "run"]


class CompilationResult:
    def __init__(self, source):
        self.source = source
        self.errors = ErrorHandler(source)
        self.tokens = None
        self.ast = None
        self.sem = None
        self.tac = None
        self.temps = None
        self.optimized = None
        self.opt_log = []
        self.asm = None
        self.spills = 0
        self.stopped_at = None

    @property
    def ok(self):
        return not self.errors.has_errors()


def compile_source(source, optimize=True, num_regs=4, stop_after="run"):
    res = CompilationResult(source)
    stop = PHASES.index(stop_after)

    # 1. Lexical analysis
    res.tokens = lexer.tokenize(source, res.errors)
    if stop == 0:
        return res

    # 2. Syntax analysis (runs even after lexical errors, to report more problems)
    res.ast = parser.parse(res.tokens, res.errors)
    if res.errors.has_errors():
        res.stopped_at = "parse"
        return res
    if stop == 1:
        return res

    # 3. Semantic analysis
    res.sem = semantic.analyze(res.ast, res.errors)
    if res.errors.has_errors():
        res.stopped_at = "semantic"
        return res
    if stop == 2:
        return res

    # 4. Intermediate code generation
    res.tac, res.temps = icg.generate(res.ast, res.sem.symtab)
    if stop == 3:
        return res

    # 5. Optimisation
    if optimize:
        res.optimized, res.opt_log = optimizer.optimize(res.tac, res.sem.outputs, res.temps)
    else:
        res.optimized = res.tac
    if stop == 4:
        return res

    # 6. Target code generation
    res.asm, res.spills = codegen.generate(res.optimized, res.sem.inputs, res.temps, num_regs)
    return res
