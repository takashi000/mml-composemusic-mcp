"""Intermediate representation for MML NoteSequence and errors."""

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class ErrorCode(Enum):
    """Machine-readable error codes."""

    SYNTAX_INVALID_TOKEN = "SYNTAX_INVALID_TOKEN"
    SYNTAX_INVALID_NUMBER = "SYNTAX_INVALID_NUMBER"
    SYNTAX_VALUE_OUT_OF_RANGE = "SYNTAX_VALUE_OUT_OF_RANGE"
    SYNTAX_UNEXPECTED_TOKEN = "SYNTAX_UNEXPECTED_TOKEN"
    SYNTAX_UNTERMINATED_REPEAT = "SYNTAX_UNTERMINATED_REPEAT"
    SYNTAX_UNMATCHED_REPEAT_END = "SYNTAX_UNMATCHED_REPEAT_END"
    SYNTAX_UNTERMINATED_TIE = "SYNTAX_UNTERMINATED_TIE"
    SYNTAX_INVALID_TRACK_HEADER = "SYNTAX_INVALID_TRACK_HEADER"
    SYNTAX_DUPLICATE_TRACK = "SYNTAX_DUPLICATE_TRACK"
    SYNTAX_EMPTY_TRACK = "SYNTAX_EMPTY_TRACK"
    SYNTAX_NOTE_OUT_OF_RANGE = "SYNTAX_NOTE_OUT_OF_RANGE"
    SYNTAX_CHANNEL_MISMATCH = "SYNTAX_CHANNEL_MISMATCH"
    SYNTAX_UNTERMINATED_HEADER = "SYNTAX_UNTERMINATED_HEADER"
    SYNTAX_UNDEFINED_REFERENCE = "SYNTAX_UNDEFINED_REFERENCE"

    SYSTEM_SYNTHESIS_FAILED = "SYSTEM_SYNTHESIS_FAILED"
    SYSTEM_WAV_WRITE_FAILED = "SYSTEM_WAV_WRITE_FAILED"
    SYSTEM_INTERNAL_ERROR = "SYSTEM_INTERNAL_ERROR"


@dataclass
class ErrorDetail:
    """Structured error/warning detail."""

    code: ErrorCode
    line: int
    column: int
    message: str
    severity: str  # "error" | "warning"
    hint: str = ""
    context: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "code": self.code.value,
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
class EnvelopeEvent:
    type: str = "envelope"
    tick_position: int = 0
    slot: int = 0
    points: list[dict[str, int]] = field(default_factory=list)


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
    | EnvelopeEvent
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
    version: str = "1.0"
    bpm: int = 120
    ticks_per_quarter: int = 192
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
            "channels": {k: v.to_dict() for k, v in self.channels.items()},
        }


def event_to_dict(event: Event) -> dict[str, Any]:
    if isinstance(
        event, (NoteEvent, RestEvent, VolumeEvent, DutyEvent, TempoEvent, RepeatEvent)
    ):
        return event.__dict__
    if isinstance(event, (EnvelopeEvent, VibratoEvent, GlideEvent)):
        return event.__dict__
    raise TypeError(f"Unsupported event type: {type(event)}")
