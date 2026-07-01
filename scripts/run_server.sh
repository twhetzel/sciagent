#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT/server"

if [[ -f "$ROOT/.env" ]]; then
  set -a
  # shellcheck disable=SC1091
  source "$ROOT/.env"
  set +a
fi

export PYTHONPATH="${PYTHONPATH:-}:$(pwd)"
export SCIAGENT_HOST="${SCIAGENT_HOST:-127.0.0.1}"
export SCIAGENT_PORT="${SCIAGENT_PORT:-8000}"

echo "Starting SciAgent API on ${SCIAGENT_HOST}:${SCIAGENT_PORT} ..."
exec uv run uvicorn sciagent_server.main:app \
  --host "$SCIAGENT_HOST" \
  --port "$SCIAGENT_PORT"
