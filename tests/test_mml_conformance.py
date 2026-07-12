"""BNF conformance tests spanning lexer, parser, semantics, and MCP validate."""

import pytest
from hypothesis import given, seed, settings
from hypothesis import strategies as st

from mml_composemusic_mcp.ast_nodes import NoteStmt, TransposeStmt
from mml_composemusic_mcp.ir import DutyEvent, ErrorCode, NoteEvent
from mml_composemusic_mcp.lexer import TokenType, tokenize
from mml_composemusic_mcp.parser_ppmck import parse_ppmck
from mml_composemusic_mcp.parser_pyxel import parse_pyxel
from mml_composemusic_mcp.semantic_ppmck import analyze_ppmck
from mml_composemusic_mcp.semantic_pyxel import analyze_pyxel
from mml_composemusic_mcp.server import _parse_mml, compose_mml


def parse_pipeline(source: str, mode: str):
    tokens = tokenize(source, mode)
    parser = parse_ppmck if mode == "ppmck" else parse_pyxel
    analyzer = analyze_ppmck if mode == "ppmck" else analyze_pyxel
    program, errors = parser(source, tokens)
    if any(error.severity == "error" for error in errors):
        return tokens, program, None, errors
    sequence, semantic_errors = analyzer(source, program)
    return tokens, program, sequence, errors + semantic_errors


def error_codes(errors):
    return {error.code for error in errors}


@pytest.mark.parametrize(
    ("mode", "source", "accidental", "length", "dots"),
    [
        ("ppmck", "A c+4.", 1, 4, 1),
        ("ppmck", "A d#8", 1, 8, 0),
        ("ppmck", "A e-16..", -1, 16, 2),
        ("pyxel", "0: C+4.", 1, 4, 1),
        ("pyxel", "0: D#8", 1, 8, 0),
        ("pyxel", "0: E-16..", -1, 16, 2),
    ],
)
def test_note_follows_bnf_accidental_before_length(
    mode, source, accidental, length, dots
):
    _, program, _, errors = parse_pipeline(source, mode)
    assert not any(error.severity == "error" for error in errors)
    note = next(
        stmt for stmt in program.tracks[0].statements if isinstance(stmt, NoteStmt)
    )
    assert (note.accidental, note.length, note.dots) == (
        accidental,
        length,
        dots,
    )


@pytest.mark.parametrize(
    ("mode", "source"),
    [
        ("ppmck", "A o l v @ t c"),
        ("pyxel", "0: O L V Q @ T K Y C"),
        ("pyxel", "0: K+ Y- C"),
    ],
)
def test_commands_requiring_numbers_reject_omission(mode, source):
    _, _, _, errors = parse_pipeline(source, mode)
    assert ErrorCode.SYNTAX_INVALID_NUMBER in error_codes(errors)


@pytest.mark.parametrize(
    ("mode", "source"), [("ppmck", "A c++4"), ("pyxel", "0: C##4")]
)
def test_multiple_accidentals_are_rejected(mode, source):
    _, _, _, errors = parse_pipeline(source, mode)
    assert ErrorCode.SYNTAX_UNEXPECTED_TOKEN in error_codes(errors)


@pytest.mark.parametrize(("command", "value"), [("K-12", -12), ("K+7", 7)])
def test_pyxel_signed_transpose_is_preserved(command, value):
    _, program, sequence, errors = parse_pipeline(f"0: O4 {command} C", "pyxel")
    assert not any(error.severity == "error" for error in errors)
    transpose = next(
        stmt for stmt in program.tracks[0].statements if isinstance(stmt, TransposeStmt)
    )
    note = next(
        event
        for event in sequence.channels["Pulse1"].events
        if isinstance(event, NoteEvent)
    )
    assert transpose.value == value
    assert note.note_number == 60 + value


def test_pyxel_signed_detune_reaches_ir():
    _, _, sequence, errors = parse_pipeline("0: Y-25 C", "pyxel")
    assert not any(error.severity == "error" for error in errors)
    note = next(
        event
        for event in sequence.channels["Pulse1"].events
        if isinstance(event, NoteEvent)
    )
    assert note.detune_cents == -25.0


@pytest.mark.parametrize("source", ["L c\nL d", "A c\nA d"])
def test_ppmck_all_track_ids_reject_duplicates(source):
    _, _, _, errors = parse_pipeline(source, "ppmck")
    assert ErrorCode.SYNTAX_DUPLICATE_TRACK in error_codes(errors)


@pytest.mark.parametrize(
    "source",
    ['#UNKNOWN "x"\nA c', "#TITLE unquoted\nA c", 'A c\n#TITLE "late"'],
)
def test_ppmck_header_key_and_placement_are_enforced(source):
    _, _, _, errors = parse_pipeline(source, "ppmck")
    assert ErrorCode.SYNTAX_UNEXPECTED_TOKEN in error_codes(errors)


def test_lexer_reports_precise_token_position_and_eof():
    tokens = tokenize("0: C\n  ?", "pyxel")
    invalid = next(token for token in tokens if token.type == TokenType.INVALID)
    assert (invalid.line, invalid.column, invalid.raw) == (2, 3, "?")
    assert tokens[-1].type == TokenType.EOF


@pytest.mark.parametrize("mode", ["ppmck", "pyxel"])
def test_empty_and_unicode_inputs_do_not_crash_pipeline(mode):
    sequence, errors = _parse_mml("", mode)
    assert sequence is not None
    assert isinstance(errors, list)
    sequence, errors = _parse_mml("♬", mode)
    assert sequence is None
    assert ErrorCode.SYNTAX_INVALID_TOKEN in error_codes(errors)


def test_validate_full_pyxel_path_preserves_warning_and_summary():
    result = compose_mml(
        action="validate",
        mode="pyxel",
        mml="0: T120 L4 O4 V100 Q80 @1 K-1 Y+5 @ENV1 100 10 C+4.",
    )
    assert result["valid"] is True
    assert result["channel_summary"]
    assert any(
        warning["code"] == ErrorCode.SEMANTIC_UNSUPPORTED_FEATURE.value
        for warning in result["warnings"]
    )


@pytest.mark.parametrize(
    ("source", "expected_warning_code"),
    [
        ("A D10 c", ErrorCode.SEMANTIC_UNSUPPORTED_FEATURE),
        ("A s1,2 c", ErrorCode.SEMANTIC_UNSUPPORTED_FEATURE),
        ("A v+5 c", ErrorCode.SEMANTIC_UNSUPPORTED_FEATURE),
        ("A @v0 c", ErrorCode.SEMANTIC_UNSUPPORTED_FEATURE),
        ("A @@0 c", ErrorCode.SEMANTIC_UNSUPPORTED_FEATURE),
        ("A MP1 c", ErrorCode.SEMANTIC_UNSUPPORTED_FEATURE),
        ("A MPOF c", ErrorCode.SEMANTIC_UNSUPPORTED_FEATURE),
        ("A EP1 c", ErrorCode.SEMANTIC_UNSUPPORTED_FEATURE),
        ("A EPOF c", ErrorCode.SEMANTIC_UNSUPPORTED_FEATURE),
        ("A EN1 c", ErrorCode.SEMANTIC_UNSUPPORTED_FEATURE),
        ("A ENOF c", ErrorCode.SEMANTIC_UNSUPPORTED_FEATURE),
    ],
)
def test_ppmck_new_commands_produce_warning(source, expected_warning_code):
    _, _, _, errors = parse_pipeline(source, "ppmck")
    assert not any(e.severity == "error" for e in errors)
    assert expected_warning_code in error_codes(errors)


def test_ppmck_at_duty_in_pulse_channel():
    _, _, ns, errors = parse_pipeline("A @2 c", "ppmck")
    assert not any(e.severity == "error" for e in errors)
    duties = [e for e in ns.channels["Pulse1"].events if isinstance(e, DutyEvent)]
    assert duties and duties[0].value == 2


def test_ppmck_at_duty_in_triangle_channel_warns():
    _, _, _, errors = parse_pipeline("T @2 c", "ppmck")
    assert ErrorCode.SEMANTIC_CHANNEL_MISMATCH in error_codes(errors)


def test_ppmck_quantize_sets_gate_time():
    _, _, ns, errors = parse_pipeline("A q4 c", "ppmck")
    assert not any(e.severity == "error" for e in errors)
    notes = [e for e in ns.channels["Pulse1"].events if isinstance(e, NoteEvent)]
    assert notes and notes[0].gate_time == 0.5


def test_ppmck_tie_cmd_extends_duration():
    _, _, ns, errors = parse_pipeline("A c4 ^4", "ppmck")
    assert not any(e.severity == "error" for e in errors)
    notes = [e for e in ns.channels["Pulse1"].events if isinstance(e, NoteEvent)]
    assert len(notes) == 1
    assert notes[0].duration == 384


note_names = st.sampled_from(tuple("cdefgab"))
accidentals = st.sampled_from(("", "+", "#", "-"))
lengths = st.one_of(st.just(""), st.integers(1, 192).map(str))
dots = st.integers(0, 3).map(lambda count: "." * count)
spaces = st.sampled_from((" ", "  ", "\t", "\n"))


@seed(20260712)
@settings(max_examples=100, deadline=None)
@given(
    mode=st.sampled_from(("ppmck", "pyxel")),
    notes=st.lists(
        st.tuples(note_names, accidentals, lengths, dots), min_size=1, max_size=20
    ),
    separator=spaces,
)
def test_generated_valid_notes_round_trip_to_ast_and_ir(mode, notes, separator):
    rendered = [
        name + accidental + length + dot for name, accidental, length, dot in notes
    ]
    if mode == "pyxel":
        rendered = [note.upper() for note in rendered]
        source = "0: " + separator.join(rendered)
    else:
        source = "A " + separator.join(rendered)
    _, program, sequence, errors = parse_pipeline(source, mode)
    assert not any(error.severity == "error" for error in errors)
    ast_notes = [
        stmt for stmt in program.tracks[0].statements if isinstance(stmt, NoteStmt)
    ]
    ir_notes = [
        event
        for event in sequence.channels["Pulse1"].events
        if isinstance(event, NoteEvent)
    ]
    assert len(ast_notes) == len(notes) == len(ir_notes)


@seed(20260712)
@settings(max_examples=50, deadline=None)
@given(
    mode=st.sampled_from(("ppmck", "pyxel")),
    bad=st.sampled_from(("?", "{", "}", ",", "♬")),
    index=st.integers(min_value=0, max_value=4),
)
def test_generated_single_token_corruption_is_not_silent(mode, bad, index):
    note = "cdefg"[index]
    source = f"A {note}{bad}" if mode == "ppmck" else f"0: {note.upper()}{bad}"
    _, _, _, errors = parse_pipeline(source, mode)
    assert any(error.severity == "error" for error in errors)


@pytest.mark.parametrize(
    ("mode", "source"),
    [("ppmck", "A l" + "9" * 1000 + " c"), ("pyxel", "0: L" + "9" * 1000 + " C")],
)
def test_very_large_numbers_are_reported_without_crashing(mode, source):
    _, _, _, errors = parse_pipeline(source, mode)
    assert ErrorCode.SEMANTIC_VALUE_OUT_OF_RANGE in error_codes(errors)
