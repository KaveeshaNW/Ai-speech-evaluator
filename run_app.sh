#!/usr/bin/env bash
# ==============================================================================
# Launcher for AI Speech Evaluator
# Automatically activates virtual environment and launches main.py
# ==============================================================================
set -e

# Change to the repository directory
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# Activate Python virtual environment
if [ -f "/home/astro/speech_env/bin/activate" ]; then
    source "/home/astro/speech_env/bin/activate"
elif [ -f "$HOME/speech_env/bin/activate" ]; then
    source "$HOME/speech_env/bin/activate"
elif [ -f "$SCRIPT_DIR/venv/bin/activate" ]; then
    source "$SCRIPT_DIR/venv/bin/activate"
elif [ -f "$SCRIPT_DIR/.venv/bin/activate" ]; then
    source "$SCRIPT_DIR/.venv/bin/activate"
fi

echo "[*] Starting AI Speech Evaluator with Python: $(which python)"
exec python main.py "$@"
