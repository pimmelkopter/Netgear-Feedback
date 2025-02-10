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
    }

    # Hier könnten weitere Validierungen hinzugefügt werden
    # z.B. Prüfen der JSON-Struktur
}

# Dienste-Verwaltung
manage_services() {
    local action="$1"
    shift
    local services=("$@")

    for service in "${services[@]}"; do
        if systemctl list-unit-files | grep -q "$service.service"; then
            case "$action" in
                restart)
                    if systemctl is-active --quiet "$service.service"; then
                        log_success "Neustarten von $service"
                        sudo systemctl restart "$service.service" || log_error "Fehler beim Neustarten von $service"
                    else
                        log_success "Starten von $service"
                        sudo systemctl start "$service.service" || log_error "Fehler beim Starten von $service"
                    fi
                    sudo systemctl enable "$service.service" || log_error "Fehler beim Aktivieren von $service"
                    ;;
                stop)
                    sudo systemctl stop "$service.service" || log_error "Fehler beim Stoppen von $service"
                    ;;
            esac
        else
            log_error "Service $service nicht gefunden"
        fi
    done
}

# Hauptfunktion
main() {
    local PROJECT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
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

    # Dienste verwalten
    local services=("switch_monitor" "hotspot" "web_interface")
    manage_services restart "${services[@]}"

    log_success "Update und Dienste-Konfiguration abgeschlossen!"
}

# Skript ausführen
main