"""Exhaustive tests for the compose_mml MCP tool."""

from pathlib import Path

VALID_PPMCK = """#TITLE "Test"
A t120 l4 o4 v15 q2
  c e g c
B o3
  c e g
T l4 o3 v7
  c2 g2
N l4 v10
  c r c r
"""

VALID_PYXEL = """0: T120 L4 O4 V100 @1
  C E G C
1: O3
  C E G
2: L4 O3 V60
  C2 G2
3: L4 V80
  C R C R
"""


def test_compose_ppmck(compose_mml, tmp_output_dir):
    result = compose_mml(action="compose", mml=VALID_PPMCK, mode="ppmck")
    assert result["success"] is True
    assert result["wav_path"] is not None
    assert Path(result["wav_path"]).exists()
    assert result["duration_sec"] > 0
    assert result["note_sequence"] is not None
    assert "validation" in result
    assert "errors" in result["validation"]
    assert "warnings" in result["validation"]


def test_compose_pyxel(compose_mml, tmp_output_dir):
    result = compose_mml(action="compose", mml=VALID_PYXEL, mode="pyxel")
    assert result["success"] is True
    assert result["wav_path"] is not None
    assert Path(result["wav_path"]).exists()
    assert result["duration_sec"] > 0


def test_validate_ppmck(compose_mml):
    result = compose_mml(action="validate", mml=VALID_PPMCK, mode="ppmck")
    assert result["valid"] is True
    assert "warnings" in result
    assert result["channel_summary"]
    for ch in result["channel_summary"]:
        assert "channel" in ch
        assert "note_count" in ch
        assert "octave_range" in ch
        assert "duration_ticks" in ch


def test_validate_pyxel(compose_mml):
    result = compose_mml(action="validate", mml=VALID_PYXEL, mode="pyxel")
    assert result["valid"] is True
    assert "warnings" in result
    assert result["channel_summary"]


def test_template_all(compose_mml):
    for mode in ("ppmck", "pyxel"):
        for template in (
            "basic",
            "melody",
            "chord",
            "drum",
            "empty",
            "expressive_lead",
            "vibrato_lead",
            "pitch_motion",
        ):
            result = compose_mml(action="template", mode=mode, template=template)
            assert "mml" in result
            assert "description" in result
            assert result["mml"]
            assert result["description"]
            validated = compose_mml(action="validate", mml=result["mml"], mode=mode)
            assert validated["valid"] is True, (
                f"{mode}/{template} template invalid: {validated['errors']}"
            )


def test_synthesis_templates_compose(compose_mml, tmp_output_dir):
    for mode in ("ppmck", "pyxel"):
        for template in ("expressive_lead", "vibrato_lead", "pitch_motion"):
            generated = compose_mml(action="template", mode=mode, template=template)
            result = compose_mml(action="compose", mml=generated["mml"], mode=mode)
            assert result["success"] is True, (
                f"{mode}/{template} synthesis failed: {result['validation']}"
            )
            assert result["duration_sec"] > 0
            assert Path(result["wav_path"]).exists()


def test_template_invalid_fallback(compose_mml):
    result = compose_mml(action="template", mode="pyxel", template="unknown")
    assert result["description"] == "基本的な4ch構成（メロディ+和音+ベース+リズム）"


def test_compose_missing_mml(compose_mml):
    result = compose_mml(action="compose", mml="", mode="ppmck")
    assert result["success"] is False
    assert any(e["severity"] == "error" for e in result["validation"]["errors"])


def test_compose_missing_mode(compose_mml):
    result = compose_mml(action="compose", mml="A c", mode="")
    assert result["success"] is False
    assert any(e["severity"] == "error" for e in result["validation"]["errors"])


def test_validate_missing_mode(compose_mml):
    result = compose_mml(action="validate", mml="A c", mode="")
    assert result["valid"] is False


def test_compose_unknown_mode(compose_mml):
    result = compose_mml(action="compose", mml="A c", mode="xyz")
    assert result["success"] is False
    assert any(
        e["code"] == "VALIDATION_INVALID_MODE" for e in result["validation"]["errors"]
    )


def test_compose_with_syntax_error(compose_mml):
    result = compose_mml(action="compose", mml="A t0\n  c", mode="ppmck")
    assert result["success"] is False
    assert result["wav_path"] is None
    assert result["duration_sec"] == 0
    assert any(e["severity"] == "error" for e in result["validation"]["errors"])


def test_compose_with_warning(compose_mml, tmp_output_dir):
    mml = """2: T120 L4 O3 V60 @1
  C4
"""
    result = compose_mml(action="compose", mml=mml, mode="pyxel")
    assert result["success"] is True
    assert result["validation"]["warnings"]


def test_action_invalid(compose_mml):
    result = compose_mml(action="unknown")
    assert result["success"] is False
    assert any("action" in e["message"] for e in result["validation"]["errors"])


def test_compose_sample_rates(compose_mml, tmp_output_dir):
    for rate in (22050, 44100, 48000):
        result = compose_mml(
            action="compose",
            mml="A t120 l4 o4 v15 q2\n  c4",
            mode="ppmck",
            sample_rate=rate,
        )
        assert result["success"] is True, f"sample_rate={rate} failed"
        assert result["duration_sec"] > 0


def test_compose_normalize(compose_mml, tmp_output_dir):
    base = """0: T120 L4 O4 V100 @1
  C4
"""
    on = compose_mml(action="compose", mml=base, mode="pyxel", normalize=True)
    off = compose_mml(action="compose", mml=base, mode="pyxel", normalize=False)
    assert on["success"] and off["success"]
    assert Path(on["wav_path"]).exists()
    assert Path(off["wav_path"]).exists()


def test_compose_creates_timestamped_output_directory(compose_mml, tmp_output_dir):
    """Compose writes the WAV and source MML in a timestamped directory."""
    mml = """A t120 l4 o4 v15 q2
  c4
"""
    result1 = compose_mml(action="compose", mml=mml, mode="ppmck")
    result2 = compose_mml(action="compose", mml=mml, mode="ppmck")
    assert result1["success"] is True
    assert result2["success"] is True

    path1 = result1["wav_path"]
    path2 = result2["wav_path"]
    assert path1 is not None
    assert path2 is not None
    assert path1 != path2, "Two compose calls produced the same output directory"

    p1 = Path(path1)
    p2 = Path(path2)
    assert p1.exists()
    assert p2.exists()
    assert p1.name == "output.wav"
    assert p2.name == "output.wav"
    assert p1.parent != p2.parent
    assert p1.parent.parent == tmp_output_dir
    assert p2.parent.parent == tmp_output_dir
    assert (p1.parent / "output.mml").read_text(encoding="utf-8") == mml
    assert (p2.parent / "output.mml").read_text(encoding="utf-8") == mml

    # Ensure the directory follows the expected timestamp pattern.
    import re

    pattern = re.compile(r"^\d{8}_\d{6}_\d{3}$")
    assert pattern.match(p1.parent.name)
    assert pattern.match(p2.parent.name)
