# Switch Monitor für VLANs und LEDs (Proof of Concept)

Dieses Projekt ist ein Proof of Concept, um VLAN-Zuordnungen auf einem Switch per API abzurufen und deren Status auf einem WS2812b LED-Streifen anzuzeigen. Zusätzlich kann eine einfache GUI oder ein Button-Interface integriert werden, um VLAN-Farben zuzuweisen.

## Funktionen

- Scannen eines IP-Bereichs, um den ersten erreichbaren Switch zu finden.
- Login auf dem Switch per API (feste Zugangsdaten).
- Abfragen der VLAN-Zuordnungen der Ports.
- Anzeigen der VLANs auf einem WS2812b LED-Streifen (max. 48 LEDs).
- LED-Farbe entspricht der VLAN-Farbe, bei mehreren VLANs auf einem Port blinkt die LED weiß.
- Optional: Eine GUI oder ein Button-Interface auf einem 3,5-Zoll-Touchscreen bzw. über ein Button-Modul zur Einstellung der VLAN-Farben und Zuordnungen.

## Installation und Einrichtung

1. **Raspberry Pi OS Lite installieren**  
   Spielen Sie ein frisches Image auf die SD-Karte.

2. **Feste IP-Adresse einrichten**  
   In `/etc/dhcpcd.conf`:
   interface eth0 static ip_address=10.18.254.3/24 static routers=10.18.254.1 static domain_name_servers=10.18.254.1

Anschließend neu starten: `sudo reboot`

3. **Dependencies installieren**
```bash
sudo chmod +x setup.sh
./setup.sh

4. **Konfiguration anpassen**
Bearbeiten Sie settings/config.json für IP-Bereiche, LED-Anzahl usw.
Bearbeiten Sie settings/secrets.json für Zugangsdaten.

5. **Starten des Scripts**
cd src
python3 main.py


Um den Dienst automatisch beim Booten zu starten:
sudo cp switch_monitor.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable switch_monitor.service
sudo systemctl start switch_monitor.service
