"""PPMCK-style MML parser: tokens -> AST."""

from .ast_nodes import (
    ASTNode,
    BarStmt,
    DutyStmt,
    Header,
    LengthStmt,
    NoteStmt,
    OctaveStmt,
    Program,
    RepeatEndStmt,
    RepeatStartStmt,
    RestStmt,
    TempoStmt,
    TieStmt,
    Track,
    VolumeStmt,
)
from .ir import ErrorCode, ErrorDetail
from .lexer import Token, TokenType
from .parser_base import ParserContext, context_line

CHANNEL_MAP = {
    "A": "Pulse1",
    "B": "Pulse2",
    "T": "Triangle",
    "N": "Noise",
}


class PpmckParser:
    def __init__(self, source: str, tokens: list[Token]) -> None:
        self.source = source
        self.ctx = ParserContext(tokens)
        self.tracks_seen: set[str] = set()

    def parse(self) -> tuple[Program, list[ErrorDetail]]:
        program = Program(line=1, column=1, tracks=[])
        headers: list[Header] = []

        while self.ctx.peek().type != TokenType.EOF:
            token = self.ctx.peek()
            if token.type == TokenType.HEADER:
                headers.append(self._parse_header())
                continue
            if token.type == TokenType.COMMENT:
                self.ctx.advance()
                continue
            if token.type == TokenType.TRACK_HEADER:
                track = self._parse_track()
                if track is not None:
                    track.headers = list(headers)
                    program.tracks.append(track)
                continue
            if token.type == TokenType.INVALID:
                self._handle_invalid(token)
                continue
            # Anything else before a track header is outside a track.
            self._warn_outside_track(token)
            self.ctx.advance()

        # Attach headers to the first track if no track exists yet
        if headers and not program.tracks:
            pass  # headers are simply discarded if no tracks
        elif headers and program.tracks:
            # Headers already attached to first parsed track; nothing to do
            pass

        return program, self.ctx.errors

    def _parse_header(self) -> Header:
        token = self.ctx.advance()
        raw = token.value
        parts = raw.split(None, 1)
        key = parts[0] if parts else raw
        value = ""
        unterminated = False
        if len(parts) > 1:
            rest = parts[1]
            if rest.startswith('"'):
                if not rest.endswith('"') or rest == '"':
                    unterminated = True
                    value = rest[1:]
                    self.ctx.add_error(
                        code=ErrorCode.SYNTAX_UNTERMINATED_HEADER,
                        line=token.line,
                        column=token.column,
                        message=f"ヘッダー '{key}' の引用符が閉じられていません。",
                        severity="error",
                        hint='二重引用符 " で値を閉じてください。例: #TITLE "My Song"',
                        context=context_line(self.source, token),
                    )
                else:
                    value = rest[1:-1]
            else:
                value = rest
        return Header(
            line=token.line,
            column=token.column,
            key=key,
            value=value,
            unterminated=unterminated,
        )

    def _parse_track(self) -> Track | None:
        token = self.ctx.advance()
        ch = token.value.upper()
        if ch == "L":
            return Track(
                line=token.line,
                column=token.column,
                track_id="L",
                channel="Loop",
                mode="ppmck",
                statements=[],
            )
        if ch not in CHANNEL_MAP:
            self.ctx.add_error(
                code=ErrorCode.SYNTAX_INVALID_TRACK_HEADER,
                line=token.line,
                column=token.column,
                message=f"無効なトラックヘッダー '{ch}' です。",
                severity="error",
                hint="A, B, T, N, L のいずれかを使用してください。",
                context=context_line(self.source, token),
            )
            return None
        channel = CHANNEL_MAP[ch]
        if channel in self.tracks_seen:
            self.ctx.add_error(
                code=ErrorCode.SYNTAX_DUPLICATE_TRACK,
                line=token.line,
                column=token.column,
                message=f"トラック '{ch}' が複数回定義されています。",
                severity="error",
                hint="各トラックは1回のみ定義できます。重複定義を削除してください。",
                context=context_line(self.source, token),
            )
        self.tracks_seen.add(channel)
        track = Track(
            line=token.line,
            column=token.column,
            track_id=ch,
            channel=channel,
            mode="ppmck",
            statements=[],
        )
        while self.ctx.peek().type not in (
            TokenType.TRACK_HEADER,
            TokenType.EOF,
        ):
            stmt = self._parse_statement()
            if stmt is not None:
                track.statements.append(stmt)
        return track

    def _parse_statement(self) -> ASTNode | None:
        token = self.ctx.peek()
        if token.type == TokenType.INVALID:
            self._handle_invalid(token)
            return None
        if token.type == TokenType.COMMENT:
            self.ctx.advance()
            return None
        if token.type == TokenType.NOTE:
            return self._parse_note()
        if token.type == TokenType.REST:
            return self._parse_rest()
        if token.type == TokenType.OCTAVE:
            return self._parse_octave()
        if token.type == TokenType.OCTAVE_UP:
            return self._parse_octave_up()
        if token.type == TokenType.OCTAVE_DOWN:
            return self._parse_octave_down()
        if token.type == TokenType.LENGTH:
            return self._parse_length()
        if token.type == TokenType.VOLUME:
            return self._parse_volume()
        if token.type == TokenType.DUTY:
            return self._parse_duty()
        if token.type == TokenType.TEMPO:
            return self._parse_tempo()
        if token.type == TokenType.TIE:
            return self._parse_tie()
        if token.type == TokenType.REPEAT_START:
            return self._parse_repeat_start()
        if token.type == TokenType.REPEAT_END:
            return self._parse_repeat_end()
        if token.type == TokenType.BAR:
            self.ctx.advance()
            return BarStmt(line=token.line, column=token.column)
        # Unknown token in track context
        self.ctx.add_error(
            code=ErrorCode.SYNTAX_UNEXPECTED_TOKEN,
            line=token.line,
            column=token.column,
            message=f"'{token.raw}' はここでは使用できません。",
            severity="error",
            hint="音符、休符、コマンド、小節線を配置してください。",
            context=context_line(self.source, token),
        )
        self.ctx.advance()
        return None

    def _read_length(self, token: Token) -> tuple[int | None, int]:
        length_token = self.ctx.match(TokenType.NUMBER)
        length: int | None = None
        if length_token is not None:
            length = int(length_token.value)
        dots = 0
        while self.ctx.match(TokenType.DOT):
            dots += 1
        return length, dots

    def _parse_note(self) -> NoteStmt:
        token = self.ctx.advance()
        length, dots = self._read_length(token)
        accidental = 0
        while True:
            if self.ctx.match(TokenType.SHARP):
                accidental += 1
            elif self.ctx.match(TokenType.FLAT):
                accidental -= 1
            else:
                break
        return NoteStmt(
            line=token.line,
            column=token.column,
            note_name=token.value.lower(),
            accidental=accidental,
            length=length,
            dots=dots,
        )

    def _parse_rest(self) -> RestStmt:
        token = self.ctx.advance()
        length, dots = self._read_length(token)
        return RestStmt(
            line=token.line,
            column=token.column,
            length=length,
            dots=dots,
        )

    def _parse_octave(self) -> OctaveStmt:
        token = self.ctx.advance()
        value = int(token.value) if token.value else 4
        return OctaveStmt(
            line=token.line,
            column=token.column,
            value=value,
            direction=None,
        )

    def _parse_octave_up(self) -> OctaveStmt:
        token = self.ctx.advance()
        return OctaveStmt(
            line=token.line,
            column=token.column,
            value=None,
            direction="up",
        )

    def _parse_octave_down(self) -> OctaveStmt:
        token = self.ctx.advance()
        return OctaveStmt(
            line=token.line,
            column=token.column,
            value=None,
            direction="down",
        )

    def _parse_length(self) -> LengthStmt:
        token = self.ctx.advance()
        value = int(token.value) if token.value else 4
        return LengthStmt(
            line=token.line,
            column=token.column,
            value=value,
        )

    def _parse_volume(self) -> VolumeStmt:
        token = self.ctx.advance()
        value = int(token.value) if token.value else 0
        return VolumeStmt(
            line=token.line,
            column=token.column,
            value=value,
        )

    def _parse_duty(self) -> DutyStmt:
        token = self.ctx.advance()
        value = int(token.value) if token.value else 0
        return DutyStmt(
            line=token.line,
            column=token.column,
            value=value,
        )

    def _parse_tempo(self) -> TempoStmt:
        token = self.ctx.advance()
        value = int(token.value) if token.value else 120
        return TempoStmt(
            line=token.line,
            column=token.column,
            value=value,
        )

    def _parse_tie(self) -> TieStmt:
        token = self.ctx.advance()
        next_token = self.ctx.peek()
        if next_token.type == TokenType.NUMBER:
            self.ctx.advance()
            return TieStmt(
                line=token.line,
                column=token.column,
                target=int(next_token.value),
            )
        if next_token.type == TokenType.NOTE:
            return TieStmt(
                line=token.line,
                column=token.column,
                target=self._parse_note(),
            )
        if next_token.type == TokenType.REST:
            return TieStmt(
                line=token.line,
                column=token.column,
                target=self._parse_rest(),
            )
        self.ctx.add_error(
            code=ErrorCode.SYNTAX_UNTERMINATED_TIE,
            line=token.line,
            column=token.column,
            message="タイ '&' の後に音符が見つかりません。",
            severity="error",
            hint="& の後に音符（例: c4）を続けてください。音長のみ（例: &16）も可能です。",
            context=context_line(self.source, token),
        )
        return TieStmt(line=token.line, column=token.column, target=None)

    def _parse_repeat_start(self) -> RepeatStartStmt:
        token = self.ctx.advance()
        return RepeatStartStmt(line=token.line, column=token.column)

    def _parse_repeat_end(self) -> RepeatEndStmt:
        token = self.ctx.advance()
        count: int | None = None
        if token.value:
            count = int(token.value)
        return RepeatEndStmt(
            line=token.line,
            column=token.column,
            count=count,
        )

    def _handle_invalid(self, token: Token) -> None:
        self.ctx.add_invalid_token_error(token, context_line(self.source, token))
        self.ctx.advance()

    def _warn_outside_track(self, token: Token) -> None:
        if token.type in (TokenType.EOF, TokenType.COMMENT):
            return
        self.ctx.add_error(
            code=ErrorCode.SEMANTIC_OUTSIDE_TRACK,
            line=token.line,
            column=token.column,
            message=f"'{token.raw}' はトラック外に書かれています。",
            severity="warning",
            hint="コマンドはトラックヘッダー（A, B, T, N）の後に記述してください。",
            context=context_line(self.source, token),
        )


def parse_ppmck(
    source: str, tokens: list[Token]
) -> tuple[Program, list[ErrorDetail]]:
    parser = PpmckParser(source, tokens)
    return parser.parse()
