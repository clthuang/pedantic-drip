"""CLI entry point for the pd UI server.

Usage (via shell wrapper):
    bash plugins/pd/mcp/run-ui-server.sh [--port PORT]

Exit codes:
    0 -- clean shutdown
    1 -- port conflict
"""

import argparse
import atexit
import os
import socket
import sys

import uvicorn

# Make server_lifecycle importable from sibling mcp/ directory.
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'mcp'))
from server_lifecycle import write_pid, remove_pid, start_lifetime_watchdog


def main(args=None):
    """Parse arguments, check port, start server."""
    parser = argparse.ArgumentParser(description="pd UI server")
    parser.add_argument(
        "--port", type=int, default=8718, help="Server port (default: 8718)"
    )
    parsed = parser.parse_args(args)
    port = parsed.port

    # Port conflict detection -- immediate, actionable error
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        try:
            sock.bind(("127.0.0.1", port))
        except OSError:
            print(
                f"Error: Port {port} is already in use.\n"
                f"Use --port to specify an alternative: "
                f"python -m plugins.pd.ui --port {port + 1}",
                file=sys.stderr,
            )
            sys.exit(1)

    from ui import create_app

    app = create_app()

    write_pid("ui_server")
    start_lifetime_watchdog(86400)
    atexit.register(remove_pid, "ui_server")

    print(f"pd UI server running at http://127.0.0.1:{port}/")

    uvicorn.run(app, host="127.0.0.1", port=port)


if __name__ == "__main__":
    main()
