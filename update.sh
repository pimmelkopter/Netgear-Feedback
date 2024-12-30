#!/usr/bin/env bash
set -e

PROJECT_DIR="$(cd "$(dirname "$0")" && pwd)"
CONFIG_FILE="${PROJECT_DIR}/settings/config.json"
DHCP=$(jq -r '.dhcp' "$CONFIG_FILE")
FIXED_IP=$(jq -r '.fixed_ip' "$CONFIG_FILE")
FIXED_GW=$(jq -r '.fixed_gw' "$CONFIG_FILE")
DNS_SERVER=$(jq -r '.dns_server' "$CONFIG_FILE")
WIRED_CONN="Wired connection 1"

# Wir lesen erneut aus config.json
if [ -f "$CONFIG_FILE" ]; then
  if [ "$DHCP" = "false" ]; then
    echo "Starte Konfiguration der statischen IP-Adresse über NetworkManager..."
    # Verbindung auf 'manual' stellen
    sudo nmcli connection delete "$WIRED_CONN"
    sudo nmcli connection add type ethernet ifname eth0 con-name "$WIRED_CONN" \
        ipv4.method manual \
        ipv4.addresses "$FIXED_IP" \
        ipv4.gateway "$FIXED_GW" \
        ipv4.dns "$DNS_SERVER" \
        ipv6.method ignore

    sudo nmcli connection up "$WIRED_CONN"
    echo "Feste IP wurde eingerichtet. ($FIXED_IP via $WIRED_CONN)"
  else
    echo "Stelle Verbindung auf DHCP um... - wenn die Nachricht länger als 30s bleibt drücke Strg+C"
    sudo nmcli connection delete "$WIRED_CONN"
    sudo nmcli connection add type ethernet ifname eth0 con-name "$WIRED_CONN" ipv4.method auto ipv6.method ignore
    
    sudo nmcli connection up "$WIRED_CONN"
  fi
else
  echo "config.json nicht gefunden unter $CONFIG_FILE!"
fi
echo -e "\033[1;32m update.sh: Netzwerk-Konfiguration mit NetworkManager abgeschlossen.\033[0m"
sudo systemctl restart switch_monitor.service