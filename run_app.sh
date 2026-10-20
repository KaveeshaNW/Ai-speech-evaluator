#!/usr/bin/env bash
# ==============================================================================
# Launcher for AI Speech Evaluator
# Automatically activates virtual environment, ensures mDNS alias and launches main.py
# ==============================================================================
set -e

# Change to the repository directory
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# 1. Update Avahi alias so ai-speech-evaluator.local always follows the active IP
CURRENT_IP=$(hostname -I 2>/dev/null | awk '{print $1}')
if [ -n "$CURRENT_IP" ]; then
    echo "$CURRENT_IP ai-speech-evaluator.local" | sudo tee /etc/avahi/hosts > /dev/null 2>&1 || true
    sudo systemctl reload avahi-daemon > /dev/null 2>&1 || true
fi

# 2. Ensure port 80 -> 8501 redirection is active if iptables is present
if command -v iptables &> /dev/null; then
    sudo iptables -t nat -C PREROUTING -p tcp --dport 80 -j REDIRECT --to-port 8501 2>/dev/null || \
    sudo iptables -t nat -A PREROUTING -p tcp --dport 80 -j REDIRECT --to-port 8501 2>/dev/null || true
    sudo iptables -t nat -C PREROUTING -p tcp --dport 8051 -j REDIRECT --to-port 8501 2>/dev/null || \
    sudo iptables -t nat -A PREROUTING -p tcp --dport 8051 -j REDIRECT --to-port 8501 2>/dev/null || true
fi

# 3. Automatically unmute and set USB microphone capture volume to 100% in ALSA
amixer set 'Mic' 100% unmute cap 2>/dev/null || true
amixer set 'Capture' 100% unmute cap 2>/dev/null || true
amixer -c 1 set 'Mic' 100% unmute cap 2>/dev/null || true
amixer -c 1 set 'Capture' 100% unmute cap 2>/dev/null || true
amixer -c 2 set 'Mic' 100% unmute cap 2>/dev/null || true
amixer -c 2 set 'Capture' 100% unmute cap 2>/dev/null || true

# 4. Activate Python virtual environment
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
