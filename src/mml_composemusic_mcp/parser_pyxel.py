"""Pyxel MML parser."""

from .ir import (
    DutyEvent,
    EnvelopeEvent,
    ErrorCode,
    ErrorDetail,
    GlideEvent,
    NoteEvent,
    NoteSequence,
    RepeatEvent,
    RestEvent,
    TempoEvent,
    VibratoEvent,
    VolumeEvent,
)
from .lexer import Token, TokenType
from .parser_base import (
    ParserContext,
    clamp,
    length_value_to_ticks,
    note_to_midi,
)

CHANNEL_MAP = {
    "0": "Pulse1",
    "1": "Pulse2",
    "2": "Triangle",
    "3": "Noise",
}
PULSE_CHANNELS = {"Pulse1", "Pulse2"}

PYXEL_DUTY = {
    "1": 2,  # Square 50%
    "2": 1,  # Pulse 25%
}


class RepeatFrame:
    """Stack frame for nested repeat expansion."""

    def __init__(self, start_tick: int) -> None:
        self.start_tick = start_tick
        # Snapshot of event indices that existed before the repeat section
        self.event_count: int = 0


class PyxelParser:
    def __init__(self, source: str, tokens: list[Token]) -> None:
        self.source = source
        self.ctx = ParserContext(tokens)
        self.note_sequence = NoteSequence()
        self.current_channel: str | None = None
        self.octave = 4
        self.default_length = 4
        self.velocity = 100
        self.gate_time = 0.8
        self.duty = 2
        self.transpose = 0
        self.detune_cents = 0
        self.tick_position = 0
        self.tracks_seen: set[str] = set()
        self.repeat_stack: list[RepeatFrame] = []
        self._tie_pending: bool = False

    def _context_line(self, token: Token) -> str:
        lines = self.source.splitlines()
        if 1 <= token.line <= len(lines):
            return lines[token.line - 1]
        return ""

    def parse(self) -> tuple[NoteSequence, list[ErrorDetail]]:
        while self.ctx.peek().type != TokenType.EOF:
            token = self.ctx.peek()
            if token.type == TokenType.TRACK_HEADER:
                self._parse_track_header()
                continue
            if self.current_channel is None:
                self._warn_outside_track(token)
                self.ctx.advance()
                continue
            self._parse_statement()

        if self.repeat_stack:
            for _frame in self.repeat_stack:
                self.ctx.add_error(
                    code=ErrorCode.SYNTAX_UNTERMINATED_REPEAT,
                    line=1,
                    column=1,
                    message="リピート '[' に対応する ']' が見つかりません。",
                    severity="error",
                    hint="] を追加してリピートを閉じてください。回数指定（例: ]2）も可能です。",
                    context="",
                )

        self._validate_tracks()

        for ch in self.note_sequence.channels.values():
            ch.total_ticks = max(
                (e.tick_position + getattr(e, "duration", 0) for e in ch.events),
                default=0,
            )

        return self.note_sequence, self.ctx.errors

    def _warn_outside_track(self, token: Token) -> None:
        if token.type == TokenType.EOF:
            return
        self.ctx.add_error(
            code=ErrorCode.SYNTAX_OUTSIDE_TRACK,
            line=token.line,
            column=token.column,
            message=f"'{token.raw}' はトラック外に書かれています。",
            severity="warning",
            hint="コマンドはトラックヘッダー（0:, 1:, 2:, 3:）の後に記述してください。",
            context=self._context_line(token),
        )

    def _parse_track_header(self) -> None:
        token = self.ctx.advance()
        ch = token.value
        if ch not in CHANNEL_MAP:
            self.ctx.add_error(
                code=ErrorCode.SYNTAX_INVALID_TRACK_HEADER,
                line=token.line,
                column=token.column,
                message=f"無効なトラックヘッダー '{ch}:' です。",
                severity="error",
                hint="0:, 1:, 2:, 3: のいずれかを使用してください。",
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
                message=f"トラック '{ch}:' が複数回定義されています。",
                severity="error",
                hint="各トラックは1回のみ定義できます。重複定義を削除してください。",
                context=self._context_line(token),
            )
        self.tracks_seen.add(self.current_channel)
        self.octave = 4
        self.default_length = 4
        self.velocity = 100
        self.gate_time = 0.8
        self.duty = 2
        self.transpose = 0
        self.detune_cents = 0
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
            TokenType.GATE_TIME: self._parse_gate_time,
            TokenType.AT: self._parse_at,
            TokenType.TEMPO: self._parse_tempo,
            TokenType.TRANSPOSE: self._parse_transpose,
            TokenType.DETUNE: self._parse_detune,
            TokenType.TIE: self._parse_tie,
            TokenType.REPEAT_START: self._parse_repeat_start,
            TokenType.REPEAT_END: self._parse_repeat_end,
            TokenType.EXT_CMD: self._parse_ext_cmd,
            TokenType.BAR: self._parse_bar,
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
            midi = note_to_midi(note, self.octave, accidental)
        else:
            midi = note_to_midi(note, self.octave, accidental) + self.transpose
            if not 0 <= midi <= 127:
                self.ctx.add_error(
                    code=ErrorCode.SYNTAX_NOTE_OUT_OF_RANGE,
                    line=token.line,
                    column=token.column,
                    message=f"音高が範囲外です（MIDI音番号 {midi}）。",
                    severity="warning",
                    hint="オクターブ/トランスポーズを調整してください。有効範囲: O0〜O7。",
                    context=self._context_line(token),
                )
                midi = clamp(midi, 0, 127)

        event = NoteEvent(
            tick_position=self.tick_position,
            duration=ticks,
            note_number=midi,
            velocity=self._normalize_velocity(self.velocity),
            duty=self.duty,
            gate_time=self.gate_time,
            detune_cents=float(self.detune_cents),
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
                message=f"'O' の値 {value} は範囲外です。有効範囲: 0〜7。",
                severity="error",
                hint="例: O4 のように指定してください。",
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
                message=f"'L' の値 {value} は範囲外です。有効範囲: 1〜192。",
                severity="error",
                hint="例: L8 のように指定してください。",
                context=self._context_line(token),
            )
            return
        self.default_length = value

    def _parse_volume(self) -> None:
        token = self.ctx.advance()
        value = int(token.value)
        if not 0 <= value <= 127:
            self.ctx.add_error(
                code=ErrorCode.SYNTAX_VALUE_OUT_OF_RANGE,
                line=token.line,
                column=token.column,
                message=f"'V' の値 {value} は範囲外です。有効範囲: 0〜127。",
                severity="error",
                hint="例: V100 のように指定してください。",
                context=self._context_line(token),
            )
            return
        self.velocity = value
        self._add_event(
            VolumeEvent(
                tick_position=self.tick_position,
                value=self._normalize_velocity(value),
            )
        )

    def _normalize_velocity(self, value: int) -> int:
        return round(value / 127 * 15)

    def _parse_gate_time(self) -> None:
        token = self.ctx.advance()
        value = int(token.value)
        if not 0 <= value <= 100:
            self.ctx.add_error(
                code=ErrorCode.SYNTAX_VALUE_OUT_OF_RANGE,
                line=token.line,
                column=token.column,
                message=f"'Q' の値 {value} は範囲外です。有効範囲: 0〜100。",
                severity="error",
                hint="例: Q80 のように指定してください。",
                context=self._context_line(token),
            )
            return
        self.gate_time = value / 100.0

    def _parse_at(self) -> None:
        token = self.ctx.advance()
        value = token.value
        if value in PYXEL_DUTY:
            if self.current_channel not in PULSE_CHANNELS:
                self.ctx.add_error(
                    code=ErrorCode.SYNTAX_CHANNEL_MISMATCH,
                    line=token.line,
                    column=token.column,
                    message=f"チャンネル '{self.current_channel}' で '@{value}' は使用できません。",
                    severity="warning",
                    hint="トラック番号がチャンネルを決定します。@ コマンドを削除するか、Pulseチャンネル（0: または 1:）に移動してください。",
                    context=self._context_line(token),
                )
                return
            self.duty = PYXEL_DUTY[value]
            self._add_event(
                DutyEvent(tick_position=self.tick_position, value=self.duty)
            )
            return
        if value == "0":
            self.ctx.add_error(
                code=ErrorCode.SYNTAX_CHANNEL_MISMATCH,
                line=token.line,
                column=token.column,
                message=f"チャンネル '{self.current_channel}' で '@0' (Triangle) は使用できません。",
                severity="warning",
                hint="トラック番号がチャンネルを決定します。@ コマンドを削除するか、適切なチャンネルに移動してください。",
                context=self._context_line(token),
            )
        elif value == "3":
            self.ctx.add_error(
                code=ErrorCode.SYNTAX_CHANNEL_MISMATCH,
                line=token.line,
                column=token.column,
                message=f"チャンネル '{self.current_channel}' で '@3' (Noise) は使用できません。",
                severity="warning",
                hint="トラック番号がチャンネルを決定します。@ コマンドを削除するか、適切なチャンネルに移動してください。",
                context=self._context_line(token),
            )
        else:
            self.ctx.add_error(
                code=ErrorCode.SYNTAX_INVALID_NUMBER,
                line=token.line,
                column=token.column,
                message=f"'@' の後に無効な値 '{value}' が見つかりました。",
                severity="error",
                hint="例: @1 のように指定してください。",
                context=self._context_line(token),
            )

    def _parse_tempo(self) -> None:
        token = self.ctx.advance()
        value = int(token.value)
        if value < 1:
            self.ctx.add_error(
                code=ErrorCode.SYNTAX_VALUE_OUT_OF_RANGE,
                line=token.line,
                column=token.column,
                message=f"'T' の値 {value} は範囲外です。有効範囲: 1以上。",
                severity="error",
                hint="例: T150 のように指定してください。",
                context=self._context_line(token),
            )
            return
        self.note_sequence.bpm = value
        self._add_event(TempoEvent(tick_position=self.tick_position, bpm=value))

    def _parse_transpose(self) -> None:
        token = self.ctx.advance()
        self.transpose = int(token.value)

    def _parse_detune(self) -> None:
        token = self.ctx.advance()
        self.detune_cents = int(token.value)

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
                hint="& の後に音符（例: C4）を続けてください。音長のみ（例: &16）も可能です。",
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
        self.ctx.advance()
        ch = self.note_sequence.channels[self.current_channel]  # type: ignore[index]
        frame = RepeatFrame(start_tick=self.tick_position)
        frame.event_count = len(ch.events)
        self.repeat_stack.append(frame)

    def _parse_repeat_end(self) -> None:
        token = self.ctx.advance()
        if not self.repeat_stack:
            self.ctx.add_error(
                code=ErrorCode.SYNTAX_UNMATCHED_REPEAT_END,
                line=token.line,
                column=token.column,
                message="']' に対応する '[' が見つかりません。",
                severity="error",
                hint="直前の [ を確認するか、余分な ] を削除してください。",
                context=self._context_line(token),
            )
            return
        frame = self.repeat_stack.pop()
        start_tick = frame.start_tick
        ch = self.note_sequence.channels[self.current_channel]  # type: ignore[index]

        count_str = token.value
        if count_str == "":
            count = 0  # infinite
            self.ctx.add_error(
                code=ErrorCode.SYNTAX_UNEXPECTED_TOKEN,
                line=token.line,
                column=token.column,
                message="無限リピートはWAV生成時に2回で打ち切られます。",
                severity="warning",
                hint="回数を指定するか、2回の再生で十分であることを確認してください。",
                context=self._context_line(token),
            )
        else:
            count = int(count_str)

        # Collect events that belong to this repeat section (created after the frame snapshot)
        segment_events = ch.events[frame.event_count :]
        segment_length = self.tick_position - start_tick

        repeat_count = 2 if count == 0 else count
        for i in range(1, repeat_count):
            offset = i * segment_length
            for ev in segment_events:
                new_event = self._clone_event(ev, ev.tick_position + offset)
                self._add_event(new_event)
                if isinstance(new_event, (NoteEvent, RestEvent)):
                    end = new_event.tick_position + new_event.duration
                    if end > self.tick_position:
                        self.tick_position = end

        ch.events.sort(key=lambda e: e.tick_position)
        self._add_event(
            RepeatEvent(
                start_tick=start_tick,
                end_tick=self.tick_position,
                repeat_count=count,
            )
        )

    def _clone_event(self, event, tick_position: int):  # type: ignore[no-untyped-def]
        import copy

        new = copy.copy(event)
        new.tick_position = tick_position
        return new

    def _parse_ext_cmd(self) -> None:
        token = self.ctx.advance()
        cmd = token.value  # ENV, VIB, GLI
        slot_token = self.ctx.match(TokenType.NUMBER)
        if slot_token is None:
            self.ctx.add_error(
                code=ErrorCode.SYNTAX_INVALID_NUMBER,
                line=token.line,
                column=token.column,
                message=f"'@{cmd}' の後にスロット番号が必要です。",
                severity="error",
                hint=f"例: @{cmd}1 のように指定してください。",
                context=self._context_line(token),
            )
            return
        slot = int(slot_token.value)
        if slot == 0:
            # OFF
            if cmd == "ENV":
                ev = EnvelopeEvent(tick_position=self.tick_position, slot=0)
            elif cmd == "VIB":
                ev = VibratoEvent(tick_position=self.tick_position, slot=0)
            else:
                ev = GlideEvent(tick_position=self.tick_position, slot=0)
            self._add_event(ev)
            return
        if self.ctx.match(TokenType.NUMBER):
            # definition without braces; simplistic parse numbers until non-number
            # Real Pyxel uses { ... }; we accept a flat sequence of ints for now.
            values = [int(slot_token.value)]
            while True:
                num = self.ctx.match(TokenType.NUMBER)
                if num is None:
                    break
                values.append(int(num.value))
            if cmd == "ENV":
                points = []
                for i in range(1, len(values), 2):
                    duration = values[i]
                    target = values[i - 1] if i - 1 < len(values) else values[-1]
                    points.append({"target_volume": target, "duration_ticks": duration})
                ev = EnvelopeEvent(
                    tick_position=self.tick_position,
                    slot=slot,
                    points=points,
                )
            elif cmd == "VIB":
                if len(values) >= 3:
                    params = {
                        "delay_ticks": values[0],
                        "period_ticks": values[1],
                        "depth_cents": values[2],
                    }
                else:
                    params = {}
                ev = VibratoEvent(
                    tick_position=self.tick_position,
                    slot=slot,
                    params=params,
                )
            else:
                if len(values) >= 2:
                    params = {
                        "initial_offset_cents": values[0],
                        "duration_ticks": values[1],
                    }
                else:
                    params = {}
                ev = GlideEvent(
                    tick_position=self.tick_position,
                    slot=slot,
                    params=params,
                )
            self._add_event(ev)
            self.ctx.add_error(
                code=ErrorCode.SYNTAX_UNEXPECTED_TOKEN,
                line=token.line,
                column=token.column,
                message=f"@{cmd} は第1段階では未サポート、無視されます。",
                severity="warning",
                hint="合成には反映されませんが、IRとして保持されます。",
                context=self._context_line(token),
            )
            return
        # Slot switch only
        if cmd == "ENV":
            ev = EnvelopeEvent(tick_position=self.tick_position, slot=slot)
        elif cmd == "VIB":
            ev = VibratoEvent(tick_position=self.tick_position, slot=slot)
        else:
            ev = GlideEvent(tick_position=self.tick_position, slot=slot)
        self._add_event(ev)
        self.ctx.add_error(
            code=ErrorCode.SYNTAX_UNEXPECTED_TOKEN,
            line=token.line,
            column=token.column,
            message=f"@{cmd} は第1段階では未サポート、無視されます。",
            severity="warning",
            hint="合成には反映されませんが、IRとして保持されます。",
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
                header_token = None
                for tok in self.ctx.tokens:
                    if tok.type == TokenType.TRACK_HEADER and tok.value == raw:
                        header_token = tok
                self.ctx.add_error(
                    code=ErrorCode.SYNTAX_EMPTY_TRACK,
                    line=header_token.line if header_token else 1,
                    column=header_token.column if header_token else 1,
                    message=f"トラック '{raw}:' に音符または休符がありません。",
                    severity="error",
                    hint="少なくとも1つの音符または休符を記述してください。",
                    context=self._context_line(header_token) if header_token else "",
                )


def parse_pyxel(
    source: str, tokens: list[Token]
) -> tuple[NoteSequence, list[ErrorDetail]]:
    parser = PyxelParser(source, tokens)
    return parser.parse()
