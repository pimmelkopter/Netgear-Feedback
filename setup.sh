#!/usr/bin/env bash
set -e

PROJECT_DIR="$(cd "$(dirname "$0")" && pwd)"

sudo apt update && sudo apt upgrade -y
sudo apt install -y python3 python3-pip python3-venv git jq
sudo chmod +x "${PROJECT_DIR}/update.sh"
sudo chmod +x "${PROJECT_DIR}/run.sh"
sudo cp "${PROJECT_DIR}/settings/secrets_initial.json" "${PROJECT_DIR}/settings/secrets.json"

# 1) Python venv erstellen
if [ ! -d "${PROJECT_DIR}/venv" ]; then
    echo "Erstelle Python-venv im Projektverzeichnis.."
    python3 -m venv "${PROJECT_DIR}/venv"
fi

# 2) venv aktivieren und Requirements installieren
source "${PROJECT_DIR}/venv/bin/activate"
pip install --upgrade pip
pip install -r "${PROJECT_DIR}/requirements.txt"

# 3) IP-Konfiguration aus config.json lesen
CONFIG_FILE="${PROJECT_DIR}/settings/config.json"
WIRED_CONN="Wired connection 1"

if [ -f "$CONFIG_FILE" ]; then
  DHCP=$(jq -r '.dhcp' "$CONFIG_FILE")
  FIXED_IP=$(jq -r '.fixed_ip' "$CONFIG_FILE")
  FIXED_GW=$(jq -r '.fixed_gw' "$CONFIG_FILE")
  DNS_SERVER=$(jq -r '.dns_server' "$CONFIG_FILE")

  if [ "$DHCP" = "false" ]; then
    echo "Starte Konfiguration der statischen IP-Adresse über NetworkManager..."
    # Verbindung auf 'manual' stellen
    sudo nmcli connection modify "$WIRED_CONN" \
        ipv4.method manual \
        ipv4.addresses "$FIXED_IP" \
        ipv4.gateway "$FIXED_GW" \
        ipv4.dns "$DNS_SERVER" \
        ipv6.method ignore

    sudo nmcli connection up "$WIRED_CONN"
    echo "Feste IP wurde eingerichtet. ($FIXED_IP via $WIRED_CONN)"
  else
    echo "Stelle Verbindung auf DHCP um..."
    sudo nmcli connection modify "$WIRED_CONN" \
        ipv4.method auto \
        ipv6.method ignore

    sudo nmcli connection up "$WIRED_CONN"
  fi
else
  echo "config.json nicht gefunden unter $CONFIG_FILE!"
fi
echo "setup.sh: Netzwerk-Konfiguration mit NetworkManager abgeschlossen."

echo "Setup complete."
echo "please configure settings/config.json and settings/secrets.json"
echo "use sudo raspi-config and setup wifi country to use wireless interface"