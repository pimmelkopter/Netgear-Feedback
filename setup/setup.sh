#!/usr/bin/env bash
set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "$0")/.." && pwd)"

# Farbige Ausgabe für bessere Lesbarkeit
RED='\033[0;31m'
GREEN='\033[0;32m'
NC='\033[0m'

echo_status() {
    echo -e "${GREEN}[+]${NC} $1"
}

echo_error() {
    echo -e "${RED}[!]${NC} $1"
}

# Nginx Konfiguration erstellen
create_nginx_config() {
    cat << 'EOL' | sudo tee /etc/nginx/sites-available/switch_monitor > /dev/null
server {
    listen 80 default_server;
    listen [::]:80 default_server;
    
    # Add netgear.switch to server names
    server_name _ connectivitycheck.gstatic.com connectivitycheck.android.com clients3.google.com netgear.switch;
    
    root /home/admin/Netgear-Feedback/web;
    
    # Redirect all captive portal detection URLs to our interface
    location / {
        proxy_pass http://127.0.0.1:5000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
    
    # Handle all captive portal detection endpoints
    location /generate_204 {
        return 302 http://192.168.0.1/;
    }
    
    location /ncsi.txt {
        return 302 http://192.168.0.1/;
    }
    
    location /hotspot-detect.html {
        return 302 http://192.168.0.1/;
    }
    
    location /success.txt {
        return 302 http://192.168.0.1/;
    }
}
EOL
}

# DNSMasq Konfiguration erstellen
create_dnsmasq_config() {
    cat << 'EOL' | sudo tee /etc/dnsmasq.conf > /dev/null
interface=wlan0
bind-interfaces
domain-needed
bogus-priv
no-poll

# DHCP configuration
dhcp-range=192.168.0.10,192.168.0.50,255.255.255.0,24h
dhcp-option=option:router,192.168.0.1
dhcp-option=option:dns-server,192.168.0.1

# Redirect all DNS queries to our IP
address=/#/192.168.0.1
EOL
}

# Systemanforderungen prüfen
check_system_requirements() {
    echo_status "Checking system requirements..."
    
    if [ "$(id -u)" -eq 0 ]; then
        echo_error "Please do not run as root"
        exit 1
    fi
    
    if ! command -v python3 >/dev/null; then
        echo_error "Python 3 is required"
        exit 1
    fi
}

# Pakete installieren
install_system_packages() {
    echo_status "Installing system packages..."
    
    sudo apt update && sudo apt upgrade -y
    sudo apt install -y \
        python3 \
        python3-pip \
        python3-venv \
        git \
        jq \
        dnsmasq \
        hostapd \
        network-manager \
        libdbus-1-dev \
        libdbus-glib-1-dev \
        dbus \
        nginx \
        gunicorn \
        iptables
    sudo apt autoremove -y
}

# Python-Umgebung einrichten
setup_python_environment() {
    echo_status "Setting up Python environment..."
    
    if [ ! -d "${PROJECT_DIR}/venv" ]; then
        python3 -m venv "${PROJECT_DIR}/venv"
    fi
    
    source "${PROJECT_DIR}/venv/bin/activate"
    pip install --upgrade pip
    pip install -r "${PROJECT_DIR}/setup/requirements.txt"
}

# Dienste konfigurieren
configure_services() {
    echo_status "Configuring services..."
    
    # Konfliktende Dienste deaktivieren
    for service in hostapd dnsmasq; do
        sudo systemctl disable $service || true
        sudo systemctl stop $service || true
    done
    
    # Nginx konfigurieren
    create_nginx_config
    sudo ln -sf /etc/nginx/sites-available/switch_monitor /etc/nginx/sites-enabled/
    sudo rm -f /etc/nginx/sites-enabled/default
    
    # DNSMasq konfigurieren
    create_dnsmasq_config
}

# Berechtigungen setzen
set_permissions() {
    echo_status "Setting permissions..."
    
    sudo chown -R admin:admin "${PROJECT_DIR}/web"
    sudo chmod +x setup/dev_tools/update.sh
    sudo chmod +x setup/dev_tools/git-reset.sh
    sudo chmod +x setup/dev_tools/fixed-hotspot.sh
}

# Hauptinstallation
main() {
    echo_status "Starting installation..."
    
    check_system_requirements
    install_system_packages
    setup_python_environment
    configure_services
    set_permissions
    
    # Dienste neustarten
    sudo systemctl daemon-reload
    sudo systemctl restart nginx
    sudo systemctl restart dnsmasq
    
    echo_status "Installation complete!"
    echo "Please ensure config/config.json and config/secrets.json are properly configured. And reboot system"
}

# Skript ausführen
main