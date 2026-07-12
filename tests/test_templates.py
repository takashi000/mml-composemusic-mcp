"""Tests for MML template generation."""

import pytest

from mml_composemusic_mcp.server import compose_mml
from mml_composemusic_mcp.templates import DESCRIPTIONS, TEMPLATES, get_template

TEMPLATE_NAMES = (
    "basic",
    "melody",
    "chord",
    "drum",
    "empty",
    "expressive_lead",
    "vibrato_lead",
    "pitch_motion",
)


def test_all_templates_exist():
    for mode in ("ppmck", "pyxel"):
        for name in TEMPLATE_NAMES:
            assert mode in TEMPLATES
            assert name in TEMPLATES[mode]
            assert TEMPLATES[mode][name]


def test_all_descriptions_exist():
    for name in TEMPLATE_NAMES:
        assert name in DESCRIPTIONS
        assert DESCRIPTIONS[name]


def test_get_template_basic():
    mml, desc = get_template("ppmck", "basic")
    assert mml
    assert desc == "基本的な4ch構成（メロディ+和音+ベース+リズム）"


def test_get_template_melody():
    mml, desc = get_template("pyxel", "melody")
    assert mml
    assert desc == "メロディ重視（Pulse1主旋律、他は伴奏最小限）"


def test_get_template_chord():
    mml, desc = get_template("ppmck", "chord")
    assert mml
    assert desc == "コード伴奏重視（Pulse2で和音、Triangleでベース）"


def test_get_template_drum():
    mml, desc = get_template("pyxel", "drum")
    assert mml
    assert desc == "リズム重視（Noise中心のビートパターン）"


def test_get_template_empty():
    mml, desc = get_template("ppmck", "empty")
    assert mml
    assert desc == "各チャンネルのヘッダーのみ（空のテンプレート）"


@pytest.mark.parametrize("mode", ["ppmck", "pyxel"])
@pytest.mark.parametrize("template", TEMPLATE_NAMES)
def test_template_validates(mode, template):
    mml, _ = get_template(mode, template)
    result = compose_mml(action="validate", mml=mml, mode=mode)
    assert result["valid"] is True, f"{mode}/{template} invalid: {result['errors']}"


def test_template_ppmck_has_headers():
    mml, _ = get_template("ppmck", "basic")
    assert "#TITLE" in mml


def test_template_pyxel_has_track_headers():
    mml, _ = get_template("pyxel", "basic")
    assert "0:" in mml
    assert "1:" in mml
    assert "2:" in mml
    assert "3:" in mml


def test_template_empty_has_rests():
    mml, _ = get_template("ppmck", "empty")
    # Even empty template should have rests (not truly empty)
    assert "r" in mml.lower()


def test_template_invalid_name_falls_back():
    result = compose_mml(action="template", mode="ppmck", template="nonexistent")
    assert result["mml"]
    assert result["description"]


@pytest.mark.parametrize(
    ("mode", "template", "event_types"),
    [
        ("ppmck", "expressive_lead", {"vol_envelope", "duty_envelope", "rel_volume"}),
        ("pyxel", "expressive_lead", {"envelope"}),
        ("ppmck", "vibrato_lead", {"lfo", "pitch_envelope", "detune"}),
        ("pyxel", "vibrato_lead", {"vibrato"}),
        ("ppmck", "pitch_motion", {"note_envelope", "sweep"}),
        ("pyxel", "pitch_motion", {"glide"}),
    ],
)
def test_synthesis_templates_contain_expected_events(mode, template, event_types):
    mml, _ = get_template(mode, template)
    result = compose_mml(action="validate", mml=mml, mode=mode)
    actual_types = {
        event["type"]
        for channel in result["note_sequence"]["channels"].values()
        for event in channel["events"]
    }
    assert event_types <= actual_types


def test_pyxel_vibrato_template_applies_detune_to_notes():
    mml, _ = get_template("pyxel", "vibrato_lead")
    result = compose_mml(action="validate", mml=mml, mode="pyxel")
    notes = [
        event
        for channel in result["note_sequence"]["channels"].values()
        for event in channel["events"]
        if event["type"] == "note"
    ]
    assert any(note["detune_cents"] != 0 for note in notes)
