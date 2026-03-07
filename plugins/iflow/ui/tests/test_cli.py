"""Tests for CLI entry point (__main__.py)."""

import socket
import unittest.mock

import pytest


# ---------------------------------------------------------------------------
# Task 4.2.2: Port conflict exits with SystemExit (AC-2)
# ---------------------------------------------------------------------------
def test_cli_port_conflict_exits():
    """CLI raises SystemExit when the requested port is already in use."""
    from ui.__main__ import main

    # Bind a socket to occupy a port
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.bind(("127.0.0.1", 0))
    occupied_port = sock.getsockname()[1]

    try:
        with pytest.raises(SystemExit):
            main(["--port", str(occupied_port)])
    finally:
        sock.close()


# ---------------------------------------------------------------------------
# Task 4.2.3: CLI startup URL output (AC-1)
# ---------------------------------------------------------------------------
def test_cli_startup_url_output(capsys):
    """CLI prints startup URL to stdout before starting uvicorn."""
    from ui.__main__ import main

    with unittest.mock.patch("ui.__main__.uvicorn") as mock_uvicorn:
        mock_uvicorn.run = unittest.mock.MagicMock()
        main([])

    captured = capsys.readouterr()
    assert "http://127.0.0.1:8718/" in captured.out
