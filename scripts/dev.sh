#!/usr/bin/env bash
set -euo pipefail

if [ ! -d ".venv" ]; then
  echo "Creating .venv..."
  python -m venv .venv
fi

if [ ! -f ".env" ]; then
  echo "Creating .env from .env.example..."
  cp .env.example .env
fi

echo "Installing dependencies..."
./.venv/bin/python -m pip install -r requirements.txt

echo "Starting Hyperdress.AI at http://127.0.0.1:8000"
./.venv/bin/python -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
