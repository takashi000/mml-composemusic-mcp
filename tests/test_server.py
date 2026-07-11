"""Tests for MCP server compose_mml tool."""

from mml_composemusic_mcp.server import compose_mml

PPMCK_MML = """#TITLE "Test"
A t120 l4 o4 v15 q2
  c e g c
"""


def test_compose_ppmck():
    result = compose_mml(action="compose", mml=PPMCK_MML, mode="ppmck")
    assert result["success"] is True
    assert result["wav_path"] is not None
    assert result["duration_sec"] > 0


def test_validate_ppmck():
    result = compose_mml(action="validate", mml=PPMCK_MML, mode="ppmck")
    assert result["valid"] is True
    assert result["channel_summary"]


def test_template():
    result = compose_mml(action="template", mode="pyxel", template="basic")
    assert "mml" in result
    assert "0:" in result["mml"]


def test_compose_error():
    result = compose_mml(action="compose", mml="A t0\n  c", mode="ppmck")
    assert result["success"] is False
    assert any(e["severity"] == "error" for e in result["validation"]["errors"])
