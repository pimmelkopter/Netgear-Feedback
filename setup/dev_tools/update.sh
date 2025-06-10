## setup/dev_tools/update.sh ##
#!/usr/bin/env bash
set -euo pipefail

# Farbige Ausgabe
RED='\033[0;31m'
GREEN='\033[0;32m'
NC='\033[0m'

# Logging-Funktion
log_error() {
    echo -e "${RED}[ERROR]${NC} $1" >&2
}

log_success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1"
}

# Konfigurationsprüfung
check_config() {
    local config_file="$1"
    if [[ ! -f "$config_file" ]]; then
        log_error "Konfigurationsdatei $config_file nicht gefunden!"
        return 1
    fi
    return 0
}


# Hauptfunktion
main() {
    local PROJECT_DIR="$(cd "$(dirname "$0")/../.." && pwd)"
    local CONFIG_FILE="${PROJECT_DIR}/config/config.json"
    local SECRETS_FILE="${PROJECT_DIR}/config/secrets.json"

    # Konfigurationen prüfen
    check_config "$CONFIG_FILE" || exit 1
    check_config "$SECRETS_FILE" || exit 1

    # Netzwerk-Konfiguration
    if [ -f "$CONFIG_FILE" ]; then
        local DHCP=$(jq -r '.dhcp' "$CONFIG_FILE")
        local FIXED_IP=$(jq -r '.fixed_ip' "$CONFIG_FILE")
        local FIXED_GW=$(jq -r '.fixed_gw' "$CONFIG_FILE")
        local DNS_SERVER=$(jq -r '.dns_server' "$CONFIG_FILE")
        local WIRED_CONN="Wired connection 1"

        if [ "$DHCP" = "false" ]; then
            log_success "Konfiguriere statische IP-Adresse..."
            sudo nmcli connection delete "$WIRED_CONN" || true
            sudo nmcli connection add type ethernet ifname eth0 con-name "$WIRED_CONN" \
                ipv4.method manual \
                ipv4.addresses "$FIXED_IP" \
                ipv4.gateway "$FIXED_GW" \
                ipv4.dns "$DNS_SERVER" \
                ipv6.method ignore
            sudo nmcli connection up "$WIRED_CONN"
            log_success "Feste IP wurde eingerichtet: $FIXED_IP"
        else
            log_success "Stelle Verbindung auf DHCP um..."
            sudo nmcli connection delete "$WIRED_CONN" || true
            sudo nmcli connection add type ethernet ifname eth0 con-name "$WIRED_CONN" \
                ipv4.method auto ipv6.method ignore
            sudo nmcli connection up "$WIRED_CONN"
        fi
    fi

    sudo systemctl restart switch_monitor.service 

    sudo chmod +x setup/dev_tools/update.sh
    sudo chmod +x setup/dev_tools/git-reset.sh

    log_success "Update und Dienste-Konfiguration abgeschlossen!"
    sudo journalctl -b -u switch_monitor.service --no-pager --since -10m
}

# Skript ausführen
main