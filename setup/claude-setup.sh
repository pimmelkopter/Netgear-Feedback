#!/usr/bin/env bash
set -e

PROJECT_DIR="$(cd "$(dirname "$0")/.." && pwd)"

echo "Starting installation..."

# System packages
echo "Installing system packages..."
sudo apt update && sudo apt upgrade -y
sudo apt install -y python3 python3-pip python3-venv git jq dnsmasq hostapd network-manager

# Create directory structure
mkdir -p "${PROJECT_DIR}/hotspot"
mkdir -p "${PROJECT_DIR}/settings"
mkdir -p "${PROJECT_DIR}/logs"

# Set execute permissions
sudo chmod +x "${PROJECT_DIR}/update.sh"
sudo chmod +x "${PROJECT_DIR}/setup/fixed-hotspot.sh"

# Create Python virtual environment
if [ ! -d "${PROJECT_DIR}/venv" ]; then
    echo "Creating Python virtual environment..."
    python3 -m venv "${PROJECT_DIR}/venv"
fi

# Activate venv and install requirements
source "${PROJECT_DIR}/venv/bin/activate"
pip install --upgrade pip

# Create requirements.txt if not exists
if [ ! -f "${PROJECT_DIR}/setup/requirements.txt" ]; then
    cat > "${PROJECT_DIR}/setup/requirements.txt" << EOL
flask>=2.0.0
requests>=2.26.0
urllib3>=1.26.0
rpi-ws281x>=4.3.0
python-networkmanager>=2.2.0
cryptography>=3.4.0
dnspython>=2.1.0
EOL
fi

pip install -r "${PROJECT_DIR}/setup/requirements.txt"

# Configure dnsmasq and hostapd
echo "Configuring network services..."
sudo systemctl unmask hostapd
sudo systemctl enable hostapd
sudo systemctl enable dnsmasq

# Create service file
cat > /tmp/switch_monitor.service << EOL
[Unit]
Description=Switch Monitor Service
After=network.target

[Service]
Type=simple
User=root
WorkingDirectory=${PROJECT_DIR}
Environment=PATH=${PROJECT_DIR}/venv/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin
ExecStart=${PROJECT_DIR}/venv/bin/python3 ${PROJECT_DIR}/hotspot/flask-server.py
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
EOL

# Install service
sudo mv /tmp/switch_monitor.service /etc/systemd/system/
sudo systemctl enable switch_monitor

# Set WiFi country
echo "Setting WiFi country to DE..."
sudo raspi-config nonint do_wifi_country DE

# Create SSL certificates for HTTPS if they don't exist
if [ ! -f "${PROJECT_DIR}/hotspot/server.crt" ]; then
    echo "Generating SSL certificates..."
    openssl req -x509 -newkey rsa:4096 -nodes \
        -out "${PROJECT_DIR}/hotspot/server.crt" \
        -keyout "${PROJECT_DIR}/hotspot/server.key" \
        -days 365 -subj "/CN=switchportal.local"
fi

# Setup permissions
sudo chown -R root:root "${PROJECT_DIR}/hotspot"
sudo chmod 644 "${PROJECT_DIR}/hotspot/server.crt"
sudo chmod 600 "${PROJECT_DIR}/hotspot/server.key"

# Reload systemd
sudo systemctl daemon-reload

echo "Installation complete!"
echo "Please ensure settings/config.json and settings/secrets.json are properly configured"
echo "The web interface will be available after restart at http://10.18.250.1"
echo "To start the service now, run: sudo systemctl start switch_monitor"

if [ -f "${PROJECT_DIR}/update.sh" ]; then
    echo "Running update script..."
    "${PROJECT_DIR}/update.sh"
fi