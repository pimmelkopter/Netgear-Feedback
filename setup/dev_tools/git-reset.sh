#!/bin/bash

# Farben für bessere Lesbarkeit
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Hilfsfunktionen
echo_status() {
    echo -e "${GREEN}[+]${NC} $1"
}

echo_warning() {
    echo -e "${YELLOW}[!]${NC} $1"
}

echo_error() {
    echo -e "${RED}[!]${NC} $1"
}

# Funktion zum Prüfen der Internetverbindung
check_internet() {
    local timeout=30
    local interval=1
    local elapsed=0
    
    echo_status "Prüfe Internetverbindung..."
    while ! ping -c 1 google.com &>/dev/null; do
        sleep $interval
        elapsed=$((elapsed + interval))
        if [ $elapsed -ge $timeout ]; then
            echo_error "Kein Internet - Timeout nach ${timeout} Sekunden"
            return 1
        fi
    done
    echo_status "Internetverbindung hergestellt!"
    return 0
}

# Funktion für Ethernet-Update
setup_ethernet() {
    echo_warning "Bitte Ethernet-Kabel ans Internet anschließen"
    echo_warning "Sie haben 5 Sekunden zum Umstecken..."
    sleep 5
    
    echo_status "Stelle Ethernet-Verbindung her..."
    sudo nmcli connection delete "Wired connection 1" 2>/dev/null || true
    sudo nmcli connection add type ethernet ifname eth0 con-name "Wired connection 1" \
         ipv4.method auto ipv6.method ignore
    sudo nmcli connection up "Wired connection 1"
    
    check_internet
    return $?
}

# Funktion für WiFi-Update
setup_wifi() {
    echo_status "Stoppe Hotspot-Service..."
    sudo systemctl stop hotspot.service
    
    echo_status "Scanne nach WLAN-Netzwerken..."
    sudo nmcli device wifi rescan
    
    # Zeige verfügbare Netzwerke
    echo_status "Verfügbare Netzwerke:"
    sudo nmcli device wifi list
    
    # Frage nach WLAN-Daten
    echo -n "WLAN-Name (SSID): "
    read SSID
    echo -n "WLAN-Passwort: "
    read -s PASSWORD
    echo
    
    echo_status "Verbinde mit WLAN..."
    sudo nmcli device wifi connect "$SSID" password "$PASSWORD"
    
    check_internet
    return $?
}

# Funktion für das eigentliche Update
perform_update() {
    echo_status "Hole Updates von GitHub..."
    git fetch origin
    git reset --hard origin/raspberrypi
    
    echo_status "Führe update.sh aus..."
    chmod +x setup/dev_tools/update.sh
    ./setup/dev_tools/update.sh
}

# Funktion für die Wiederherstellung
restore_connection() {
    echo_warning "Stelle ursprüngliche Verbindung wieder her..."
    echo_warning "Sie haben 5 Sekunden zum Umstecken/Verbinden..."
    sudo systemctl restart NetworkManager.service
    sudo systemctl start hotspot.service
    sleep 5
    
    echo_status "Starte switch_monitor neu..."
    sudo systemctl restart switch_monitor.service
    sleep 5
    
    # Zeige Status
    echo_status "Status des switch_monitor Service:"
    sudo systemctl status switch_monitor.service --no-pager
    
    echo_status "Letzte Logs:"
    sudo journalctl -b -u switch_monitor.service --no-pager --since -10m
}

# Hauptprogramm
main() {
    # Menü anzeigen
    echo "Bitte Updatemethod wählen:"
    echo "1) Ethernet (Internet-Kabel umstecken)"
    echo "2) WLAN (Hotspot wird kurzzeitig deaktiviert)"
    echo "Q) Abbrechen"
    
    read -p "Auswahl (1/2/Q): " choice
    
    case $choice in
        1)
            if setup_ethernet; then
                perform_update
                restore_connection
            fi
            ;;
        2)
            if setup_wifi; then
                perform_update
                restore_connection
            fi
            ;;
        [Qq])
            echo_status "Update abgebrochen"
            exit 0
            ;;
        *)
            echo_error "Ungültige Auswahl"
            exit 1
            ;;
    esac
}

# Skript ausführen
main