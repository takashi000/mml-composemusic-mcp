"""Base semantic analyzer: AST -> NoteSequence IR."""

from dataclasses import dataclass, field

from .ast_nodes import (
    ASTNode,
    BarStmt,
    DetuneStmt,
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
    Statement,
    TempoStmt,
    TieStmt,
    Track,
    TransposeStmt,
    VolumeStmt,
)
from .ir import (
    ErrorCode,
    ErrorDetail,
    ErrorPhase,
    NoteEvent,
    NoteSequence,
    RestEvent,
)
from .parser_base import length_value_to_ticks


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

    def analyze(self) -> tuple[NoteSequence, list[ErrorDetail]]:
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
        for stmt in track.statements:
            self._analyze_statement(stmt)

    def _reset_state(self, track: Track) -> None:
        self.octave = 4
        self.default_length = 4
        self.velocity = 15
        self.gate_time = 1.0
        self.duty = 2
        self.tick_position = 0

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
        elif isinstance(stmt, TieStmt):
            self._analyze_tie(stmt)
        elif isinstance(stmt, RepeatStartStmt):
            self._analyze_repeat_start(stmt)
        elif isinstance(stmt, RepeatEndStmt):
            self._analyze_repeat_end(stmt)
        elif isinstance(stmt, BarStmt):
            pass
        elif isinstance(stmt, ExtCmdStmt):
            self._analyze_ext_cmd(stmt)
        elif isinstance(stmt, EnvelopeDefStmt):
            self._analyze_stage2(stmt)
        else:
            self._analyze_stage2(stmt)

    def _ticks_for(self, stmt: NoteStmt | RestStmt) -> int:
        length = stmt.length if stmt.length is not None else self.default_length
        return length_value_to_ticks(length, stmt.dots)

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

    def _analyze_tie(self, stmt: TieStmt) -> None:
        raise NotImplementedError

    def _analyze_repeat_start(self, stmt: RepeatStartStmt) -> None:
        raise NotImplementedError

    def _analyze_repeat_end(self, stmt: RepeatEndStmt) -> None:
        raise NotImplementedError

    def _analyze_ext_cmd(self, stmt: ExtCmdStmt) -> None:
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
