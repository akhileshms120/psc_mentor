#!/usr/bin/env bash
# Start the PSC Mentor backend on port 8000 (creates the Python environment the first time).
set -euo pipefail
cd "$(dirname "$0")/../server"

if [ ! -x .venv/bin/uvicorn ]; then
  python3 -m venv .venv
  .venv/bin/pip install -r requirements-dev.txt
fi

if [ -z "${ANTHROPIC_API_KEY:-}" ]; then
  echo "Note: ANTHROPIC_API_KEY is not set, so the AI mentor, Malayalam papers and question generation are off."
fi

# 0.0.0.0 so a phone or emulator on the same Wi-Fi can reach it too.
exec .venv/bin/uvicorn psc_mentor_server.main:app --host 0.0.0.0 --port 8000
