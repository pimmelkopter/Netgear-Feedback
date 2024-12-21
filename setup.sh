#!/usr/bin/env bash
set -e

PROJECT_DIR="$(cd "$(dirname "$0")" && pwd)"

sudo apt update && sudo apt upgrade -y
sudo apt install -y python3 python3-pip python3-venv git

# 1) Python venv erstellen
if [ ! -d "${PROJECT_DIR}/venv"]; then
    echo "Erstelle Python-venv im Projektverzeichnis.."
    python3 -m venv "${PROJECT_DIR}/venv"
fi

# 2) venv aktivieren und Requirements installieren
source "${PROJECT_DIR}/venv/bin/activate"
pip install --upgrade pip
pip install -r "${PROJECT_DIR}/requirements.txt"

# 3) IP-Konfiguration aus config.json lesen
CONFIG_FILE="${PROJECT_DIR}/settings/config.json"

if [ -f "$CONFIG_FILE" ]; then
  # Verwenden von jq, um Werte aus config.json zu lesen
  # Falls 'jq' noch nicht installiert ist:
  sudo apt-get install -y jq

  DHCP=$(jq -r '.dhcp' "$CONFIG_FILE")
  FIXED_IP=$(jq -r '.fixed_ip' "$CONFIG_FILE")
  FIXED_GW=$(jq -r '.fixed_gw' "$CONFIG_FILE")
  DNS_SERVER=$(jq -r '.dns_server' "$CONFIG_FILE")

  if [ "$DHCP" = "false" ]; then
    echo "Starte Konfiguration der statischen IP-Adresse..."
    # /etc/dhcpcd.conf anpassen
    sudo sed -i '/^interface eth0/,$d' /etc/dhcpcd.conf  # Alte Konfiguration entfernen
    {
      echo "interface eth0"
      echo "static ip_address=$FIXED_IP"
      echo "static routers=$FIXED_GW"
      echo "static domain_name_servers=$DNS_SERVER"
    } | sudo tee -a /etc/dhcpcd.conf
    echo "Feste IP wurde eingerichtet. Bitte Pi neustarten, damit es wirksam wird."
  else
    echo "DHCP konfiguriert, keine statische IP."
  fi
fi

echo "Setup complete."
