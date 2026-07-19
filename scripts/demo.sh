#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "$0")/.." && pwd)"
cd "$repo_root"

cleanup() {
  kill "${api_pid:-}" "${web_pid:-}" 2>/dev/null || true
}
trap cleanup EXIT INT TERM

uv run groundloop-api &
api_pid=$!
(cd apps/web && pnpm dev --host 127.0.0.1) &
web_pid=$!

echo "GroundLoop is running at http://127.0.0.1:5173"
echo "Press Ctrl-C to stop both local services."
wait "$api_pid" "$web_pid"
