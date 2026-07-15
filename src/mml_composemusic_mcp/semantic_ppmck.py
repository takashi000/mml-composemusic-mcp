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
from .parser_base import clamp, note_to_midi
from .semantic_base import SemanticAnalyzer

PULSE_CHANNELS = {"Pulse1", "Pulse2"}


class PpmckSemanticAnalyzer(SemanticAnalyzer):
    def __init__(self, source: str, program: Program) -> None:
        super().__init__(source, program)
        self.note_sequence.mode = "ppmck"
        self.loop_start: int | None = None
        self.detune_cents = 0.0

    def _define(self, kind: str, slot: int, value: dict, stmt) -> bool:  # type: ignore[no-untyped-def]
        if not self._validate_range(stmt, slot, 0, 255, "エフェクトスロット"):
            return False
        table = self.note_sequence.definitions[kind]
        if slot in table:
            self.ctx.add_error(
                ErrorCode.SEMANTIC_DUPLICATE_DEFINITION,
                stmt.line,
                stmt.column,
                f"エフェクトスロット {slot} は既に定義されています。",
                "error",
                "別のスロット番号を使用してください。",
                self._context_line(stmt),
            )
            return False
        table[slot] = value
        return True

    def _validate_values(
        self,
        stmt,
        values: list[int],
        minimum: int,
        maximum: int,
        label: str,  # type: ignore[no-untyped-def]
    ) -> bool:
        return all(
            self._validate_range(stmt, value, minimum, maximum, label)
            for value in values
        )

    def _use_defined(self, stmt, kind: str, slot: int) -> bool:  # type: ignore[no-untyped-def]
        if not self._validate_range(stmt, slot, 0, 255, "エフェクトスロット"):
            return False
        if slot in self.note_sequence.definitions[kind]:
            return True
        self.ctx.add_error(
            ErrorCode.SEMANTIC_UNDEFINED_REFERENCE,
            stmt.line,
            stmt.column,
            f"未定義のエフェクトスロット {slot} です。",
            "error",
            "先に同じ番号の定義を追加してください。",
            self._context_line(stmt),
        )
        return False

    def analyze(self) -> tuple[NoteSequence, list[ErrorDetail]]:
        ns, errors = super().analyze()
        if self.loop_start is not None:
            max_tick = max(ch.total_ticks for ch in ns.channels.values())
            if self.loop_start >= max_tick:
                loop_track = next(
                    track for track in self.program.tracks if track.channel == "Loop"
                )
                self.ctx.add_error(
                    ErrorCode.SEMANTIC_VALUE_OUT_OF_RANGE,
                    loop_track.line,
                    loop_track.column,
                    f"Lトラックのloop_start {self.loop_start} は曲長 {max_tick} 以上です。",
                    "error",
                    "Lトラックの時間を音声トラックの曲長より短くしてください。",
                    self._context_line(loop_track),
                )
                return ns, errors
            for ch in ns.channels.values():
                ch.events.append(
                    RepeatEvent(
                        tick_position=max_tick,
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

    def _handle_loop_track(self, track: Track) -> None:
        statements = self._expand_repeats(track.statements)
        if statements is None:
            return
        for stmt in statements:
            if isinstance(stmt, LengthStmt):
                self._analyze_length(stmt)
            elif isinstance(stmt, RestStmt):
                ticks = self._ticks_for(stmt)
                if ticks is not None:
                    self.tick_position += ticks
        self.loop_start = self.tick_position

    def _analyze_note(self, stmt: NoteStmt) -> None:
        ticks = self._ticks_for(stmt)
        if ticks is None:
            return
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
        if self.current_channel == "Triangle":
            return
        self.velocity = stmt.value
        self._add_event(VolumeEvent(tick_position=self.tick_position, value=stmt.value))

    def _analyze_duty(self, stmt: DutyStmt) -> None:
        if not self._validate_range(stmt, stmt.value, 0, 3, "デューティ比"):
            return
        if self.current_channel not in PULSE_CHANNELS:
            self.ctx.add_error(
                code=ErrorCode.SEMANTIC_CHANNEL_MISMATCH,
                line=stmt.line,
                column=stmt.column,
                message=f"チャンネル '{self.current_channel}' で '@' は使用できません。",
                severity="error",
                hint="Triangleチャンネルはデューティ比を持ちません。@ コマンドを削除してください。",
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

    def _analyze_detune_cmd(self, stmt: DetuneCmdStmt) -> None:
        if not self._validate_range(stmt, stmt.value, -127, 126, "ディチューン"):
            return
        self.detune_cents = float(stmt.value)
        self._add_event(DetuneEvent(tick_position=self.tick_position, value=stmt.value))

    def _analyze_relative_volume(self, stmt: RelativeVolumeStmt) -> None:
        if not self._validate_range(stmt, abs(stmt.delta), 1, 15, "相対音量"):
            return
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
        if not self._use_defined(stmt, "volume_envelopes", stmt.slot):
            return
        self._add_event(
            VolumeEnvelopeEvent(tick_position=self.tick_position, slot=stmt.slot)
        )

    def _analyze_vol_env_def(self, stmt: VolumeEnvelopeDefStmt) -> None:
        if not self._validate_values(
            stmt, stmt.points + stmt.loop_points, 0, 15, "音量エンベロープ"
        ):
            return
        if not self._define(
            "volume_envelopes",
            stmt.slot,
            {"points": stmt.points, "loop_points": stmt.loop_points},
            stmt,
        ):
            return
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
        if not self._validate_values(
            stmt, stmt.points + stmt.loop_points, 0, 3, "デューティエンベロープ"
        ):
            return
        if not self._define(
            "duty_envelopes",
            stmt.slot,
            {"points": stmt.points, "loop_points": stmt.loop_points},
            stmt,
        ):
            return
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
        if not self._use_defined(stmt, "duty_envelopes", stmt.slot):
            return
        if self.current_channel is not None:
            self._add_event(
                DutyEnvelopeEvent(tick_position=self.tick_position, slot=stmt.slot)
            )

    def _analyze_lfo_def(self, stmt: LfoDefStmt) -> None:
        if not (
            self._validate_range(stmt, stmt.delay, 0, 255, "LFO delay")
            and self._validate_range(stmt, stmt.speed, 1, 255, "LFO period")
            and self._validate_range(stmt, stmt.depth, 0, 255, "LFO depth")
            and stmt.transition == 0
        ):
            if stmt.transition == 0:
                return
            self.ctx.add_error(
                ErrorCode.SEMANTIC_VALUE_OUT_OF_RANGE,
                stmt.line,
                stmt.column,
                "@MPはspeed>0、transition=0で指定してください。",
                "error",
                context=self._context_line(stmt),
            )
            return
        if not self._define(
            "lfos",
            stmt.slot,
            {
                "delay": stmt.delay,
                "speed": stmt.speed,
                "depth": stmt.depth,
                "transition": stmt.transition,
            },
            stmt,
        ):
            return
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
        if not self._use_defined(stmt, "lfos", stmt.slot):
            return
        self._add_event(LfoEvent(tick_position=self.tick_position, slot=stmt.slot))

    def _analyze_lfo_off(self, stmt: LfoOffStmt) -> None:
        self._add_event(LfoEvent(tick_position=self.tick_position, slot=0, is_off=True))

    def _analyze_pitch_env_def(self, stmt: PitchEnvDefStmt) -> None:
        if not self._validate_values(
            stmt, stmt.points + stmt.loop_points, -127, 126, "ピッチエンベロープ"
        ):
            return
        if not self._define(
            "pitch_envelopes",
            stmt.slot,
            {"points": stmt.points, "loop_points": stmt.loop_points},
            stmt,
        ):
            return
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
        if not self._use_defined(stmt, "pitch_envelopes", stmt.slot):
            return
        self._add_event(PitchEnvEvent(tick_position=self.tick_position, slot=stmt.slot))

    def _analyze_pitch_env_off(self, stmt: PitchEnvOffStmt) -> None:
        self._add_event(
            PitchEnvEvent(tick_position=self.tick_position, slot=0, is_off=True)
        )

    def _analyze_note_env_def(self, stmt: NoteEnvDefStmt) -> None:
        if not self._validate_values(
            stmt, stmt.points + stmt.loop_points, -127, 126, "ノートエンベロープ"
        ):
            return
        if not self._define(
            "note_envelopes",
            stmt.slot,
            {"points": stmt.points, "loop_points": stmt.loop_points},
            stmt,
        ):
            return
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
        if not self._use_defined(stmt, "note_envelopes", stmt.slot):
            return
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
