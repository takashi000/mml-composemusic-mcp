"""Pyxel semantic analyzer: AST -> NoteSequence IR."""

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
    RestEvent,
    TempoEvent,
    VibratoEvent,
    VolumeEvent,
)
from .parser_base import clamp, note_to_midi
from .semantic_base import SemanticAnalyzer

PULSE_CHANNELS = {"Pulse1", "Pulse2"}
PYXEL_DUTY = {
    1: 2,  # Square 50%
    2: 1,  # Pulse 25%
}


class PyxelSemanticAnalyzer(SemanticAnalyzer):
    def __init__(self, source: str, program: Program) -> None:
        super().__init__(source, program)
        self.note_sequence.mode = "pyxel"
        self.transpose = 0
        self.detune_cents = 0.0

    def _reset_state(self, track: Track) -> None:
        super()._reset_state(track)
        self.velocity = 100
        self.gate_time = 0.8
        self.transpose = 0
        self.detune_cents = 0.0

    def _analyze_note(self, stmt: NoteStmt) -> None:
        ticks = self._ticks_for(stmt)
        if ticks is None:
            return
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
        if ticks is None:
            return
        event = RestEvent(tick_position=self.tick_position, duration=ticks)
        self._add_event(event)
        self.tick_position += ticks

    def _analyze_octave(self, stmt: OctaveStmt) -> None:
        if stmt.direction == "up":
            if self.octave < 7:
                self.octave += 1
            else:
                self._validate_range(stmt, self.octave + 1, 0, 7, "オクターブ")
            return
        if stmt.direction == "down":
            if self.octave > 0:
                self.octave -= 1
            else:
                self._validate_range(stmt, self.octave - 1, 0, 7, "オクターブ")
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
        if not self._validate_range(stmt, stmt.value, 0, 3, "音色"):
            return
        if stmt.value in PYXEL_DUTY:
            if self.current_channel not in PULSE_CHANNELS:
                self.ctx.add_error(
                    code=ErrorCode.SEMANTIC_CHANNEL_MISMATCH,
                    line=stmt.line,
                    column=stmt.column,
                    message=f"チャンネル '{self.current_channel}' で '@{stmt.value}' は使用できません。",
                    severity="error",
                    hint="トラック番号がチャンネルを決定します。@ コマンドを削除するか、Pulseチャンネル（0: または 1:）に移動してください。",
                    context=self._context_line(stmt),
                )
                return
            self.duty = PYXEL_DUTY[stmt.value]
            self._add_event(
                DutyEvent(tick_position=self.tick_position, value=self.duty)
            )
            return
        if stmt.value == 0 and self.current_channel == "Triangle":
            return
        if stmt.value == 3 and self.current_channel == "Noise":
            return
        if stmt.value == 0:
            self.ctx.add_error(
                code=ErrorCode.SEMANTIC_CHANNEL_MISMATCH,
                line=stmt.line,
                column=stmt.column,
                message=f"チャンネル '{self.current_channel}' で '@0' (Triangle) は使用できません。",
                severity="error",
                hint="トラック番号がチャンネルを決定します。@ コマンドを削除するか、適切なチャンネルに移動してください。",
                context=self._context_line(stmt),
            )
        else:
            self.ctx.add_error(
                code=ErrorCode.SEMANTIC_CHANNEL_MISMATCH,
                line=stmt.line,
                column=stmt.column,
                message=f"チャンネル '{self.current_channel}' で '@3' (Noise) は使用できません。",
                severity="error",
                hint="トラック番号がチャンネルを決定します。@ コマンドを削除するか、適切なチャンネルに移動してください。",
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
        if self.tick_position == 0:
            self.note_sequence.bpm = stmt.value
        self._add_event(TempoEvent(tick_position=self.tick_position, bpm=stmt.value))

    def _analyze_transpose(self, stmt: TransposeStmt) -> None:
        if not self._validate_range(stmt, stmt.value, -127, 127, "トランスポーズ"):
            return
        self.transpose = stmt.value

    def _analyze_detune(self, stmt) -> None:  # type: ignore[no-untyped-def]
        if not self._validate_range(stmt, stmt.value, -127, 127, "ディチューン"):
            return
        self.detune_cents = float(stmt.value)

    def _analyze_tie(self, stmt: TieStmt) -> None:
        if stmt.target is None:
            return
        if isinstance(stmt.target, int):
            ticks = self._ticks_for_value(stmt.target, stmt)
            if ticks is None:
                return
            self._extend_last_note(ticks)
            self.tick_position += ticks
            return
        if isinstance(stmt.target, NoteStmt):
            target_ticks = self._ticks_for(stmt.target)
            if target_ticks is None:
                return
            self._extend_last_note(target_ticks)
            self.tick_position += target_ticks
            return
        if isinstance(stmt.target, RestStmt):
            target_ticks = self._ticks_for(stmt.target)
            if target_ticks is None:
                return
            self._extend_last_note(target_ticks)
            self.tick_position += target_ticks
            return

    def _analyze_repeat_start(self, stmt: RepeatStartStmt) -> None:
        super()._analyze_repeat_start(stmt)

    def _analyze_repeat_end(self, stmt: RepeatEndStmt) -> None:
        super()._analyze_repeat_end(stmt)

    def _analyze_ext_cmd(self, stmt: ExtCmdStmt) -> None:
        if stmt.slot == 0:
            if stmt.params:
                self.ctx.add_error(
                    ErrorCode.SEMANTIC_VALUE_OUT_OF_RANGE,
                    stmt.line,
                    stmt.column,
                    f"@{stmt.cmd}0 は解除専用で、パラメータを指定できません。",
                    "error",
                    context=self._context_line(stmt),
                )
                return
            if stmt.cmd == "ENV":
                ev = EnvelopeEvent(tick_position=self.tick_position, slot=0)
            elif stmt.cmd == "VIB":
                ev = VibratoEvent(tick_position=self.tick_position, slot=0)
            else:
                ev = GlideEvent(tick_position=self.tick_position, slot=0)
            self._add_event(ev)
            return
        if stmt.params:
            table_name = {
                "ENV": "envelopes",
                "VIB": "vibratos",
                "GLI": "glides",
            }[stmt.cmd]
            if stmt.slot in self.note_sequence.definitions[table_name]:
                self.ctx.add_error(
                    ErrorCode.SEMANTIC_DUPLICATE_DEFINITION,
                    stmt.line,
                    stmt.column,
                    f"@{stmt.cmd}スロット {stmt.slot} は既に定義されています。",
                    "error",
                    "別のスロット番号を使用してください。",
                    self._context_line(stmt),
                )
                return
            if stmt.cmd == "ENV":
                if len(stmt.params) < 2 or len(stmt.params) % 2:
                    self.ctx.add_error(
                        ErrorCode.SEMANTIC_VALUE_OUT_OF_RANGE,
                        stmt.line,
                        stmt.column,
                        "@ENVのパラメータはtarget,durationの組で指定してください。",
                        "error",
                        context=self._context_line(stmt),
                    )
                    return
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
                self.note_sequence.definitions["envelopes"][stmt.slot] = {
                    "points": points
                }
            elif stmt.cmd == "VIB":
                if len(stmt.params) != 3:
                    self.ctx.add_error(
                        ErrorCode.SEMANTIC_VALUE_OUT_OF_RANGE,
                        stmt.line,
                        stmt.column,
                        "@VIBのパラメータは3値で指定してください。",
                        "error",
                        context=self._context_line(stmt),
                    )
                    return
                params = {
                    "delay_ticks": stmt.params[0],
                    "period_ticks": stmt.params[1],
                    "depth_cents": stmt.params[2],
                }
                ev = VibratoEvent(
                    tick_position=self.tick_position,
                    slot=stmt.slot,
                    params=params,
                )
                self.note_sequence.definitions["vibratos"][stmt.slot] = params
            else:
                if len(stmt.params) != 2:
                    self.ctx.add_error(
                        ErrorCode.SEMANTIC_VALUE_OUT_OF_RANGE,
                        stmt.line,
                        stmt.column,
                        "@GLIのパラメータは2値で指定してください。",
                        "error",
                        context=self._context_line(stmt),
                    )
                    return
                params = {
                    "initial_offset_cents": stmt.params[0],
                    "duration_ticks": stmt.params[1],
                }
                ev = GlideEvent(
                    tick_position=self.tick_position,
                    slot=stmt.slot,
                    params=params,
                )
                self.note_sequence.definitions["glides"][stmt.slot] = params
            self._add_event(ev)
        else:
            table_name = {
                "ENV": "envelopes",
                "VIB": "vibratos",
                "GLI": "glides",
            }[stmt.cmd]
            if stmt.slot not in self.note_sequence.definitions[table_name]:
                self.ctx.add_error(
                    ErrorCode.SEMANTIC_UNDEFINED_REFERENCE,
                    stmt.line,
                    stmt.column,
                    f"未定義の@{stmt.cmd}スロット {stmt.slot} が参照されました。",
                    "error",
                    "先に同じスロットをパラメータ付きで定義してください。",
                    self._context_line(stmt),
                )
                return
            if stmt.cmd == "ENV":
                ev = EnvelopeEvent(tick_position=self.tick_position, slot=stmt.slot)
            elif stmt.cmd == "VIB":
                ev = VibratoEvent(tick_position=self.tick_position, slot=stmt.slot)
            else:
                ev = GlideEvent(tick_position=self.tick_position, slot=stmt.slot)
            self._add_event(ev)


def analyze_pyxel(
    source: str, program: Program
) -> tuple[NoteSequence, list[ErrorDetail]]:
    analyzer = PyxelSemanticAnalyzer(source, program)
    return analyzer.analyze()
