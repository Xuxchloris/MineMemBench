"""CLI entry point for ``python -m minemembench.dashboard``."""

from __future__ import annotations

import argparse

from .server import create_server


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Read-only MineMemBench results dashboard and replay."
    )
    parser.add_argument("--results-dir", default="results")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--poll-interval", type=float, default=1.0)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    server = create_server(
        args.results_dir,
        host=args.host,
        port=args.port,
        poll_interval=args.poll_interval,
    )
    host, port = server.server_address[:2]
    print(f"MineMemBench dashboard: http://{host}:{port}")
    print("Read-only mode; raw result JSON remains the source of truth.")
    try:
        server.serve_forever(poll_interval=0.25)
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
