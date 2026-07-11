"""Common lexer for MML."""

from collections.abc import Iterable
from dataclasses import dataclass
from enum import Enum, auto


class TokenType(Enum):
    NOTE = auto()
    REST = auto()
    OCTAVE = auto()
    OCTAVE_UP = auto()
    OCTAVE_DOWN = auto()
    LENGTH = auto()
    VOLUME = auto()
    DUTY = auto()
    TEMPO = auto()
    GATE_TIME = auto()
    TIE = auto()
    REPEAT_START = auto()
    REPEAT_END = auto()
    BAR = auto()
    TRACK_HEADER = auto()
    HEADER = auto()
    COMMENT = auto()
    NUMBER = auto()
    SHARP = auto()
    FLAT = auto()
    DOT = auto()
    TEXT = auto()
    AT = auto()
    TRANSPOSE = auto()
    DETUNE = auto()
    EXT_CMD = auto()  # @ENV, @VIB, @GLI
    EOF = auto()


@dataclass
class Token:
    type: TokenType
    value: str
    line: int
    column: int
    raw: str = ""


def _track_header_char(ch: str) -> bool:
    return ch.isupper() and ch in "ABTNL"


class Lexer:
    def __init__(self, source: str, mode: str = "ppmck") -> None:
        self.source = source
        self.mode = mode.lower()
        self.tokens: list[Token] = []
        self.line = 1
        self.column = 1
        self.pos = 0

    def _peek(self, offset: int = 0) -> str:
        idx = self.pos + offset
        if idx >= len(self.source):
            return ""
        return self.source[idx]

    def _advance(self) -> str:
        ch = self.source[self.pos]
        self.pos += 1
        if ch == "\n":
            self.line += 1
            self.column = 1
        else:
            self.column += 1
        return ch

    def _skip_whitespace(self) -> None:
        while self.pos < len(self.source) and self.source[self.pos] in " \t\r":
            self._advance()

    def _read_number(self) -> str:
        start = ""
        while self.pos < len(self.source) and self.source[self.pos].isdigit():
            start += self._advance()
        return start

    def _read_until_newline(self) -> str:
        start = ""
        while self.pos < len(self.source) and self.source[self.pos] not in "\r\n":
            start += self._advance()
        return start

    def _read_header_value(self) -> str:
        value = ""
        if self._peek() == '"':
            self._advance()
            while self.pos < len(self.source) and self._peek() not in '"\r\n':
                value += self._advance()
            if self._peek() == '"':
                self._advance()
            else:
                # Return raw unterminated header; parser reports error
                pass
        return value

    def tokenize(self) -> list[Token]:
        while self.pos < len(self.source):
            self._skip_whitespace()
            if self.pos >= len(self.source):
                break
            ch = self._peek()
            start_line = self.line
            start_col = self.column

            if self.mode == "ppmck":
                self._tokenize_ppmck(ch, start_line, start_col)
            else:
                self._tokenize_pyxel(ch, start_line, start_col)
        self.tokens.append(Token(TokenType.EOF, "", self.line, self.column))
        return self.tokens

    def _emit(self, ttype: TokenType, value: str, raw: str = "") -> None:
        self.tokens.append(
            Token(ttype, value, self.line, self.column - len(raw), raw or value)
        )

    def _tokenize_ppmck(self, ch: str, start_line: int, start_col: int) -> None:  # noqa: ARG002
        if ch == "\n":
            self._advance()
            return
        if ch == ";":
            raw = self._read_until_newline()
            self._emit(TokenType.COMMENT, raw, raw)
            return
        if ch == "#":
            raw = "#" + self._read_until_newline()
            self._emit(TokenType.HEADER, raw, raw)
            return
        if ch == "|":
            self._advance()
            self._emit(TokenType.BAR, "|", "|")
            return
        if ch == ">":
            self._advance()
            self._emit(TokenType.OCTAVE_UP, ">", ">")
            return
        if ch == "<":
            self._advance()
            self._emit(TokenType.OCTAVE_DOWN, "<", "<")
            return
        if ch == "&":
            self._advance()
            self._emit(TokenType.TIE, "&", "&")
            return
        if ch == "[":
            self._advance()
            self._emit(TokenType.REPEAT_START, "[", "[")
            return
        if ch == "]":
            self._advance()
            count = self._read_number()
            self._emit(TokenType.REPEAT_END, count, "]" + count)
            return
        if ch == ".":
            self._advance()
            self._emit(TokenType.DOT, ".", ".")
            return
        if ch == "+":
            self._advance()
            self._emit(TokenType.SHARP, "+", "+")
            return
        if ch == "-":
            self._advance()
            self._emit(TokenType.FLAT, "-", "-")
            return
        if ch.isdigit():
            num = self._read_number()
            self._emit(TokenType.NUMBER, num, num)
            return
        if _track_header_char(ch):
            raw = self._advance()
            self._emit(TokenType.TRACK_HEADER, raw.upper(), raw)
            return
        if ch.isalpha():
            cmd = self._advance()
            if ch in "olvtq":
                num = self._read_number()
                raw = cmd + num
                if ch == "o":
                    self._emit(TokenType.OCTAVE, num, raw)
                elif ch == "l":
                    self._emit(TokenType.LENGTH, num, raw)
                elif ch == "v":
                    self._emit(TokenType.VOLUME, num, raw)
                elif ch == "t":
                    self._emit(TokenType.TEMPO, num, raw)
                elif ch == "q":
                    self._emit(TokenType.DUTY, num, raw)
                return
            # Note commands
            note = ch.lower()
            if note in "cdefgabr":
                if note == "r":
                    self._emit(TokenType.REST, note, note)
                else:
                    self._emit(TokenType.NOTE, note, note)
                return
            # Unknown command
            self._emit(TokenType.TEXT, cmd, cmd)
            return
        # Fallback invalid char
        raw = self._advance()
        self._emit(TokenType.TEXT, raw, raw)

    def _tokenize_pyxel(self, ch: str, start_line: int, start_col: int) -> None:  # noqa: ARG002
        if ch == "\n":
            self._advance()
            return
        if ch == "|":
            self._advance()
            self._emit(TokenType.BAR, "|", "|")
            return
        if ch == ">":
            self._advance()
            self._emit(TokenType.OCTAVE_UP, ">", ">")
            return
        if ch == "<":
            self._advance()
            self._emit(TokenType.OCTAVE_DOWN, "<", "<")
            return
        if ch == "&":
            self._advance()
            self._emit(TokenType.TIE, "&", "&")
            return
        if ch == "[":
            self._advance()
            self._emit(TokenType.REPEAT_START, "[", "[")
            return
        if ch == "]":
            self._advance()
            count = self._read_number()
            self._emit(TokenType.REPEAT_END, count, "]" + count)
            return
        if ch == ".":
            self._advance()
            self._emit(TokenType.DOT, ".", ".")
            return
        if ch == "+":
            self._advance()
            self._emit(TokenType.SHARP, "+", "+")
            return
        if ch == "-":
            self._advance()
            self._emit(TokenType.FLAT, "-", "-")
            return
        if ch.isdigit():
            num = self._read_number()
            if self._peek() == ":":
                self._advance()
                self._emit(TokenType.TRACK_HEADER, num, num + ":")
            else:
                self._emit(TokenType.NUMBER, num, num)
            return
        if ch == "@":
            self._advance()
            if self.source[self.pos : self.pos + 3].upper() in ("ENV", "VIB", "GLI"):
                ext = self.source[self.pos : self.pos + 3].upper()
                self.pos += 3
                self.column += 3
                raw = "@" + ext
                self._emit(TokenType.EXT_CMD, ext, raw)
                return
            num = self._read_number()
            self._emit(TokenType.AT, num, "@" + num)
            return
        if ch.isalpha():
            cmd = self._advance()
            if cmd in "OLVTQKY":
                num = self._read_number()
                raw = cmd + num
                if cmd == "O":
                    self._emit(TokenType.OCTAVE, num, raw)
                elif cmd == "L":
                    self._emit(TokenType.LENGTH, num, raw)
                elif cmd == "V":
                    self._emit(TokenType.VOLUME, num, raw)
                elif cmd == "T":
                    self._emit(TokenType.TEMPO, num, raw)
                elif cmd == "Q":
                    self._emit(TokenType.GATE_TIME, num, raw)
                elif cmd == "K":
                    self._emit(TokenType.TRANSPOSE, num, raw)
                elif cmd == "Y":
                    self._emit(TokenType.DETUNE, num, raw)
                return
            note = cmd.upper()
            if note in "CDEFGABR":
                if note == "R":
                    self._emit(TokenType.REST, note, note)
                else:
                    self._emit(TokenType.NOTE, note, note)
                return
            self._emit(TokenType.TEXT, cmd, cmd)
            return
        # Fallback
        raw = self._advance()
        self._emit(TokenType.TEXT, raw, raw)


def tokenize(source: str, mode: str = "ppmck") -> list[Token]:
    return Lexer(source, mode).tokenize()


def iter_token_text(tokens: Iterable[Token]) -> str:
    return " ".join(f"{t.type.name}:{t.value}" for t in tokens)
