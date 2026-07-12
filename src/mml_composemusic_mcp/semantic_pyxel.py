"""Pyxel semantic analyzer: AST -> NoteSequence IR."""

import copy

from .ast_nodes import (
    DutyStmt,
    ExtCmdStmt,
    GateTimeStmt,
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
    TransposeStmt,
    VolumeStmt,
)
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
from .parser_base import clamp, length_value_to_ticks, note_to_midi
from .semantic_base import SemanticAnalyzer

PULSE_CHANNELS = {"Pulse1", "Pulse2"}
PYXEL_DUTY = {
    1: 2,  # Square 50%
    2: 1,  # Pulse 25%
}


class RepeatFrame:
    """Stack frame for nested repeat expansion."""

    def __init__(self, start_tick: int) -> None:
        self.start_tick = start_tick
        self.event_count: int = 0


class PyxelSemanticAnalyzer(SemanticAnalyzer):
    def __init__(self, source: str, program: Program) -> None:
        super().__init__(source, program)
        self.transpose = 0
        self.detune_cents = 0.0
        self.repeat_stack: list[RepeatFrame] = []

    def _reset_state(self, track: Track) -> None:
        self.octave = 4
        self.default_length = 4
        self.velocity = 100
        self.gate_time = 0.8
        self.duty = 2
        self.transpose = 0
        self.detune_cents = 0.0
        self.tick_position = 0
        self.repeat_stack = []

    def _analyze_track(self, track: Track) -> None:
        self.current_channel = track.channel
        self._reset_state(track)
        for stmt in track.statements:
            self._analyze_statement(stmt)
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

    def _analyze_note(self, stmt: NoteStmt) -> None:
        ticks = self._ticks_for(stmt)
        midi = note_to_midi(stmt.note_name, self.octave, stmt.accidental)
        if self.current_channel != "Noise":
            midi += self.transpose
        if not 0 <= midi <= 127:
            self.ctx.add_error(
                code=ErrorCode.SEMANTIC_NOTE_OUT_OF_RANGE,
                line=stmt.line,
                column=stmt.column,
                message=f"音高が範囲外です（MIDI音番号 {midi}）。",
                severity="warning",
                hint="オクターブ/トランスポーズを調整してください。有効範囲: O0〜O7。",
                context=self._context_line(stmt),
            )
            midi = clamp(midi, 0, 127)
        event = NoteEvent(
            tick_position=self.tick_position,
            duration=ticks,
            note_number=midi,
            velocity=self._normalize_velocity(self.velocity),
            duty=self.duty,
            gate_time=self.gate_time,
            detune_cents=self.detune_cents,
        )
        self._add_event(event)
        self.tick_position += ticks

    def _analyze_rest(self, stmt: RestStmt) -> None:
        ticks = self._ticks_for(stmt)
        event = RestEvent(tick_position=self.tick_position, duration=ticks)
        self._add_event(event)
        self.tick_position += ticks

    def _analyze_octave(self, stmt: OctaveStmt) -> None:
        if stmt.direction == "up":
            if self.octave < 7:
                self.octave += 1
            return
        if stmt.direction == "down":
            if self.octave > 0:
                self.octave -= 1
            return
        if stmt.value is None:
            return
        if not 0 <= stmt.value <= 7:
            self.ctx.add_error(
                code=ErrorCode.SEMANTIC_VALUE_OUT_OF_RANGE,
                line=stmt.line,
                column=stmt.column,
                message=f"'O' の値 {stmt.value} は範囲外です。有効範囲: 0〜7。",
                severity="error",
                hint="例: O4 のように指定してください。",
                context=self._context_line(stmt),
            )
            return
        self.octave = stmt.value

    def _analyze_length(self, stmt: LengthStmt) -> None:
        if not 1 <= stmt.value <= 192:
            self.ctx.add_error(
                code=ErrorCode.SEMANTIC_VALUE_OUT_OF_RANGE,
                line=stmt.line,
                column=stmt.column,
                message=f"'L' の値 {stmt.value} は範囲外です。有効範囲: 1〜192。",
                severity="error",
                hint="例: L8 のように指定してください。",
                context=self._context_line(stmt),
            )
            return
        self.default_length = stmt.value

    def _analyze_volume(self, stmt: VolumeStmt) -> None:
        if not 0 <= stmt.value <= 127:
            self.ctx.add_error(
                code=ErrorCode.SEMANTIC_VALUE_OUT_OF_RANGE,
                line=stmt.line,
                column=stmt.column,
                message=f"'V' の値 {stmt.value} は範囲外です。有効範囲: 0〜127。",
                severity="error",
                hint="例: V100 のように指定してください。",
                context=self._context_line(stmt),
            )
            return
        self.velocity = stmt.value
        self._add_event(
            VolumeEvent(
                tick_position=self.tick_position,
                value=self._normalize_velocity(stmt.value),
            )
        )

    def _normalize_velocity(self, value: int) -> int:
        return round(value / 127 * 15)

    def _analyze_gate_time(self, stmt: GateTimeStmt) -> None:
        if not 0 <= stmt.value <= 100:
            self.ctx.add_error(
                code=ErrorCode.SEMANTIC_VALUE_OUT_OF_RANGE,
                line=stmt.line,
                column=stmt.column,
                message=f"'Q' の値 {stmt.value} は範囲外です。有効範囲: 0〜100。",
                severity="error",
                hint="例: Q80 のように指定してください。",
                context=self._context_line(stmt),
            )
            return
        self.gate_time = stmt.value / 100.0

    def _analyze_duty(self, stmt: DutyStmt) -> None:
        if stmt.value in PYXEL_DUTY:
            if self.current_channel not in PULSE_CHANNELS:
                self.ctx.add_error(
                    code=ErrorCode.SEMANTIC_CHANNEL_MISMATCH,
                    line=stmt.line,
                    column=stmt.column,
                    message=f"チャンネル '{self.current_channel}' で '@{stmt.value}' は使用できません。",
                    severity="warning",
                    hint="トラック番号がチャンネルを決定します。@ コマンドを削除するか、Pulseチャンネル（0: または 1:）に移動してください。",
                    context=self._context_line(stmt),
                )
                return
            self.duty = PYXEL_DUTY[stmt.value]
            self._add_event(
                DutyEvent(tick_position=self.tick_position, value=self.duty)
            )
            return
        if stmt.value == 0:
            self.ctx.add_error(
                code=ErrorCode.SEMANTIC_CHANNEL_MISMATCH,
                line=stmt.line,
                column=stmt.column,
                message=f"チャンネル '{self.current_channel}' で '@0' (Triangle) は使用できません。",
                severity="warning",
                hint="トラック番号がチャンネルを決定します。@ コマンドを削除するか、適切なチャンネルに移動してください。",
                context=self._context_line(stmt),
            )
        elif stmt.value == 3:
            self.ctx.add_error(
                code=ErrorCode.SEMANTIC_CHANNEL_MISMATCH,
                line=stmt.line,
                column=stmt.column,
                message=f"チャンネル '{self.current_channel}' で '@3' (Noise) は使用できません。",
                severity="warning",
                hint="トラック番号がチャンネルを決定します。@ コマンドを削除するか、適切なチャンネルに移動してください。",
                context=self._context_line(stmt),
            )
        else:
            self.ctx.add_error(
                code=ErrorCode.SYNTAX_INVALID_NUMBER,
                line=stmt.line,
                column=stmt.column,
                message=f"'@' の後に無効な値 '{stmt.value}' が見つかりました。",
                severity="error",
                hint="例: @1 のように指定してください。",
                context=self._context_line(stmt),
            )

    def _analyze_tempo(self, stmt: TempoStmt) -> None:
        if stmt.value < 1:
            self.ctx.add_error(
                code=ErrorCode.SEMANTIC_VALUE_OUT_OF_RANGE,
                line=stmt.line,
                column=stmt.column,
                message=f"'T' の値 {stmt.value} は範囲外です。有効範囲: 1以上。",
                severity="error",
                hint="例: T150 のように指定してください。",
                context=self._context_line(stmt),
            )
            return
        self.note_sequence.bpm = stmt.value
        self._add_event(TempoEvent(tick_position=self.tick_position, bpm=stmt.value))

    def _analyze_transpose(self, stmt: TransposeStmt) -> None:
        self.transpose = stmt.value

    def _analyze_detune(self, stmt) -> None:  # type: ignore[no-untyped-def]
        self.detune_cents = float(stmt.value)

    def _analyze_tie(self, stmt: TieStmt) -> None:
        if stmt.target is None:
            return
        if isinstance(stmt.target, int):
            ticks = length_value_to_ticks(stmt.target, 0)
            self._extend_last_note(ticks)
            self.tick_position += ticks
            return
        if isinstance(stmt.target, NoteStmt):
            target_ticks = self._ticks_for(stmt.target)
            self._extend_last_note(target_ticks)
            self.tick_position += target_ticks
            return
        if isinstance(stmt.target, RestStmt):
            target_ticks = self._ticks_for(stmt.target)
            self._extend_last_note(target_ticks)
            self.tick_position += target_ticks
            return

    def _analyze_repeat_start(self, stmt: RepeatStartStmt) -> None:
        ch = self.note_sequence.channels[self.current_channel]  # type: ignore[index]
        frame = RepeatFrame(start_tick=self.tick_position)
        frame.event_count = len(ch.events)
        self.repeat_stack.append(frame)

    def _analyze_repeat_end(self, stmt: RepeatEndStmt) -> None:
        if not self.repeat_stack:
            self.ctx.add_error(
                code=ErrorCode.SYNTAX_UNMATCHED_REPEAT_END,
                line=stmt.line,
                column=stmt.column,
                message="']' に対応する '[' が見つかりません。",
                severity="error",
                hint="直前の [ を確認するか、余分な ] を削除してください。",
                context=self._context_line(stmt),
            )
            return
        frame = self.repeat_stack.pop()
        start_tick = frame.start_tick
        ch = self.note_sequence.channels[self.current_channel]  # type: ignore[index]

        count = stmt.count
        if count is None:
            count = 0  # infinite
            self.ctx.add_error(
                code=ErrorCode.SEMANTIC_UNSUPPORTED_FEATURE,
                line=stmt.line,
                column=stmt.column,
                message="無限リピートはWAV生成時に2回で打ち切られます。",
                severity="warning",
                hint="回数を指定するか、2回の再生で十分であることを確認してください。",
                context=self._context_line(stmt),
            )

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
        new = copy.copy(event)
        new.tick_position = tick_position
        return new

    def _analyze_ext_cmd(self, stmt: ExtCmdStmt) -> None:
        if stmt.slot == 0:
            if stmt.cmd == "ENV":
                ev = EnvelopeEvent(tick_position=self.tick_position, slot=0)
            elif stmt.cmd == "VIB":
                ev = VibratoEvent(tick_position=self.tick_position, slot=0)
            else:
                ev = GlideEvent(tick_position=self.tick_position, slot=0)
            self._add_event(ev)
            return
        if stmt.params:
            if stmt.cmd == "ENV":
                points = []
                for i in range(1, len(stmt.params), 2):
                    duration = stmt.params[i]
                    target = (
                        stmt.params[i - 1]
                        if i - 1 < len(stmt.params)
                        else stmt.params[-1]
                    )
                    points.append({"target_volume": target, "duration_ticks": duration})
                ev = EnvelopeEvent(
                    tick_position=self.tick_position,
                    slot=stmt.slot,
                    points=points,
                )
            elif stmt.cmd == "VIB":
                if len(stmt.params) >= 3:
                    params = {
                        "delay_ticks": stmt.params[0],
                        "period_ticks": stmt.params[1],
                        "depth_cents": stmt.params[2],
                    }
                else:
                    params = {}
                ev = VibratoEvent(
                    tick_position=self.tick_position,
                    slot=stmt.slot,
                    params=params,
                )
            else:
                if len(stmt.params) >= 2:
                    params = {
                        "initial_offset_cents": stmt.params[0],
                        "duration_ticks": stmt.params[1],
                    }
                else:
                    params = {}
                ev = GlideEvent(
                    tick_position=self.tick_position,
                    slot=stmt.slot,
                    params=params,
                )
            self._add_event(ev)
        else:
            if stmt.cmd == "ENV":
                ev = EnvelopeEvent(tick_position=self.tick_position, slot=stmt.slot)
            elif stmt.cmd == "VIB":
                ev = VibratoEvent(tick_position=self.tick_position, slot=stmt.slot)
            else:
                ev = GlideEvent(tick_position=self.tick_position, slot=stmt.slot)
            self._add_event(ev)
        self.ctx.add_error(
            code=ErrorCode.SEMANTIC_UNSUPPORTED_FEATURE,
            line=stmt.line,
            column=stmt.column,
            message=f"@{stmt.cmd} は第1段階では未サポート、無視されます。",
            severity="warning",
            hint="合成には反映されませんが、IRとして保持されます。",
            context=self._context_line(stmt),
        )


def analyze_pyxel(
    source: str, program: Program
) -> tuple[NoteSequence, list[ErrorDetail]]:
    analyzer = PyxelSemanticAnalyzer(source, program)
    return analyzer.analyze()
