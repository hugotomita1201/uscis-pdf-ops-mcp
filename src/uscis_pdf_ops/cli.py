"""CLI entrypoint for the MCP server."""

from __future__ import annotations

import argparse

from uscis_pdf_ops.server.app import run_server


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="USCIS PDF Ops MCP server")
    parser.add_argument(
        "--transport",
        default="stdio",
        choices=["stdio"],
        help="Transport to run. v0.1.0 supports stdio only.",
    )
    return parser


def main() -> None:
    args = build_parser().parse_args()
    run_server(transport=args.transport)


if __name__ == "__main__":
    main()

