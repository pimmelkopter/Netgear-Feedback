#!/usr/bin/env bash
set -e

PROJECT_DIR="$(cd "$(dirname "$0")" && pwd)"
CONFIG_FILE="${PROJECT_DIR}/settings/config.json"

# Wir lesen erneut aus config.json
if [ -f "$CONFIG_FILE" ]; then
  sudo apt-get update && sudo apt-get install -y jq
  DHCP=$(jq -r '.dhcp' "$CONFIG_FILE")
  FIXED_IP=$(jq -r '.fixed_ip' "$CONFIG_FILE")
  FIXED_GW=$(jq -r '.fixed_gw' "$CONFIG_FILE")
  DNS_SERVER=$(jq -r '.dns_server' "$CONFIG_FILE")

  if [ "$DHCP" = "false" ]; then
    echo "Setze statische IP neu..."
    sudo sed -i '/^interface eth0/,$d' /etc/dhcpcd.conf
    {
      echo "interface eth0"
      echo "static ip_address=$FIXED_IP"
      echo "static routers=$FIXED_GW"
      echo "static domain_name_servers=$DNS_SERVER"
    } | sudo tee -a /etc/dhcpcd.conf
    echo "Feste IP wurde aktualisiert. Bitte Pi neustarten."
  else
    echo "Wechsle zu DHCP..."
    sudo sed -i '/^interface eth0/,$d' /etc/dhcpcd.conf
    echo "# DHCP Einstellungen wiederhergestellt." | sudo tee -a /etc/dhcpcd.conf
    echo "DHCP aktiviert. Bitte Pi neustarten."
  fi
else
  echo "config.json nicht gefunden!"
fi