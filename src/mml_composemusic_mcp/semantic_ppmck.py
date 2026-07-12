"""PPMCK semantic analyzer: AST -> NoteSequence IR."""


from .ast_nodes import (
    DutyStmt,
    EnvelopeDefStmt,
    ExtCmdStmt,
    GateTimeStmt,
    LengthStmt,
    NoteStmt,
    OctaveStmt,
    Program,
    RepeatEndStmt,
    RepeatStartStmt,
    RestStmt,
    SweepStmt,
    TempoStmt,
    TieStmt,
    Track,
    VolumeStmt,
)
from .ir import (
    DutyEvent,
    ErrorCode,
    ErrorDetail,
    NoteEvent,
    NoteSequence,
    RepeatEvent,
    RestEvent,
    TempoEvent,
    VolumeEvent,
)
from .parser_base import clamp, length_value_to_ticks, note_to_midi
from .semantic_base import SemanticAnalyzer

PULSE_CHANNELS = {"Pulse1", "Pulse2"}


class PpmckSemanticAnalyzer(SemanticAnalyzer):
    def __init__(self, source: str, program: Program) -> None:
        super().__init__(source, program)
        self.loop_start: int | None = None

    def analyze(self) -> tuple[NoteSequence, list[ErrorDetail]]:
        ns, errors = super().analyze()
        if self.loop_start is not None:
            max_tick = max(
                ch.total_ticks for ch in ns.channels.values()
            )
            for ch in ns.channels.values():
                ch.events.append(
                    RepeatEvent(
                        start_tick=self.loop_start,
                        end_tick=max_tick,
                        repeat_count=0,
                    )
                )
            # Recompute total_ticks after adding loop events
            for ch in ns.channels.values():
                ch.total_ticks = max(
                    (e.tick_position + getattr(e, "duration", 0) for e in ch.events),
                    default=0,
                )
        return ns, errors

    def _reset_state(self, track: Track) -> None:
        self.octave = 4
        self.default_length = 4
        self.velocity = 15
        self.gate_time = 1.0
        self.duty = 2
        self.tick_position = 0

    def _analyze_track(self, track: Track) -> None:
        if track.channel == "Loop":
            self.loop_start = 0
            return
        super()._analyze_track(track)

    def _analyze_note(self, stmt: NoteStmt) -> None:
        ticks = self._ticks_for(stmt)
        midi = note_to_midi(stmt.note_name, self.octave, stmt.accidental)
        if self.current_channel == "Noise":
            self.ctx.add_error(
                code=ErrorCode.SEMANTIC_CHANNEL_MISMATCH,
                line=stmt.line,
                column=stmt.column,
                message="チャンネル 'Noise' で音高指定は使用できません。",
                severity="warning",
                hint="Noiseチャンネルでは音高ではなく音長と音量のみ指定してください。",
                context=self._context_line(stmt),
            )
            midi = 0
        if not 0 <= midi <= 127:
            self.ctx.add_error(
                code=ErrorCode.SEMANTIC_NOTE_OUT_OF_RANGE,
                line=stmt.line,
                column=stmt.column,
                message=f"音高が範囲外です（MIDI音番号 {midi}）。",
                severity="warning",
                hint="オクターブを調整してください。有効範囲: o0〜o7。",
                context=self._context_line(stmt),
            )
            midi = clamp(midi, 0, 127)
        event = NoteEvent(
            tick_position=self.tick_position,
            duration=ticks,
            note_number=midi,
            velocity=self.velocity,
            duty=self.duty,
            gate_time=self.gate_time,
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
                message=f"'o' の値 {stmt.value} は範囲外です。有効範囲: 0〜7。",
                severity="error",
                hint="例: o4 のように指定してください。",
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
                message=f"'l' の値 {stmt.value} は範囲外です。有効範囲: 1〜192。",
                severity="error",
                hint="例: l8 のように指定してください。",
                context=self._context_line(stmt),
            )
            return
        self.default_length = stmt.value

    def _analyze_volume(self, stmt: VolumeStmt) -> None:
        if self.current_channel == "Triangle":
            # Silently ignored per spec
            return
        if not 0 <= stmt.value <= 15:
            self.ctx.add_error(
                code=ErrorCode.SEMANTIC_VALUE_OUT_OF_RANGE,
                line=stmt.line,
                column=stmt.column,
                message=f"'v' の値 {stmt.value} は範囲外です。有効範囲: 0〜15。",
                severity="error",
                hint="例: v15 のように指定してください。",
                context=self._context_line(stmt),
            )
            return
        self.velocity = stmt.value
        self._add_event(VolumeEvent(tick_position=self.tick_position, value=stmt.value))

    def _analyze_duty(self, stmt: DutyStmt) -> None:
        if self.current_channel not in PULSE_CHANNELS:
            self.ctx.add_error(
                code=ErrorCode.SEMANTIC_CHANNEL_MISMATCH,
                line=stmt.line,
                column=stmt.column,
                message=f"チャンネル '{self.current_channel}' で 'q' は使用できません。",
                severity="warning",
                hint="Triangleチャンネルはデューティ比を持ちません。q コマンドを削除してください。",
                context=self._context_line(stmt),
            )
            return
        if not 0 <= stmt.value <= 3:
            self.ctx.add_error(
                code=ErrorCode.SEMANTIC_VALUE_OUT_OF_RANGE,
                line=stmt.line,
                column=stmt.column,
                message=f"'q' の値 {stmt.value} は範囲外です。有効範囲: 0〜3。",
                severity="error",
                hint="例: q2 のように指定してください。",
                context=self._context_line(stmt),
            )
            return
        self.duty = stmt.value
        self._add_event(DutyEvent(tick_position=self.tick_position, value=stmt.value))

    def _analyze_tempo(self, stmt: TempoStmt) -> None:
        if stmt.value < 1:
            self.ctx.add_error(
                code=ErrorCode.SEMANTIC_VALUE_OUT_OF_RANGE,
                line=stmt.line,
                column=stmt.column,
                message=f"'t' の値 {stmt.value} は範囲外です。有効範囲: 1以上。",
                severity="error",
                hint="例: t150 のように指定してください。",
                context=self._context_line(stmt),
            )
            return
        self.note_sequence.bpm = stmt.value
        self._add_event(TempoEvent(tick_position=self.tick_position, bpm=stmt.value))

    def _analyze_gate_time(self, stmt: GateTimeStmt) -> None:
        # ppmck does not support gate time
        self._analyze_stage2(stmt)

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
        # Stage 2 feature
        self._analyze_stage2(stmt)

    def _analyze_repeat_end(self, stmt: RepeatEndStmt) -> None:
        # Stage 2 feature
        self._analyze_stage2(stmt)

    def _analyze_ext_cmd(self, stmt: ExtCmdStmt) -> None:
        # ppmck does not use pyxel ext commands
        self._analyze_stage2(stmt)

    def _analyze_stage2(self, stmt) -> None:  # type: ignore[no-untyped-def]
        if isinstance(stmt, EnvelopeDefStmt):
            self.ctx.add_error(
                code=ErrorCode.SEMANTIC_UNSUPPORTED_FEATURE,
                line=stmt.line,
                column=stmt.column,
                message="エンベロープ定義 '@v' は第2段階で実装されます。",
                severity="warning",
                hint="現時点では無視されます。",
                context=self._context_line(stmt),
            )
        elif isinstance(stmt, SweepStmt):
            self.ctx.add_error(
                code=ErrorCode.SEMANTIC_UNSUPPORTED_FEATURE,
                line=stmt.line,
                column=stmt.column,
                message="スイープ 's' は第2段階で実装されます。",
                severity="warning",
                hint="現時点では無視されます。",
                context=self._context_line(stmt),
            )
        else:
            super()._analyze_stage2(stmt)


def analyze_ppmck(
    source: str, program: Program
) -> tuple[NoteSequence, list[ErrorDetail]]:
    analyzer = PpmckSemanticAnalyzer(source, program)
    return analyzer.analyze()
