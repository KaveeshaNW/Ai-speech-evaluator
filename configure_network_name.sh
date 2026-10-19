#!/usr/bin/env bash
# ==============================================================================
# Set custom network hostname & friendly URL for AI Speech Evaluator
# Changes hostname to 'ai-speech-evaluator' so any device on the network can
# access the dashboard at:
#   http://ai-speech-evaluator.local:8501
#   http://ai-speech-evaluator.local:8051
#   http://ai-speech-evaluator.local (port 80 default)
# ==============================================================================
set -e

NEW_NAME="ai-speech-evaluator"

echo "================================================================="
echo " Configuring friendly network name: $NEW_NAME"
echo "================================================================="

# 1. Update system hostname
echo "[*] Setting hostname to $NEW_NAME..."
sudo hostnamectl set-hostname "$NEW_NAME"

# 2. Update /etc/hosts for local loopback resolution
echo "[*] Updating /etc/hosts..."
if grep -q "127.0.1.1" /etc/hosts; then
    sudo sed -i "s/127\.0\.1\.1.*/127.0.1.1\t$NEW_NAME/" /etc/hosts
else
    echo -e "127.0.1.1\t$NEW_NAME" | sudo tee -a /etc/hosts > /dev/null
fi

# 3. Ensure avahi-daemon (mDNS broadcast) is running
if ! command -v avahi-daemon &> /dev/null; then
    echo "[*] Installing avahi-daemon for .local resolution..."
    sudo apt-get update && sudo apt-get install -y avahi-daemon
fi

sudo systemctl enable avahi-daemon
sudo systemctl restart avahi-daemon

# 4. Optional port redirection: allow access on port 80 and port 8051
echo "[*] Configuring port redirection (80 and 8051 -> 8501)..."
if ! command -v iptables &> /dev/null; then
    echo "[*] Installing iptables package..."
    sudo apt-get update -y && sudo apt-get install -y iptables || true
fi

if command -v iptables &> /dev/null; then
    sudo iptables -t nat -C PREROUTING -p tcp --dport 80 -j REDIRECT --to-port 8501 2>/dev/null || \
    sudo iptables -t nat -A PREROUTING -p tcp --dport 80 -j REDIRECT --to-port 8501 || true

    sudo iptables -t nat -C PREROUTING -p tcp --dport 8051 -j REDIRECT --to-port 8501 2>/dev/null || \
    sudo iptables -t nat -A PREROUTING -p tcp --dport 8051 -j REDIRECT --to-port 8501 || true
    echo "[*] Port redirection active!"
fi

echo ""
echo "================================================================="
echo " SUCCESS! Your dashboard is now accessible at:"
echo "   ⭐ http://ai-speech-evaluator.local:8501"
echo "   ⭐ http://ai-speech-evaluator.local:8051"
echo "   ⭐ http://ai-speech-evaluator.local"
echo "================================================================="
