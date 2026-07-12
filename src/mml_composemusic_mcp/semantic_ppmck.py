"""PPMCK semantic analyzer: AST -> NoteSequence IR."""

from .ast_nodes import (
    DetuneCmdStmt,
    DutyEnvelopeDefStmt,
    DutyEnvelopeUseStmt,
    DutyStmt,
    ExtCmdStmt,
    GateTimeStmt,
    LengthStmt,
    LfoDefStmt,
    LfoOffStmt,
    LfoUseStmt,
    NoteEnvDefStmt,
    NoteEnvOffStmt,
    NoteEnvUseStmt,
    NoteStmt,
    OctaveStmt,
    PitchEnvDefStmt,
    PitchEnvOffStmt,
    PitchEnvUseStmt,
    Program,
    QuantizeStmt,
    RelativeVolumeStmt,
    RepeatEndStmt,
    RepeatStartStmt,
    RestStmt,
    SweepStmt,
    TempoStmt,
    TieCmdStmt,
    TieStmt,
    Track,
    VolumeEnvelopeDefStmt,
    VolumeEnvelopeUseStmt,
    VolumeStmt,
)
from .ir import (
    DetuneEvent,
    DutyEnvelopeEvent,
    DutyEvent,
    ErrorCode,
    ErrorDetail,
    LfoEvent,
    NoteEnvEvent,
    NoteEvent,
    NoteSequence,
    PitchEnvEvent,
    QuantizeEvent,
    RelativeVolumeEvent,
    RepeatEvent,
    RestEvent,
    SweepEvent,
    TempoEvent,
    VolumeEnvelopeEvent,
    VolumeEvent,
)
from .parser_base import clamp, length_value_to_ticks, note_to_midi
from .semantic_base import SemanticAnalyzer

PULSE_CHANNELS = {"Pulse1", "Pulse2"}


class PpmckSemanticAnalyzer(SemanticAnalyzer):
    def __init__(self, source: str, program: Program) -> None:
        super().__init__(source, program)
        self.note_sequence.mode = "ppmck"
        self.loop_start: int | None = None
        self.detune_cents = 0.0

    def _define(self, kind: str, slot: int, value: dict) -> None:
        table = self.note_sequence.definitions[kind]
        if slot in table:
            self.ctx.add_error(
                ErrorCode.SEMANTIC_DUPLICATE_DEFINITION,
                0,
                0,
                f"エフェクトスロット {slot} は既に定義されています。",
                "error",
                "別のスロット番号を使用してください。",
            )
            return
        table[slot] = value

    def analyze(self) -> tuple[NoteSequence, list[ErrorDetail]]:
        ns, errors = super().analyze()
        references = (
            (VolumeEnvelopeEvent, "volume_envelopes"),
            (DutyEnvelopeEvent, "duty_envelopes"),
            (LfoEvent, "lfos"),
            (PitchEnvEvent, "pitch_envelopes"),
            (NoteEnvEvent, "note_envelopes"),
        )
        for channel in ns.channels.values():
            for event in channel.events:
                for event_type, table_name in references:
                    if (
                        isinstance(event, event_type)
                        and not event.is_definition
                        and not getattr(event, "is_off", False)
                        and event.slot not in ns.definitions[table_name]
                    ):
                        self.ctx.add_error(
                            ErrorCode.SEMANTIC_UNDEFINED_REFERENCE,
                            0,
                            0,
                            f"未定義のエフェクトスロット {event.slot} です。",
                            "error",
                            "先に同じ番号の定義を追加してください。",
                        )
        if self.loop_start is not None:
            max_tick = max(ch.total_ticks for ch in ns.channels.values())
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
        self.detune_cents = 0.0

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
                message=f"チャンネル '{self.current_channel}' で '@' は使用できません。",
                severity="warning",
                hint="Triangleチャンネルはデューティ比を持ちません。@ コマンドを削除してください。",
                context=self._context_line(stmt),
            )
            return
        if not 0 <= stmt.value <= 3:
            self.ctx.add_error(
                code=ErrorCode.SEMANTIC_VALUE_OUT_OF_RANGE,
                line=stmt.line,
                column=stmt.column,
                message=f"'@' の値 {stmt.value} は範囲外です。有効範囲: 0〜3。",
                severity="error",
                hint="例: @2 のように指定してください。",
                context=self._context_line(stmt),
            )
            return
        self.duty = stmt.value
        self._add_event(DutyEvent(tick_position=self.tick_position, value=stmt.value))

    def _analyze_quantize(self, stmt: QuantizeStmt) -> None:
        if not 1 <= stmt.value <= 8:
            self.ctx.add_error(
                code=ErrorCode.SEMANTIC_VALUE_OUT_OF_RANGE,
                line=stmt.line,
                column=stmt.column,
                message=f"'q' の値 {stmt.value} は範囲外です。有効範囲: 1〜8。",
                severity="error",
                hint="例: q4 のように指定してください。",
                context=self._context_line(stmt),
            )
            return
        self.gate_time = stmt.value / 8.0
        self._add_event(
            QuantizeEvent(tick_position=self.tick_position, value=stmt.value)
        )

    def _analyze_tie_cmd(self, stmt: TieCmdStmt) -> None:
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

    def _analyze_detune_cmd(self, stmt: DetuneCmdStmt) -> None:
        self.detune_cents = float(stmt.value)
        self._add_event(DetuneEvent(tick_position=self.tick_position, value=stmt.value))

    def _analyze_relative_volume(self, stmt: RelativeVolumeStmt) -> None:
        self.velocity = clamp(self.velocity + stmt.delta, 0, 15)
        self._add_event(
            RelativeVolumeEvent(tick_position=self.tick_position, delta=stmt.delta)
        )

    def _analyze_sweep(self, stmt: SweepStmt) -> None:
        if self.current_channel not in PULSE_CHANNELS:
            self.ctx.add_error(
                ErrorCode.SEMANTIC_CHANNEL_MISMATCH,
                stmt.line,
                stmt.column,
                "スイープはPulseチャンネル専用です。",
                "error",
                "AまたはBトラックで使用してください。",
                self._context_line(stmt),
            )
            return
        if not 0 <= stmt.speed <= 7 or not 1 <= abs(stmt.depth) <= 7:
            self.ctx.add_error(
                ErrorCode.SEMANTIC_VALUE_OUT_OF_RANGE,
                stmt.line,
                stmt.column,
                "スイープ値はspeed=0〜7、depth=±1〜±7で指定してください。",
                "error",
                context=self._context_line(stmt),
            )
            return
        self._add_event(
            SweepEvent(
                tick_position=self.tick_position,
                speed=stmt.speed,
                depth=stmt.depth,
            )
        )

    def _analyze_vol_env_use(self, stmt: VolumeEnvelopeUseStmt) -> None:
        self._add_event(
            VolumeEnvelopeEvent(tick_position=self.tick_position, slot=stmt.slot)
        )

    def _analyze_vol_env_def(self, stmt: VolumeEnvelopeDefStmt) -> None:
        self._define(
            "volume_envelopes",
            stmt.slot,
            {"points": stmt.points, "loop_points": stmt.loop_points},
        )
        if self.current_channel is not None:
            self._add_event(
                VolumeEnvelopeEvent(
                    tick_position=self.tick_position,
                    slot=stmt.slot,
                    points=stmt.points,
                    loop_points=stmt.loop_points,
                    is_definition=True,
                )
            )

    def _analyze_duty_env_def(self, stmt: DutyEnvelopeDefStmt) -> None:
        self._define(
            "duty_envelopes",
            stmt.slot,
            {"points": stmt.points, "loop_points": stmt.loop_points},
        )
        if self.current_channel is not None:
            self._add_event(
                DutyEnvelopeEvent(
                    tick_position=self.tick_position,
                    slot=stmt.slot,
                    points=stmt.points,
                    loop_points=stmt.loop_points,
                    is_definition=True,
                )
            )

    def _analyze_duty_env_use(self, stmt: DutyEnvelopeUseStmt) -> None:
        if self.current_channel is not None:
            self._add_event(
                DutyEnvelopeEvent(tick_position=self.tick_position, slot=stmt.slot)
            )

    def _analyze_lfo_def(self, stmt: LfoDefStmt) -> None:
        if stmt.transition != 0 or stmt.speed <= 0:
            self.ctx.add_error(
                ErrorCode.SEMANTIC_VALUE_OUT_OF_RANGE,
                stmt.line,
                stmt.column,
                "@MPはspeed>0、transition=0で指定してください。",
                "error",
                context=self._context_line(stmt),
            )
            return
        self._define(
            "lfos",
            stmt.slot,
            {
                "delay": stmt.delay,
                "speed": stmt.speed,
                "depth": stmt.depth,
                "transition": stmt.transition,
            },
        )
        if self.current_channel is not None:
            self._add_event(
                LfoEvent(
                    tick_position=self.tick_position,
                    slot=stmt.slot,
                    delay=stmt.delay,
                    speed=stmt.speed,
                    depth=stmt.depth,
                    transition=stmt.transition,
                    is_definition=True,
                )
            )

    def _analyze_lfo_use(self, stmt: LfoUseStmt) -> None:
        self._add_event(LfoEvent(tick_position=self.tick_position, slot=stmt.slot))

    def _analyze_lfo_off(self, stmt: LfoOffStmt) -> None:
        self._add_event(LfoEvent(tick_position=self.tick_position, slot=0, is_off=True))

    def _analyze_pitch_env_def(self, stmt: PitchEnvDefStmt) -> None:
        self._define(
            "pitch_envelopes",
            stmt.slot,
            {"points": stmt.points, "loop_points": stmt.loop_points},
        )
        if self.current_channel is not None:
            self._add_event(
                PitchEnvEvent(
                    tick_position=self.tick_position,
                    slot=stmt.slot,
                    points=stmt.points,
                    loop_points=stmt.loop_points,
                    is_definition=True,
                )
            )

    def _analyze_pitch_env_use(self, stmt: PitchEnvUseStmt) -> None:
        self._add_event(PitchEnvEvent(tick_position=self.tick_position, slot=stmt.slot))

    def _analyze_pitch_env_off(self, stmt: PitchEnvOffStmt) -> None:
        self._add_event(
            PitchEnvEvent(tick_position=self.tick_position, slot=0, is_off=True)
        )

    def _analyze_note_env_def(self, stmt: NoteEnvDefStmt) -> None:
        self._define(
            "note_envelopes",
            stmt.slot,
            {"points": stmt.points, "loop_points": stmt.loop_points},
        )
        if self.current_channel is not None:
            self._add_event(
                NoteEnvEvent(
                    tick_position=self.tick_position,
                    slot=stmt.slot,
                    points=stmt.points,
                    loop_points=stmt.loop_points,
                    is_definition=True,
                )
            )

    def _analyze_note_env_use(self, stmt: NoteEnvUseStmt) -> None:
        self._add_event(NoteEnvEvent(tick_position=self.tick_position, slot=stmt.slot))

    def _analyze_note_env_off(self, stmt: NoteEnvOffStmt) -> None:
        self._add_event(
            NoteEnvEvent(tick_position=self.tick_position, slot=0, is_off=True)
        )

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
        if self.tick_position == 0:
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
        # VolumeEnvelopeDefStmt is handled by _analyze_vol_env_def.
        # SweepStmt is handled by _analyze_sweep.
        # Remaining stage2 items: count-length notes, noise mode, pyxel ext.
        super()._analyze_stage2(stmt)


def analyze_ppmck(
    source: str, program: Program
) -> tuple[NoteSequence, list[ErrorDetail]]:
    analyzer = PpmckSemanticAnalyzer(source, program)
    return analyzer.analyze()
