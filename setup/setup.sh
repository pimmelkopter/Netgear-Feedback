#!/usr/bin/env bash
set -e

PROJECT_DIR="$(cd "$(dirname "$0")/.." && pwd)"

sudo apt update && sudo apt upgrade -y
sudo apt install -y python3 python3-pip python3-venv git jq #nmcli
sudo chmod +x "${PROJECT_DIR}/update.sh"
sudo chmod +x "${PROJECT_DIR}/setup/fixed-hotspot.sh"
#sudo cp "${PROJECT_DIR}/settings/secrets_initial.json" "${PROJECT_DIR}/settings/secrets.json"

# 1) Python venv erstellen
if [ ! -d "${PROJECT_DIR}/venv" ]; then
    echo "Erstelle Python-venv im Projektverzeichnis.."
    python3 -m venv "${PROJECT_DIR}/venv"
fi

# 2) venv aktivieren und Requirements installieren
source "${PROJECT_DIR}/venv/bin/activate"
pip install --upgrade pip
pip install -r "${PROJECT_DIR}/setup/requirements.txt"
sudo cp "${PROJECT_DIR}/setup/switch_monitor.service" /etc/systemd/system/switch_monitor.service
sudo systemctl enable switch_monitor

#./update.sh

echo "Setup complete."
echo "please configure settings/config.json and settings/secrets.json"
echo "use sudo raspi-config and setup wifi country to use wireless interface"