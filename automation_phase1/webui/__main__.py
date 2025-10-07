from __future__ import annotations

import argparse
from wsgiref.simple_server import make_server

from .app import create_app


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the Automation Phase 1 web UI")
    parser.add_argument("--host", default="127.0.0.1", help="Host interface to bind to")
    parser.add_argument("--port", type=int, default=5000, help="Port to listen on")
    args = parser.parse_args()

    app = create_app()
    with make_server(args.host, args.port, app) as server:
        print(f"Serving on http://{args.host}:{args.port}")
        try:
            server.serve_forever()
        except KeyboardInterrupt:  # pragma: no cover - manual shutdown
            print("\nShutting down web UI")


if __name__ == "__main__":
    main()
