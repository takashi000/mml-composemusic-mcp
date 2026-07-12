"""Tests for the MML lexer."""

from mml_composemusic_mcp.lexer import TokenType, tokenize


def test_ppmck_tokens():
    source = "A t150 l8 o4 v15 @2\nc d e f"
    tokens = tokenize(source, "ppmck")
    types = [t.type for t in tokens]
    assert TokenType.TRACK_HEADER in types
    assert TokenType.TEMPO in types
    assert TokenType.NOTE in types
    assert TokenType.DUTY in types


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


def test_ppmck_invalid_token():
    tokens = tokenize("A t120 l4 o4 x c", "ppmck")
    assert any(t.type == TokenType.INVALID for t in tokens)


def test_pyxel_invalid_token():
    tokens = tokenize("0: T120 L4 O4 X C", "pyxel")
    assert any(t.type == TokenType.INVALID for t in tokens)


def test_ppmck_at_duty():
    tokens = tokenize("A @2 c", "ppmck")
    assert any(t.type == TokenType.DUTY for t in tokens)


def test_ppmck_quantize():
    tokens = tokenize("A q4 c", "ppmck")
    assert any(t.type == TokenType.QUANTIZE for t in tokens)


def test_ppmck_tie_cmd():
    tokens = tokenize("A c4 ^4", "ppmck")
    assert any(t.type == TokenType.TIE_CMD for t in tokens)


def test_ppmck_detune():
    tokens = tokenize("A D10 c", "ppmck")
    assert any(t.type == TokenType.DETUNE for t in tokens)


def test_ppmck_sweep():
    tokens = tokenize("A s1,2 c", "ppmck")
    assert any(t.type == TokenType.SWEEP for t in tokens)


def test_ppmck_rel_vol():
    tokens = tokenize("A v+5 v-3 c", "ppmck")
    assert any(t.type == TokenType.REL_VOL_UP for t in tokens)
    assert any(t.type == TokenType.REL_VOL_DOWN for t in tokens)


def test_ppmck_vol_env():
    tokens = tokenize("A @v0 c", "ppmck")
    assert any(t.type == TokenType.VOL_ENV for t in tokens)


def test_ppmck_vol_env_def():
    tokens = tokenize("@v0 = { 15, 10, | 5 }", "ppmck")
    assert any(t.type == TokenType.VOL_ENV for t in tokens)
    assert any(t.type == TokenType.BRACE_OPEN for t in tokens)
    assert any(t.type == TokenType.BRACE_CLOSE for t in tokens)


def test_ppmck_lfo_def():
    tokens = tokenize("@MP0 = { 0, 10, 5, 0 }", "ppmck")
    assert any(t.type == TokenType.LFO_DEF for t in tokens)


def test_ppmck_lfo_use_off():
    tokens = tokenize("A MP1 MPOF c", "ppmck")
    assert any(t.type == TokenType.LFO_USE for t in tokens)
    assert any(t.type == TokenType.LFO_OFF for t in tokens)


def test_ppmck_pitch_env():
    tokens = tokenize("A EP1 EPOF c", "ppmck")
    assert any(t.type == TokenType.PITCH_ENV_USE for t in tokens)
    assert any(t.type == TokenType.PITCH_ENV_OFF for t in tokens)


def test_ppmck_note_env():
    tokens = tokenize("A EN1 ENOF c", "ppmck")
    assert any(t.type == TokenType.NOTE_ENV_USE for t in tokens)
    assert any(t.type == TokenType.NOTE_ENV_OFF for t in tokens)


def test_ppmck_duty_env_use():
    tokens = tokenize("A @@0 c", "ppmck")
    assert any(t.type == TokenType.DUTY_ENV_USE for t in tokens)
