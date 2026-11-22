"""
Command-line interface.

    python3 -m logicc examples/full_adder.lg
    python3 -m logicc -e "x = a AND b;"
    python3 -m logicc examples/full_adder.lg --phase icg
    python3 -m logicc examples/full_adder.lg -O0 --regs 3 -o out.asm --dot out.dot
"""

import argparse
import sys

from . import ui
from .compiler import compile_source, PHASES
from .ast_nodes import format_ast
from .icg import format_tac, format_quadruples, format_triples
from .optimizer import gate_count
from .codegen import format_asm
from .simulator import simulate, format_truth_table, minterms, MAX_INPUTS
from .circuit import to_dot


def build_arg_parser():
    p = argparse.ArgumentParser(prog="logicc", description="Logic Gate Compiler - a 7-phase compiler for boolean circuits")
    p.add_argument("file", nargs="?", help="source file (.lg)")
    p.add_argument("-e", "--expr", help="compile source code given on the command line")
    p.add_argument("--phase", choices=PHASES, default="run", help="stop after this phase (default: run everything)")
    p.add_argument("-O0", dest="optimize", action="store_false", help="disable the optimiser")
    p.add_argument("--regs", type=int, default=4, help="number of machine registers (default 4, min 3)")
    p.add_argument("-o", "--output", help="write the generated assembly to this file")
    p.add_argument("--dot", help="write a Graphviz circuit diagram to this file")
    p.add_argument("--no-color", action="store_true", help="disable coloured output")
    return p


def main(argv=None):
    args = build_arg_parser().parse_args(argv)
    if args.no_color:
        ui.USE_COLOR = False
    if args.regs < 3:
        print("error: --regs must be at least 3", file=sys.stderr)
        return 2

    if args.expr is not None:
        source, name = args.expr, "<command line>"
    elif args.file:
        try:
            with open(args.file, encoding="utf-8") as f:
                source = f.read()
        except OSError as e:
            print(f"error: cannot read {args.file}: {e.strerror}", file=sys.stderr)
            return 2
        name = args.file
    else:
        build_arg_parser().print_help()
        return 2

    res = compile_source(source, optimize=args.optimize, num_regs=args.regs, stop_after=args.phase)
    print(ui.bold(f"Logic Gate Compiler  -  compiling {name}"))
    print(ui.header("SOURCE PROGRAM"))
    for i, line in enumerate(source.splitlines(), 1):
        print(f"  {i:>3} | {line}")

    # ---- Phase 1
    print(ui.header("PHASE 1: LEXICAL ANALYSIS  (source -> tokens)"))
    rows = [[t.lexeme, t.type, t.value if t.type in ("OP", "CONST") else "", f"{t.line}:{t.col}"]
            for t in res.tokens if t.type != "EOF"]
    print(ui.table(["Lexeme", "Token", "Attribute", "Line:Col"], rows))
    print(f"Total tokens: {len(rows)}")

    # ---- Phase 2
    if res.ast is not None and res.stopped_at != "parse":
        print(ui.header("PHASE 2: SYNTAX ANALYSIS  (tokens -> abstract syntax tree)"))
        print("\n".join(format_ast(res.ast)))
        print(ui.green("Syntax OK - program matches the grammar."))

    # ---- Phase 3
    if res.sem is not None:
        print(ui.header("PHASE 3: SEMANTIC ANALYSIS  (type/scope checks + symbol table)"))
        print(res.sem.symtab.format())
        print(f"Inputs : {', '.join(res.sem.inputs) or '-'}")
        print(f"Outputs: {', '.join(res.sem.outputs) or '-'}")
        print(ui.green("Semantic checks passed."))

    # ---- Diagnostics (error handler)
    if res.errors.diagnostics or not res.ok:
        print(ui.header("ERROR HANDLER: DIAGNOSTICS"))
        print(res.errors.report())
    if not res.ok:
        print(ui.red(f"\nCompilation failed during the {res.stopped_at or 'lexical'} phase."))
        return 1

    # ---- Phase 4
    if res.tac is not None:
        print(ui.header("PHASE 4: INTERMEDIATE CODE GENERATION  (three-address code)"))
        print(format_tac(res.tac))
        print("\nQuadruples:")
        print(format_quadruples(res.tac))
        print("\nTriples:")
        print(format_triples(res.tac, res.temps))

    # ---- Phase 5
    if res.optimized is not None:
        print(ui.header("PHASE 5: CODE OPTIMIZATION"))
        if not args.optimize:
            print(ui.yellow("Optimiser disabled (-O0)."))
        elif not res.opt_log:
            print("No optimisation opportunities found.")
        else:
            for rnd, name_, msg in res.opt_log:
                print(f"  [round {rnd}] {ui.cyan(name_ + ':'):<40} {msg}")
        print("\nOptimised three-address code:")
        print(format_tac(res.optimized))
        print("\n" + ui.table(["Metric", "Before", "After"], [
            ["TAC instructions", len(res.tac), len(res.optimized)],
            ["Logic gates", gate_count(res.tac), gate_count(res.optimized)],
        ]))

    # ---- Phase 6
    if res.asm is not None:
        print(ui.header(f"PHASE 6: TARGET CODE GENERATION  (LGM assembly, {args.regs} registers)"))
        print(format_asm(res.asm))
        print(f"\nInstructions: {len(res.asm)}   Register spills: {res.spills}")
        if args.output:
            with open(args.output, "w", encoding="utf-8") as f:
                f.write(f"; generated by logicc from {name}\n" + format_asm(res.asm) + "\n")
            print(ui.green(f"Assembly written to {args.output}"))
        if args.dot:
            with open(args.dot, "w", encoding="utf-8") as f:
                f.write(to_dot(res.optimized, res.sem.inputs, res.sem.outputs) + "\n")
            print(ui.green(f"Circuit diagram written to {args.dot}  (render: dot -Tpng {args.dot} -o circuit.png)"))

        # ---- Phase 7
        if args.phase == "run":
            print(ui.header("PHASE 7: EXECUTION ON VIRTUAL MACHINE  (truth table + verification)"))
            if len(res.sem.inputs) > MAX_INPUTS:
                print(ui.yellow(f"Skipped: {len(res.sem.inputs)} inputs is too many for a truth table."))
            else:
                rows, bad = simulate(res.ast, res.asm, res.sem.inputs, res.sem.outputs)
                print(format_truth_table(rows, res.sem.inputs, res.sem.outputs))
                for out, ms in minterms(rows, res.sem.outputs).items():
                    print(f"  {out} = Σm({', '.join(map(str, ms))})")
                if bad:
                    print(ui.red(f"\nVERIFICATION FAILED on {len(bad)} row(s): {bad[:3]}"))
                    return 1
                print(ui.green(f"\nVerified: target code output matches the source program on all "
                               f"{len(rows)} input combinations."))

    print(ui.green("\nCompilation successful."))
    return 0


if __name__ == "__main__":
    sys.exit(main())
