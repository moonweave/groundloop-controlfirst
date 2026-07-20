#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "$0")/.." && pwd)"
cd "$repo_root"
api_pid=""
web_pid=""

cleanup() {
  for pid in "$api_pid" "$web_pid"; do
    if [[ -n "$pid" ]] && kill -0 "$pid" 2>/dev/null; then
      kill "$pid" 2>/dev/null || true
    fi
  done
}
trap cleanup EXIT INT TERM

uv run groundloop-api &
api_pid=$!
for _ in {1..40}; do
  if curl --fail --silent http://127.0.0.1:8000/health >/dev/null; then
    break
  fi
  if ! kill -0 "$api_pid" 2>/dev/null; then
    echo "GroundLoop API failed to start. Check the error above." >&2
    exit 1
  fi
  sleep 0.25
done
if ! curl --fail --silent http://127.0.0.1:8000/health >/dev/null; then
  echo "GroundLoop API did not become ready at http://127.0.0.1:8000/health." >&2
  exit 1
fi

(cd apps/web && pnpm dev --host 127.0.0.1 --port 5173 --strictPort) &
web_pid=$!
for _ in {1..40}; do
  if curl --fail --silent http://127.0.0.1:5173/ >/dev/null; then
    break
  fi
  if ! kill -0 "$web_pid" 2>/dev/null; then
    echo "GroundLoop web UI failed to start. Check the error above." >&2
    exit 1
  fi
  sleep 0.25
done
if ! curl --fail --silent http://127.0.0.1:5173/ >/dev/null; then
  echo "GroundLoop web UI did not become ready at http://127.0.0.1:5173/." >&2
  exit 1
fi

echo "GroundLoop is running at http://127.0.0.1:5173"
echo "Press Ctrl-C to stop both local services."
wait "$api_pid"
