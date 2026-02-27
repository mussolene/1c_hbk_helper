#!/bin/sh
# MCP-only entrypoint: no ingest, cron, watchdog, or load-snippets.
# Use when mcp runs as api-only service (e.g. with separate ingest-worker).
# Alternative: set MCP_MODE=api with the default entrypoint.sh.
if [ "$(id -u)" = "0" ] && [ -d /data ]; then
  chown -R app:app /data 2>/dev/null || true
  exec gosu app "$@"
fi
exec "$@"
