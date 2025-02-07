#!/usr/bin/env bash
set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
SERVICE_TEMPLATE="[Unit]
Description=%s
After=network.target
%s

[Service]
Type=simple
WorkingDirectory=${PROJECT_DIR}
Environment=\"PYTHONPATH=${PROJECT_DIR}\"
%s
ExecStart=${PROJECT_DIR}/venv/bin/python3 %s
Restart=always
RestartSec=2
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target"

create_service() {
    local name=$1
    local desc=$2
    local deps=$3
    local env=$4
    local exec=$5
    
    printf "$SERVICE_TEMPLATE" "$desc" "$deps" "$env" "$exec" | \
    sudo tee "/etc/systemd/system/${name}.service" > /dev/null
}

echo "Starting installation..."

# System packages
echo "Installing system packages..."
sudo apt update && sudo apt upgrade -y
sudo apt install -y python3 python3-pip python3-venv git jq dnsmasq hostapd network-manager libdbus-1-dev libdbus-glib-1-dev dbus

# Remove old config
echo "Removing old hotspot configuration..."
sudo nmcli connection delete "MyHotspot" || true

# Create Python venv
if [ ! -d "${PROJECT_DIR}/venv" ]; then
    echo "Creating Python virtual environment..."
    python3 -m venv "${PROJECT_DIR}/venv"
fi

echo "Activating venv and installing Python packages..."
source "${PROJECT_DIR}/venv/bin/activate"
pip install --upgrade pip
pip install -r "${PROJECT_DIR}/setup/requirements.txt"

# Disable conflicting services
for service in hostapd dnsmasq; do
    sudo systemctl disable $service || true
    sudo systemctl stop $service || true
done

# Create service files
echo "Installing systemd services..."

# Hotspot Service
create_service "hotspot" \
    "WiFi Hotspot Service" \
    "Requires=NetworkManager.service" \
    "" \
    "-m hotspot.hotspot"

# Switch Monitor Service
create_service "switch_monitor" \
    "Switch Monitor Service" \
    "" \
    "Environment=\"OPENSSL_CONF=${PROJECT_DIR}/config/openssl.cnf\"" \
    "-m src.main"

# Web Interface Service
create_service "web_interface" \
    "Web Interface Service" \
    "After=network.target hotspot.service\nRequires=hotspot.service" \
    "-m hotspot.flask-server"

# Enable services
for service in switch_monitor hotspot web_interface; do
    sudo systemctl enable $service.service
done

sudo systemctl daemon-reload
sudo chmod +x setup/dev_tools/update.sh
sudo chmod +x setup/dev_tools/git-reset.sh
sudo chmod +x setup/dev_tools/fixed-hotspot.sh

echo "Installation complete!"
echo "Please ensure config/config.json and config/secrets.json are properly configured."