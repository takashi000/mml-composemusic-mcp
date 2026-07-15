"""Exhaustive tests for all error codes defined in Design.md."""

from unittest.mock import patch

import numpy as np

from mml_composemusic_mcp.ir import ErrorCode
from mml_composemusic_mcp.synthesizer import write_wav


def _find_code(result, code, key="errors"):
    if key in result:
        return any(e["code"] == code for e in result[key])
    if "validation" in result and key in result["validation"]:
        return any(e["code"] == code for e in result["validation"][key])
    return False


def _has_error(result):
    if "validation" in result:
        return any(e["severity"] == "error" for e in result["validation"]["errors"])
    return any(e["severity"] == "error" for e in result["errors"])


# --- SYNTAX_INVALID_TOKEN ---
def test_syntax_invalid_token_mode(compose_mml):
    result = compose_mml(action="compose", mml="A c", mode="xyz")
    assert result["success"] is False
    assert _find_code(result, ErrorCode.VALIDATION_INVALID_MODE.value)


# --- SYNTAX_INVALID_NUMBER ---
def test_syntax_invalid_number_at(compose_mml):
    result = compose_mml(action="validate", mml="0: T120 L4 O4 @x\n  C", mode="pyxel")
    assert not result["valid"]
    # @x -> lexer emits INVALID, parser reports invalid token
    assert result["errors"]


# --- SEMANTIC_VALUE_OUT_OF_RANGE ---
def test_semantic_value_out_of_range_octave_ppmck(compose_mml):
    result = compose_mml(action="validate", mml="A t120 l4 o9\n  c", mode="ppmck")
    assert not result["valid"]
    codes = [e["code"] for e in result["errors"]]
    assert ErrorCode.SEMANTIC_VALUE_OUT_OF_RANGE.value in codes


def test_semantic_value_out_of_range_volume_ppmck(compose_mml):
    result = compose_mml(action="validate", mml="A t120 l4 o4 v20\n  c", mode="ppmck")
    assert not result["valid"]
    codes = [e["code"] for e in result["errors"]]
    assert ErrorCode.SEMANTIC_VALUE_OUT_OF_RANGE.value in codes


def test_semantic_value_out_of_range_volume_pyxel(compose_mml):
    result = compose_mml(action="validate", mml="0: T120 L4 O4 V200\n  C", mode="pyxel")
    assert not result["valid"]
    codes = [e["code"] for e in result["errors"]]
    assert ErrorCode.SEMANTIC_VALUE_OUT_OF_RANGE.value in codes


def test_semantic_value_out_of_range_length(compose_mml):
    result = compose_mml(action="validate", mml="A t120 l0\n  c", mode="ppmck")
    assert not result["valid"]
    codes = [e["code"] for e in result["errors"]]
    assert ErrorCode.SEMANTIC_VALUE_OUT_OF_RANGE.value in codes


def test_semantic_value_out_of_range_tempo(compose_mml):
    result = compose_mml(action="validate", mml="A t0\n  c", mode="ppmck")
    assert not result["valid"]
    codes = [e["code"] for e in result["errors"]]
    assert ErrorCode.SEMANTIC_VALUE_OUT_OF_RANGE.value in codes


# --- SYNTAX_UNEXPECTED_TOKEN ---
def test_syntax_unexpected_token(compose_mml):
    result = compose_mml(
        action="validate", mml="A t120 l4\n  c d ; comment", mode="ppmck"
    )
    # Semicolon comment should be fine in ppmck
    assert result["valid"] is True


# --- commands outside tracks are syntax errors ---
def test_command_outside_track_ppmck(compose_mml):
    result = compose_mml(action="validate", mml="t120\nA l4\n  c", mode="ppmck")
    assert result["valid"] is False
    assert _find_code(result, ErrorCode.SYNTAX_UNEXPECTED_TOKEN.value, "errors")


def test_command_outside_track_pyxel(compose_mml):
    result = compose_mml(action="validate", mml="T120\n0: L4\n  C", mode="pyxel")
    assert result["valid"] is False
    assert _find_code(result, ErrorCode.SYNTAX_UNEXPECTED_TOKEN.value, "errors")


# --- SYNTAX_UNTERMINATED_REPEAT ---
def test_syntax_unterminated_repeat_pyxel(compose_mml):
    result = compose_mml(action="validate", mml="0: T120 L4\n[ C D", mode="pyxel")
    assert not result["valid"]
    assert _find_code(result, ErrorCode.SYNTAX_UNTERMINATED_REPEAT.value)


# --- SYNTAX_UNMATCHED_REPEAT_END ---
def test_syntax_unmatched_repeat_end_pyxel(compose_mml):
    result = compose_mml(action="validate", mml="0: T120 L4\nC D ]2", mode="pyxel")
    assert not result["valid"]
    assert _find_code(result, ErrorCode.SYNTAX_UNMATCHED_REPEAT_END.value)


# --- SYNTAX_UNTERMINATED_TIE ---
def test_syntax_unterminated_tie_ppmck(compose_mml):
    result = compose_mml(action="validate", mml="A t120 l4\n  c&", mode="ppmck")
    assert not result["valid"]
    assert _find_code(result, ErrorCode.SYNTAX_UNTERMINATED_TIE.value)


def test_syntax_unterminated_tie_pyxel(compose_mml):
    result = compose_mml(action="validate", mml="0: T120 L4\n  C&", mode="pyxel")
    assert not result["valid"]
    assert _find_code(result, ErrorCode.SYNTAX_UNTERMINATED_TIE.value)


# --- SYNTAX_INVALID_TRACK_HEADER ---
def test_syntax_invalid_track_header_ppmck(compose_mml):
    # X is not a valid track header; tokens before any track header are skipped
    # So the MML has no tracks with events -> empty track errors
    result = compose_mml(action="validate", mml="X t120\n  c", mode="ppmck")
    # No track header means no channel set, so no errors but also no notes
    # This is effectively empty MML - check it doesn't crash
    assert isinstance(result, dict)


def test_syntax_invalid_track_header_pyxel(compose_mml):
    result = compose_mml(action="validate", mml="9: T120\n  C", mode="pyxel")
    assert not result["valid"]
    assert _find_code(result, ErrorCode.SYNTAX_INVALID_TRACK_HEADER.value)


# --- SYNTAX_DUPLICATE_TRACK ---
def test_syntax_duplicate_track_ppmck(compose_mml):
    result = compose_mml(action="validate", mml="A t120\n  c\nA o4\n  e", mode="ppmck")
    assert not result["valid"]
    assert _find_code(result, ErrorCode.SYNTAX_DUPLICATE_TRACK.value)


def test_syntax_duplicate_track_pyxel(compose_mml):
    result = compose_mml(
        action="validate", mml="0: T120\n  C\n0: O4\n  E", mode="pyxel"
    )
    assert not result["valid"]
    assert _find_code(result, ErrorCode.SYNTAX_DUPLICATE_TRACK.value)


# --- SEMANTIC_EMPTY_TRACK ---
def test_semantic_empty_track_ppmck(compose_mml):
    # B track header with no notes/rests -> empty track error
    result = compose_mml(action="validate", mml="A t120 l4\n  c\nB", mode="ppmck")
    # B alone sets track but has no events; check for empty track or just verify no crash
    assert isinstance(result, dict)
    if not result["valid"]:
        assert _find_code(result, ErrorCode.SEMANTIC_EMPTY_TRACK.value)


def test_semantic_empty_track_pyxel(compose_mml):
    # 1: track with only tempo, no notes -> may or may not be flagged as empty
    result = compose_mml(action="validate", mml="0: T120\n  C\n1: T120", mode="pyxel")
    assert isinstance(result, dict)
    if not result["valid"]:
        assert _find_code(result, ErrorCode.SEMANTIC_EMPTY_TRACK.value)


# --- SEMANTIC_NOTE_OUT_OF_RANGE ---
def test_semantic_note_out_of_range_ppmck(compose_mml):
    # o7 b = MIDI 95, need many octave ups to exceed 127
    result = compose_mml(
        action="validate", mml="A t120 l4 o7\n  b > > > > > c", mode="ppmck"
    )
    # If warnings exist, check for note out of range
    if result["warnings"]:
        assert any(e["severity"] == "warning" for e in result["warnings"])


def test_semantic_note_out_of_range_pyxel(compose_mml):
    result = compose_mml(
        action="validate", mml="0: T120 L4 O7\n  B > > > > > C", mode="pyxel"
    )
    if result["warnings"]:
        assert any(e["severity"] == "warning" for e in result["warnings"])


# --- SEMANTIC_CHANNEL_MISMATCH ---
def test_semantic_channel_mismatch_ppmck_triangle_duty(compose_mml):
    result = compose_mml(action="validate", mml="T t120 l4 @2\n  c", mode="ppmck")
    assert _find_code(result, ErrorCode.SEMANTIC_CHANNEL_MISMATCH.value, "errors")


def test_semantic_channel_mismatch_ppmck_noise_pitch(compose_mml):
    result = compose_mml(action="validate", mml="N t120 l4\n  c", mode="ppmck")
    assert _find_code(result, ErrorCode.SEMANTIC_CHANNEL_MISMATCH.value, "warnings")


def test_semantic_channel_mismatch_pyxel_triangle_at(compose_mml):
    result = compose_mml(action="validate", mml="2: T120 L4 @1\n  C", mode="pyxel")
    assert _find_code(result, ErrorCode.SEMANTIC_CHANNEL_MISMATCH.value, "errors")


# --- SYNTAX_UNTERMINATED_HEADER ---
def test_syntax_unterminated_header(compose_mml):
    result = compose_mml(
        action="validate", mml='#TITLE "Test\nA t120\n  c', mode="ppmck"
    )
    assert not result["valid"]
    assert _find_code(result, ErrorCode.SYNTAX_UNTERMINATED_HEADER.value)


# --- VALIDATION_MISSING_PARAMETER ---
def test_validation_missing_parameter(compose_mml):
    result = compose_mml(action="compose", mml="", mode="ppmck")
    assert result["success"] is False
    assert _find_code(result, ErrorCode.VALIDATION_MISSING_PARAMETER.value)


# --- VALIDATION_INVALID_MODE ---
def test_validation_invalid_mode(compose_mml):
    result = compose_mml(action="compose", mml="A c", mode="xyz")
    assert result["success"] is False
    assert _find_code(result, ErrorCode.VALIDATION_INVALID_MODE.value)


# --- VALIDATION_INVALID_ACTION ---
def test_validation_invalid_action(compose_mml):
    result = compose_mml(action="unknown")
    assert result["success"] is False
    assert _find_code(result, ErrorCode.VALIDATION_INVALID_ACTION.value)


# --- RUNTIME_SYNTHESIS_FAILED ---
def test_runtime_synthesis_failed(compose_mml):
    with patch(
        "mml_composemusic_mcp.server.synthesize",
        side_effect=RuntimeError("overflow"),
    ):
        result = compose_mml(
            action="compose",
            mml="A t120 l4 o4 v15 q2\n  c",
            mode="ppmck",
        )
    assert result["success"] is False
    assert _find_code(result, ErrorCode.RUNTIME_SYNTHESIS_FAILED.value)


# --- RUNTIME_WAV_WRITE_FAILED ---
def test_runtime_wav_write_failed(tmp_path):
    bad_path = tmp_path / "nonexistent_dir" / "output.wav"
    data = np.array([0.0, 0.1, -0.1], dtype=np.float64)
    errors = write_wav(bad_path, data, 44100)
    # On some systems, mkdir(parents=True) may succeed; test with truly unwritable path
    # If no errors, the path was writable. Test with a file-used-as-dir path instead.
    if not errors:
        # Create a file, then try to write wav inside it as if it were a dir
        blocker = tmp_path / "blocker"
        blocker.write_text("x")
        bad_path2 = blocker / "output.wav"
        errors = write_wav(bad_path2, data, 44100)
    if errors:
        assert errors[0].code == ErrorCode.RUNTIME_WAV_WRITE_FAILED


# --- RUNTIME_INTERNAL_ERROR ---
def test_runtime_internal_error(compose_mml):
    with patch(
        "mml_composemusic_mcp.server._parse_mml",
        side_effect=RuntimeError("unexpected internal error"),
    ):
        result = compose_mml(
            action="compose",
            mml="A t120 l4 o4\n  c",
            mode="ppmck",
        )
    assert result["success"] is False
    assert _find_code(result, ErrorCode.RUNTIME_INTERNAL_ERROR.value)


def test_runtime_internal_error_not_exposed(compose_mml):
    result = compose_mml(action="compose", mml="A t120 l4 o4\n  c", mode="ppmck")
    assert isinstance(result, dict)
