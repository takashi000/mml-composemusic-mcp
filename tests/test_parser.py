"""Tests for PPMCK and Pyxel parsers."""

from mml_composemusic_mcp.ir import NoteEvent
from mml_composemusic_mcp.lexer import tokenize
from mml_composemusic_mcp.parser_ppmck import parse_ppmck
from mml_composemusic_mcp.parser_pyxel import parse_pyxel

PPMCK_EXAMPLE = """#TITLE "Test"
A t150 l8 o4 v15 q2
  c d e f
B o3
  c e g
"""

PYXEL_EXAMPLE = """0: T150 L8 O4 V100 @1
  C D E F
1: O3
  C E G
"""


def test_ppmck_parse():
    tokens = tokenize(PPMCK_EXAMPLE, "ppmck")
    ns, errors = parse_ppmck(PPMCK_EXAMPLE, tokens)
    assert not any(e.severity == "error" for e in errors)
    assert ns.channels["Pulse1"].events
    assert ns.channels["Pulse2"].events
    notes = [e for e in ns.channels["Pulse1"].events if isinstance(e, NoteEvent)]
    assert notes[0].note_number == 60  # C4


def test_pyxel_parse():
    tokens = tokenize(PYXEL_EXAMPLE, "pyxel")
    ns, errors = parse_pyxel(PYXEL_EXAMPLE, tokens)
    assert not any(e.severity == "error" for e in errors)
    assert ns.channels["Pulse1"].events
    notes = [e for e in ns.channels["Pulse1"].events if isinstance(e, NoteEvent)]
    assert notes[0].note_number == 60  # C4


def test_pyxel_repeat_expansion():
    source = "0: T120 L4 O4\n[ C D ]2"
    tokens = tokenize(source, "pyxel")
    ns, errors = parse_pyxel(source, tokens)
    notes = [e for e in ns.channels["Pulse1"].events if isinstance(e, NoteEvent)]
    assert len(notes) == 4


def test_invalid_mode_error():
    from mml_composemusic_mcp.server import _parse_mml

    seq, errors = _parse_mml("A c", "unknown")
    assert any(e.severity == "error" for e in errors)
