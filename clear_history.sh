#!/usr/bin/env bash
# =================================================================
# AI Speech Evaluator - Clear All Speech History
# =================================================================
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

if [ -f "/home/astro/speech_env/bin/python3" ]; then
    /home/astro/speech_env/bin/python3 clear_history.py
else
    python3 clear_history.py
fi
