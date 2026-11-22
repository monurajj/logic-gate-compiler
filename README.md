# Logic Gate Compiler (`logicc`)

**Compiler Design Project – Team CD_2023_Team_1**

`logicc` compiles a small hardware-description language for **combinational
logic circuits** (AND, OR, NOT, XOR, NAND, NOR, XNOR) through **all the
classic phases of a compiler**. The output is assembly for a register
machine, which is then run on a virtual machine to print and check the
circuit's truth table.

```
x = a AND b;
```

```
input a, b, cin;
output sum, cout;

p    = a XOR b;
g    = a AND b;
sum  = p XOR cin;
cout = g OR (p AND cin);
```

Written in pure Python 3 (3.8 or newer). No external libraries are needed.

---

## Web UI (for demos)

```bash
python3 -m logicc.web          # opens http://127.0.0.1:8000 in your browser
```

The left side is a code editor. It compiles as you type, lists errors with
their line numbers, and you can click an error to jump to that line. The
right side shows **each of the 7 phases as a step** (← → arrow keys move
between them):

* token stream and token table
* graphical **syntax tree** and the grammar
* symbol table and the semantic checks
* TAC, quadruples and triples
* before/after optimisation with every rule that was applied
* the generated assembly
* the verified truth table
* a **Live Circuit**: the optimised netlist drawn as logic gates. Click
  an input to toggle it and the wires and output lamps update.

**▶ Step-by-step** (bottom bar) animates the whole compilation. It moves
through the phases on its own and builds each one up piece by piece: tokens
one at a time, the syntax tree level by level, symbol-table rows, TAC lines
together with their quadruple and triple rows, one optimisation at a time,
assembly line by line, truth-table rows, and finally the circuit going
through every input combination. You can pause it, stop it, or change the
speed (0.5×–4×). It stops at the phase where compilation fails, if there are
errors.

**ⓘ icons**: every compiler term in the UI (token, lexeme, AST, LL(1),
symbol table, quadruples, triples, CSE, register spill, minterm, every gate
…) has an info icon. Hover over it, or tap it on a touchscreen, to see a short
explanation.

You can link straight to a phase and example, e.g.
`http://127.0.0.1:8000/#tab=8&ex=full_adder`. Adding `&play=1` starts the
animation as soon as the page opens, e.g. `#ex=full_adder&play=1&speed=1`.

## Deploy publicly on Vercel (free)

The repo is ready for Vercel. The page is served as a static file, and
`api/compile.py` and `api/examples.py` run as Python serverless functions
that use the same compiler code. No packages or build step are needed.

1. Go to <https://vercel.com> and **sign in with GitHub**.
2. Click **Add New… → Project** and **Import** `logic-gate-compiler`.
3. Leave every setting at its default (Framework preset: **Other**, no build command) and click **Deploy**.
4. Vercel gives you a public URL like `https://logic-gate-compiler.vercel.app`.

From then on, every push to `main` redeploys the site automatically.

| File | Purpose |
|---|---|
| `vercel.json` | serves the UI at `/` and bundles `logicc/` + `examples/` with the functions |
| `api/compile.py` | `POST /api/compile`, runs all phases and returns JSON |
| `api/examples.py` | `GET /api/examples`, returns the example programs |
| `requirements.txt` | empty: no third-party packages |

Safety limits for public use: programs over 20 KB are rejected, expressions
nested too deeply return an error instead of crashing, and truth tables are
limited to 12 inputs.

## Quick start

```bash
git clone <repo-url>
cd logic-gate-compiler

python3 -m logicc examples/full_adder.lg          # run all 7 phases
python3 -m logicc -e "x = a AND b;"               # compile code from the command line
python3 -m logicc examples/mux2.lg --phase icg    # stop after a given phase
python3 -m logicc examples/optimize_demo.lg       # see every optimisation
python3 -m logicc examples/semantic_errors.lg     # see error reporting
python3 -m logicc examples/full_adder.lg --regs 3 -o adder.asm --dot adder.dot

python3 -m unittest discover -s tests -v          # run the test suite
```

| Option | Meaning |
|---|---|
| `--phase {lex,parse,semantic,icg,opt,codegen,run}` | stop after that phase |
| `-O0` | turn the optimiser off (compare the code before and after) |
| `--regs N` | number of machine registers (min 3). Fewer registers cause spills |
| `-o FILE` | save the generated assembly |
| `--dot FILE` | save a Graphviz circuit diagram (`dot -Tpng FILE -o circuit.png`) |
| `--no-color` | plain output (for reports / screenshots) |

---

## The 7 phases

```
 source.lg
    │
    ▼
┌──────────────────────────┐
│ 1. Lexical Analysis      │  lexer.py      characters → tokens
├──────────────────────────┤
│ 2. Syntax Analysis       │  parser.py     tokens → Abstract Syntax Tree
├──────────────────────────┤        ┌──────────────────────────┐
│ 3. Semantic Analysis     │  ◄────►│ Symbol Table             │ symbol_table.py
├──────────────────────────┤        │ Error Handler            │ errors.py
│ 4. Intermediate Code Gen │  icg.py│ (used by every phase)    │
├──────────────────────────┤        └──────────────────────────┘
│ 5. Code Optimisation     │  optimizer.py
├──────────────────────────┤
│ 6. Target Code Gen       │  codegen.py    TAC → register-machine assembly
├──────────────────────────┤
│ 7. Execution/Verification│  simulator.py  run on VM → truth table, verified
└──────────────────────────┘
```

> In textbooks (Aho, Ullman – *the Dragon Book*) the compiler has **6 phases**
> (lexical → syntax → semantic → ICG → optimisation → code generation) plus
> **the symbol table manager and the error handler**. This project implements
> all of them and adds a 7th execution phase that checks that the compiled
> code is correct.

### Phase 1 – Lexical Analysis (`logicc/lexer.py`)
A hand-written scanner that turns characters into tokens. It removes
whitespace and comments (`#`, `//`, `/* */`). Keywords and gate names are
case-insensitive. `&  |  ^  !  ~` can be used instead of `AND OR XOR NOT NOT`.

| Token | Examples |
|---|---|
| `INPUT`, `OUTPUT` | `input`, `output` |
| `IDENT` | `a`, `cin`, `carry_out` |
| `CONST` | `0`, `1`, `true`, `false` |
| `OP` | `AND OR NOT XOR NAND NOR XNOR & \| ^ ! ~` |
| `ASSIGN SEMI COMMA LPAREN RPAREN` | `= ; , ( )` |

Lexical errors: illegal characters (`$`), invalid constants (`2`),
identifiers starting with a digit (`3y`), and unterminated comments.

### Phase 2 – Syntax Analysis (`logicc/parser.py`)
A **recursive-descent (LL(1)) parser** that builds an AST.

```ebnf
program     → statement* EOF
statement   → declaration | assignment
declaration → ("input" | "output") IDENT ("," IDENT)* ";"
assignment  → IDENT "=" expr ";"
expr        → or_expr
or_expr     → xor_expr (("OR"  | "NOR")  xor_expr)*
xor_expr    → and_expr (("XOR" | "XNOR") and_expr)*
and_expr    → unary    (("AND" | "NAND") unary)*
unary       → "NOT" unary | primary
primary     → IDENT | CONST | "(" expr ")"
```

* Operator precedence: `NOT` > `AND/NAND` > `XOR/XNOR` > `OR/NOR`. Binary operators are left-associative.
* Left recursion is removed (`E → E OR T | T` becomes `E → T (OR T)*`).
* **Panic-mode error recovery**: after a syntax error the parser skips to `;`
  or to the start of the next statement and keeps going, so it reports all
  syntax errors in one run.

### Phase 3 – Semantic Analysis (`logicc/semantic.py`, `logicc/symbol_table.py`)
This phase fills the **symbol table** (name, kind, type, declaration line,
assignment line, number of uses) and checks the rules a real circuit must follow:

| Check | Example |
|---|---|
| redeclaration | `input a, b, a;` |
| both input and output | `input a; output a;` |
| assigning to an input | `b = a OR c;` |
| multiple drivers | `y = a; y = b;` |
| use before definition / undefined | `y = a AND d;` |
| combinational loop | `z = z XOR a;` |
| output never assigned | `output v;` with no `v = ...` |
| *warning:* unused input / dead wire | |

Short form: if no `input` is declared, unknown names become **implicit
inputs**. If no `output` is declared, every assigned signal becomes an
output. This is why the one-line program `x = a AND b;` works.

### Phase 4 – Intermediate Code Generation (`logicc/icg.py`)
The AST is converted to **three-address code**, using a new temporary for each gate.
The code is shown three ways: TAC, **quadruples** and **triples**.

```
cout = g OR (p AND cin);   →   t4 = p AND cin
                               t5 = g OR t4
                               cout = t5
```

### Phase 5 – Code Optimisation (`logicc/optimizer.py`)
The passes repeat until no pass changes anything:

| Pass | Before | After |
|---|---|---|
| Constant folding | `t1 = 1 XOR 0` | `t1 = 1` |
| Algebraic simplification (Boolean laws) | `t1 = a AND 1`, `a XOR a`, `a OR NOT a` | `a`, `0`, `1` |
| Double negation | `NOT NOT x` | `x` |
| Common sub-expression elimination | `a AND b` … `b AND a` | computed once |
| Copy / constant propagation | `t1 = a; t2 = t1 OR c` | `t2 = a OR c` |
| Copy coalescing | `t3 = a XOR b; s = t3` | `s = a XOR b` |
| Dead code elimination | results that never reach an output | removed |

`examples/optimize_demo.lg` goes from **12 gates to 1**.

### Phase 6 – Target Code Generation (`logicc/codegen.py`)
Generates assembly for **LGM** (Logic Gate Machine), a register machine:

```
LOAD Rd, var | LOADI Rd, 0/1 | MOV Rd, Rs | NOT Rd, Rs
AND/OR/XOR/NAND/NOR/XNOR Rd, Ra, Rb | STORE var, Rs | HALT
```

Register allocation uses a **register descriptor**, an **address descriptor**
and **next-use information**. When it runs out of registers it **spills** the
value whose next use is farthest away. Try `--regs 3` to see spills.

### Phase 7 – Execution & Verification (`logicc/simulator.py`)
The generated assembly runs on a virtual machine for all 2ⁿ input
combinations, which gives the **truth table** and the canonical form
`y = Σm(...)`. Each row is checked against a direct evaluation of the
original AST, which shows that phases 4–6 did not change what the program
computes.

---

## Sample output (full adder, shortened)

```
PHASE 4: INTERMEDIATE CODE GENERATION        PHASE 6: TARGET CODE GENERATION
    0:  t1 = a XOR b                             LOAD   R0, a     ; p = a XOR b
    1:  p = t1                                   LOAD   R1, b
    2:  t2 = a AND b                             XOR    R2, R0, R1
    ...                                          STORE  p, R2
PHASE 5: CODE OPTIMIZATION                       AND    R0, R0, R1 ; g = a AND b
    0:  p = a XOR b                              ...
    1:  g = a AND b
    2:  sum = p XOR cin                      PHASE 7: truth table
    3:  t4 = p AND cin                         a b cin || sum cout
    4:  cout = g OR t4                         0 0 0   || 0   0   ...
                                               sum  = Σm(1, 2, 4, 7)
                                               cout = Σm(3, 5, 6, 7)
```

---

## Auto-commit while working

```bash
python3 tools/autocommit.py              # every 30 s: commit + push any changes
python3 tools/autocommit.py --no-push    # commit locally only
```

It commits only after the files have stopped changing, so half-typed
edits aren't saved. If a teammate pushed first, it pulls their commits and
then pushes. Stop it with `Ctrl+C`.

## Project structure

```
logic-gate-compiler/
├── logicc/
│   ├── lexer.py          Phase 1
│   ├── parser.py         Phase 2
│   ├── ast_nodes.py      AST classes + tree printer
│   ├── semantic.py       Phase 3
│   ├── symbol_table.py   Symbol table
│   ├── errors.py         Error handler
│   ├── icg.py            Phase 4
│   ├── optimizer.py      Phase 5
│   ├── codegen.py        Phase 6 + virtual machine
│   ├── simulator.py      Phase 7
│   ├── circuit.py        Graphviz circuit export
│   ├── compiler.py       runs the phases in order
│   ├── main.py           command-line interface
│   ├── web.py            web UI server (python3 -m logicc.web)
│   └── static/index.html web UI page
├── api/                  Vercel serverless functions (public deployment)
├── examples/             .lg sample programs (adders, mux, comparator, error demos)
└── tests/                unit tests + random-program (fuzz) tests
```

## Suggested work split for the team

| Member | Module(s) | Phase |
|---|---|---|
| 1 | `lexer.py` | Lexical analysis |
| 2 | `parser.py`, `ast_nodes.py` | Syntax analysis |
| 3 | `semantic.py`, `symbol_table.py`, `errors.py` | Semantic analysis, symbol table, error handling |
| 4 | `icg.py` | Intermediate code generation |
| 5 | `optimizer.py` | Code optimisation |
| 6 | `codegen.py`, `simulator.py` | Code generation, execution and testing |

## Tools used

* **Python 3** standard library only (no third-party packages).
* **Claude Code** (Anthropic's AI coding assistant). We used it as a coding
  assistant while building this project, and it wrote much of the code
  following our instructions. Commits it helped write are marked
  `Co-Authored-By: Claude`.
* **Our team** chose the project scope and the language syntax. We asked for
  and reviewed every feature (the 7 phases, the web UI, step-by-step mode,
  the ⓘ explanations, auto-compile, Vercel deployment). We tested it with
  the example programs and the test suite, and we understand each phase well
  enough to explain it and change it.
