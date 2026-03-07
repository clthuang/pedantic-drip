"""CLI entry point for the iflow UI server.

Usage (via shell wrapper):
    bash plugins/iflow/mcp/run-ui-server.sh [--port PORT]

Exit codes:
    0 -- clean shutdown
    1 -- port conflict
"""

import argparse
import socket
import sys

import uvicorn


def main(args=None):
    """Parse arguments, check port, start server."""
    parser = argparse.ArgumentParser(description="iflow UI server")
    parser.add_argument(
        "--port", type=int, default=8718, help="Server port (default: 8718)"
    )
    parsed = parser.parse_args(args)
    port = parsed.port

    # Port conflict detection -- immediate, actionable error
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        sock.bind(("127.0.0.1", port))
    except OSError:
        print(
            f"Error: Port {port} is already in use.\n"
            f"Use --port to specify an alternative: "
            f"python -m plugins.iflow.ui --port {port + 1}",
            file=sys.stderr,
        )
        sys.exit(1)
    finally:
        sock.close()

    from ui import create_app

    app = create_app()

    print(f"iflow UI server running at http://127.0.0.1:{port}/")

    uvicorn.run(app, host="127.0.0.1", port=port)


if __name__ == "__main__":
    main()
