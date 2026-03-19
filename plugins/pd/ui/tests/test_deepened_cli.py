"""Deepened tests for CLI entry point (__main__.py).

Covers boundary values for port parsing and port override behavior.
"""

import socket
import unittest.mock

import pytest


# ===========================================================================
# Dimension 1: BDD Scenario — Port Override
# ===========================================================================


# ---------------------------------------------------------------------------
# test_port_override_via_flag
# derived_from: spec:AC-2 (--port flag), design:C2 CLI arguments
# ---------------------------------------------------------------------------
def test_port_override_via_flag(capsys):
    """CLI with --port 9000 prints the correct URL with port 9000."""
    from ui.__main__ import main

    # Given port 9000 is specified via --port flag
    # When developer runs the startup command with --port 9000
    with unittest.mock.patch("ui.__main__.uvicorn") as mock_uvicorn:
        mock_uvicorn.run = unittest.mock.MagicMock()
        main(["--port", "9000"])

    # Then the server prints the correct URL with port 9000
    captured = capsys.readouterr()
    assert "http://127.0.0.1:9000/" in captured.out

    # And uvicorn.run is called with port 9000
    mock_uvicorn.run.assert_called_once()
    assert mock_uvicorn.run.call_args.kwargs["port"] == 9000


# ===========================================================================
# Dimension 2: Boundary Values — Port Parsing
# ===========================================================================


# ---------------------------------------------------------------------------
# test_port_argument_minimum_valid
# derived_from: dimension:boundary (numeric min)
# ---------------------------------------------------------------------------
def test_port_argument_minimum_valid(capsys):
    """CLI accepts --port 1 as a valid integer."""
    from ui.__main__ import main

    # Given CLI is invoked with --port 1
    # When the port argument is parsed
    with unittest.mock.patch("ui.__main__.uvicorn") as mock_uvicorn:
        mock_uvicorn.run = unittest.mock.MagicMock()
        # Port 1 is privileged but argparse should still parse it
        # The socket bind will likely fail but that's a different test
        # We mock to test parsing only
        with unittest.mock.patch("socket.socket") as mock_socket:
            mock_instance = unittest.mock.MagicMock()
            mock_socket.return_value.__enter__ = unittest.mock.MagicMock(
                return_value=mock_instance
            )
            mock_socket.return_value.__exit__ = unittest.mock.MagicMock(
                return_value=False
            )
            main(["--port", "1"])

    # Then the port value is accepted as integer 1
    captured = capsys.readouterr()
    assert "http://127.0.0.1:1/" in captured.out


# ---------------------------------------------------------------------------
# test_port_argument_maximum_valid
# derived_from: dimension:boundary (numeric max)
# ---------------------------------------------------------------------------
def test_port_argument_maximum_valid(capsys):
    """CLI accepts --port 65535 as a valid integer."""
    from ui.__main__ import main

    # Given CLI is invoked with --port 65535
    # When the port argument is parsed
    with unittest.mock.patch("ui.__main__.uvicorn") as mock_uvicorn:
        mock_uvicorn.run = unittest.mock.MagicMock()
        with unittest.mock.patch("socket.socket") as mock_socket:
            mock_instance = unittest.mock.MagicMock()
            mock_socket.return_value.__enter__ = unittest.mock.MagicMock(
                return_value=mock_instance
            )
            mock_socket.return_value.__exit__ = unittest.mock.MagicMock(
                return_value=False
            )
            main(["--port", "65535"])

    # Then the port value is accepted as integer 65535
    captured = capsys.readouterr()
    assert "http://127.0.0.1:65535/" in captured.out
