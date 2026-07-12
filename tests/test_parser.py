"""Tests for PPMCK and Pyxel parsers (AST output)."""

from mml_composemusic_mcp.ast_nodes import NoteStmt, Program, Track
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
    program, errors = parse_ppmck(PPMCK_EXAMPLE, tokens)
    assert isinstance(program, Program)
    assert not any(e.severity == "error" for e in errors)
    assert len(program.tracks) == 2
    assert program.tracks[0].channel == "Pulse1"
    assert program.tracks[1].channel == "Pulse2"
    notes = [
        s for s in program.tracks[0].statements if isinstance(s, NoteStmt)
    ]
    assert notes[0].note_name == "c"


def test_pyxel_parse():
    tokens = tokenize(PYXEL_EXAMPLE, "pyxel")
    program, errors = parse_pyxel(PYXEL_EXAMPLE, tokens)
    assert isinstance(program, Program)
    assert not any(e.severity == "error" for e in errors)
    assert len(program.tracks) == 2
    assert program.tracks[0].channel == "Pulse1"
    notes = [
        s for s in program.tracks[0].statements if isinstance(s, NoteStmt)
    ]
    assert notes[0].note_name == "c"


def test_pyxel_repeat_ast():
    source = "0: T120 L4 O4\n[ C D ]2"
    tokens = tokenize(source, "pyxel")
    program, errors = parse_pyxel(source, tokens)
    assert not any(e.severity == "error" for e in errors)
    assert isinstance(program.tracks[0], Track)


def test_invalid_mode_error():
    from mml_composemusic_mcp.server import _parse_mml

    seq, errors = _parse_mml("A c", "unknown")
    assert seq is None
    assert any(e.severity == "error" for e in errors)
