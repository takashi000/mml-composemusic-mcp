"""Detailed parser tests for ppmck and pyxel modes."""

from mml_composemusic_mcp.ir import (
    DutyEvent,
    EnvelopeEvent,
    NoteEvent,
)
from mml_composemusic_mcp.lexer import tokenize
from mml_composemusic_mcp.parser_ppmck import parse_ppmck
from mml_composemusic_mcp.parser_pyxel import parse_pyxel

# --- Channel assignment ---


def test_ppmck_channel_assignment():
    source = "A t120 l4 o4\n  c\nB o4\n  d\nT o3\n  e\nN v10\n  r"
    tokens = tokenize(source, "ppmck")
    ns, errors = parse_ppmck(source, tokens)
    assert not any(e.severity == "error" for e in errors)
    assert ns.channels["Pulse1"].events
    assert ns.channels["Pulse2"].events
    assert ns.channels["Triangle"].events
    assert ns.channels["Noise"].events


def test_pyxel_channel_assignment():
    source = "0: T120 L4 O4\n  C\n1: O4\n  D\n2: O3\n  E\n3: V80\n  R"
    tokens = tokenize(source, "pyxel")
    ns, errors = parse_pyxel(source, tokens)
    assert not any(e.severity == "error" for e in errors)
    assert ns.channels["Pulse1"].events
    assert ns.channels["Pulse2"].events
    assert ns.channels["Triangle"].events
    assert ns.channels["Noise"].events


# --- Duty ---


def test_ppmck_duty_q():
    source = "A t120 l4 o4 q3\n  c"
    tokens = tokenize(source, "ppmck")
    ns, errors = parse_ppmck(source, tokens)
    duties = [e for e in ns.channels["Pulse1"].events if isinstance(e, DutyEvent)]
    assert duties and duties[0].value == 3


def test_pyxel_at_duty():
    source = "0: T120 L4 O4 @1\n  C"
    tokens = tokenize(source, "pyxel")
    ns, errors = parse_pyxel(source, tokens)
    duties = [e for e in ns.channels["Pulse1"].events if isinstance(e, DutyEvent)]
    assert duties and duties[0].value == 2  # @1 maps to duty 2 (50%)


def test_pyxel_at2_duty():
    source = "0: T120 L4 O4 @2\n  C"
    tokens = tokenize(source, "pyxel")
    ns, errors = parse_pyxel(source, tokens)
    duties = [e for e in ns.channels["Pulse1"].events if isinstance(e, DutyEvent)]
    assert duties and duties[0].value == 1  # @2 maps to duty 1 (25%)


# --- Volume normalization ---


def test_pyxel_volume_normalization():
    source = "0: T120 L4 O4 V100\n  C"
    tokens = tokenize(source, "pyxel")
    ns, errors = parse_pyxel(source, tokens)
    notes = [e for e in ns.channels["Pulse1"].events if isinstance(e, NoteEvent)]
    assert notes
    # V100 -> round(100/127*15) = 12
    assert notes[0].velocity == 12


def test_pyxel_volume_zero():
    source = "0: T120 L4 O4 V0\n  C"
    tokens = tokenize(source, "pyxel")
    ns, errors = parse_pyxel(source, tokens)
    notes = [e for e in ns.channels["Pulse1"].events if isinstance(e, NoteEvent)]
    assert notes and notes[0].velocity == 0


def test_pyxel_volume_max():
    source = "0: T120 L4 O4 V127\n  C"
    tokens = tokenize(source, "pyxel")
    ns, errors = parse_pyxel(source, tokens)
    notes = [e for e in ns.channels["Pulse1"].events if isinstance(e, NoteEvent)]
    assert notes and notes[0].velocity == 15


# --- Gate time ---


def test_pyxel_gate_time():
    source = "0: T120 L4 O4 Q50\n  C"
    tokens = tokenize(source, "pyxel")
    ns, errors = parse_pyxel(source, tokens)
    notes = [e for e in ns.channels["Pulse1"].events if isinstance(e, NoteEvent)]
    assert notes and notes[0].gate_time == 0.5


# --- Transpose ---


def test_pyxel_transpose():
    source = "0: T120 L4 O4 K2\n  C"
    tokens = tokenize(source, "pyxel")
    ns, errors = parse_pyxel(source, tokens)
    notes = [e for e in ns.channels["Pulse1"].events if isinstance(e, NoteEvent)]
    # C4=60, transpose+2 -> 62
    assert notes and notes[0].note_number == 62


# --- Detune ---


def test_pyxel_detune():
    source = "0: T120 L4 O4 Y10\n  C"
    tokens = tokenize(source, "pyxel")
    ns, errors = parse_pyxel(source, tokens)
    notes = [e for e in ns.channels["Pulse1"].events if isinstance(e, NoteEvent)]
    assert notes and notes[0].detune_cents == 10.0


# --- Repeat ---


def test_pyxel_repeat_expansion():
    source = "0: T120 L4 O4\n[ C D ]2"
    tokens = tokenize(source, "pyxel")
    ns, errors = parse_pyxel(source, tokens)
    notes = [e for e in ns.channels["Pulse1"].events if isinstance(e, NoteEvent)]
    assert len(notes) == 4


def test_pyxel_repeat_count3():
    source = "0: T120 L4 O4\n[ C D ]3"
    tokens = tokenize(source, "pyxel")
    ns, errors = parse_pyxel(source, tokens)
    notes = [e for e in ns.channels["Pulse1"].events if isinstance(e, NoteEvent)]
    assert len(notes) == 6


# --- Tie ---


def test_ppmck_tie_note():
    source = "A t120 l4 o4\n  c4 & c4"
    tokens = tokenize(source, "ppmck")
    ns, errors = parse_ppmck(source, tokens)
    # Tie should merge notes; check no error
    assert not any(e.severity == "error" for e in errors)


def test_pyxel_tie_length():
    source = "0: T120 L4 O4\n  C4 & 4"
    tokens = tokenize(source, "pyxel")
    ns, errors = parse_pyxel(source, tokens)
    notes = [e for e in ns.channels["Pulse1"].events if isinstance(e, NoteEvent)]
    # & 4 extends last note by l4 ticks
    assert notes and notes[0].duration > 192  # 192 + 48 = 240


# --- Octave up/down ---


def test_ppmck_octave_up():
    source = "A t120 l4 o4\n  c > d"
    tokens = tokenize(source, "ppmck")
    ns, errors = parse_ppmck(source, tokens)
    notes = [e for e in ns.channels["Pulse1"].events if isinstance(e, NoteEvent)]
    assert notes[0].note_number == 60  # o4 c
    assert notes[1].note_number == 74  # o5 d


def test_pyxel_octave_down():
    source = "0: T120 L4 O4\n  C < D"
    tokens = tokenize(source, "pyxel")
    ns, errors = parse_pyxel(source, tokens)
    notes = [e for e in ns.channels["Pulse1"].events if isinstance(e, NoteEvent)]
    assert notes[0].note_number == 60  # O4 C
    assert notes[1].note_number == 50  # O3 D


# --- Length with dots ---


def test_ppmck_dotted_note():
    source = "A t120 l4 o4\n  c."
    tokens = tokenize(source, "ppmck")
    ns, errors = parse_ppmck(source, tokens)
    notes = [e for e in ns.channels["Pulse1"].events if isinstance(e, NoteEvent)]
    # l4 = 192 ticks, dotted = 192 + 96 = 288
    assert notes and notes[0].duration == 288


# --- Triangle volume ignored in ppmck ---


def test_ppmck_triangle_volume_ignored():
    source = "T t120 l4 o3 v7\n  c"
    tokens = tokenize(source, "ppmck")
    ns, errors = parse_ppmck(source, tokens)
    notes = [e for e in ns.channels["Triangle"].events if isinstance(e, NoteEvent)]
    assert notes and notes[0].velocity == 15  # default, v ignored


# --- @ENV/@VIB/@GLI ---


def test_pyxel_env_event():
    source = "0: T120 L4 O4\n@ENV1 100 10\n  C"
    tokens = tokenize(source, "pyxel")
    ns, errors = parse_pyxel(source, tokens)
    envs = [e for e in ns.channels["Pulse1"].events if isinstance(e, EnvelopeEvent)]
    assert envs and envs[0].slot == 1


def test_pyxel_vib_event():
    source = "0: T120 L4 O4\n@VIB1 10 20 5\n  C"
    tokens = tokenize(source, "pyxel")
    ns, errors = parse_pyxel(source, tokens)
    from mml_composemusic_mcp.ir import VibratoEvent

    vibs = [e for e in ns.channels["Pulse1"].events if isinstance(e, VibratoEvent)]
    assert vibs and vibs[0].slot == 1


def test_pyxel_gli_event():
    source = "0: T120 L4 O4\n@GLI1 100 50\n  C"
    tokens = tokenize(source, "pyxel")
    ns, errors = parse_pyxel(source, tokens)
    from mml_composemusic_mcp.ir import GlideEvent

    glis = [e for e in ns.channels["Pulse1"].events if isinstance(e, GlideEvent)]
    assert glis and glis[0].slot == 1


# --- Noise channel ---


def test_ppmck_noise_ignores_pitch():
    source = "N t120 l4 v10\n  c r"
    tokens = tokenize(source, "ppmck")
    ns, errors = parse_ppmck(source, tokens)
    notes = [e for e in ns.channels["Noise"].events if isinstance(e, NoteEvent)]
    assert notes  # NoteEvent is created but with midi=0
    assert notes[0].note_number == 0  # pitch ignored
