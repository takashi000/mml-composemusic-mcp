"""Common AST node definitions for ppmck and pyxel MML."""

from dataclasses import dataclass, field
from typing import Any


@dataclass
class ASTNode:
    """Base class for all AST nodes."""

    line: int
    column: int


@dataclass
class Program(ASTNode):
    """Root program node."""

    tracks: list[Track] = field(default_factory=list)
    global_statements: list[Statement] = field(default_factory=list)


@dataclass
class Track(ASTNode):
    """A single track definition."""

    track_id: str  # "A" / "B" / "T" / "N" / "L" (ppmck) or "0"-"3" (pyxel)
    channel: str  # "Pulse1" / "Pulse2" / "Triangle" / "Noise" / "Loop"
    mode: str  # "ppmck" / "pyxel"
    statements: list[Statement] = field(default_factory=list)
    headers: list[Header] = field(default_factory=list)


@dataclass
class Header(ASTNode):
    """ppmck # header line."""

    key: str
    value: str
    unterminated: bool = False


# --- Statements ---


@dataclass
class NoteStmt(ASTNode):
    """A note command (c, d, e, ...)."""

    note_name: str  # normalized to lowercase: "c"-"b"
    accidental: int = 0  # +1 sharp, -1 flat, 0 none
    length: int | None = None  # None means use default length
    dots: int = 0


@dataclass
class RestStmt(ASTNode):
    """A rest command (r / R)."""

    length: int | None = None
    dots: int = 0


@dataclass
class OctaveStmt(ASTNode):
    """Octave command or relative octave shift."""

    value: int | None = None  # absolute octave number
    direction: str | None = None  # "up" or "down" for relative shifts


@dataclass
class LengthStmt(ASTNode):
    """Default length command (l / L)."""

    value: int


@dataclass
class VolumeStmt(ASTNode):
    """Volume command (v / V)."""

    value: int


@dataclass
class DutyStmt(ASTNode):
    """Duty/tone command (q / @)."""

    value: int


@dataclass
class TempoStmt(ASTNode):
    """Tempo command (t / T)."""

    value: int


@dataclass
class GateTimeStmt(ASTNode):
    """Gate time command (Q, pyxel only)."""

    value: int


@dataclass
class TransposeStmt(ASTNode):
    """Transpose command (K, pyxel only)."""

    value: int


@dataclass
class DetuneStmt(ASTNode):
    """Detune command (Y, pyxel only)."""

    value: int


@dataclass
class QuantizeStmt(ASTNode):
    """ppmck quantize command (q1-q8)."""

    value: int


@dataclass
class TieStmt(ASTNode):
    """Tie/slur command (&)."""

    target: NoteStmt | RestStmt | int | None = None


@dataclass
class TieCmdStmt(ASTNode):
    """ppmck tie command (^). Extends duration, pitch from previous note."""

    target: NoteStmt | int | None = None


@dataclass
class DetuneCmdStmt(ASTNode):
    """ppmck detune command (D<num>)."""

    value: int


@dataclass
class RelativeVolumeStmt(ASTNode):
    """ppmck relative volume (v+num / v-num)."""

    delta: int  # positive=up, negative=down


@dataclass
class RepeatStartStmt(ASTNode):
    """Start of repeat section ([)."""

    pass


@dataclass
class RepeatBreakStmt(ASTNode):
    """Last-pass break marker (|) inside a ppmck repeat."""

    pass


@dataclass
class RepeatEndStmt(ASTNode):
    """End of repeat section (] with optional count)."""

    count: int | None = None  # None means infinite


@dataclass
class BarStmt(ASTNode):
    """Bar line (|), visual only."""

    pass


@dataclass
class ExtCmdStmt(ASTNode):
    """pyxel @ENV / @VIB / @GLI command."""

    cmd: str  # "ENV" / "VIB" / "GLI"
    slot: int
    params: list[int] = field(default_factory=list)


# --- Envelope / LFO / vibrato statements (IR kept, synthesis warning) ---


@dataclass
class VolumeEnvelopeUseStmt(ASTNode):
    """ppmck volume envelope use (@v<num>)."""

    slot: int


@dataclass
class VolumeEnvelopeDefStmt(ASTNode):
    """ppmck volume envelope definition (@v<num> = {...|...})."""

    slot: int
    points: list[int] = field(default_factory=list)
    loop_points: list[int] = field(default_factory=list)


@dataclass
class DutyEnvelopeDefStmt(ASTNode):
    """ppmck duty envelope definition (@<num> = {...|...})."""

    slot: int
    points: list[int] = field(default_factory=list)
    loop_points: list[int] = field(default_factory=list)


@dataclass
class DutyEnvelopeUseStmt(ASTNode):
    """ppmck duty envelope use (@@<num>)."""

    slot: int


@dataclass
class LfoDefStmt(ASTNode):
    """ppmck LFO definition (@MP<num> = {p1,p2,p3,p4})."""

    slot: int
    delay: int
    speed: int
    depth: int
    transition: int


@dataclass
class LfoUseStmt(ASTNode):
    """ppmck LFO use (MP<num>)."""

    slot: int


@dataclass
class LfoOffStmt(ASTNode):
    """ppmck LFO off (MPOF)."""

    pass


@dataclass
class PitchEnvDefStmt(ASTNode):
    """ppmck pitch envelope definition (@EP<num> = {...|...})."""

    slot: int
    points: list[int] = field(default_factory=list)
    loop_points: list[int] = field(default_factory=list)


@dataclass
class PitchEnvUseStmt(ASTNode):
    """ppmck pitch envelope use (EP<num>)."""

    slot: int


@dataclass
class PitchEnvOffStmt(ASTNode):
    """ppmck pitch envelope off (EPOF)."""

    pass


@dataclass
class NoteEnvDefStmt(ASTNode):
    """ppmck note envelope definition (@EN<num> = {...|...})."""

    slot: int
    points: list[int] = field(default_factory=list)
    loop_points: list[int] = field(default_factory=list)


@dataclass
class NoteEnvUseStmt(ASTNode):
    """ppmck note envelope use (EN<num>)."""

    slot: int


@dataclass
class NoteEnvOffStmt(ASTNode):
    """ppmck note envelope off (ENOF)."""

    pass


# --- Stage 2 statements (kept in AST but ignored by semantic analyzer) ---


@dataclass
class CountLengthStmt(ASTNode):
    """ppmck count length note (c%48)."""

    note_name: str
    accidental: int
    count: int


@dataclass
class SweepStmt(ASTNode):
    """ppmck sweep command (s1,2)."""

    speed: int
    depth: int


@dataclass
class NoiseModeStmt(ASTNode):
    """ppmck noise mode command (m0 / m1)."""

    mode: int


Statement = (
    NoteStmt
    | RestStmt
    | OctaveStmt
    | LengthStmt
    | VolumeStmt
    | DutyStmt
    | TempoStmt
    | GateTimeStmt
    | TransposeStmt
    | DetuneStmt
    | QuantizeStmt
    | TieStmt
    | TieCmdStmt
    | DetuneCmdStmt
    | RelativeVolumeStmt
    | RepeatStartStmt
    | RepeatBreakStmt
    | RepeatEndStmt
    | BarStmt
    | ExtCmdStmt
    | VolumeEnvelopeUseStmt
    | VolumeEnvelopeDefStmt
    | DutyEnvelopeDefStmt
    | DutyEnvelopeUseStmt
    | LfoDefStmt
    | LfoUseStmt
    | LfoOffStmt
    | PitchEnvDefStmt
    | PitchEnvUseStmt
    | PitchEnvOffStmt
    | NoteEnvDefStmt
    | NoteEnvUseStmt
    | NoteEnvOffStmt
    | CountLengthStmt
    | SweepStmt
    | NoiseModeStmt
)


def _node_to_dict(node: Any) -> Any:
    """Recursively convert an AST node to a JSON-compatible dict."""
    if isinstance(node, list):
        return [_node_to_dict(item) for item in node]
    if not isinstance(node, ASTNode):
        return node
    data: dict[str, Any] = {"__type__": node.__class__.__name__}
    for key, value in node.__dict__.items():
        data[key] = _node_to_dict(value)
    return data


def ast_to_dict(node: ASTNode) -> dict[str, Any]:
    """Convert an AST node to a JSON-compatible dict."""
    return _node_to_dict(node)
