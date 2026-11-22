"""
PHASE 1 — LEXICAL ANALYSIS (Scanner)
====================================

Reads the source program character by character and groups the characters
into *tokens* (lexemes with a category). Whitespace and comments are removed.

Token types
-----------
  INPUT, OUTPUT     keywords                 input a, b;
  IDENT             identifier               [A-Za-z_][A-Za-z0-9_]*
  CONST             boolean constant         0 1 true false
  OP                gate operator            AND OR NOT XOR NAND NOR XNOR  & | ^ ! ~
  ASSIGN            =
  SEMI  COMMA       ;  ,
  LPAREN RPAREN     (  )
  EOF               end of input

Keywords and gate names are case-insensitive (AND == and == And).
Comments: `# ...`, `// ...` and `/* ... */`.
"""

from dataclasses import dataclass

KEYWORDS = {"input": "INPUT", "output": "OUTPUT"}
GATES = {"AND", "OR", "NOT", "XOR", "NAND", "NOR", "XNOR"}
BOOL_WORDS = {"true": 1, "false": 0}
OP_SYMBOLS = {"&": "AND", "|": "OR", "^": "XOR", "!": "NOT", "~": "NOT"}
PUNCT = {"=": "ASSIGN", ";": "SEMI", ",": "COMMA", "(": "LPAREN", ")": "RPAREN"}


@dataclass
class Token:
    type: str
    value: object   # gate name for OP, int for CONST, text otherwise
    lexeme: str     # exact text from the source
    line: int
    col: int

    def describe(self):
        if self.type == "EOF":
            return "end of file"
        return f"'{self.lexeme}'"


class Lexer:
    PHASE = "Lexical"

    def __init__(self, source, errors):
        self.src = source
        self.errors = errors
        self.i = 0
        self.line = 1
        self.col = 1

    # -- character helpers -------------------------------------------------
    def _peek(self, k=0):
        j = self.i + k
        return self.src[j] if j < len(self.src) else ""

    def _advance(self):
        ch = self.src[self.i]
        self.i += 1
        if ch == "\n":
            self.line += 1
            self.col = 1
        else:
            self.col += 1
        return ch

    # -- main loop -----------------------------------------------------------
    def tokenize(self):
        tokens = []
        while self.i < len(self.src):
            ch = self._peek()
            line, col = self.line, self.col

            if ch.isspace():
                self._advance()
            elif ch == "#" or (ch == "/" and self._peek(1) == "/"):
                while self.i < len(self.src) and self._peek() != "\n":
                    self._advance()
            elif ch == "/" and self._peek(1) == "*":
                self._advance(); self._advance()
                while self.i < len(self.src) and not (self._peek() == "*" and self._peek(1) == "/"):
                    self._advance()
                if self.i >= len(self.src):
                    self.errors.error(self.PHASE, "unterminated block comment '/*'", line, col)
                else:
                    self._advance(); self._advance()
            elif ch.isalpha() or ch == "_":
                tokens.append(self._word(line, col))
            elif ch.isdigit():
                tok = self._number(line, col)
                if tok:
                    tokens.append(tok)
            elif ch in OP_SYMBOLS:
                self._advance()
                tokens.append(Token("OP", OP_SYMBOLS[ch], ch, line, col))
            elif ch in PUNCT:
                self._advance()
                tokens.append(Token(PUNCT[ch], ch, ch, line, col))
            else:
                self._advance()
                self.errors.error(self.PHASE, f"unexpected character '{ch}'", line, col)

        tokens.append(Token("EOF", None, "", self.line, self.col))
        return tokens

    def _word(self, line, col):
        start = self.i
        while self.i < len(self.src) and (self._peek().isalnum() or self._peek() == "_"):
            self._advance()
        word = self.src[start:self.i]
        low, up = word.lower(), word.upper()
        if low in KEYWORDS:
            return Token(KEYWORDS[low], low, word, line, col)
        if up in GATES:
            return Token("OP", up, word, line, col)
        if low in BOOL_WORDS:
            return Token("CONST", BOOL_WORDS[low], word, line, col)
        return Token("IDENT", word, word, line, col)

    def _number(self, line, col):
        start = self.i
        while self.i < len(self.src) and (self._peek().isalnum() or self._peek() == "_"):
            self._advance()
        text = self.src[start:self.i]
        if text in ("0", "1"):
            return Token("CONST", int(text), text, line, col)
        if text.isdigit():
            self.errors.error(self.PHASE, f"invalid constant '{text}' (only 0 and 1 are allowed)", line, col)
        else:
            self.errors.error(self.PHASE, f"invalid identifier '{text}' (identifiers cannot start with a digit)", line, col)
        return None


def tokenize(source, errors):
    return Lexer(source, errors).tokenize()
