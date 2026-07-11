"""Tests for the MML lexer."""

from mml_composemusic_mcp.lexer import TokenType, tokenize


def test_ppmck_tokens():
    source = "A t150 l8 o4 v15 q2\nc d e f"
    tokens = tokenize(source, "ppmck")
    types = [t.type for t in tokens]
    assert TokenType.TRACK_HEADER in types
    assert TokenType.TEMPO in types
    assert TokenType.NOTE in types


def test_pyxel_tokens():
    source = "0: T150 L8 O4 V100 @1\nC D E F"
    tokens = tokenize(source, "pyxel")
    types = [t.type for t in tokens]
    assert TokenType.TRACK_HEADER in types
    assert TokenType.AT in types
    assert TokenType.NOTE in types


def test_pyxel_repeat():
    tokens = tokenize("[ C D ]2", "pyxel")
    assert any(t.type == TokenType.REPEAT_START for t in tokens)
    assert any(t.type == TokenType.REPEAT_END for t in tokens)
