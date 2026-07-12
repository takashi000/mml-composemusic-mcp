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
    TIE_CMD = auto()  # ^ (ppmck tie)
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
    AT = auto()
    TRANSPOSE = auto()
    DETUNE = auto()  # D (ppmck detune)
    SWEEP = auto()  # s (ppmck sweep)
    QUANTIZE = auto()  # q (ppmck quantize)
    REL_VOL_UP = auto()  # v+ (ppmck)
    REL_VOL_DOWN = auto()  # v- (ppmck)
    DUTY_ENV_USE = auto()  # @@ (ppmck)
    VOL_ENV = auto()  # @v (ppmck)
    LFO_DEF = auto()  # @MP (ppmck)
    LFO_USE = auto()  # MP (ppmck)
    LFO_OFF = auto()  # MPOF (ppmck)
    PITCH_ENV_DEF = auto()  # @EP (ppmck)
    PITCH_ENV_USE = auto()  # EP (ppmck)
    PITCH_ENV_OFF = auto()  # EPOF (ppmck)
    NOTE_ENV_DEF = auto()  # @EN (ppmck)
    NOTE_ENV_USE = auto()  # EN (ppmck)
    NOTE_ENV_OFF = auto()  # ENOF (ppmck)
    BRACE_OPEN = auto()  # { (ppmck envelope def)
    BRACE_CLOSE = auto()  # } (ppmck envelope def)
    EQUAL = auto()  # = (ppmck envelope def)
    COMMA = auto()  # , (ppmck sweep/envelope def)
    EXT_CMD = auto()  # @ENV, @VIB, @GLI
    INVALID = auto()  # unrecognised character
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

    def _read_signed_number(self) -> str:
        sign = ""
        if self._peek() in "+-":
            sign = self._advance()
        number = self._read_number()
        return sign + number if number else sign

    def _read_until_newline(self) -> str:
        start = ""
        while self.pos < len(self.source) and self.source[self.pos] not in "\r\n":
            start += self._advance()
        return start

    def _at_line_start(self) -> bool:
        line_start = self.source.rfind("\n", 0, self.pos) + 1
        return not self.source[line_start : self.pos].strip()

    def _emit(self, ttype: TokenType, value: str, raw: str = "") -> None:
        self.tokens.append(
            Token(ttype, value, self.line, self.column - len(raw), raw or value)
        )

    def tokenize(self) -> list[Token]:
        while self.pos < len(self.source):
            self._skip_whitespace()
            if self.pos >= len(self.source):
                break
            ch = self._peek()
            if self.mode == "ppmck":
                self._tokenize_ppmck(ch)
            else:
                self._tokenize_pyxel(ch)
        self.tokens.append(Token(TokenType.EOF, "", self.line, self.column))
        return self.tokens

    def _tokenize_ppmck(self, ch: str) -> None:
        if ch == "\n":
            self._advance()
            return
        if ch == ";":
            raw = self._read_until_newline()
            self._emit(TokenType.COMMENT, raw, raw)
            return
        if ch == "#":
            if self._at_line_start():
                self._advance()
                raw = "#" + self._read_until_newline()
                self._emit(TokenType.HEADER, raw, raw)
            else:
                self._advance()
                self._emit(TokenType.SHARP, "#", "#")
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
        if ch == "^":
            self._advance()
            self._emit(TokenType.TIE_CMD, "^", "^")
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
        if ch == "{":
            self._advance()
            self._emit(TokenType.BRACE_OPEN, "{", "{")
            return
        if ch == "}":
            self._advance()
            self._emit(TokenType.BRACE_CLOSE, "}", "}")
            return
        if ch == "=":
            self._advance()
            self._emit(TokenType.EQUAL, "=", "=")
            return
        if ch == ",":
            self._advance()
            self._emit(TokenType.COMMA, ",", ",")
            return
        if ch == ".":
            self._advance()
            self._emit(TokenType.DOT, ".", ".")
            return
        if ch == "+":
            self._advance()
            self._emit(TokenType.SHARP, "+", "+")
            return
        if ch == "#":
            self._advance()
            self._emit(TokenType.SHARP, "#", "#")
            return
        if ch == "-":
            self._advance()
            self._emit(TokenType.FLAT, "-", "-")
            return
        if ch == "@":
            self._advance()
            next_ch = self._peek()
            if next_ch == "@":
                self._advance()
                num = self._read_number()
                self._emit(TokenType.DUTY_ENV_USE, num, "@@" + num)
                return
            if next_ch == "v":
                self._advance()
                num = self._read_number()
                self._emit(TokenType.VOL_ENV, num, "@v" + num)
                return
            if next_ch == "M" and self._peek(1) == "P":
                self._advance()
                self._advance()
                num = self._read_number()
                self._emit(TokenType.LFO_DEF, num, "@MP" + num)
                return
            if next_ch == "E" and self._peek(1) == "P":
                self._advance()
                self._advance()
                num = self._read_number()
                self._emit(TokenType.PITCH_ENV_DEF, num, "@EP" + num)
                return
            if next_ch == "E" and self._peek(1) == "N":
                self._advance()
                self._advance()
                num = self._read_number()
                self._emit(TokenType.NOTE_ENV_DEF, num, "@EN" + num)
                return
            num = self._read_number()
            self._emit(TokenType.DUTY, num, "@" + num)
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
            # 2-character commands: MP, EP, EN and their OFF variants
            if ch == "M" and self._peek(1) == "P":
                self._advance()
                self._advance()
                if self._peek() == "O" and self._peek(1) == "F":
                    self._advance()
                    self._advance()
                    self._emit(TokenType.LFO_OFF, "MPOF", "MPOF")
                else:
                    num = self._read_number()
                    self._emit(TokenType.LFO_USE, num, "MP" + num)
                return
            if ch == "E" and self._peek(1) == "P":
                self._advance()
                self._advance()
                if self._peek() == "O" and self._peek(1) == "F":
                    self._advance()
                    self._advance()
                    self._emit(TokenType.PITCH_ENV_OFF, "EPOF", "EPOF")
                else:
                    num = self._read_number()
                    self._emit(TokenType.PITCH_ENV_USE, num, "EP" + num)
                return
            if ch == "E" and self._peek(1) == "N":
                self._advance()
                self._advance()
                if self._peek() == "O" and self._peek(1) == "F":
                    self._advance()
                    self._advance()
                    self._emit(TokenType.NOTE_ENV_OFF, "ENOF", "ENOF")
                else:
                    num = self._read_number()
                    self._emit(TokenType.NOTE_ENV_USE, num, "EN" + num)
                return

            cmd = self._advance()
            lower = cmd.lower()
            if lower in "olvt":
                if lower == "v" and self._peek() in "+-":
                    sign = self._advance()
                    num = self._read_number()
                    raw = cmd + sign + num
                    if sign == "+":
                        self._emit(TokenType.REL_VOL_UP, num, raw)
                    else:
                        self._emit(TokenType.REL_VOL_DOWN, num, raw)
                    return
                num = self._read_number()
                raw = cmd + num
                if lower == "o":
                    self._emit(TokenType.OCTAVE, num, raw)
                elif lower == "l":
                    self._emit(TokenType.LENGTH, num, raw)
                elif lower == "v":
                    self._emit(TokenType.VOLUME, num, raw)
                elif lower == "t":
                    self._emit(TokenType.TEMPO, num, raw)
                return
            if lower == "q":
                num = self._read_number()
                self._emit(TokenType.QUANTIZE, num, "q" + num)
                return
            if cmd == "D":
                num = self._read_signed_number()
                self._emit(TokenType.DETUNE, num, "D" + num)
                return
            if lower == "s":
                num0 = self._read_number()
                if self._peek() == ",":
                    self._advance()
                num1 = self._read_signed_number()
                raw = f"s{num0},{num1}"
                self._emit(TokenType.SWEEP, f"{num0},{num1}", raw)
                return
            note = lower
            if note in "cdefgabr":
                if note == "r":
                    self._emit(TokenType.REST, note, note)
                else:
                    self._emit(TokenType.NOTE, note, note)
                return
            # Unknown command: emit as invalid token for parser to report
            self._emit(TokenType.INVALID, cmd, cmd)
            return
        # Fallback invalid char
        raw = self._advance()
        self._emit(TokenType.INVALID, raw, raw)

    def _tokenize_pyxel(self, ch: str) -> None:
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
        if ch == "#":
            self._advance()
            self._emit(TokenType.SHARP, "#", "#")
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
                num = self._read_signed_number() if cmd in "KY" else self._read_number()
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
            self._emit(TokenType.INVALID, cmd, cmd)
            return
        # Fallback invalid char
        raw = self._advance()
        self._emit(TokenType.INVALID, raw, raw)


def tokenize(source: str, mode: str = "ppmck") -> list[Token]:
    return Lexer(source, mode).tokenize()


def iter_token_text(tokens: Iterable[Token]) -> str:
    return " ".join(f"{t.type.name}:{t.value}" for t in tokens)
