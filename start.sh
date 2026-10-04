#!/usr/bin/env bash
# Quick launcher script for Multi-Agent Trading System

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# Activate virtualenv if present
if [ -f ".venv/bin/activate" ]; then
    source .venv/bin/activate
fi

# Pass all arguments to start.py
exec python start.py "$@"
