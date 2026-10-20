#!/usr/bin/env bash
# ==============================================================================
# Restore Hostname to MrX and Configure ai-speech-evaluator.local Alias
# ==============================================================================
set -e

ORIGINAL_HOSTNAME="MrX"
ALIAS_NAME="ai-speech-evaluator.local"

echo "================================================================="
echo " Restoring system hostname to: $ORIGINAL_HOSTNAME"
echo " Setting up persistent mDNS alias: $ALIAS_NAME"
echo "================================================================="

# 1. Restore the original system hostname
echo "[*] Restoring system hostname to $ORIGINAL_HOSTNAME..."
sudo hostnamectl set-hostname "$ORIGINAL_HOSTNAME"

# 2. Update /etc/hosts to restore MrX
echo "[*] Updating /etc/hosts..."
sudo sed -i "s/127\.0\.1\.1.*/127.0.1.1\t$ORIGINAL_HOSTNAME/" /etc/hosts
if ! grep -q "ai-speech-evaluator" /etc/hosts; then
    echo -e "127.0.0.1\tai-speech-evaluator.local" | sudo tee -a /etc/hosts > /dev/null
fi

# 3. Detect current IP address
CURRENT_IP=$(hostname -I | awk '{print $1}')
echo "[*] Detected active IP: $CURRENT_IP"

# 4. Configure Avahi mDNS alias in /etc/avahi/hosts
echo "[*] Registering $ALIAS_NAME alias with Avahi..."
echo "$CURRENT_IP $ALIAS_NAME" | sudo tee /etc/avahi/hosts > /dev/null

# 5. Reload Avahi to publish both MrX.local AND ai-speech-evaluator.local
sudo systemctl reload avahi-daemon 2>/dev/null || sudo systemctl restart avahi-daemon

# 6. Install NetworkManager dispatcher hook so alias updates whenever IP changes
DISPATCHER_DIR="/etc/NetworkManager/dispatcher.d"
if [ -d "$DISPATCHER_DIR" ]; then
    echo "[*] Installing dynamic IP update hook in NetworkManager..."
    cat << 'EOF' | sudo tee "$DISPATCHER_DIR/99-speech-evaluator-alias.sh" > /dev/null
#!/usr/bin/env bash
if [ "$2" = "up" ] || [ "$2" = "dhcp4-change" ]; then
    IP=$(hostname -I | awk '{print $1}')
    if [ -n "$IP" ]; then
        echo "$IP ai-speech-evaluator.local" > /etc/avahi/hosts
        systemctl reload avahi-daemon 2>/dev/null || true
    fi
fi
EOF
    sudo chmod +x "$DISPATCHER_DIR/99-speech-evaluator-alias.sh"
fi

# 7. Configure port 80 -> 8501 redirection
if command -v iptables &> /dev/null; then
    echo "[*] Ensuring port 80 and 8051 redirection to 8501..."
    sudo iptables -t nat -C PREROUTING -p tcp --dport 80 -j REDIRECT --to-port 8501 2>/dev/null || \
    sudo iptables -t nat -A PREROUTING -p tcp --dport 80 -j REDIRECT --to-port 8501 2>/dev/null || true
    sudo iptables -t nat -C PREROUTING -p tcp --dport 8051 -j REDIRECT --to-port 8501 2>/dev/null || \
    sudo iptables -t nat -A PREROUTING -p tcp --dport 8051 -j REDIRECT --to-port 8501 2>/dev/null || true
fi

echo ""
echo "================================================================="
echo " SUCCESS!"
echo " 1. Your Raspberry Pi's network name is restored to: $ORIGINAL_HOSTNAME"
echo " 2. Both addresses are now active and working:"
echo "    - http://$ORIGINAL_HOSTNAME.local:8501"
echo "    - http://$ALIAS_NAME:8501 (and http://$ALIAS_NAME)"
echo " 3. Whenever your IP changes, $ALIAS_NAME will"
echo "    automatically follow the new IP!"
echo "================================================================="
