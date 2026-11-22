"""Small terminal helpers: colours, section headers and ASCII tables."""

import sys

USE_COLOR = sys.stdout.isatty()


def _c(code):
    def wrap(text):
        text = str(text)
        return f"\033[{code}m{text}\033[0m" if USE_COLOR else text
    return wrap


red = _c("1;31")
green = _c("1;32")
yellow = _c("1;33")
blue = _c("1;34")
cyan = _c("36")
bold = _c("1")
dim = _c("2")


def header(title):
    line = "=" * 70
    return f"\n{blue(line)}\n{blue(title)}\n{blue(line)}"


def table(headers, rows):
    rows = [[str(c) for c in r] for r in rows]
    widths = [len(h) for h in headers]
    for r in rows:
        for i, c in enumerate(r):
            widths[i] = max(widths[i], len(c))
    sep = "+" + "+".join("-" * (w + 2) for w in widths) + "+"
    fmt = lambda r: "| " + " | ".join(c.ljust(w) for c, w in zip(r, widths)) + " |"
    out = [sep, fmt(headers), sep.replace("-", "=")]
    out += [fmt(r) for r in rows]
    out.append(sep)
    return "\n".join(out)
