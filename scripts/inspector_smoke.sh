#!/usr/bin/env bash
set -euo pipefail

PACKAGE_NAME="${1:-uscis-pdf-ops-mcp}"

echo "Starting MCP Inspector smoke test for ${PACKAGE_NAME}"
echo "Open the local Inspector UI and confirm the five tools are visible."
npx @modelcontextprotocol/inspector uvx "$PACKAGE_NAME"

