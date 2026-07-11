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
    """CLI prints startup URL to stdout before starting uvicorn.

    Runs on an ephemeral free port, not the 8718 default: the plugin's
    session-start hook legitimately holds 8718 whenever a real pd session
    is live, which made the old `main([])` form environmentally flaky.
    The pid-file/watchdog lifecycle trio is mocked for the same reason --
    the unmocked test overwrote (then atexit-DELETED) the live server's
    pid bookkeeping.
    """
    from ui.__main__ import main

    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
        probe.bind(("127.0.0.1", 0))
        free_port = probe.getsockname()[1]

    with (
        unittest.mock.patch("ui.__main__.uvicorn") as mock_uvicorn,
        unittest.mock.patch("ui.__main__.write_pid"),
        unittest.mock.patch("ui.__main__.remove_pid"),
        unittest.mock.patch("ui.__main__.start_lifetime_watchdog"),
    ):
        mock_uvicorn.run = unittest.mock.MagicMock()
        main(["--port", str(free_port)])

    captured = capsys.readouterr()
    assert f"http://127.0.0.1:{free_port}/" in captured.out
