#!/usr/bin/env bash
# ==============================================================================
# Auto-Start Installer for AI Speech Evaluator on Raspberry Pi
# Configures systemd to run the evaluator automatically every time the Pi powers on.
#
# Usage:
#     sudo bash setup_autostart.sh
# ==============================================================================
set -e

# Determine real user (even if executed with sudo)
RUN_USER="${SUDO_USER:-$USER}"
PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
LAUNCHER="$PROJECT_DIR/run_app.sh"
SERVICE_PATH="/etc/systemd/system/ai-speech-evaluator.service"

echo "================================================================="
echo "   TOASTMASTERS AI SPEECH EVALUATOR - AUTOSTART SETUP"
echo "================================================================="
echo "[*] Configuring user:       $RUN_USER"
echo "[*] Working directory:      $PROJECT_DIR"
echo "[*] Launcher script:        $LAUNCHER"
echo ""

# Ensure launcher script is executable
chmod +x "$LAUNCHER"

# Check if .env exists
if [ ! -f "$PROJECT_DIR/.env" ]; then
    echo "[!] WARNING: No .env file found in $PROJECT_DIR."
    echo "    Make sure your API keys are configured before running."
fi

echo "[*] Generating systemd service unit at $SERVICE_PATH..."

cat <<EOF > "$SERVICE_PATH"
[Unit]
Description=AI Speech Evaluator - Toastmasters Embedded Assistant
After=network.target sound.target
Wants=network.target

[Service]
Type=simple
User=$RUN_USER
Group=$RUN_USER
WorkingDirectory=$PROJECT_DIR
ExecStart=/bin/bash "$LAUNCHER"
Restart=always
RestartSec=3
StandardOutput=journal
StandardError=journal
SupplementaryGroups=i2c gpio audio

[Install]
WantedBy=multi-user.target
EOF

chmod 644 "$SERVICE_PATH"

echo "[*] Reloading systemd daemon..."
systemctl daemon-reload

echo "[*] Enabling ai-speech-evaluator.service for boot..."
systemctl enable ai-speech-evaluator.service

echo "[*] Starting ai-speech-evaluator.service now..."
systemctl restart ai-speech-evaluator.service

echo ""
echo "================================================================="
echo " SUCCESS! The service is installed and set to launch on boot."
echo " Every time you power on the Raspberry Pi:"
echo "   1. The LCD will initialize and display 'Ready...'"
echo "   2. The Streamlit dashboard will be live at http://<pi-ip>:8501"
echo "   3. Flipping the physical switch ON starts recording and timing."
echo "   4. Flipping the switch OFF finalizes and displays the evaluation."
echo "================================================================="
echo ""
echo "Helpful service management commands:"
echo "  Check live status: sudo systemctl status ai-speech-evaluator"
echo "  Follow live logs:  sudo journalctl -u ai-speech-evaluator -f"
echo "  Restart service:   sudo systemctl restart ai-speech-evaluator"
echo "  Stop service:      sudo systemctl stop ai-speech-evaluator"
echo "  Disable autostart: sudo systemctl disable ai-speech-evaluator"
echo "================================================================="
echo ""
systemctl status ai-speech-evaluator.service --no-pager || true
