#!/usr/bin/env bash
set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "$0")/.." && pwd)"

SERVICE_TEMPLATE="[Unit]
Description=%s
After=network.target
%s

[Service]
Type=simple
User=admin
WorkingDirectory=${PROJECT_DIR}
Environment=\"PYTHONPATH=${PROJECT_DIR}\"
%s
ExecStart=${PROJECT_DIR}/venv/bin/python3 %s
Restart=always
RestartSec=2
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target"

create_service() {
    local name=$1
    local desc=$2
    local deps=$3
    local env=$4
    local exec=$5
    
    printf "$SERVICE_TEMPLATE" "$desc" "$deps" "$env" "$exec" | \
    sudo tee "/etc/systemd/system/${name}.service" > /dev/null
}

# Nginx Konfiguration erstellen
create_nginx_config() {
    cat << 'EOL' | sudo tee /etc/nginx/sites-available/switch_monitor > /dev/null
server {
    listen 80 default_server;
    listen [::]:80 default_server;

    server_name _ connectivitycheck.gstatic.com connectivitycheck.android.com clients3.google.com;

    root /home/admin/Netgear-Feedback/web;

    location / {
        proxy_pass http://127.0.0.1:5000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }

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
dhcp-range=192.168.0.50,192.168.0.150,12h
dhcp-option=3,192.168.0.1
dhcp-option=6,192.168.0.1
address=/#/192.168.0.1
EOL
}

echo "Starting installation..."

# System packages
echo "Installing system packages..."
sudo apt update && sudo apt upgrade -y
sudo apt install -y python3 python3-pip python3-venv git jq dnsmasq hostapd network-manager \
    libdbus-1-dev libdbus-glib-1-dev dbus nginx gunicorn

# Create Python venv
if [ ! -d "${PROJECT_DIR}/venv" ]; then
    echo "Creating Python virtual environment..."
    python3 -m venv "${PROJECT_DIR}/venv"
fi

echo "Activating venv and installing Python packages..."
source "${PROJECT_DIR}/venv/bin/activate"
pip install --upgrade pip
pip install -r "${PROJECT_DIR}/setup/requirements.txt"

# Disable conflicting services
for service in hostapd dnsmasq; do
    sudo systemctl disable $service || true
    sudo systemctl stop $service || true
done

# Create service files
echo "Installing systemd services..."

# Switch Monitor Service
create_service "switch_monitor" \
    "Switch Monitor Service" \
    "" \
    "Environment=\"OPENSSL_CONF=${PROJECT_DIR}/config/openssl.cnf\"\nEnvironment=\"FLASK_APP=wsgi.py\"\nEnvironment=\"FLASK_ENV=production\"" \
    "-m src.main"

# Hotspot Service
create_service "hotspot" \
    "WiFi Hotspot Service" \
    "Requires=NetworkManager.service" \
    "" \
    "-m hotspot.hotspot"

# Enable services
for service in switch_monitor hotspot; do
    sudo systemctl enable $service.service
done

# Configure nginx
echo "Configuring nginx..."
create_nginx_config
sudo ln -sf /etc/nginx/sites-available/switch_monitor /etc/nginx/sites-enabled/
sudo rm -f /etc/nginx/sites-enabled/default

# Configure dnsmasq
echo "Configuring dnsmasq..."
create_dnsmasq_config

# Set permissions
sudo chown -R admin:admin "${PROJECT_DIR}/web"

# Restart services
sudo systemctl daemon-reload
sudo systemctl restart nginx
sudo systemctl restart dnsmasq

sudo chmod +x setup/dev_tools/update.sh
sudo chmod +x setup/dev_tools/git-reset.sh
sudo chmod +x setup/dev_tools/fixed-hotspot.sh

echo "Installation complete!"
echo "Please ensure config/config.json and config/secrets.json are properly configured."