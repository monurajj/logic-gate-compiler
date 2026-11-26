# Project Report: Logic Gate Compiler (`logicc`)

**Course:** Compiler Design
**Team:** CD_2023_Team_1
**Repository:** <https://github.com/monurajj/logic-gate-compiler>
**Date:** 26 November 2026

| # | Name | Main responsibility |
|---|---|---|
| 1 | Monu Raj | Design, implementation and testing of all phases, web interface and deployment |

---

## 1. Abstract

We built `logicc`, a compiler for a small hardware-description language that
describes **combinational logic circuits** made of AND, OR, NOT, XOR, NAND,
NOR and XNOR gates. The compiler goes through every phase of the standard
compiler model: lexical analysis, syntax analysis, semantic analysis,
intermediate code generation, code optimisation and target code generation.
It also has a symbol table and an error handler that all the phases use. We
added a seventh phase that runs the generated assembly on a virtual machine,
prints the circuit's truth table, and checks every row against the source
program. This checks that the compiler is correct for every input.

The project is written in pure Python 3 with no third-party libraries. It has
a command-line interface and a web interface that animates each phase step by
step. The web interface can be deployed on Vercel. A test suite of 20 tests,
including randomly generated programs, passes in full.

## 2. Introduction and Motivation

Compiler design is usually taught with a general-purpose language as the
example, which makes a full compiler too large for a semester project. We
picked **Boolean logic circuits** as the source language for three reasons:

1. **The language is small but complete.** It has declarations, assignments,
   expressions with precedence, and named variables, so every phase has real
   work to do.
2. **Optimisation is easy to see.** Boolean algebra (for example
   `a AND 1 = a` and `a OR NOT a = 1`) gives clear optimisations, and the
   result can be measured as a number of logic gates.
3. **Correctness can be checked fully.** A circuit with *n* inputs has only
   2ⁿ input combinations, so we can run the compiled code on every one and
   prove that it computes the same function as the source.

### Objectives

- Implement all six textbook phases, plus the symbol table and error handler.
- Report **all** errors in one run, with line and column numbers.
- Apply several optimisation passes and show each change.
- Generate assembly for a register machine, with register allocation and
  spilling.
- Check automatically that the generated code is correct.
- Provide a visual tool that is useful for teaching and demonstrations.

## 3. The Source Language

A program declares inputs and outputs, then assigns a Boolean expression to
each signal. Example (1-bit full adder, `examples/full_adder.lg`):

```
input a, b, cin;
output sum, cout;

p    = a XOR b;            # propagate
g    = a AND b;            # generate
sum  = p XOR cin;
cout = g OR (p AND cin);
```

Features:

- Gates: `AND OR NOT XOR NAND NOR XNOR`, with symbol forms `& | ^ ! ~`.
- Constants `0`, `1`, `true`, `false`.
- Comments: `#`, `//` and `/* ... */`.
- Keywords are case-insensitive.
- **Short form:** if no `input` is declared, unknown names become inputs, and
  if no `output` is declared, every assigned signal becomes an output. So the
  one-line program `x = a AND b;` is valid.

## 4. System Architecture

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

`compiler.py` runs the phases in order and stops at the first phase that
reports errors. `main.py` is the command-line interface, and `web.py` with
`static/index.html` is the web interface.

## 5. Design and Implementation of Each Phase

### 5.1 Phase 1: Lexical Analysis (`lexer.py`)

A hand-written scanner reads the source one character at a time and produces
tokens with their line and column. It skips whitespace and all three kinds of
comment.

| Token | Examples |
|---|---|
| `INPUT`, `OUTPUT` | `input`, `output` |
| `IDENT` | `a`, `cin`, `carry_out` |
| `CONST` | `0`, `1`, `true`, `false` |
| `OP` | `AND OR NOT XOR NAND NOR XNOR & \| ^ ! ~` |
| `ASSIGN SEMI COMMA LPAREN RPAREN` | `= ; , ( )` |

**Errors detected:** illegal characters (`$`), invalid constants (`2`),
identifiers that start with a digit (`3y`), and comments that are never
closed. The full-adder program produces 40 tokens.

### 5.2 Phase 2: Syntax Analysis (`parser.py`, `ast_nodes.py`)

A **recursive-descent LL(1) parser** builds an Abstract Syntax Tree. The
grammar:

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

- **Precedence:** `NOT` > `AND/NAND` > `XOR/XNOR` > `OR/NOR`. Each level is a
  separate grammar rule.
- **Associativity:** binary operators are left-associative.
- **Left recursion removed:** `E → E OR T | T` is rewritten as
  `E → T (OR T)*` so that recursive descent can parse it.
- **Panic-mode error recovery:** after a syntax error the parser skips to the
  next `;` or the start of the next statement and continues, so one run
  reports every syntax error.

AST produced for the full adder:

```
Program
├── Declaration [input]: a, b, cin
├── Declaration [output]: sum, cout
├── Assign  p =
│   └── Gate XOR
│       ├── Var a
│       └── Var b
...
└── Assign  cout =
    └── Gate OR
        ├── Var g
        └── Gate AND
            ├── Var p
            └── Var cin
```

### 5.3 Phase 3: Semantic Analysis (`semantic.py`, `symbol_table.py`)

This phase walks the AST, fills the **symbol table**, and checks the rules a
real circuit must follow.

Symbol table for the full adder:

| # | Name | Kind | Type | Declared | Assigned | Uses |
|---|---|---|---|---|---|---|
| 1 | a | input | bit | 4 | - | 2 |
| 2 | b | input | bit | 4 | - | 2 |
| 3 | cin | input | bit | 4 | - | 2 |
| 4 | sum | output | bit | 5 | 9 | 0 |
| 5 | cout | output | bit | 5 | 10 | 0 |
| 6 | p | wire | bit | 7 | 7 | 2 |
| 7 | g | wire | bit | 8 | 8 | 1 |

Checks performed:

| Check | Example |
|---|---|
| Redeclaration | `input a, b, a;` |
| Signal declared as both input and output | `input a; output a;` |
| Assigning to an input | `b = a OR c;` |
| Multiple drivers | `y = a; y = b;` |
| Undefined signal or use before definition | `y = a AND d;` |
| Combinational loop | `z = z XOR a;` |
| Output never assigned | `output v;` with no `v = ...` |
| *Warning:* unused input or wire | `w = a NAND b;` with `w` never used |

### 5.4 Error Handler (`errors.py`)

Every phase reports problems to one shared error handler. Each message has a
category (Lexical, Syntax, Semantic), a line and column, and a plain-English
explanation. Errors and warnings are collected, sorted, and printed together.

Output for `examples/syntax_errors.lg` (lexical and syntax errors):

```
ERROR [Lexical] (line 6, col 7): unexpected character '$'
ERROR [Lexical] (line 8, col 7): invalid constant '2' (only 0 and 1 are allowed)
ERROR [Syntax] (line 5, col 11): expected an operand (variable, 0/1 or '('), but found ';'
ERROR [Syntax] (line 6, col 9): expected ';' after the expression, but found 'b'
ERROR [Syntax] (line 7, col 12): expected ')' to close '(', but found ';'
ERROR [Syntax] (line 8, col 9): expected ';' after the expression, but found 'b'
6 error(s), 0 warning(s)
```

Output for `examples/semantic_errors.lg`:

```
ERROR [Semantic] (line 2, col 13): redeclaration of input 'a' (first declared at line 2)
ERROR [Semantic] (line 6, col 11): undefined signal 'd' (not an input and not assigned before this line)
ERROR [Semantic] (line 7, col 1): cannot assign to input 'b' (inputs are driven from outside the circuit)
ERROR [Semantic] (line 8, col 5): combinational loop: 'z' is used in its own definition
ERROR [Semantic] (line 9, col 1): 'y' is already assigned at line 6 (a signal can have only one driver)
ERROR [Semantic] (line 4): output 'v' is declared but never assigned
WARNING [Semantic] (line 10): wire 'w' is assigned but never used (it will be removed as dead code)
6 error(s), 1 warning(s)
```

### 5.5 Phase 4: Intermediate Code Generation (`icg.py`)

The AST is translated into **three-address code (TAC)**, with a new temporary
for each gate. The same code is also shown as **quadruples** and **triples**.

Three-address code for the full adder:

```
0:  t1 = a XOR b
1:  p = t1
2:  t2 = a AND b
3:  g = t2
4:  t3 = p XOR cin
5:  sum = t3
6:  t4 = p AND cin
7:  t5 = g OR t4
8:  cout = t5
```

| # | op | arg1 | arg2 | result |   | # | op | arg1 | arg2 |
|---|---|---|---|---|---|---|---|---|---|
| 0 | XOR | a | b | t1 | | (0) | XOR | a | b |
| 1 | = | t1 | | p | | (1) | = | p | (0) |
| 2 | AND | a | b | t2 | | (2) | AND | a | b |
| … | | | | | | … | | | |
| 7 | OR | g | t4 | t5 | | (7) | OR | g | (6) |
| 8 | = | t5 | | cout | | (8) | = | cout | (7) |

*(Left: quadruples. Right: triples, where results are referred to by
instruction number.)*

### 5.6 Phase 5: Code Optimisation (`optimizer.py`)

The optimiser applies these passes repeatedly until a full round changes
nothing (a fixed point):

| Pass | Before | After |
|---|---|---|
| Constant folding | `t1 = 1 XOR 0` | `t1 = 1` |
| Algebraic simplification (Boolean laws) | `a AND 1`, `a XOR a`, `a OR NOT a` | `a`, `0`, `1` |
| Double negation | `NOT NOT x` | `x` |
| Common sub-expression elimination (handles commutativity) | `a AND b` … `b AND a` | computed once |
| Copy and constant propagation | `t1 = a; t2 = t1 OR c` | `t2 = a OR c` |
| Copy coalescing | `t3 = a XOR b; s = t3` | `s = a XOR b` |
| Dead code elimination | results that never reach an output | removed |

Every change is logged. For the full adder, copy coalescing reduces the code
from **9 TAC instructions to 5**.

**Optimisation demo** (`examples/optimize_demo.lg`), a program written badly
on purpose:

```
input a, b, c;
output x, y, z;

t      = a AND 1;                 # a AND 1 = a
x      = (t AND b) OR (b AND a);  # CSE + (p OR p = p)
k      = 1 XOR 0;                 # constant folding -> 1
y      = NOT NOT (c AND k);       # double negation + constant propagation
unused = a NAND b;                # dead code
z      = (a OR NOT a) AND c;      # complement law: a OR NOT a = 1
```

After 4 rounds the optimiser produces:

```
x = a AND b
y = c
z = c
```

| Metric | Before | After |
|---|---|---|
| TAC instructions | 18 | 3 |
| Logic gates | 12 | 1 |

### 5.7 Phase 6: Target Code Generation (`codegen.py`)

The target is **LGM** (Logic Gate Machine), a simple register machine that we
designed:

```
LOAD Rd, var | LOADI Rd, 0/1 | MOV Rd, Rs | NOT Rd, Rs
AND/OR/XOR/NAND/NOR/XNOR Rd, Ra, Rb | STORE var, Rs | HALT
```

Register allocation follows the textbook *getReg* method. It keeps a
**register descriptor** (what each register holds), an **address descriptor**
(where each variable's current value is), and **next-use information** for
each instruction. When no register is free, it **spills** the value whose next
use is furthest away. The number of registers can be set with `--regs N`
(minimum 3).

Generated code for the full adder (4 registers):

```
LOAD   R0, a              ; p = a XOR b
LOAD   R1, b
XOR    R2, R0, R1
STORE  p, R2
AND    R0, R0, R1         ; g = a AND b
STORE  g, R0
LOAD   R3, cin            ; sum = p XOR cin
XOR    R1, R2, R3
STORE  sum, R1
AND    R2, R2, R3         ; t4 = p AND cin
OR     R0, R0, R2         ; cout = g OR t4
STORE  cout, R0
HALT
```

13 instructions, 0 register spills. `a` and `b` are loaded only once and
reused, because the address descriptor shows they are already in registers.

### 5.8 Phase 7: Execution and Verification (`simulator.py`)

The generated assembly runs on a virtual machine for all 2ⁿ input
combinations. This gives the truth table and the canonical sum-of-minterms
form of each output. Each row is also computed **directly from the original
AST**, without using phases 4 to 6. If the two results differ, the compiler
has a bug, and the row is reported.

| a | b | cin | sum | cout |
|---|---|---|---|---|
| 0 | 0 | 0 | 0 | 0 |
| 0 | 0 | 1 | 1 | 0 |
| 0 | 1 | 0 | 1 | 0 |
| 0 | 1 | 1 | 0 | 1 |
| 1 | 0 | 0 | 1 | 0 |
| 1 | 0 | 1 | 0 | 1 |
| 1 | 1 | 0 | 0 | 1 |
| 1 | 1 | 1 | 1 | 1 |

```
sum  = Σm(1, 2, 4, 7)
cout = Σm(3, 5, 6, 7)
Verified: target code output matches the source program on all 8 input combinations.
```

This is the correct truth table for a full adder.

## 6. User Interfaces

### 6.1 Command line

```bash
python3 -m logicc examples/full_adder.lg          # run all 7 phases
python3 -m logicc -e "x = a AND b;"               # compile code given on the command line
python3 -m logicc examples/mux2.lg --phase icg    # stop after a given phase
python3 -m logicc examples/full_adder.lg -O0      # turn the optimiser off
python3 -m logicc examples/full_adder.lg --regs 3 -o adder.asm --dot adder.dot
```

`--dot` exports the optimised circuit as a Graphviz diagram.

### 6.2 Web interface

`python3 -m logicc.web` opens a browser page with a code editor on the left
and the compiler phases on the right:

- It compiles as you type and lists errors. Clicking an error jumps to its
  line.
- Each phase has its own step: token table, graphical syntax tree, symbol
  table, TAC/quadruples/triples, optimisation before and after, assembly, and
  truth table.
- **Live Circuit:** the optimised netlist is drawn as logic gates. Clicking an
  input toggles it, and the wires and output lamps update.
- **Step-by-step mode** animates the whole compilation: tokens one at a time,
  the tree level by level, one optimisation at a time, and so on. It can be
  paused, stopped, or run at 0.5× to 4× speed.
- Every compiler term has an **ⓘ** icon that explains it, for teaching.

The same compiler code runs as Python serverless functions on **Vercel**
(`api/compile.py`, `api/examples.py`). Programs over 20 KB, very deeply
nested expressions, and truth tables with more than 12 inputs are rejected,
so the public site cannot be overloaded.

## 7. Testing

`python3 -m unittest discover -s tests -v` runs **20 tests**, and all of them
pass (0.5 s).

| Test group | What is tested |
|---|---|
| Lexer | token types; lexical errors |
| Parser | operator precedence; left associativity; panic mode reports several errors |
| Semantic | every error type; input-and-output conflict; implicit (short form) mode; unused-signal warning |
| Optimiser | constant folding; algebraic laws; double negation; CSE; dead code; demo shrinks to 1 gate |
| End-to-end | full adder; every example program compiles (error examples fail as expected); a 4-input circuit on 3 registers must spill and still be correct |
| **Fuzz test** | 300 random programs (1–4 inputs, up to 5 signals, nested expressions), each compiled with and without optimisation on 3–6 registers; the VM output must match direct evaluation of the AST for every input |
| Web API | compile request returns correct JSON |

The fuzz test is the most important. It tests the whole pipeline (parser,
ICG, optimiser, register allocator and VM) on programs we did not write by
hand, so it finds cases that hand-written tests miss.

Example programs in `examples/`: `simple`, `half_adder`, `full_adder`,
`mux2`, `comparator`, `optimize_demo`, `syntax_errors`, `semantic_errors`.

## 8. Project Structure and Size

```
logic-gate-compiler/
├── logicc/
│   ├── lexer.py          Phase 1                  139 lines
│   ├── parser.py         Phase 2                  160 lines
│   ├── ast_nodes.py      AST + tree printer       116 lines
│   ├── semantic.py       Phase 3                  127 lines
│   ├── symbol_table.py   Symbol table              60 lines
│   ├── errors.py         Error handler             68 lines
│   ├── icg.py            Phase 4                  149 lines
│   ├── optimizer.py      Phase 5                  190 lines
│   ├── codegen.py        Phase 6 + VM             204 lines
│   ├── simulator.py      Phase 7                   70 lines
│   ├── circuit.py        Graphviz export           40 lines
│   ├── compiler.py       Phase driver              69 lines
│   ├── main.py           Command line             154 lines
│   ├── web.py            Web server               208 lines
│   └── static/index.html Web interface
├── api/                  Vercel serverless functions
├── examples/             8 sample programs
└── tests/                20 unit, end-to-end and fuzz tests (204 lines)
```

The Python compiler is about 1,800 lines. With the web interface, tests and
API the project is about 3,000 lines.

## 9. Tools and Technologies

- **Python 3.8+**, standard library only. No third-party packages.
- **HTML, CSS and JavaScript** for the web interface (no frameworks).
- **Vercel** for public deployment.
- **Git and GitHub** for version control. The commit history follows the
  phases in order (setup → error handler → phase 1 → … → phase 7 → tests →
  web UI → deployment).
- **Claude Code** (Anthropic's AI coding assistant). We used it as a coding
  assistant, and it wrote much of the code following our instructions. Commits
  it helped write are marked `Co-Authored-By: Claude`. Our team chose the
  project scope and the language, asked for and reviewed every feature, tested
  it, and can explain and change every phase.

## 10. Limitations and Future Work

- **Combinational circuits only.** There are no flip-flops, clocks or
  sequential logic.
- **Single-bit signals.** Buses such as `a[3:0]` and multi-bit operations are
  not supported.
- **No modules.** A circuit cannot be defined once and used as a component in
  another (for example, building a 4-bit adder from full adders).
- **Local optimisation only.** The optimiser applies rule-based Boolean laws.
  It does not find the minimum circuit, which would need Karnaugh maps or the
  Quine–McCluskey algorithm.
- **Exhaustive verification grows as 2ⁿ,** so the web interface limits truth
  tables to 12 inputs.

Possible extensions: modules, multi-bit buses, Quine–McCluskey minimisation,
and Verilog output so the circuits could run on real FPGA hardware.

## 11. Conclusion

We built a complete compiler that takes a logic-circuit description through
lexical, syntax and semantic analysis, intermediate code generation,
optimisation and target code generation, with a shared symbol table and error
handler. Because the source language is Boolean logic, we could add a
verification phase that proves every compiled program correct on all inputs,
and a fuzz test that checks this on random programs. The optimiser
measurably reduces circuits (12 gates to 1 in the demo), and the error handler
reports every error in a program in one run. The web interface makes each
phase visible step by step, which makes the project useful for learning how a
compiler works.

## 12. References

1. A. V. Aho, M. S. Lam, R. Sethi, J. D. Ullman, *Compilers: Principles,
   Techniques, and Tools*, 2nd ed., Pearson, 2006.
2. M. M. Mano, M. D. Ciletti, *Digital Design*, 5th ed., Pearson, 2013.
3. Python Software Foundation, *Python 3 Documentation*,
   <https://docs.python.org/3/>.
