"""Tests for MCP server transport CLI argument parsing."""

from unittest.mock import patch

import pytest

from mml_composemusic_mcp.server import main


def test_transport_stdio_default():
    """Default transport should be stdio."""
    with patch("sys.argv", ["server", "--output-dir", "./data"]):
        with patch("mml_composemusic_mcp.server.mcp.run") as mock_run:
            main()
            mock_run.assert_called_once()
            call_kwargs = mock_run.call_args
            assert call_kwargs[1]["transport"] == "stdio"


def test_transport_http():
    """HTTP transport should pass host and port."""
    with patch(
        "sys.argv",
        ["server", "--transport", "http", "--host", "0.0.0.0", "--port", "9000"],
    ):
        with patch("mml_composemusic_mcp.server.mcp.run") as mock_run:
            main()
            call_kwargs = mock_run.call_args
            assert call_kwargs[1]["transport"] == "http"
            assert call_kwargs[1]["host"] == "0.0.0.0"
            assert call_kwargs[1]["port"] == 9000


def test_transport_sse():
    """SSE transport should be accepted."""
    with patch("sys.argv", ["server", "--transport", "sse", "--port", "8080"]):
        with patch("mml_composemusic_mcp.server.mcp.run") as mock_run:
            main()
            call_kwargs = mock_run.call_args
            assert call_kwargs[1]["transport"] == "sse"


def test_transport_streamable_http():
    """Streamable HTTP transport should be accepted."""
    with patch("sys.argv", ["server", "--transport", "streamable-http"]):
        with patch("mml_composemusic_mcp.server.mcp.run") as mock_run:
            main()
            call_kwargs = mock_run.call_args
            assert call_kwargs[1]["transport"] == "streamable-http"


def test_transport_invalid_rejected():
    """Invalid transport should be rejected by argparse."""
    with patch("sys.argv", ["server", "--transport", "invalid"]):
        with pytest.raises(SystemExit):
            main()


def test_output_dir_override(tmp_path):
    """--output-dir should set OUTPUT_DIR."""
    with patch("sys.argv", ["server", "--output-dir", str(tmp_path / "out")]):
        with patch("mml_composemusic_mcp.server.mcp.run"):
            import mml_composemusic_mcp.server as srv

            main()
            assert srv.OUTPUT_DIR == tmp_path / "out"
