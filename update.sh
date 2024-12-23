#!/usr/bin/env bash
set -e

PROJECT_DIR="$(cd "$(dirname "$0")" && pwd)"
CONFIG_FILE="${PROJECT_DIR}/settings/config.json"

# Wir lesen erneut aus config.json
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