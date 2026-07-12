"""Intermediate representation for MML NoteSequence and errors."""

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class ErrorPhase(Enum):
    """Phase where an error occurred."""

    LEXER = "lexer"
    SYNTAX = "syntax"
    SEMANTIC = "semantic"
    RUNTIME = "runtime"
    API = "api"


class ErrorCode(Enum):
    """Machine-readable error codes.

    Errors are classified by phase:
    - SYNTAX_*: token sequence violates the BNF grammar.
    - SEMANTIC_*: syntactically valid but semantically invalid (range,
      channel mismatch, undefined reference, etc.).
    - RUNTIME_*: failure during synthesis or WAV output.
    - VALIDATION_*: API-level parameter validation errors.
    """

    # --- Syntax errors (Parser phase) ---
    SYNTAX_INVALID_TOKEN = "SYNTAX_INVALID_TOKEN"
    SYNTAX_INVALID_NUMBER = "SYNTAX_INVALID_NUMBER"
    SYNTAX_UNEXPECTED_TOKEN = "SYNTAX_UNEXPECTED_TOKEN"
    SYNTAX_UNTERMINATED_REPEAT = "SYNTAX_UNTERMINATED_REPEAT"
    SYNTAX_UNMATCHED_REPEAT_END = "SYNTAX_UNMATCHED_REPEAT_END"
    SYNTAX_UNTERMINATED_TIE = "SYNTAX_UNTERMINATED_TIE"
    SYNTAX_INVALID_TRACK_HEADER = "SYNTAX_INVALID_TRACK_HEADER"
    SYNTAX_DUPLICATE_TRACK = "SYNTAX_DUPLICATE_TRACK"
    SYNTAX_UNTERMINATED_HEADER = "SYNTAX_UNTERMINATED_HEADER"

    # --- Semantic errors (SemanticAnalyzer phase) ---
    SEMANTIC_VALUE_OUT_OF_RANGE = "SEMANTIC_VALUE_OUT_OF_RANGE"
    SEMANTIC_NOTE_OUT_OF_RANGE = "SEMANTIC_NOTE_OUT_OF_RANGE"
    SEMANTIC_CHANNEL_MISMATCH = "SEMANTIC_CHANNEL_MISMATCH"
    SEMANTIC_EMPTY_TRACK = "SEMANTIC_EMPTY_TRACK"
    SEMANTIC_OUTSIDE_TRACK = "SEMANTIC_OUTSIDE_TRACK"
    SEMANTIC_UNDEFINED_REFERENCE = "SEMANTIC_UNDEFINED_REFERENCE"
    SEMANTIC_DUPLICATE_DEFINITION = "SEMANTIC_DUPLICATE_DEFINITION"
    SEMANTIC_UNSUPPORTED_FEATURE = "SEMANTIC_UNSUPPORTED_FEATURE"

    # --- Runtime errors (Synthesizer phase) ---
    RUNTIME_SYNTHESIS_FAILED = "RUNTIME_SYNTHESIS_FAILED"
    RUNTIME_WAV_WRITE_FAILED = "RUNTIME_WAV_WRITE_FAILED"
    RUNTIME_INTERNAL_ERROR = "RUNTIME_INTERNAL_ERROR"

    # --- API-level errors (parameter validation, not MML syntax) ---
    VALIDATION_MISSING_PARAMETER = "VALIDATION_MISSING_PARAMETER"
    VALIDATION_INVALID_MODE = "VALIDATION_INVALID_MODE"
    VALIDATION_INVALID_ACTION = "VALIDATION_INVALID_ACTION"


@dataclass
class ErrorDetail:
    """Structured error/warning detail."""

    code: ErrorCode
    phase: ErrorPhase
    line: int
    column: int
    message: str
    severity: str  # "error" | "warning"
    hint: str = ""
    context: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "code": self.code.value,
            "phase": self.phase.value,
            "line": self.line,
            "column": self.column,
            "message": self.message,
            "severity": self.severity,
            "hint": self.hint,
            "context": self.context,
        }


@dataclass
class NoteEvent:
    type: str = "note"
    tick_position: int = 0
    duration: int = 0
    note_number: int = 69
    velocity: int = 15
    duty: int = 2
    gate_time: float = 1.0
    detune_cents: float = 0.0


@dataclass
class RestEvent:
    type: str = "rest"
    tick_position: int = 0
    duration: int = 0


@dataclass
class VolumeEvent:
    type: str = "volume"
    tick_position: int = 0
    value: int = 15


@dataclass
class DutyEvent:
    type: str = "duty"
    tick_position: int = 0
    value: int = 2


@dataclass
class TempoEvent:
    type: str = "tempo"
    tick_position: int = 0
    bpm: int = 120


@dataclass
class RepeatEvent:
    type: str = "repeat"
    tick_position: int = 0
    start_tick: int = 0
    end_tick: int = 0
    repeat_count: int = 1
    duration: int = 0


@dataclass
class QuantizeEvent:
    type: str = "quantize"
    tick_position: int = 0
    value: int = 8  # 1-8


@dataclass
class DetuneEvent:
    type: str = "detune"
    tick_position: int = 0
    value: int = 0  # -127 to 126


@dataclass
class SweepEvent:
    type: str = "sweep"
    tick_position: int = 0
    speed: int = 0
    depth: int = 0


@dataclass
class RelativeVolumeEvent:
    type: str = "rel_volume"
    tick_position: int = 0
    delta: int = 0


@dataclass
class EnvelopeEvent:
    type: str = "envelope"
    tick_position: int = 0
    slot: int = 0
    points: list[dict[str, int]] = field(default_factory=list)


@dataclass
class VolumeEnvelopeEvent:
    type: str = "vol_envelope"
    tick_position: int = 0
    slot: int = 0
    points: list[int] = field(default_factory=list)
    loop_points: list[int] = field(default_factory=list)
    is_definition: bool = False


@dataclass
class DutyEnvelopeEvent:
    type: str = "duty_envelope"
    tick_position: int = 0
    slot: int = 0
    points: list[int] = field(default_factory=list)
    loop_points: list[int] = field(default_factory=list)
    is_definition: bool = False


@dataclass
class LfoEvent:
    type: str = "lfo"
    tick_position: int = 0
    slot: int = 0
    delay: int = 0
    speed: int = 0
    depth: int = 0
    transition: int = 0
    is_definition: bool = False
    is_off: bool = False


@dataclass
class PitchEnvEvent:
    type: str = "pitch_envelope"
    tick_position: int = 0
    slot: int = 0
    points: list[int] = field(default_factory=list)
    loop_points: list[int] = field(default_factory=list)
    is_definition: bool = False
    is_off: bool = False


@dataclass
class NoteEnvEvent:
    type: str = "note_envelope"
    tick_position: int = 0
    slot: int = 0
    points: list[int] = field(default_factory=list)
    loop_points: list[int] = field(default_factory=list)
    is_definition: bool = False
    is_off: bool = False


@dataclass
class VibratoEvent:
    type: str = "vibrato"
    tick_position: int = 0
    slot: int = 0
    params: dict[str, int] = field(default_factory=dict)


@dataclass
class GlideEvent:
    type: str = "glide"
    tick_position: int = 0
    slot: int = 0
    params: dict[str, int] = field(default_factory=dict)


Event = (
    NoteEvent
    | RestEvent
    | VolumeEvent
    | DutyEvent
    | TempoEvent
    | RepeatEvent
    | QuantizeEvent
    | DetuneEvent
    | SweepEvent
    | RelativeVolumeEvent
    | EnvelopeEvent
    | VolumeEnvelopeEvent
    | DutyEnvelopeEvent
    | LfoEvent
    | PitchEnvEvent
    | NoteEnvEvent
    | VibratoEvent
    | GlideEvent
)


@dataclass
class ChannelSequence:
    channel_type: str = "pulse"
    events: list[Event] = field(default_factory=list)
    total_ticks: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "channel_type": self.channel_type,
            "events": [event_to_dict(e) for e in self.events],
            "total_ticks": self.total_ticks,
        }


@dataclass
class NoteSequence:
    version: str = "2.0"
    bpm: int = 120
    ticks_per_quarter: int = 192
    mode: str = "ppmck"
    definitions: dict[str, dict[int, Any]] = field(
        default_factory=lambda: {
            "volume_envelopes": {},
            "duty_envelopes": {},
            "pitch_envelopes": {},
            "note_envelopes": {},
            "lfos": {},
            "envelopes": {},
            "vibratos": {},
            "glides": {},
        }
    )
    channels: dict[str, ChannelSequence] = field(
        default_factory=lambda: {
            "Pulse1": ChannelSequence("pulse"),
            "Pulse2": ChannelSequence("pulse"),
            "Triangle": ChannelSequence("triangle"),
            "Noise": ChannelSequence("noise"),
        }
    )

    def to_dict(self) -> dict[str, Any]:
        return {
            "version": self.version,
            "bpm": self.bpm,
            "ticks_per_quarter": self.ticks_per_quarter,
            "mode": self.mode,
            "definitions": self.definitions,
            "channels": {k: v.to_dict() for k, v in self.channels.items()},
        }


def event_to_dict(event: Event) -> dict[str, Any]:
    if isinstance(
        event,
        (
            NoteEvent,
            RestEvent,
            VolumeEvent,
            DutyEvent,
            TempoEvent,
            RepeatEvent,
            QuantizeEvent,
            DetuneEvent,
            SweepEvent,
            RelativeVolumeEvent,
            EnvelopeEvent,
            VolumeEnvelopeEvent,
            DutyEnvelopeEvent,
            LfoEvent,
            PitchEnvEvent,
            NoteEnvEvent,
            VibratoEvent,
            GlideEvent,
        ),
    ):
        return event.__dict__
    raise TypeError(f"Unsupported event type: {type(event)}")
