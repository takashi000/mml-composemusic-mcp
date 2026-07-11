"""Shared pytest fixtures."""

import pytest

import mml_composemusic_mcp.server as server_mod


@pytest.fixture
def tmp_output_dir(tmp_path, monkeypatch):
    """Provide an isolated output directory and patch server.OUTPUT_DIR."""
    out = tmp_path / "data"
    out.mkdir()
    monkeypatch.setattr(server_mod, "OUTPUT_DIR", out)
    return out


@pytest.fixture
def compose_mml(tmp_output_dir):
    """Return the compose_mml function with output dir patched."""
    return server_mod.compose_mml
