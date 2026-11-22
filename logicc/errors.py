"""
Error Handler (cross-cutting component of the compiler)
=======================================================

Every phase reports problems here instead of crashing on the first one.
This lets the compiler show *all* errors in one run (like gcc / javac),
with the line, column and a caret (^) under the offending token.
"""

from . import ui


class Diagnostic:
    def __init__(self, level, phase, message, line=None, col=None):
        self.level = level      # "error" | "warning" | "note"
        self.phase = phase      # "Lexical" | "Syntax" | "Semantic" ...
        self.message = message
        self.line = line
        self.col = col

    def format(self, source_lines):
        color = {"error": ui.red, "warning": ui.yellow, "note": ui.cyan}[self.level]
        where = ""
        if self.line:
            where = f" (line {self.line}, col {self.col})" if self.col else f" (line {self.line})"
        out = [f"{color(self.level.upper())} [{self.phase}]{where}: {self.message}"]
        if self.line and 1 <= self.line <= len(source_lines):
            src = source_lines[self.line - 1]
            out.append(f"    {self.line:>3} | {src}")
            if self.col:
                out.append("        | " + " " * (self.col - 1) + color("^"))
        return "\n".join(out)

    def __repr__(self):
        return f"Diagnostic({self.level}, {self.phase}, {self.message!r}, {self.line}, {self.col})"


class ErrorHandler:
    def __init__(self, source=""):
        self.source_lines = source.splitlines()
        self.diagnostics = []

    def error(self, phase, message, line=None, col=None):
        self.diagnostics.append(Diagnostic("error", phase, message, line, col))

    def warning(self, phase, message, line=None, col=None):
        self.diagnostics.append(Diagnostic("warning", phase, message, line, col))

    def note(self, phase, message, line=None, col=None):
        self.diagnostics.append(Diagnostic("note", phase, message, line, col))

    @property
    def errors(self):
        return [d for d in self.diagnostics if d.level == "error"]

    @property
    def warnings(self):
        return [d for d in self.diagnostics if d.level == "warning"]

    def has_errors(self):
        return bool(self.errors)

    def report(self):
        if not self.diagnostics:
            return ui.green("No errors, no warnings.")
        lines = [d.format(self.source_lines) for d in self.diagnostics]
        lines.append(f"\n{len(self.errors)} error(s), {len(self.warnings)} warning(s)")
        return "\n".join(lines)
