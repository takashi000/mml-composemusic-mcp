"""BNF conformance tests spanning lexer, parser, semantics, and MCP validate."""

import pytest
from hypothesis import given, seed, settings
from hypothesis import strategies as st

from mml_composemusic_mcp.ast_nodes import (
    BarStmt,
    DetuneCmdStmt,
    DetuneStmt,
    DutyStmt,
    ExtCmdStmt,
    GateTimeStmt,
    Header,
    LengthStmt,
    NoteStmt,
    OctaveStmt,
    QuantizeStmt,
    RelativeVolumeStmt,
    RepeatBreakStmt,
    RepeatEndStmt,
    RepeatStartStmt,
    RestStmt,
    SweepStmt,
    TempoStmt,
    TieCmdStmt,
    TieStmt,
    TransposeStmt,
    VolumeEnvelopeDefStmt,
    VolumeStmt,
)
from mml_composemusic_mcp.ir import (
    DutyEvent,
    ErrorCode,
    ErrorPhase,
    NoteEvent,
    RepeatEvent,
)
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


def parser_errors(source: str, mode: str):
    tokens = tokenize(source, mode)
    parser = parse_ppmck if mode == "ppmck" else parse_pyxel
    return parser(source, tokens)


def first_statement(source: str, mode: str):
    program, errors = parser_errors(source, mode)
    assert not any(error.severity == "error" for error in errors)
    return program.tracks[0].statements[0]


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


def test_validate_full_pyxel_path_supports_extension_and_summary():
    result = compose_mml(
        action="validate",
        mode="pyxel",
        mml="0: T120 L4 O4 V100 Q80 @1 K-1 Y+5 @ENV1 100 10 C+4.",
    )
    assert result["valid"] is True
    assert result["channel_summary"]
    assert not result["warnings"]


@pytest.mark.parametrize(
    "source",
    [
        "A D10 c",
        "A s1,2 c",
        "A v+5 c",
        "A @v0={15|10} @v0 c",
        "A @0={0|1} @@0 c",
        "A @MP1={0,10,5,0} MP1 c",
        "A MPOF c",
        "A @EP1={0|5} EP1 c",
        "A EPOF c",
        "A @EN1={0|1} EN1 c",
        "A ENOF c",
    ],
)
def test_ppmck_extension_commands_are_supported(source):
    _, _, _, errors = parse_pipeline(source, "ppmck")
    assert not any(e.severity == "error" for e in errors)
    assert ErrorCode.SEMANTIC_UNSUPPORTED_FEATURE not in error_codes(errors)


def test_ppmck_definition_is_allowed_before_track():
    _, _, sequence, errors = parse_pipeline("@v1={15|8}\nA @v1 c", "ppmck")
    assert not errors
    assert sequence.definitions["volume_envelopes"][1] == {
        "points": [15],
        "loop_points": [8],
    }


def test_ppmck_duplicate_definition_is_rejected():
    _, _, _, errors = parse_pipeline("@v1={15}\n@v1={8}\nA c", "ppmck")
    assert ErrorCode.SEMANTIC_DUPLICATE_DEFINITION in error_codes(errors)


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


@pytest.mark.parametrize(
    ("mode", "source", "expected"),
    [
        pytest.param(
            "ppmck",
            "A c+4. r8 > < | ; comment",
            [
                TokenType.TRACK_HEADER,
                TokenType.NOTE,
                TokenType.SHARP,
                TokenType.NUMBER,
                TokenType.DOT,
                TokenType.REST,
                TokenType.NUMBER,
                TokenType.OCTAVE_UP,
                TokenType.OCTAVE_DOWN,
                TokenType.BAR,
                TokenType.COMMENT,
                TokenType.EOF,
            ],
            id="BNF-COMMON-LEX-ppmck",
        ),
        pytest.param(
            "pyxel",
            "0: C#4. R8 > < |",
            [
                TokenType.TRACK_HEADER,
                TokenType.NOTE,
                TokenType.SHARP,
                TokenType.NUMBER,
                TokenType.DOT,
                TokenType.REST,
                TokenType.NUMBER,
                TokenType.OCTAVE_UP,
                TokenType.OCTAVE_DOWN,
                TokenType.BAR,
                TokenType.EOF,
            ],
            id="BNF-COMMON-LEX-pyxel",
        ),
    ],
)
def test_bnf_common_lexer_token_contract(mode, source, expected):
    assert [token.type for token in tokenize(source, mode)] == expected


@pytest.mark.parametrize(
    ("source", "token_type", "value"),
    [
        pytest.param("A o7", TokenType.OCTAVE, "7", id="BNF-PPMCK-OCTAVE"),
        pytest.param("A l192", TokenType.LENGTH, "192", id="BNF-PPMCK-LENGTH"),
        pytest.param("A v15", TokenType.VOLUME, "15", id="BNF-PPMCK-VOLUME"),
        pytest.param("A @3", TokenType.DUTY, "3", id="BNF-PPMCK-DUTY"),
        pytest.param("A q8", TokenType.QUANTIZE, "8", id="BNF-PPMCK-QUANTIZE"),
        pytest.param("A t120", TokenType.TEMPO, "120", id="BNF-PPMCK-TEMPO"),
        pytest.param("A D-127", TokenType.DETUNE, "-127", id="BNF-PPMCK-DETUNE"),
        pytest.param("A s7,-7", TokenType.SWEEP, "7,-7", id="BNF-PPMCK-SWEEP"),
        pytest.param("A v+", TokenType.REL_VOL_UP, "", id="BNF-PPMCK-REL-VOL"),
        pytest.param("A ^16", TokenType.TIE_CMD, "^", id="BNF-PPMCK-TIE"),
    ],
)
def test_bnf_ppmck_command_lexer_contract(source, token_type, value):
    token = next(
        token for token in tokenize(source, "ppmck") if token.type == token_type
    )
    assert token.value == value


@pytest.mark.parametrize(
    ("source", "token_type", "value"),
    [
        pytest.param("0: O7", TokenType.OCTAVE, "7", id="BNF-PYXEL-OCTAVE"),
        pytest.param("0: L192", TokenType.LENGTH, "192", id="BNF-PYXEL-LENGTH"),
        pytest.param("0: V127", TokenType.VOLUME, "127", id="BNF-PYXEL-VOLUME"),
        pytest.param("0: Q100", TokenType.GATE_TIME, "100", id="BNF-PYXEL-GATE"),
        pytest.param("0: @3", TokenType.AT, "3", id="BNF-PYXEL-TONE"),
        pytest.param("0: T120", TokenType.TEMPO, "120", id="BNF-PYXEL-TEMPO"),
        pytest.param("0: K-127", TokenType.TRANSPOSE, "-127", id="BNF-PYXEL-TRANSPOSE"),
        pytest.param("0: Y+127", TokenType.DETUNE, "+127", id="BNF-PYXEL-DETUNE"),
        pytest.param("0: @ENV1 100 10", TokenType.EXT_CMD, "ENV", id="BNF-PYXEL-EXT"),
    ],
)
def test_bnf_pyxel_command_lexer_contract(source, token_type, value):
    token = next(
        token for token in tokenize(source, "pyxel") if token.type == token_type
    )
    assert token.value == value


@pytest.mark.parametrize(
    ("source", "node_type", "attributes"),
    [
        pytest.param("A o7", OctaveStmt, {"value": 7}, id="BNF-PPMCK-AST-o"),
        pytest.param("A >", OctaveStmt, {"direction": "up"}, id="BNF-PPMCK-AST-up"),
        pytest.param("A l192", LengthStmt, {"value": 192}, id="BNF-PPMCK-AST-l"),
        pytest.param("A v15", VolumeStmt, {"value": 15}, id="BNF-PPMCK-AST-v"),
        pytest.param("A @3", DutyStmt, {"value": 3}, id="BNF-PPMCK-AST-duty"),
        pytest.param("A q8", QuantizeStmt, {"value": 8}, id="BNF-PPMCK-AST-q"),
        pytest.param("A t1", TempoStmt, {"value": 1}, id="BNF-PPMCK-AST-t"),
        pytest.param("A D-127", DetuneCmdStmt, {"value": -127}, id="BNF-PPMCK-AST-D"),
        pytest.param(
            "A s7,-7", SweepStmt, {"speed": 7, "depth": -7}, id="BNF-PPMCK-AST-s"
        ),
        pytest.param(
            "A v-15", RelativeVolumeStmt, {"delta": -15}, id="BNF-PPMCK-AST-rel-v"
        ),
        pytest.param("A ^16", TieCmdStmt, {"target": 16}, id="BNF-PPMCK-AST-tie"),
        pytest.param("A &r8", TieStmt, {}, id="BNF-PPMCK-AST-slur"),
        pytest.param("A |", BarStmt, {}, id="BNF-PPMCK-AST-bar"),
        pytest.param(
            "A @v1={15,12|8}",
            VolumeEnvelopeDefStmt,
            {"slot": 1, "points": [15, 12], "loop_points": [8]},
            id="BNF-PPMCK-AST-envelope",
        ),
    ],
)
def test_bnf_ppmck_parser_ast_contract(source, node_type, attributes):
    statement = first_statement(source, "ppmck")
    assert isinstance(statement, node_type)
    for name, value in attributes.items():
        assert getattr(statement, name) == value
    if source == "A &r8":
        assert isinstance(statement.target, RestStmt)
        assert statement.target.length == 8


@pytest.mark.parametrize(
    ("source", "node_type", "attributes"),
    [
        pytest.param("0: O7", OctaveStmt, {"value": 7}, id="BNF-PYXEL-AST-O"),
        pytest.param(
            "0: <", OctaveStmt, {"direction": "down"}, id="BNF-PYXEL-AST-down"
        ),
        pytest.param("0: L192", LengthStmt, {"value": 192}, id="BNF-PYXEL-AST-L"),
        pytest.param("0: V127", VolumeStmt, {"value": 127}, id="BNF-PYXEL-AST-V"),
        pytest.param("0: Q100", GateTimeStmt, {"value": 100}, id="BNF-PYXEL-AST-Q"),
        pytest.param("0: @2", DutyStmt, {"value": 2}, id="BNF-PYXEL-AST-tone"),
        pytest.param("0: T1", TempoStmt, {"value": 1}, id="BNF-PYXEL-AST-T"),
        pytest.param("0: K-127", TransposeStmt, {"value": -127}, id="BNF-PYXEL-AST-K"),
        pytest.param("0: Y127", DetuneStmt, {"value": 127}, id="BNF-PYXEL-AST-Y"),
        pytest.param("0: &16", TieStmt, {"target": 16}, id="BNF-PYXEL-AST-tie"),
        pytest.param(
            "0: @VIB1 24 12 100",
            ExtCmdStmt,
            {"cmd": "VIB", "slot": 1, "params": [24, 12, 100]},
            id="BNF-PYXEL-AST-extension",
        ),
    ],
)
def test_bnf_pyxel_parser_ast_contract(source, node_type, attributes):
    statement = first_statement(source, "pyxel")
    assert isinstance(statement, node_type)
    for name, value in attributes.items():
        assert getattr(statement, name) == value


@pytest.mark.parametrize(
    ("mode", "source", "count"),
    [
        pytest.param("ppmck", "A [c]2", 2, id="BNF-PPMCK-AST-repeat"),
        pytest.param("pyxel", "0: [C]3", 3, id="BNF-PYXEL-AST-repeat"),
    ],
)
def test_bnf_repeat_ast_requires_a_complete_structure(mode, source, count):
    program, errors = parser_errors(source, mode)
    assert not any(error.severity == "error" for error in errors)
    statements = program.tracks[0].statements
    assert isinstance(statements[0], RepeatStartStmt)
    assert isinstance(statements[-1], RepeatEndStmt)
    assert statements[-1].count == count


@pytest.mark.parametrize(
    ("mode", "source", "track_ids", "channels"),
    [
        pytest.param(
            "ppmck",
            "A c\nB d\nT e\nN r\nL",
            ["A", "B", "T", "N", "L"],
            ["Pulse1", "Pulse2", "Triangle", "Noise", "Loop"],
            id="BNF-PPMCK-TRACKS",
        ),
        pytest.param(
            "pyxel",
            "0: C\n1: D\n2: E\n3: R",
            ["0", "1", "2", "3"],
            ["Pulse1", "Pulse2", "Triangle", "Noise"],
            id="BNF-PYXEL-TRACKS",
        ),
    ],
)
def test_bnf_track_mapping(mode, source, track_ids, channels):
    program, errors = parser_errors(source, mode)
    assert not any(error.severity == "error" for error in errors)
    assert [track.track_id for track in program.tracks] == track_ids
    assert [track.channel for track in program.tracks] == channels


def test_bnf_ppmck_header_ast_and_placement():
    source = '#TITLE "Song"\n#COMPOSER "Composer"\nA c'
    program, errors = parser_errors(source, "ppmck")
    assert not errors
    headers = program.tracks[0].headers
    assert all(isinstance(header, Header) for header in headers)
    assert [(header.key, header.value) for header in headers] == [
        ("#TITLE", "Song"),
        ("#COMPOSER", "Composer"),
    ]


@pytest.mark.parametrize(
    ("mode", "source"),
    [
        pytest.param("ppmck", "A K12 c", id="BNF-MODE-ppmck-rejects-pyxel"),
        pytest.param("pyxel", "0: v15 C", id="BNF-MODE-pyxel-rejects-ppmck"),
    ],
)
def test_bnf_cross_mode_command_is_not_silent(mode, source):
    _, _, _, errors = parse_pipeline(source, mode)
    assert any(error.severity == "error" for error in errors)


@pytest.mark.parametrize(
    ("mode", "source"),
    [
        pytest.param("ppmck", "A c", id="BNF-DEFAULTS-ppmck"),
        pytest.param("pyxel", "0: C", id="BNF-DEFAULTS-pyxel"),
    ],
)
def test_bnf_default_note_state_reaches_ir(mode, source):
    _, _, sequence, errors = parse_pipeline(source, mode)
    assert not any(error.severity == "error" for error in errors)
    note = next(
        event
        for event in sequence.channels["Pulse1"].events
        if isinstance(event, NoteEvent)
    )
    assert note.note_number == 60
    assert note.duration == 192
    assert note.gate_time == (1.0 if mode == "ppmck" else 0.8)


@pytest.mark.parametrize(
    ("mode", "source"),
    [
        pytest.param(
            "ppmck",
            "A o0 o7 l1 l192 v0 v15 @0 @3 q1 q8 t1 c",
            id="BNF-RANGE-ppmck-valid",
        ),
        pytest.param("ppmck", "A s0,1 s7,-7 c", id="BNF-RANGE-ppmck-sweep-valid"),
        pytest.param(
            "pyxel",
            "0: O0 O7 L1 L192 V0 V127 Q0 Q100 @1 @2 T1 C",
            id="BNF-RANGE-pyxel-valid",
        ),
        pytest.param(
            "pyxel", "0: K-127 K127 Y-127 Y127 C", id="BNF-RANGE-pyxel-signed-valid"
        ),
    ],
)
def test_bnf_semantic_boundary_values_are_accepted(mode, source):
    _, _, _, errors = parse_pipeline(source, mode)
    assert not any(error.severity == "error" for error in errors)


@pytest.mark.parametrize(
    ("mode", "source"),
    [
        pytest.param("ppmck", "A o8 c", id="BNF-RANGE-ppmck-o"),
        pytest.param("ppmck", "A l0 c", id="BNF-RANGE-ppmck-l-low"),
        pytest.param("ppmck", "A l193 c", id="BNF-RANGE-ppmck-l-high"),
        pytest.param("ppmck", "A v16 c", id="BNF-RANGE-ppmck-v"),
        pytest.param("ppmck", "A @4 c", id="BNF-RANGE-ppmck-duty"),
        pytest.param("ppmck", "A q0 c", id="BNF-RANGE-ppmck-q-low"),
        pytest.param("ppmck", "A q9 c", id="BNF-RANGE-ppmck-q-high"),
        pytest.param("ppmck", "A t0 c", id="BNF-RANGE-ppmck-t"),
        pytest.param("ppmck", "A s8,1 c", id="BNF-RANGE-ppmck-s-speed"),
        pytest.param("ppmck", "A s0,0 c", id="BNF-RANGE-ppmck-s-depth"),
        pytest.param("pyxel", "0: O8 C", id="BNF-RANGE-pyxel-O"),
        pytest.param("pyxel", "0: L0 C", id="BNF-RANGE-pyxel-L-low"),
        pytest.param("pyxel", "0: L193 C", id="BNF-RANGE-pyxel-L-high"),
        pytest.param("pyxel", "0: V128 C", id="BNF-RANGE-pyxel-V"),
        pytest.param("pyxel", "0: Q101 C", id="BNF-RANGE-pyxel-Q"),
        pytest.param("pyxel", "0: @4 C", id="BNF-RANGE-pyxel-tone"),
        pytest.param("pyxel", "0: T0 C", id="BNF-RANGE-pyxel-T"),
    ],
)
def test_bnf_semantic_out_of_range_reports_phase(mode, source):
    _, _, _, errors = parse_pipeline(source, mode)
    matching = [
        error for error in errors if error.code == ErrorCode.SEMANTIC_VALUE_OUT_OF_RANGE
    ]
    assert matching
    assert all(error.phase == ErrorPhase.SEMANTIC for error in matching)


@pytest.mark.parametrize(
    ("mode", "source"),
    [
        pytest.param("ppmck", "T @2 c", id="BNF-CHANNEL-ppmck-duty"),
        pytest.param("ppmck", "T s1,1 c", id="BNF-CHANNEL-ppmck-sweep"),
        pytest.param("pyxel", "2: @1 C", id="BNF-CHANNEL-pyxel-tone"),
    ],
)
def test_bnf_channel_mismatch_is_semantic(mode, source):
    _, _, _, errors = parse_pipeline(source, mode)
    mismatch = [
        error for error in errors if error.code == ErrorCode.SEMANTIC_CHANNEL_MISMATCH
    ]
    assert mismatch
    assert all(error.phase == ErrorPhase.SEMANTIC for error in mismatch)


def test_bnf_pyxel_nested_repeat_reaches_ir():
    _, _, sequence, errors = parse_pipeline("0: [C [D]2]3", "pyxel")
    assert not any(error.severity == "error" for error in errors)
    notes = [
        event
        for event in sequence.channels["Pulse1"].events
        if isinstance(event, NoteEvent)
    ]
    assert len(notes) == 9


@pytest.mark.parametrize(
    ("source", "event_key"),
    [
        pytest.param("0: @ENV1 100 10 C", "envelopes", id="BNF-PYXEL-IR-ENV"),
        pytest.param("0: @VIB1 24 12 100 C", "vibratos", id="BNF-PYXEL-IR-VIB"),
        pytest.param("0: @GLI1 100 24 C", "glides", id="BNF-PYXEL-IR-GLI"),
    ],
)
def test_bnf_pyxel_extension_definition_reaches_ir(source, event_key):
    _, _, sequence, errors = parse_pipeline(source, "pyxel")
    assert not any(error.severity == "error" for error in errors)
    assert 1 in sequence.definitions[event_key]


def test_parser_error_stops_pipeline_before_semantic_ir():
    _, _, sequence, errors = parse_pipeline("0: C ? D", "pyxel")
    assert sequence is None
    assert ErrorCode.SYNTAX_INVALID_TOKEN in error_codes(errors)
    assert all(error.phase == ErrorPhase.SYNTAX for error in errors)


def test_semantic_error_is_distinguishable_from_parser_error():
    _, program, sequence, errors = parse_pipeline("0: O8 C", "pyxel")
    assert program.tracks
    assert sequence is not None
    assert any(error.phase == ErrorPhase.SEMANTIC for error in errors)


@pytest.mark.parametrize(
    ("mode", "source"),
    [
        pytest.param("ppmck", "A C", id="STRICT-CASE-ppmck-note"),
        pytest.param("ppmck", "A O4 c", id="STRICT-CASE-ppmck-command"),
        pytest.param("pyxel", "0: c", id="STRICT-CASE-pyxel-note"),
        pytest.param("pyxel", "0: o4 C", id="STRICT-CASE-pyxel-command"),
        pytest.param("pyxel", "0: @env1 1 1 C", id="STRICT-CASE-pyxel-ext"),
    ],
)
def test_case_rules_are_enforced_by_the_lexer(mode, source):
    tokens, _, sequence, errors = parse_pipeline(source, mode)
    assert any(token.type == TokenType.INVALID for token in tokens)
    assert sequence is None
    assert ErrorCode.SYNTAX_INVALID_TOKEN in error_codes(errors)


@pytest.mark.parametrize(
    ("source", "raw"),
    [
        pytest.param("A D+", "D+", id="RAW-sign-only"),
        pytest.param("A s1,-", "s1,-", id="RAW-sweep-sign-only"),
        pytest.param("A s1 2", "s1", id="RAW-missing-comma"),
    ],
)
def test_malformed_compound_tokens_preserve_source_raw_and_report(source, raw):
    tokens, _, sequence, errors = parse_pipeline(source, "ppmck")
    assert raw in [token.raw for token in tokens]
    assert sequence is None
    assert ErrorCode.SYNTAX_INVALID_NUMBER in error_codes(errors)


def test_ppmck_top_level_order_and_global_definitions():
    valid = '#TITLE "Song"\n@v1={15,8}\n@EP2={-12,+12}\nA @v1 EP2 c'
    _, program, sequence, errors = parse_pipeline(valid, "ppmck")
    assert not any(error.severity == "error" for error in errors)
    assert len(program.global_statements) == 2
    assert 1 in sequence.definitions["volume_envelopes"]
    assert 2 in sequence.definitions["pitch_envelopes"]

    for invalid in ('@v1={15}\n#TITLE "Late"\nA c', "c\nA c", "@v1\nA c"):
        _, _, sequence, errors = parse_pipeline(invalid, "ppmck")
        assert sequence is None
        assert ErrorCode.SYNTAX_UNEXPECTED_TOKEN in error_codes(errors)


def test_ppmck_repeat_break_ast_and_expansion():
    source = "A l4 [c|d]3 e"
    _, program, sequence, errors = parse_pipeline(source, "ppmck")
    assert not any(error.severity == "error" for error in errors)
    assert isinstance(program.tracks[0].statements[3], RepeatBreakStmt)
    notes = [
        event
        for event in sequence.channels["Pulse1"].events
        if isinstance(event, NoteEvent)
    ]
    assert [note.note_number for note in notes] == [60, 62, 60, 62, 60, 64]
    assert [note.tick_position for note in notes] == [0, 192, 384, 576, 768, 960]


@pytest.mark.parametrize(
    ("source", "expected_notes"),
    [
        pytest.param("A [c d]1", [60, 62], id="REPEAT-normal-N1"),
        pytest.param("A [c|d]1", [60], id="REPEAT-break-N1"),
        pytest.param(
            "A [c [d|e]2|f]2",
            [60, 62, 64, 62, 65, 60, 62, 64, 62],
            id="REPEAT-nested-breaks",
        ),
    ],
)
def test_ppmck_repeat_variants(source, expected_notes):
    _, _, sequence, errors = parse_pipeline(source, "ppmck")
    assert not any(error.severity == "error" for error in errors)
    notes = [
        event.note_number
        for event in sequence.channels["Pulse1"].events
        if isinstance(event, NoteEvent)
    ]
    assert notes == expected_notes


@pytest.mark.parametrize(
    "source",
    [
        pytest.param("A | c", id="REPEAT-outside-bar-valid"),
        pytest.param("A [c|d|e]2", id="REPEAT-duplicate-break"),
        pytest.param("A [c", id="REPEAT-unterminated"),
        pytest.param("A c]2", id="REPEAT-extra-end"),
    ],
)
def test_ppmck_repeat_structure_is_checked_in_parser(source):
    program, errors = parser_errors(source, "ppmck")
    if source == "A | c":
        assert not any(error.severity == "error" for error in errors)
        assert isinstance(program.tracks[0].statements[0], BarStmt)
    else:
        assert any(error.severity == "error" for error in errors)


def test_infinite_repeat_has_two_cycle_preview_and_repeat_count_zero():
    _, _, sequence, errors = parse_pipeline("A [c d]", "ppmck")
    assert not any(error.severity == "error" for error in errors)
    assert any(error.severity == "warning" for error in errors)
    events = sequence.channels["Pulse1"].events
    assert len([event for event in events if isinstance(event, NoteEvent)]) == 4
    repeat = next(event for event in events if isinstance(event, RepeatEvent))
    assert repeat.repeat_count == 0
    assert (repeat.start_tick, repeat.end_tick) == (0, 768)


@pytest.mark.parametrize(
    ("count", "accepted"),
    [
        pytest.param(99_999, True, id="REPEAT-LIMIT-exact-100000-events"),
        pytest.param(100_000, False, id="REPEAT-LIMIT-100001-events"),
    ],
)
def test_repeat_expansion_event_limit_is_transactional(count, accepted):
    _, _, sequence, errors = parse_pipeline(f"A [c]{count}", "ppmck")
    range_errors = [
        error for error in errors if error.code == ErrorCode.SEMANTIC_VALUE_OUT_OF_RANGE
    ]
    if accepted:
        assert not range_errors
        assert len(sequence.channels["Pulse1"].events) == 100_000
    else:
        assert range_errors
        assert sequence.channels["Pulse1"].events == []


def test_nested_repeat_limit_is_preflighted_without_partial_events():
    _, _, sequence, errors = parse_pipeline("A [[c]500]201", "ppmck")
    assert ErrorCode.SEMANTIC_VALUE_OUT_OF_RANGE in error_codes(errors)
    assert sequence.channels["Pulse1"].events == []


@pytest.mark.parametrize(
    ("loop_body", "expected_start"),
    [
        pytest.param("", 0, id="LOOP-empty"),
        pytest.param("l8 r", 96, id="LOOP-default-length"),
        pytest.param("l8 r.", 144, id="LOOP-dotted-rest"),
        pytest.param("l8 [r]3", 288, id="LOOP-finite-repeat"),
        pytest.param("l8 [r|r]2", 288, id="LOOP-repeat-break"),
        pytest.param("l8 [r]", 192, id="LOOP-infinite-preview"),
    ],
)
def test_loop_track_calculates_global_loop_start(loop_body, expected_start):
    _, _, sequence, errors = parse_pipeline(f"A l1 c\nL {loop_body}", "ppmck")
    assert not any(error.severity == "error" for error in errors)
    for channel in sequence.channels.values():
        repeats = [event for event in channel.events if isinstance(event, RepeatEvent)]
        assert repeats[-1].repeat_count == 0
        assert repeats[-1].start_tick == expected_start
        assert repeats[-1].end_tick == 768


@pytest.mark.parametrize(
    "source",
    [
        pytest.param("A c\nL c", id="LOOP-note-forbidden"),
        pytest.param("A c\nL v1", id="LOOP-volume-forbidden"),
        pytest.param("A c\nL r\nL", id="LOOP-duplicate"),
    ],
)
def test_loop_track_rejects_forbidden_or_duplicate_content(source):
    _, _, sequence, errors = parse_pipeline(source, "ppmck")
    assert sequence is None
    assert any(error.severity == "error" for error in errors)


def test_loop_start_must_be_before_the_longest_audio_track_end():
    _, _, sequence, errors = parse_pipeline("A l4 c\nL l4 r", "ppmck")
    assert sequence is not None
    assert ErrorCode.SEMANTIC_VALUE_OUT_OF_RANGE in error_codes(errors)
    assert not any(
        isinstance(event, RepeatEvent)
        for channel in sequence.channels.values()
        for event in channel.events
    )


@pytest.mark.parametrize(
    ("source", "accepted"),
    [
        pytest.param("@v0={0,15}\nA c", True, id="ENV-volume-boundaries"),
        pytest.param("@1={0,3}\nA c", True, id="ENV-duty-boundaries"),
        pytest.param("@EP255={-127,+126}\nA c", True, id="ENV-pitch-signed"),
        pytest.param("@EN255={-127,126}\nA c", True, id="ENV-note-signed"),
        pytest.param("@v256={1}\nA c", False, id="ENV-slot-high"),
        pytest.param("@v1={16}\nA c", False, id="ENV-volume-high"),
        pytest.param("@1={4}\nA c", False, id="ENV-duty-high"),
        pytest.param("@EP1={127}\nA c", False, id="ENV-pitch-high"),
        pytest.param("@EN1={-128}\nA c", False, id="ENV-note-low"),
    ],
)
def test_ppmck_definition_ranges(source, accepted):
    _, _, _, errors = parse_pipeline(source, "ppmck")
    range_errors = [
        error for error in errors if error.code == ErrorCode.SEMANTIC_VALUE_OUT_OF_RANGE
    ]
    assert bool(range_errors) is not accepted


@pytest.mark.parametrize(
    "source",
    [
        pytest.param("@v1={}\nA c", id="DEF-empty"),
        pytest.param("@v1={1\nA c", id="DEF-unterminated"),
        pytest.param("@MP1={0,1,2}\nA c", id="DEF-lfo-missing-value"),
        pytest.param("@MP1={0 1,2,0}\nA c", id="DEF-lfo-missing-comma"),
    ],
)
def test_ppmck_broken_definitions_stop_before_semantics(source):
    _, _, sequence, errors = parse_pipeline(source, "ppmck")
    assert sequence is None
    assert any(error.phase == ErrorPhase.SYNTAX for error in errors)


@pytest.mark.parametrize(
    ("cmd", "params", "accepted"),
    [
        pytest.param("ENV", "1 2", True, id="PYXEL-ENV-two"),
        pytest.param("ENV", "1 2 3 4", True, id="PYXEL-ENV-four"),
        pytest.param("ENV", "1", False, id="PYXEL-ENV-one"),
        pytest.param("ENV", "1 2 3", False, id="PYXEL-ENV-odd"),
        pytest.param("VIB", "1 2 3", True, id="PYXEL-VIB-three"),
        pytest.param("VIB", "1 2", False, id="PYXEL-VIB-two"),
        pytest.param("VIB", "1 2 3 4", False, id="PYXEL-VIB-four"),
        pytest.param("GLI", "1 2", True, id="PYXEL-GLI-two"),
        pytest.param("GLI", "1", False, id="PYXEL-GLI-one"),
        pytest.param("GLI", "1 2 3", False, id="PYXEL-GLI-three"),
    ],
)
def test_pyxel_extension_arity(cmd, params, accepted):
    _, _, _, errors = parse_pipeline(f"0: @{cmd}1 {params} C", "pyxel")
    range_errors = [
        error for error in errors if error.code == ErrorCode.SEMANTIC_VALUE_OUT_OF_RANGE
    ]
    assert bool(range_errors) is not accepted


def test_pyxel_extension_selection_and_definition_errors_use_source_position():
    source = "0: @VIB1 1 2 3 C @VIB1 D"
    _, _, sequence, errors = parse_pipeline(source, "pyxel")
    assert not any(error.severity == "error" for error in errors)
    assert 1 in sequence.definitions["vibratos"]

    for invalid, code in (
        ("0: @VIB1 C", ErrorCode.SEMANTIC_UNDEFINED_REFERENCE),
        ("0: @VIB0 1 2 3 C", ErrorCode.SEMANTIC_VALUE_OUT_OF_RANGE),
        ("0: @VIB1 1 2 3 @VIB1 4 5 6 C", ErrorCode.SEMANTIC_DUPLICATE_DEFINITION),
    ):
        _, _, _, errors = parse_pipeline(invalid, "pyxel")
        matching = [error for error in errors if error.code == code]
        assert matching and matching[0].line == 1 and matching[0].column > 0


@pytest.mark.parametrize(
    ("mode", "source"),
    [
        pytest.param("ppmck", "A c0", id="LENGTH-ppmck-note-zero"),
        pytest.param("ppmck", "A c193", id="LENGTH-ppmck-note-high"),
        pytest.param("ppmck", "A c ^0", id="LENGTH-ppmck-tie-zero"),
        pytest.param("ppmck", "A c ^193", id="LENGTH-ppmck-tie-high"),
        pytest.param("pyxel", "0: C0", id="LENGTH-pyxel-note-zero"),
        pytest.param("pyxel", "0: C193", id="LENGTH-pyxel-note-high"),
        pytest.param("pyxel", "0: C &0", id="LENGTH-pyxel-tie-zero"),
        pytest.param("pyxel", "0: C &193", id="LENGTH-pyxel-tie-high"),
    ],
)
def test_explicit_and_tie_lengths_are_checked_before_division(mode, source):
    _, _, _, errors = parse_pipeline(source, mode)
    assert ErrorCode.SEMANTIC_VALUE_OUT_OF_RANGE in error_codes(errors)


def test_invalid_note_length_does_not_advance_state_or_add_partial_event():
    _, _, sequence, errors = parse_pipeline("A l4 c c0 d", "ppmck")
    assert ErrorCode.SEMANTIC_VALUE_OUT_OF_RANGE in error_codes(errors)
    notes = [
        event
        for event in sequence.channels["Pulse1"].events
        if isinstance(event, NoteEvent)
    ]
    assert len(notes) == 2
    assert notes[1].tick_position == 192


def test_compose_does_not_call_synthesizer_after_syntax_or_semantic_error(monkeypatch):
    import mml_composemusic_mcp.server as server

    called = False

    def fail_if_called(*args, **kwargs):  # type: ignore[no-untyped-def]
        nonlocal called
        called = True
        raise AssertionError("synthesizer must not be called")

    monkeypatch.setattr(server, "synthesize", fail_if_called)
    for mode, source in (("ppmck", "A C"), ("pyxel", "0: O8 C")):
        result = compose_mml(action="compose", mml=source, mode=mode)
        assert result["success"] is False
    assert called is False


@pytest.mark.parametrize(
    ("mode", "source"),
    [
        pytest.param("ppmck", "A [c]0", id="REPEAT-ZERO-ppmck"),
        pytest.param("pyxel", "0: [C]0", id="REPEAT-ZERO-pyxel"),
    ],
)
def test_repeat_count_zero_is_rejected_without_partial_expansion(mode, source):
    _, _, sequence, errors = parse_pipeline(source, mode)
    assert ErrorCode.SEMANTIC_VALUE_OUT_OF_RANGE in error_codes(errors)
    assert sequence.channels["Pulse1"].events == []


def test_ppmck_effect_reference_errors_keep_ast_source_position():
    source = "A c @v7"
    _, _, _, errors = parse_pipeline(source, "ppmck")
    undefined = [
        error
        for error in errors
        if error.code == ErrorCode.SEMANTIC_UNDEFINED_REFERENCE
    ]
    assert undefined and (undefined[0].line, undefined[0].column) == (1, 5)

    duplicate_source = "@v1={1}\n@v1={2}\nA c"
    _, _, _, errors = parse_pipeline(duplicate_source, "ppmck")
    duplicate = [
        error
        for error in errors
        if error.code == ErrorCode.SEMANTIC_DUPLICATE_DEFINITION
    ]
    assert duplicate and (duplicate[0].line, duplicate[0].column) == (2, 1)


@pytest.mark.parametrize(
    "source",
    [
        pytest.param("2: @0 C", id="PYXEL-TONE-triangle"),
        pytest.param("3: @3 C", id="PYXEL-TONE-noise"),
    ],
)
def test_pyxel_non_pulse_tones_match_their_track(source):
    _, _, _, errors = parse_pipeline(source, "pyxel")
    assert not any(error.severity == "error" for error in errors)


def test_giant_numeric_value_is_diagnosed_without_parser_failure():
    source = "A l" + ("9" * 1_000) + " c"
    _, _, sequence, errors = parse_pipeline(source, "ppmck")
    assert sequence is not None
    assert ErrorCode.SEMANTIC_VALUE_OUT_OF_RANGE in error_codes(errors)
