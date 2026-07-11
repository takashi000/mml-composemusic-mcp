"""Base parser utilities shared between ppmck and pyxel parsers."""

from dataclasses import dataclass

from .ir import ErrorCode, ErrorDetail
from .lexer import Token, TokenType


@dataclass
class ParserContext:
    tokens: list[Token]
    pos: int = 0
    errors: list[ErrorDetail] = None  # type: ignore[assignment]

    def __post_init__(self) -> None:
        if self.errors is None:
            self.errors = []

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
        self.errors.append(
            ErrorDetail(
                code=code,
                line=line,
                column=column,
                message=message,
                severity=severity,
                hint=hint,
                context=context,
            )
        )


class ParserError(Exception):
    pass


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
