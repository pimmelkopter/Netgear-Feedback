cp git-reset.sh git-reset.bak
echo "dhcp nicht vergessen!"
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

echo "Internetverbindung hergestellt!"
git fetch origin
git reset --hard origin/raspberrypi
sudo chmod +x update.sh
sudo chmod +x run.sh
sudo chmod +x setup.sh
mv git-reset.bak git-reset.sh
sudo chmod +x git-reset.sh
./update.sh
sudo systemctl restart switch_monitor.service