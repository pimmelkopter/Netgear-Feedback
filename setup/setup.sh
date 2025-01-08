#!/usr/bin/env bash
set -e

PROJECT_DIR="$(cd "$(dirname "$0")/.." && pwd)"

echo "Starting installation..."

# System packages
echo "Installing system packages..."
sudo apt update && sudo apt upgrade -y
sudo apt install -y python3 python3-pip python3-venv git jq dnsmasq hostapd network-manager libdbus-1-dev libdbus-glib-1-dev dbus

# In setup.sh nach den apt-install Befehlen:
echo "Removing old hotspot configuration..."
sudo nmcli connection delete "MyHotspot" || true  # || true verhindert Fehler wenn nicht existiert

# Set execute permissions
echo "Setting executable permissions..."
sudo chmod +x "${PROJECT_DIR}/update.sh"
sudo chmod +x "${PROJECT_DIR}/setup/fixed-hotspot.sh"
#sudo cp "${PROJECT_DIR}/settings/secrets_initial.json" "${PROJECT_DIR}/settings/secrets.json"

# Create Python virtual environment
if [ ! -d "${PROJECT_DIR}/venv" ]; then
    echo "Creating Python virtual environment..."
    python3 -m venv "${PROJECT_DIR}/venv"
fi

# Activate venv and install requirements
echo "Activating venv and installing Python packages..."
source "${PROJECT_DIR}/venv/bin/activate"
pip install --upgrade pip
pip install -r "${PROJECT_DIR}/setup/requirements.txt"

# Configure dnsmasq and hostapd
#echo "Configuring network services..."
#sudo systemctl unmask hostapd
#sudo systemctl enable hostapd
#sudo systemctl enable dnsmasq
##doppelt mit der config im hotspot.py deswegen
sudo systemctl disable hostapd
sudo systemctl disable dnsmasq
sudo systemctl stop hostapd
sudo systemctl stop dnsmasq


# Install systemd service files
echo "Installing systemd services..."
sudo cp "${PROJECT_DIR}/setup/switch_monitor.service" /etc/systemd/system/switch_monitor.service
sudo cp "${PROJECT_DIR}/setup/hotspot.service" /etc/systemd/system/hotspot.service
sudo cp "${PROJECT_DIR}/setup/web_interface.service" /etc/systemd/system/web_interface.service
for service in switch_monitor hotspot web_interface; do
    sudo systemctl enable $service.service
done

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
sudo chown -R pi:pi /home/pi/Netgear-Feedback
sudo chmod -R u+rwX /home/pi/Netgear-Feedback

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