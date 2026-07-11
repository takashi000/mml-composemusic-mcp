"""PPMCK-style MML parser."""

from .ir import (
    DutyEvent,
    ErrorCode,
    ErrorDetail,
    NoteEvent,
    NoteSequence,
    RepeatEvent,
    RestEvent,
    TempoEvent,
)
from .lexer import Token, TokenType
from .parser_base import (
    ParserContext,
    clamp,
    length_value_to_ticks,
    note_to_midi,
)

CHANNEL_MAP = {
    "A": "Pulse1",
    "B": "Pulse2",
    "T": "Triangle",
    "N": "Noise",
}
PULSE_CHANNELS = {"Pulse1", "Pulse2"}


class PpmckParser:
    def __init__(self, source: str, tokens: list[Token]) -> None:
        self.source = source
        self.ctx = ParserContext(tokens)
        self.note_sequence = NoteSequence()
        self.current_channel: str | None = None
        self.octave = 4
        self.default_length = 4
        self.velocity = 15
        self.duty = 2
        self.tick_position = 0
        self.headers: list[tuple[str, str]] = []
        self.loop_start: int | None = None
        self.tracks_seen: set[str] = set()
        self._tie_pending: bool = False

    def _context_line(self, token: Token) -> str:
        lines = self.source.splitlines()
        if 1 <= token.line <= len(lines):
            return lines[token.line - 1]
        return ""

    def parse(self) -> tuple[NoteSequence, list[ErrorDetail]]:
        while self.ctx.peek().type != TokenType.EOF:
            token = self.ctx.peek()
            if token.type == TokenType.HEADER:
                self._parse_header()
                continue
            if token.type == TokenType.COMMENT:
                self.ctx.advance()
                continue
            if token.type == TokenType.TRACK_HEADER:
                self._parse_track_header()
                continue
            if self.current_channel is None:
                self._warn_outside_track(token)
                self.ctx.advance()
                continue
            self._parse_statement()

        self._validate_tracks()

        if self.loop_start is not None:
            max_tick = max(
                ch.total_ticks for ch in self.note_sequence.channels.values()
            )
            for ch in self.note_sequence.channels.values():
                ch.events.append(
                    RepeatEvent(
                        start_tick=self.loop_start,
                        end_tick=max_tick,
                        repeat_count=0,
                    )
                )

        for ch in self.note_sequence.channels.values():
            ch.total_ticks = max(
                (e.tick_position + getattr(e, "duration", 0) for e in ch.events),
                default=0,
            )

        return self.note_sequence, self.ctx.errors

    def _parse_header(self) -> None:
        token = self.ctx.advance()
        raw = token.value
        parts = raw.split(None, 1)
        key = parts[0] if parts else raw
        value = ""
        if len(parts) > 1 and parts[1].startswith('"'):
            value = parts[1].strip('"')
            if not parts[1].endswith('"') or parts[1] == '"':
                self.ctx.add_error(
                    code=ErrorCode.SYNTAX_UNTERMINATED_HEADER,
                    line=token.line,
                    column=token.column,
                    message=f"ヘッダー '{key}' の引用符が閉じられていません。",
                    severity="error",
                    hint='二重引用符 " で値を閉じてください。例: #TITLE "My Song"',
                    context=self._context_line(token),
                )
        self.headers.append((key, value))

    def _warn_outside_track(self, token: Token) -> None:
        if token.type in (TokenType.EOF, TokenType.COMMENT):
            return
        self.ctx.add_error(
            code=ErrorCode.SYNTAX_OUTSIDE_TRACK,
            line=token.line,
            column=token.column,
            message=f"'{token.raw}' はトラック外に書かれています。",
            severity="warning",
            hint="コマンドはトラックヘッダー（A, B, T, N）の後に記述してください。",
            context=self._context_line(token),
        )

    def _parse_track_header(self) -> None:
        token = self.ctx.advance()
        ch = token.value.upper()
        if ch == "L":
            self.loop_start = 0
            return
        if ch not in CHANNEL_MAP:
            self.ctx.add_error(
                code=ErrorCode.SYNTAX_INVALID_TRACK_HEADER,
                line=token.line,
                column=token.column,
                message=f"無効なトラックヘッダー '{ch}' です。",
                severity="error",
                hint="A, B, T, N, L のいずれかを使用してください。",
                context=self._context_line(token),
            )
            self.current_channel = None
            return
        self.current_channel = CHANNEL_MAP[ch]
        if self.current_channel in self.tracks_seen:
            self.ctx.add_error(
                code=ErrorCode.SYNTAX_DUPLICATE_TRACK,
                line=token.line,
                column=token.column,
                message=f"トラック '{ch}' が複数回定義されています。",
                severity="error",
                hint="各トラックは1回のみ定義できます。重複定義を削除してください。",
                context=self._context_line(token),
            )
        self.tracks_seen.add(self.current_channel)
        self.octave = 4
        self.default_length = 4
        self.velocity = 15
        self.duty = 2
        self.tick_position = 0

    def _parse_statement(self) -> None:
        token = self.ctx.peek()
        handlers = {
            TokenType.NOTE: self._parse_note,
            TokenType.REST: self._parse_rest,
            TokenType.OCTAVE: self._parse_octave,
            TokenType.OCTAVE_UP: self._parse_octave_up,
            TokenType.OCTAVE_DOWN: self._parse_octave_down,
            TokenType.LENGTH: self._parse_length,
            TokenType.VOLUME: self._parse_volume,
            TokenType.DUTY: self._parse_duty,
            TokenType.TEMPO: self._parse_tempo,
            TokenType.TIE: self._parse_tie,
            TokenType.REPEAT_START: self._parse_repeat_start,
            TokenType.REPEAT_END: self._parse_repeat_end,
            TokenType.BAR: self._parse_bar,
            TokenType.COMMENT: lambda: self.ctx.advance(),
        }
        handler = handlers.get(token.type)
        if handler:
            handler()
        else:
            self.ctx.add_error(
                code=ErrorCode.SYNTAX_UNEXPECTED_TOKEN,
                line=token.line,
                column=token.column,
                message=f"'{token.raw}' はここでは使用できません。",
                severity="error",
                hint="音符、休符、コマンド、小節線を配置してください。",
                context=self._context_line(token),
            )
            self.ctx.advance()

    def _read_length(self) -> tuple[int, int]:
        dots = 0
        length_token = self.ctx.match(TokenType.NUMBER)
        if length_token is None:
            length = self.default_length
        else:
            length = int(length_token.value)
        while self.ctx.match(TokenType.DOT):
            dots += 1
        return length, dots

    def _parse_note(self) -> None:
        token = self.ctx.advance()
        note = token.value.lower()
        length, dots = self._read_length()
        ticks = length_value_to_ticks(length, dots)
        accidental = 0
        while True:
            if self.ctx.match(TokenType.SHARP):
                accidental += 1
            elif self.ctx.match(TokenType.FLAT):
                accidental -= 1
            else:
                break

        if self._tie_pending:
            # Tie: extend the last note/rest's duration instead of creating a new event
            self._extend_last_note(ticks)
            self.tick_position += ticks
            self._tie_pending = False
            return

        if self.current_channel == "Noise":
            self.ctx.add_error(
                code=ErrorCode.SYNTAX_CHANNEL_MISMATCH,
                line=token.line,
                column=token.column,
                message="チャンネル 'Noise' で音高指定は使用できません。",
                severity="warning",
                hint="Noiseチャンネルでは音高ではなく音長と音量のみ指定してください。",
                context=self._context_line(token),
            )
            midi = 0
        else:
            midi = note_to_midi(note, self.octave, accidental)
            if not 0 <= midi <= 127:
                self.ctx.add_error(
                    code=ErrorCode.SYNTAX_NOTE_OUT_OF_RANGE,
                    line=token.line,
                    column=token.column,
                    message=f"音高が範囲外です（MIDI音番号 {midi}）。",
                    severity="warning",
                    hint="オクターブを調整してください。有効範囲: o0〜o7。",
                    context=self._context_line(token),
                )
                midi = clamp(midi, 0, 127)

        event = NoteEvent(
            tick_position=self.tick_position,
            duration=ticks,
            note_number=midi,
            velocity=self.velocity,
            duty=self.duty,
            gate_time=1.0,
        )
        self._add_event(event)
        self.tick_position += ticks

    def _parse_rest(self) -> None:
        self.ctx.advance()
        length, dots = self._read_length()
        ticks = length_value_to_ticks(length, dots)
        if self._tie_pending:
            self._extend_last_note(ticks)
            self.tick_position += ticks
            self._tie_pending = False
            return
        event = RestEvent(tick_position=self.tick_position, duration=ticks)
        self._add_event(event)
        self.tick_position += ticks

    def _parse_octave(self) -> None:
        token = self.ctx.advance()
        value = int(token.value)
        if not 0 <= value <= 7:
            self.ctx.add_error(
                code=ErrorCode.SYNTAX_VALUE_OUT_OF_RANGE,
                line=token.line,
                column=token.column,
                message=f"'o' の値 {value} は範囲外です。有効範囲: 0〜7。",
                severity="error",
                hint="例: o4 のように指定してください。",
                context=self._context_line(token),
            )
            return
        self.octave = value

    def _parse_octave_up(self) -> None:
        self.ctx.advance()
        if self.octave < 7:
            self.octave += 1

    def _parse_octave_down(self) -> None:
        self.ctx.advance()
        if self.octave > 0:
            self.octave -= 1

    def _parse_length(self) -> None:
        token = self.ctx.advance()
        value = int(token.value)
        if not 1 <= value <= 192:
            self.ctx.add_error(
                code=ErrorCode.SYNTAX_VALUE_OUT_OF_RANGE,
                line=token.line,
                column=token.column,
                message=f"'l' の値 {value} は範囲外です。有効範囲: 1〜192。",
                severity="error",
                hint="例: l8 のように指定してください。",
                context=self._context_line(token),
            )
            return
        self.default_length = value

    def _parse_volume(self) -> None:
        token = self.ctx.advance()
        if self.current_channel == "Triangle":
            # Silently ignored per spec
            return
        value = int(token.value)
        if not 0 <= value <= 15:
            self.ctx.add_error(
                code=ErrorCode.SYNTAX_VALUE_OUT_OF_RANGE,
                line=token.line,
                column=token.column,
                message=f"'v' の値 {value} は範囲外です。有効範囲: 0〜15。",
                severity="error",
                hint="例: v15 のように指定してください。",
                context=self._context_line(token),
            )
            return
        self.velocity = value

    def _parse_duty(self) -> None:
        token = self.ctx.advance()
        if self.current_channel not in PULSE_CHANNELS:
            self.ctx.add_error(
                code=ErrorCode.SYNTAX_CHANNEL_MISMATCH,
                line=token.line,
                column=token.column,
                message=f"チャンネル '{self.current_channel}' で 'q' は使用できません。",
                severity="warning",
                hint="Triangleチャンネルはデューティ比を持ちません。q コマンドを削除してください。",
                context=self._context_line(token),
            )
            return
        value = int(token.value)
        if not 0 <= value <= 3:
            self.ctx.add_error(
                code=ErrorCode.SYNTAX_VALUE_OUT_OF_RANGE,
                line=token.line,
                column=token.column,
                message=f"'q' の値 {value} は範囲外です。有効範囲: 0〜3。",
                severity="error",
                hint="例: q2 のように指定してください。",
                context=self._context_line(token),
            )
            return
        self.duty = value
        self._add_event(DutyEvent(tick_position=self.tick_position, value=value))

    def _parse_tempo(self) -> None:
        token = self.ctx.advance()
        value = int(token.value)
        if value < 1:
            self.ctx.add_error(
                code=ErrorCode.SYNTAX_VALUE_OUT_OF_RANGE,
                line=token.line,
                column=token.column,
                message=f"'t' の値 {value} は範囲外です。有効範囲: 1以上。",
                severity="error",
                hint="例: t150 のように指定してください。",
                context=self._context_line(token),
            )
            return
        self.note_sequence.bpm = value
        self._add_event(TempoEvent(tick_position=self.tick_position, bpm=value))

    def _parse_tie(self) -> None:
        token = self.ctx.advance()
        next_token = self.ctx.peek()
        if next_token.type not in (TokenType.NOTE, TokenType.REST, TokenType.NUMBER):
            self.ctx.add_error(
                code=ErrorCode.SYNTAX_UNTERMINATED_TIE,
                line=token.line,
                column=token.column,
                message="タイ '&' の後に音符が見つかりません。",
                severity="error",
                hint="& の後に音符（例: c4）を続けてください。",
                context=self._context_line(token),
            )
            return
        if next_token.type == TokenType.NUMBER:
            self.ctx.advance()
            ticks = length_value_to_ticks(int(next_token.value), 0)
            self._extend_last_note(ticks)
            self.tick_position += ticks
            return
        # For note/rest: back up tick_position so the next event starts at the
        # end of the last note/rest. The next note's duration will be added
        # to the previous note's duration via _tie_pending flag.
        self.tick_position = self._last_note_end()
        self._tie_pending = True

    def _last_note_end(self) -> int:
        ch = self.note_sequence.channels[self.current_channel]  # type: ignore[index]
        for ev in reversed(ch.events):
            if isinstance(ev, (NoteEvent, RestEvent)):
                return ev.tick_position + ev.duration
        return self.tick_position

    def _extend_last_note(self, ticks: int) -> None:
        ch = self.note_sequence.channels[self.current_channel]  # type: ignore[index]
        for ev in reversed(ch.events):
            if isinstance(ev, (NoteEvent, RestEvent)):
                ev.duration += ticks
                return

    def _parse_repeat_start(self) -> None:
        # Stage 2 feature: keep token but do not expand
        token = self.ctx.advance()
        self.ctx.add_error(
            code=ErrorCode.SYNTAX_UNEXPECTED_TOKEN,
            line=token.line,
            column=token.column,
            message="区間リピート '[' は第2段階で実装されます。",
            severity="warning",
            hint="現時点では無視されます。",
            context=self._context_line(token),
        )

    def _parse_repeat_end(self) -> None:
        token = self.ctx.advance()
        self.ctx.add_error(
            code=ErrorCode.SYNTAX_UNEXPECTED_TOKEN,
            line=token.line,
            column=token.column,
            message="区間リピート ']' は第2段階で実装されます。",
            severity="warning",
            hint="現時点では無視されます。",
            context=self._context_line(token),
        )

    def _parse_bar(self) -> None:
        self.ctx.advance()

    def _add_event(self, event) -> None:  # type: ignore[no-untyped-def]
        ch = self.note_sequence.channels[self.current_channel]  # type: ignore[index]
        ch.events.append(event)

    def _validate_tracks(self) -> None:
        for raw, name in CHANNEL_MAP.items():
            ch = self.note_sequence.channels[name]
            if name in self.tracks_seen and not ch.events:
                # Determine approximate line of header (last track header token)
                header_token = None
                for tok in self.ctx.tokens:
                    if tok.type == TokenType.TRACK_HEADER and tok.value.upper() == raw:
                        header_token = tok
                self.ctx.add_error(
                    code=ErrorCode.SYNTAX_EMPTY_TRACK,
                    line=header_token.line if header_token else 1,
                    column=header_token.column if header_token else 1,
                    message=f"トラック '{raw}' に音符または休符がありません。",
                    severity="error",
                    hint="少なくとも1つの音符または休符を記述してください。",
                    context=self._context_line(header_token) if header_token else "",
                )


def parse_ppmck(
    source: str, tokens: list[Token]
) -> tuple[NoteSequence, list[ErrorDetail]]:
    parser = PpmckParser(source, tokens)
    return parser.parse()
