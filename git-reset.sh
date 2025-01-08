#!/bin/bash
cp git-reset.sh git-reset.bak
echo -e "\033[31m Bitte ans Internet anschließen! \033[0m"
sleep 10
echo "Stelle Verbindung auf DHCP um... - wenn die Nachricht länger als 30s bleibt drücke Strg+C"
sudo nmcli connection delete "Wired connection 1"
sudo nmcli connection add type ethernet ifname eth0 con-name "Wired connection 1" ipv4.method auto ipv6.method ignore
sudo nmcli connection up "Wired connection 1"

# Warte auf Internetverbindung
echo "Warte auf Internetverbindung..."
timeout=30  # Max. Wartezeit in Sekunden
interval=1  # Intervalle zwischen den Ping-Versuchen
elapsed=0

while ! ping -c 1 google.com &>/dev/null; do
    sleep $interval
    elapsed=$((elapsed + interval))
    if [ $elapsed -ge $timeout ]; then
        echo "Kein Internet - bitte Einstellungen überprüfen."
        exit 1
    fi
done

echo -e "\033[1;32m Internetverbindung hergestellt! \033[0m"
git fetch origin
git reset --hard origin/raspberrypi

mv git-reset.bak git-reset.sh

cp src/claude-main.py src/main.py
cp src/claude-utils.py src/utils.py

sudo chmod +x update.sh
sudo chmod +x setup/setup.sh
sudo chmod +x git-reset.sh

echo -e "\033[31m Bitte wieder an den Switch anschließen! \033[0m"
sleep 10
./update.sh
echo "Update.sh durchgeführt"
echo -e "\033[1;32m switch_monitor Service neu gestartet durch update.sh \033[0m"
sleep 10
sudo systemctl status switch_monitor.service --no-pager
sleep 2
sudo journalctl -b -u switch_monitor.service --no-pager --since -10m