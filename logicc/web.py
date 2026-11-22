"""
Web UI for the Logic Gate Compiler (no external libraries needed).

    python3 -m logicc.web            # opens http://127.0.0.1:8000 in the browser
    python3 -m logicc.web --port 9000 --no-browser

The browser page sends the source code to /api/compile; this server runs the
same compiler phases as the command-line tool and returns every phase's
output as JSON, which the page displays.
"""

import argparse
import json
import os
import threading
import webbrowser
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler

from .compiler import compile_source
from .ast_nodes import _label, _children
from .icg import triples_rows
from .optimizer import gate_count
from .simulator import simulate, minterms, MAX_INPUTS

HERE = os.path.dirname(os.path.abspath(__file__))
STATIC = os.path.join(HERE, "static")
EXAMPLES = os.path.join(os.path.dirname(HERE), "examples")
EXAMPLE_ORDER = ["simple", "half_adder", "full_adder", "mux2", "comparator",
                 "optimize_demo", "syntax_errors", "semantic_errors"]
MAX_SOURCE = 20_000          # bytes of request body (public deployment safety limit)

PHASE_NAMES = ["Lexical Analysis", "Syntax Analysis", "Semantic Analysis",
               "Intermediate Code", "Optimization", "Code Generation", "Execution"]


def _arg(x):
    return "" if x is None else x


def ast_to_dict(node):
    return {"label": _label(node), "children": [ast_to_dict(c) for c in _children(node)]}


def compile_to_json(source, optimize=True, regs=4):
    res = compile_source(source, optimize=optimize, num_regs=regs)
    diags = res.errors.diagnostics
    err_in = lambda phase: any(d.level == "error" and d.phase == phase for d in diags)

    out = {
        "ok": res.ok,
        "diagnostics": [{"level": d.level, "phase": d.phase, "message": d.message,
                         "line": d.line, "col": d.col} for d in diags],
        "tokens": [{"lexeme": t.lexeme, "type": t.type,
                    "attr": t.value if t.type in ("OP", "CONST") else "",
                    "line": t.line, "col": t.col} for t in res.tokens if t.type != "EOF"],
        "ast": None, "symtab": None, "inputs": [], "outputs": [],
        "tac": None, "quads": None, "triples": None, "temps": [],
        "opt_log": [], "optimized": None, "optimized_quads": None, "metrics": None,
        "asm": None, "spills": 0, "regs": regs, "optimize": optimize, "truth": None,
    }
    status = ["error" if err_in("Lexical") else "ok"]
    status.append("error" if err_in("Syntax") else "ok")

    if res.ast is not None:
        out["ast"] = ast_to_dict(res.ast)
    if res.sem is not None:
        rows = []
        for s in res.sem.symtab:
            kind = s.kind + (" (implicit)" if s.implicit else "")
            if s.kind == "wire" and s.is_output:
                kind = "output (implicit)"
            rows.append({"name": s.name, "kind": kind, "type": s.type, "declared": s.declared,
                         "assigned": s.assigned, "uses": s.uses})
        out.update(symtab=rows, inputs=res.sem.inputs, outputs=res.sem.outputs)
        status.append("error" if err_in("Semantic") else "ok")
    else:
        status.append("skipped")

    if res.tac is not None:
        out["tac"] = [str(q) for q in res.tac]
        out["quads"] = [[q.op, _arg(q.arg1), _arg(q.arg2), q.result] for q in res.tac]
        out["triples"] = triples_rows(res.tac, res.temps)
        out["temps"] = res.temps
        status.append("ok")
    else:
        status.append("skipped")

    if res.optimized is not None:
        out["opt_log"] = [{"round": r, "pass": p, "message": m} for r, p, m in res.opt_log]
        out["optimized"] = [str(q) for q in res.optimized]
        out["optimized_quads"] = [[q.op, _arg(q.arg1), _arg(q.arg2), q.result] for q in res.optimized]
        out["metrics"] = {"tac_before": len(res.tac), "tac_after": len(res.optimized),
                          "gates_before": gate_count(res.tac), "gates_after": gate_count(res.optimized)}
        status.append("ok")
    else:
        status.append("skipped")

    if res.asm is not None:
        out["asm"] = [{"op": i.op, "args": [str(a) for a in i.args], "comment": i.comment} for i in res.asm]
        out["spills"] = res.spills
        status.append("ok")
        if len(res.sem.inputs) <= MAX_INPUTS:
            rows, bad = simulate(res.ast, res.asm, res.sem.inputs, res.sem.outputs)
            out["truth"] = {"rows": [[list(i), list(o)] for i, o in rows],
                            "minterms": minterms(rows, res.sem.outputs),
                            "verified": not bad, "mismatches": len(bad)}
            status.append("ok" if not bad else "error")
        else:
            status.append("skipped")
    else:
        status += ["skipped", "skipped"]

    out["phases"] = [{"name": n, "status": s} for n, s in zip(PHASE_NAMES, status)]
    return out


def load_examples():
    found = {}
    if os.path.isdir(EXAMPLES):
        for f in os.listdir(EXAMPLES):
            if f.endswith(".lg"):
                with open(os.path.join(EXAMPLES, f), encoding="utf-8") as fh:
                    found[f[:-3]] = fh.read()
    names = [n for n in EXAMPLE_ORDER if n in found] + sorted(n for n in found if n not in EXAMPLE_ORDER)
    return [{"name": n, "source": found[n]} for n in names]


class JSONHandlerMixin:
    """Response helpers shared by the local server and the Vercel functions (api/*.py)."""

    def _send(self, code, body, ctype):
        data = body if isinstance(body, bytes) else body.encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(data)

    def _json(self, code, obj):
        self._send(code, json.dumps(obj), "application/json; charset=utf-8")

    def handle_compile(self):
        """Read a JSON body {source, optimize, regs}, compile it and reply with every phase as JSON."""
        try:
            length = int(self.headers.get("Content-Length", 0))
            if length > MAX_SOURCE:
                return self._json(413, {"error": f"program too large (limit {MAX_SOURCE // 1000} KB)"})
            req = json.loads(self.rfile.read(length) or b"{}")
            source = str(req.get("source", ""))
            regs = max(3, min(16, int(req.get("regs", 4))))
            self._json(200, compile_to_json(source, bool(req.get("optimize", True)), regs))
        except RecursionError:
            self._json(400, {"error": "expression is nested too deeply"})
        except Exception as e:      # never crash the server
            self._json(500, {"error": f"{type(e).__name__}: {e}"})

    def log_message(self, fmt, *args):
        pass


class Handler(JSONHandlerMixin, BaseHTTPRequestHandler):
    def do_GET(self):
        path = self.path.split("?")[0]
        if path in ("/", "/index.html"):
            with open(os.path.join(STATIC, "index.html"), "rb") as f:
                self._send(200, f.read(), "text/html; charset=utf-8")
        elif path == "/api/examples":
            self._json(200, load_examples())
        else:
            self._send(404, "not found", "text/plain")

    def do_POST(self):
        if self.path != "/api/compile":
            return self._send(404, "not found", "text/plain")
        self.handle_compile()


def main(argv=None):
    p = argparse.ArgumentParser(prog="logicc.web", description="Web UI for the Logic Gate Compiler")
    p.add_argument("--port", type=int, default=8000)
    p.add_argument("--no-browser", action="store_true")
    args = p.parse_args(argv)

    server = None
    for port in range(args.port, args.port + 20):
        try:
            server = ThreadingHTTPServer(("127.0.0.1", port), Handler)
            break
        except OSError:
            continue
    if server is None:
        raise SystemExit(f"no free port found in {args.port}-{args.port + 19}")

    url = f"http://127.0.0.1:{server.server_address[1]}/"
    print(f"Logic Gate Compiler UI running at  {url}\nPress Ctrl+C to stop.")
    if not args.no_browser:
        threading.Timer(0.6, lambda: webbrowser.open(url)).start()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopped.")
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
