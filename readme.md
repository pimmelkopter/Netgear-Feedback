
ToDos

- in update ändern auf /etc/dhcp/dhc.conf

✅ Script läuft und gibt die Farbe der VLAN-IDs des Mockservers korrekt auf LED band
- mit echtem Switch testen (echte Daten) 
- interface testen für vlan Änderungen
/ gui über Bildschirm + button interface
/ gui über touchscreen
/ gui über TFT und buttons
/ gui über Hotspot + webinterface


Falls alles eefolgreich
- portieren auf pi zero
- portieren auf esp32
- evtl gui mit Push/turn - encoder
- evtl button-leds


Der ganze Text hierunter ist nur chat gpt, Räume ich noch auf. 

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


Readme V2

) README.md (Beispiel)

    Tipp: Passen Sie den Inhalt an Ihr tatsächliches Projekt, Ihren Switch und Ihre Hardware an.

# Netgear Switch VLAN & LED Monitor

Dieses Projekt dient als Proof-of-Concept, um folgende Funktionen zu demonstrieren:

- **Login** auf einen Netgear-Switch per REST-API (oder Mock-Server).
- **Abfrage** der Port- und VLAN-Konfiguration.
- **Ansteuerung** eines WS2812b-LED-Streifens, um VLAN-Zuordnungen zu visualisieren.
- **Optionale** Netzwerk-Scan-Funktion, um automatisch den Switch zu finden.
- **Automatisches Setzen** einer festen IP-Adresse, falls in der `config.json` konfiguriert.

## Hardware-Voraussetzungen

- **Raspberry Pi 4** (oder ähnliches Modell mit Hardware-PWM auf GPIO 18).
- **WS2812b LED-Streifen** (NeoPixel), Datenleitung an **GPIO 18**, 5V und GND an eine geeignete 5V-Stromquelle.
  - Achten Sie darauf, dass **GND** des LED-Streifens mit dem **GND** des Raspberry Pi verbunden ist.
- **Netgear Switch** (oder kompatibel), erreichbar über das gleiche Netzwerk.
- Optional: **Button-Modul** oder **Touchscreen**, falls eine erweiterte Interaktion geplant ist.

### Verkabelung des LED-Streifens

- **WS2812b Datenpin** -> **GPIO 18** (Pin 12 auf dem 40-Pin GPIO Header)
- **+5V** -> **5V** (Pin 2 oder 4 auf dem GPIO Header)
- **GND** -> **GND** (Pin 6 oder 9 oder 14 etc.)

## Installation und Einrichtung

1. **Raspberry Pi OS Lite** installieren und einmalig einrichten.  
2. **Projektdateien** in ein Verzeichnis auf dem Raspberry Pi kopieren, z. B. `/home/pi/switch-project/`.
3. **Erstinbetriebnahme** durch `setup.sh`:
   ```bash
   cd /home/pi/switch-project
   sudo chmod +x setup.sh
   ./setup.sh

    Erstellt eine Python-Umgebung venv.
    Installiert alle Python-Abhängigkeiten.
    Liest settings/config.json und konfiguriert ggf. eine feste IP-Adresse in /etc/dhcpcd.conf (nur, wenn dhcp auf false steht).

    Konfiguration anpassen
        settings/config.json:
            dhcp, switch_ip, ip_scan, port_led_mapping, usw.
        settings/secrets.json:
            username, password für Ihren Switch.

    Update / Änderungen
        Falls Sie später DHCP oder IP ändern möchten, können Sie update.sh ausführen:

    sudo chmod +x update.sh
    ./update.sh

Starten des Programms

    cd src
    ../venv/bin/python3 main.py

        Das Programm wird versuchen (je nach Konfiguration) entweder:
            per Netzwerk-Scan (wenn ip_scan=true) den Switch zu finden oder
            direkt die in switch_ip angegebene IP zu nutzen.
        Anschließend werden Port-Infos über /device_info abgerufen, um numOfPorts zu ermitteln, und die LEDs werden entsprechend gesteuert.

GPIO-Pin ändern

    Möchten Sie statt GPIO 18 einen anderen Pin nutzen, passen Sie in main.py (bzw. an entsprechender Stelle) die Variable LED_PIN an. Beachten Sie, dass nur GPIO 18 und GPIO 19 (und einige wenige andere) über Hardware-PWM für den WS2812b-Streifen geeignet sind.

Abhängigkeiten

    Python 3
    rpi_ws281x
    requests
    (weitere siehe requirements.txt)

Fehlerbehandlung

    Bei Verbindungsfehlern (z. B. kein Switch gefunden), überprüfen Sie die Netzwerk-Einstellungen.
    Prüfen Sie, ob die LED-Library Zugriff hat; falls nötig, starten Sie das Skript mit sudo.

Lizenz / Hinweis

Diese Beispiel-Codebasis wird ohne Gewähr bereitgestellt. Verwenden Sie sie als Grundlage für eigene Experimente.