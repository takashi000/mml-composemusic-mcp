"""Base parser utilities shared between ppmck and pyxel parsers."""

from dataclasses import dataclass, field

from .ast_nodes import ASTNode
from .ir import ErrorCode, ErrorDetail, ErrorPhase
from .lexer import Token, TokenType


@dataclass
class ParserContext:
    tokens: list[Token]
    pos: int = 0
    errors: list[ErrorDetail] = field(default_factory=list)

    def peek(self, offset: int = 0) -> Token:
        idx = self.pos + offset
        if idx >= len(self.tokens):
            return self.tokens[-1]
        return self.tokens[idx]

    def advance(self) -> Token:
        token = self.peek()
        self.pos += 1
        return token

    def match(self, *types: TokenType) -> Token | None:
        token = self.peek()
        if token.type in types:
            return self.advance()
        return None

    def expect(self, *types: TokenType) -> Token | None:
        return self.match(*types)

    def synchronize(self, *types: TokenType) -> None:
        """Advance to a recovery token without ever consuming past EOF."""
        while self.peek().type not in (*types, TokenType.EOF):
            self.advance()

    def add_error(
        self,
        code: ErrorCode,
        line: int,
        column: int,
        message: str,
        severity: str,
        hint: str = "",
        context: str = "",
    ) -> None:
        phase = _code_to_phase(code)
        self.errors.append(
            ErrorDetail(
                code=code,
                phase=phase,
                line=line,
                column=column,
                message=message,
                severity=severity,
                hint=hint,
                context=context,
            )
        )

    def add_invalid_token_error(self, token: Token, context: str = "") -> None:
        self.add_error(
            code=ErrorCode.SYNTAX_INVALID_TOKEN,
            line=token.line,
            column=token.column,
            message=f"無効な文字 '{token.raw}' が見つかりました。",
            severity="error",
            hint="MMLコマンド（c,d,e,f,g,a,b,r,o,l,v,t,q など）を使用してください。",
            context=context,
        )

    def add_missing_number_error(
        self, token: Token, command: str, context: str = ""
    ) -> None:
        self.add_error(
            code=ErrorCode.SYNTAX_INVALID_NUMBER,
            line=token.line,
            column=token.column,
            message=f"'{command}' の後に数値が必要です。",
            severity="error",
            hint=f"例: {command}4 のように数値を続けてください。",
            context=context,
        )


class ParserError(Exception):
    """Raised by parsers to abort a single statement and recover."""

    pass


def _code_to_phase(code: ErrorCode) -> ErrorPhase:
    if code.value.startswith("SYNTAX_"):
        return ErrorPhase.SYNTAX
    if code.value.startswith("SEMANTIC_"):
        return ErrorPhase.SEMANTIC
    if code.value.startswith("RUNTIME_"):
        return ErrorPhase.RUNTIME
    return ErrorPhase.API


def length_value_to_ticks(length: int, dots: int, ticks_per_quarter: int = 192) -> int:
    base = ticks_per_quarter * 4 // length
    total = base
    add = base
    for _ in range(dots):
        add //= 2
        total += add
    return total


NOTE_OFFSET = {
    "c": 0,
    "d": 2,
    "e": 4,
    "f": 5,
    "g": 7,
    "a": 9,
    "b": 11,
}


def note_to_midi(note: str, octave: int, accidental: int = 0) -> int:
    return (octave + 1) * 12 + NOTE_OFFSET[note] + accidental


def clamp(value: int, min_val: int, max_val: int) -> int:
    return max(min_val, min(value, max_val))


def context_line(source: str, node: ASTNode | Token) -> str:
    """Return the source line for a node or token."""
    lines = source.splitlines()
    line = getattr(node, "line", 1)
    if 1 <= line <= len(lines):
        return lines[line - 1]
    return ""
