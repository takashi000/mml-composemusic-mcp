"""Base semantic analyzer: AST -> NoteSequence IR."""

from dataclasses import dataclass, field

from .ast_nodes import (
    ASTNode,
    BarStmt,
    DetuneCmdStmt,
    DetuneStmt,
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
    RepeatBreakStmt,
    RepeatEndStmt,
    RepeatStartStmt,
    RestStmt,
    Statement,
    SweepStmt,
    TempoStmt,
    TieCmdStmt,
    TieStmt,
    Track,
    TransposeStmt,
    VolumeEnvelopeDefStmt,
    VolumeEnvelopeUseStmt,
    VolumeStmt,
)
from .ir import (
    ErrorCode,
    ErrorDetail,
    ErrorPhase,
    NoteEvent,
    NoteSequence,
    RepeatEvent,
    RestEvent,
)
from .parser_base import length_value_to_ticks

MAX_EXPANDED_EVENTS = 100_000


@dataclass
class SemanticContext:
    errors: list[ErrorDetail] = field(default_factory=list)

    def add_error(
        self,
        code: ErrorCode,
        line: int,
        column: int,
        message: str,
        severity: str,
        hint: str = "",
        context: str = "",
    ) -> None:
        self.errors.append(
            ErrorDetail(
                code=code,
                phase=ErrorPhase.SEMANTIC,
                line=line,
                column=column,
                message=message,
                severity=severity,
                hint=hint,
                context=context,
            )
        )


class SemanticAnalyzer:
    """Base class for converting AST to NoteSequence IR."""

    def __init__(self, source: str, program: Program) -> None:
        self.source = source
        self.program = program
        self.ctx = SemanticContext()
        self.note_sequence = NoteSequence()
        self.current_channel: str | None = None
        self.octave = 4
        self.default_length = 4
        self.velocity = 15
        self.gate_time = 1.0
        self.duty = 2
        self.tick_position = 0
        self.repeat_tick_stack: list[int] = []

    def analyze(self) -> tuple[NoteSequence, list[ErrorDetail]]:
        self.current_channel = None
        for stmt in self.program.global_statements:
            self._analyze_statement(stmt)
        for track in self.program.tracks:
            self._analyze_track(track)
        self._finalize()
        return self.note_sequence, self.ctx.errors

    def _analyze_track(self, track: Track) -> None:
        self.current_channel = track.channel
        self._reset_state(track)
        if track.channel == "Loop":
            self._handle_loop_track(track)
            return
        statements = self._expand_repeats(track.statements)
        if statements is None:
            return
        for stmt in statements:
            self._analyze_statement(stmt)

    def _reset_state(self, track: Track) -> None:
        self.octave = 4
        self.default_length = 4
        self.velocity = 15
        self.gate_time = 1.0
        self.duty = 2
        self.tick_position = 0
        self.repeat_tick_stack = []

    def _handle_loop_track(self, track: Track) -> None:
        # Loop track is handled after all tracks are processed.
        pass

    def _finalize(self) -> None:
        for ch in self.note_sequence.channels.values():
            ch.total_ticks = max(
                (e.tick_position + getattr(e, "duration", 0) for e in ch.events),
                default=0,
            )

    def _analyze_statement(self, stmt: Statement) -> None:
        if isinstance(stmt, NoteStmt):
            self._analyze_note(stmt)
        elif isinstance(stmt, RestStmt):
            self._analyze_rest(stmt)
        elif isinstance(stmt, OctaveStmt):
            self._analyze_octave(stmt)
        elif isinstance(stmt, LengthStmt):
            self._analyze_length(stmt)
        elif isinstance(stmt, VolumeStmt):
            self._analyze_volume(stmt)
        elif isinstance(stmt, DutyStmt):
            self._analyze_duty(stmt)
        elif isinstance(stmt, TempoStmt):
            self._analyze_tempo(stmt)
        elif isinstance(stmt, GateTimeStmt):
            self._analyze_gate_time(stmt)
        elif isinstance(stmt, TransposeStmt):
            self._analyze_transpose(stmt)
        elif isinstance(stmt, DetuneStmt):
            self._analyze_detune(stmt)
        elif isinstance(stmt, QuantizeStmt):
            self._analyze_quantize(stmt)
        elif isinstance(stmt, TieStmt):
            self._analyze_tie(stmt)
        elif isinstance(stmt, TieCmdStmt):
            self._analyze_tie_cmd(stmt)
        elif isinstance(stmt, DetuneCmdStmt):
            self._analyze_detune_cmd(stmt)
        elif isinstance(stmt, RelativeVolumeStmt):
            self._analyze_relative_volume(stmt)
        elif isinstance(stmt, RepeatStartStmt):
            self._analyze_repeat_start(stmt)
        elif isinstance(stmt, RepeatBreakStmt):
            pass
        elif isinstance(stmt, RepeatEndStmt):
            self._analyze_repeat_end(stmt)
        elif isinstance(stmt, BarStmt):
            pass
        elif isinstance(stmt, ExtCmdStmt):
            self._analyze_ext_cmd(stmt)
        elif isinstance(stmt, VolumeEnvelopeUseStmt):
            self._analyze_vol_env_use(stmt)
        elif isinstance(stmt, VolumeEnvelopeDefStmt):
            self._analyze_vol_env_def(stmt)
        elif isinstance(stmt, DutyEnvelopeDefStmt):
            self._analyze_duty_env_def(stmt)
        elif isinstance(stmt, DutyEnvelopeUseStmt):
            self._analyze_duty_env_use(stmt)
        elif isinstance(stmt, LfoDefStmt):
            self._analyze_lfo_def(stmt)
        elif isinstance(stmt, LfoUseStmt):
            self._analyze_lfo_use(stmt)
        elif isinstance(stmt, LfoOffStmt):
            self._analyze_lfo_off(stmt)
        elif isinstance(stmt, PitchEnvDefStmt):
            self._analyze_pitch_env_def(stmt)
        elif isinstance(stmt, PitchEnvUseStmt):
            self._analyze_pitch_env_use(stmt)
        elif isinstance(stmt, PitchEnvOffStmt):
            self._analyze_pitch_env_off(stmt)
        elif isinstance(stmt, NoteEnvDefStmt):
            self._analyze_note_env_def(stmt)
        elif isinstance(stmt, NoteEnvUseStmt):
            self._analyze_note_env_use(stmt)
        elif isinstance(stmt, NoteEnvOffStmt):
            self._analyze_note_env_off(stmt)
        elif isinstance(stmt, SweepStmt):
            self._analyze_sweep(stmt)
        else:
            self._analyze_stage2(stmt)

    def _ticks_for(self, stmt: NoteStmt | RestStmt) -> int | None:
        length = stmt.length if stmt.length is not None else self.default_length
        if not 1 <= length <= 192:
            self.ctx.add_error(
                code=ErrorCode.SEMANTIC_VALUE_OUT_OF_RANGE,
                line=stmt.line,
                column=stmt.column,
                message=f"音長 {length} は範囲外です。有効範囲: 1〜192。",
                severity="error",
                hint="1〜192の音長を指定してください。",
                context=self._context_line(stmt),
            )
            return None
        return length_value_to_ticks(length, stmt.dots)

    def _ticks_for_value(self, value: int, stmt: ASTNode) -> int | None:
        if not 1 <= value <= 192:
            self.ctx.add_error(
                code=ErrorCode.SEMANTIC_VALUE_OUT_OF_RANGE,
                line=stmt.line,
                column=stmt.column,
                message=f"タイ音長 {value} は範囲外です。有効範囲: 1〜192。",
                severity="error",
                hint="1〜192の音長を指定してください。",
                context=self._context_line(stmt),
            )
            return None
        return length_value_to_ticks(value, 0)

    def _validate_range(
        self, stmt: ASTNode, value: int, minimum: int, maximum: int, label: str
    ) -> bool:
        if minimum <= value <= maximum:
            return True
        self.ctx.add_error(
            code=ErrorCode.SEMANTIC_VALUE_OUT_OF_RANGE,
            line=stmt.line,
            column=stmt.column,
            message=(
                f"{label}の値 {value} は範囲外です。有効範囲: {minimum}〜{maximum}。"
            ),
            severity="error",
            context=self._context_line(stmt),
        )
        return False

    def _analyze_note(self, stmt: NoteStmt) -> None:
        raise NotImplementedError

    def _analyze_rest(self, stmt: RestStmt) -> None:
        raise NotImplementedError

    def _analyze_octave(self, stmt: OctaveStmt) -> None:
        raise NotImplementedError

    def _analyze_length(self, stmt: LengthStmt) -> None:
        raise NotImplementedError

    def _analyze_volume(self, stmt: VolumeStmt) -> None:
        raise NotImplementedError

    def _analyze_duty(self, stmt: DutyStmt) -> None:
        raise NotImplementedError

    def _analyze_tempo(self, stmt: TempoStmt) -> None:
        raise NotImplementedError

    def _analyze_gate_time(self, stmt: GateTimeStmt) -> None:
        raise NotImplementedError

    def _analyze_quantize(self, stmt: QuantizeStmt) -> None:
        raise NotImplementedError

    def _analyze_tie(self, stmt: TieStmt) -> None:
        raise NotImplementedError

    def _analyze_tie_cmd(self, stmt: TieCmdStmt) -> None:
        raise NotImplementedError

    def _analyze_detune_cmd(self, stmt: DetuneCmdStmt) -> None:
        raise NotImplementedError

    def _analyze_relative_volume(self, stmt: RelativeVolumeStmt) -> None:
        raise NotImplementedError

    def _analyze_repeat_start(self, stmt: RepeatStartStmt) -> None:
        self.repeat_tick_stack.append(self.tick_position)

    def _analyze_repeat_end(self, stmt: RepeatEndStmt) -> None:
        if not self.repeat_tick_stack:
            return
        start_tick = self.repeat_tick_stack.pop()
        self._add_event(
            RepeatEvent(
                tick_position=self.tick_position,
                start_tick=start_tick,
                end_tick=self.tick_position,
                repeat_count=0 if stmt.count is None else stmt.count,
            )
        )

    def _analyze_ext_cmd(self, stmt: ExtCmdStmt) -> None:
        raise NotImplementedError

    def _analyze_vol_env_use(self, stmt: VolumeEnvelopeUseStmt) -> None:
        raise NotImplementedError

    def _analyze_vol_env_def(self, stmt: VolumeEnvelopeDefStmt) -> None:
        raise NotImplementedError

    def _analyze_duty_env_def(self, stmt: DutyEnvelopeDefStmt) -> None:
        raise NotImplementedError

    def _analyze_duty_env_use(self, stmt: DutyEnvelopeUseStmt) -> None:
        raise NotImplementedError

    def _analyze_lfo_def(self, stmt: LfoDefStmt) -> None:
        raise NotImplementedError

    def _analyze_lfo_use(self, stmt: LfoUseStmt) -> None:
        raise NotImplementedError

    def _analyze_lfo_off(self, stmt: LfoOffStmt) -> None:
        raise NotImplementedError

    def _analyze_pitch_env_def(self, stmt: PitchEnvDefStmt) -> None:
        raise NotImplementedError

    def _analyze_pitch_env_use(self, stmt: PitchEnvUseStmt) -> None:
        raise NotImplementedError

    def _analyze_pitch_env_off(self, stmt: PitchEnvOffStmt) -> None:
        raise NotImplementedError

    def _analyze_note_env_def(self, stmt: NoteEnvDefStmt) -> None:
        raise NotImplementedError

    def _analyze_note_env_use(self, stmt: NoteEnvUseStmt) -> None:
        raise NotImplementedError

    def _analyze_note_env_off(self, stmt: NoteEnvOffStmt) -> None:
        raise NotImplementedError

    def _analyze_sweep(self, stmt: SweepStmt) -> None:
        raise NotImplementedError

    def _analyze_stage2(self, stmt: ASTNode) -> None:
        self.ctx.add_error(
            code=ErrorCode.SEMANTIC_UNSUPPORTED_FEATURE,
            line=stmt.line,
            column=stmt.column,
            message=f"'{stmt.__class__.__name__}' は第2段階で実装されます。",
            severity="warning",
            hint="現時点では無視されます。",
            context=self._context_line(stmt),
        )

    def _add_event(self, event) -> None:  # type: ignore[no-untyped-def]
        ch = self.note_sequence.channels[self.current_channel]  # type: ignore[index]
        ch.events.append(event)

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

    def _context_line(self, node: ASTNode) -> str:
        lines = self.source.splitlines()
        if 1 <= node.line <= len(lines):
            return lines[node.line - 1]
        return ""

    def _expand_repeats(self, statements: list[Statement]) -> list[Statement] | None:
        """Expand nested repeats transactionally before semantic state updates."""
        initial_error_count = sum(e.severity == "error" for e in self.ctx.errors)

        def segment(index: int) -> tuple[list[Statement], int, str | None]:
            result: list[Statement] = []
            while index < len(statements):
                stmt = statements[index]
                if isinstance(stmt, RepeatBreakStmt):
                    return result, index + 1, "break"
                if isinstance(stmt, RepeatEndStmt):
                    return result, index + 1, "end"
                if not isinstance(stmt, RepeatStartStmt):
                    result.append(stmt)
                    index += 1
                    continue

                prefix, index, terminator = segment(index + 1)
                suffix: list[Statement] = []
                if terminator == "break":
                    suffix, index, terminator = segment(index)
                if terminator != "end":
                    return result, index, terminator

                end_stmt = statements[index - 1]
                assert isinstance(end_stmt, RepeatEndStmt)
                count = end_stmt.count
                if count is not None and count < 1:
                    self.ctx.add_error(
                        code=ErrorCode.SEMANTIC_VALUE_OUT_OF_RANGE,
                        line=end_stmt.line,
                        column=end_stmt.column,
                        message="リピート回数は1以上で指定してください。",
                        severity="error",
                        context=self._context_line(end_stmt),
                    )
                    return [], len(statements), None

                full = prefix + suffix
                prefix_cost = sum(self._event_cost(item) for item in prefix)
                full_cost = sum(self._event_cost(item) for item in full)
                if count is None:
                    body_cost = full_cost * 2
                elif suffix:
                    body_cost = full_cost * (count - 1) + prefix_cost
                else:
                    body_cost = prefix_cost * count
                projected = (
                    sum(self._event_cost(item) for item in result)
                    + body_cost
                    + self._event_cost(end_stmt)
                )
                if projected > MAX_EXPANDED_EVENTS:
                    self._add_repeat_limit_error(end_stmt, projected)
                    return [], len(statements), None
                expanded_body: list[Statement] = []
                if count is None:
                    expanded_body = full * 2
                    self.ctx.add_error(
                        code=ErrorCode.SEMANTIC_UNSUPPORTED_FEATURE,
                        line=end_stmt.line,
                        column=end_stmt.column,
                        message="無限リピートはWAV生成用IRで2回に展開されます。",
                        severity="warning",
                        hint="IRのRepeatEventにはrepeat_count=0を保持します。",
                        context=self._context_line(end_stmt),
                    )
                elif suffix:
                    expanded_body = full * (count - 1) + prefix
                else:
                    expanded_body = prefix * count
                result.extend([stmt, *expanded_body, end_stmt])
            return result, index, None

        expanded, _, _ = segment(0)
        if sum(e.severity == "error" for e in self.ctx.errors) > initial_error_count:
            return None
        projected = sum(self._event_cost(stmt) for stmt in expanded)
        if projected > MAX_EXPANDED_EVENTS:
            node = next(
                (
                    stmt
                    for stmt in reversed(statements)
                    if isinstance(stmt, RepeatEndStmt)
                ),
                statements[-1] if statements else ASTNode(line=1, column=1),
            )
            self._add_repeat_limit_error(node, projected)
            return None
        return expanded

    def _add_repeat_limit_error(self, node: ASTNode, projected: int) -> None:
        self.ctx.add_error(
            code=ErrorCode.SEMANTIC_VALUE_OUT_OF_RANGE,
            line=node.line,
            column=node.column,
            message=(
                f"リピート展開後のイベント数 {projected} が上限 "
                f"{MAX_EXPANDED_EVENTS} を超えます。"
            ),
            severity="error",
            hint="リピート回数またはリピート内のイベント数を減らしてください。",
            context=self._context_line(node),
        )

    def _event_cost(self, stmt: Statement) -> int:
        no_event = (
            BarStmt,
            LengthStmt,
            OctaveStmt,
            GateTimeStmt,
            TransposeStmt,
            TieStmt,
            TieCmdStmt,
            RepeatStartStmt,
            RepeatBreakStmt,
        )
        return 0 if isinstance(stmt, no_event) else 1
