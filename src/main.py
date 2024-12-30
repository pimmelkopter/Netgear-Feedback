import time
import ssl
import requests
import sys
import subprocess
from rpi_ws281x import PixelStrip, Color, ws
from .utils import load_config, load_secrets, parse_port_led_mapping, parse_vlan_color_map, parse_rgb_string
import urllib3

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

def ping_ip(ip):
    """ Sendet einen einzelnen Ping, um zu prüfen, ob IP erreichbar ist. """
    # -c 1 => 1 Paket; -W 1 => 1 Sekunde warten
    ret = subprocess.call(['ping', '-c', '1', '-W', '0.4', ip], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    return (ret == 0)

def scan_for_switch(subnet_prefix, start, end, strip=None, led_count=48): #led count wird in main dann ausgelesen
    total = end - start + 1
    scanned = 0
    for i in range(start, end+1):
        candidate = f"{subnet_prefix}.{i}"
        # Fortschritt in %
        progress = int((scanned / total) * led_count)
        # Zeichne Ladebalken in weiß
        if strip is not None:
            for led_i in range(led_count):
                if led_i < progress:
                    strip.setPixelColor(led_i, Color(255,255,255)) # weiß
                else:
                    strip.setPixelColor(led_i, 0)
            strip.show()

        print(f"\rScanning: {candidate} ({scanned}/{total})", end="")
        if ping_ip(candidate):
            print(f"\nSwitch found at: {candidate}")
            return candidate
        scanned += 1
    print()
    return None

def main():
    config = load_config()
    secrets = load_secrets()

    ip_scan = config.get('ip_scan', True)
    switch_ip = config.get('switch_ip', '192.168.0.1')  # Fallback
    base_url_suffix = config.get('base_url_suffix', '/api/v1')
    led_count = config.get('led_count', 48)
    led_pin = config.get('led_pin', 18)
    led_brightness = config.get('led_brightness', 255)  # Neu
    default_vlan_color_str = config.get('default_vlan_color', '0,0,255')  # Neu
    vlan_color_map_str = config.get('vlan_color_map', '')  # Neu
    update_interval = config.get('update_interval', 15)
    start = config.get('scan_range_start', 10)
    end = config.get('scan_range_end', 255)
    subnet_prefix = config.get('scan_base', '10.18.254')

    # Parset die neuen Farb-Mappings
    vlan_color_map = parse_vlan_color_map(vlan_color_map_str)
    default_vlan_color = parse_rgb_string(default_vlan_color_str)


    # Falls ip_scan==true => versuche Switch im Netz zu finden,
    # ansonsten benutze switch_ip direkt.
    if ip_scan:
        print("Scanne Netzwerk nach erstem erreichbarem Switch...")
        # Beispiel: Vorbelegen mit 10.18.254.* oder aus fixed_ip extrahieren
        # Hier hartkodiert als Bsp. anwendbar:
        scanned_ip = scan_for_switch(subnet_prefix, start, end, strip=strip, led_count=led_count)
        if scanned_ip:
            print(f"Switch gefunden: {scanned_ip}")
            switch_ip = scanned_ip
            for i in range(led_count):
                strip.setPixelColor(i, Color(0,255,0)) # grün für erfolg
            strip.show()
            time.sleep(1.0)
        else:
            print("Kein Switch gefunden, skript restartet in 10s")
            for sec in range(10):
                # pro Sekunde 1 LED rot
                if sec < led_count:
                    strip.setPixelColor(sec, Color(255,0,0))
                strip.show()
                time.sleep(1)
            # Dann Neustart:
            print("Skript beendet - sollte neu starten")
            sys.exit(1)
    else:
        print(f"Nutze konfiguriertes Switch-IP: {switch_ip}")

    base_url = f"https://{switch_ip}{base_url_suffix}"
    username = secrets.get('username', 'admin')
    password = secrets.get('password', 'admin')

    # Setup PixelStrip
    strip = PixelStrip(
        led_count,
        led_pin,
        800000, # Standardfreq WS2812
        10,     # DMA
        False,  # invert
        led_brightness,    # brightness
        0,      # channel
        ws.WS2812_STRIP
    )
    strip.begin()

    # LED1 weiß als "Script läuft" - LED index 0
    strip.setPixelColor(0,255,255,255)
    strip.show()

    headers = {
        "Content-Type": "application/json"
    }

    # Login Definition
    login_data = {
        "login": {
            "username": username,
            "password": password
        }
    }

    # Login
    token = None
    try:
        resp = requests.post(f"{base_url}/login", json=login_data, headers=headers, verify=False)
        resp.raise_for_status()
        token = resp.json()['login']['token']
    except Exception as e:
        print(f"Login fehlgeschlagen: {e}")
        sys.exit(1)

    print("Login erfolgreich, Token abgerufen.")

    # Auto-Detect Ports?
    auto_detect_ports = config.get('auto_detect_ports', True)
    port_count = config.get('fixed_port_count', 24)
    if auto_detect_ports:
        try:
            headers = {"Authorization": f"Bearer {token}"}
            resp_dev = requests.get(f"{base_url}/device_info", headers=headers, verify=False)
            resp_dev.raise_for_status()
            dev_info = resp_dev.json().get("device_info", {})
            port_count = int(dev_info.get("numOfPorts", 24))
            print(f"Switch meldet {port_count} Ports.")
            for i in range(led_count): # Port Anzahl in blau anzeigen
                if i < port_count:
                    strip.setPixelColor(i, Color(0,0,255))
                else:
                    strip.setPixelColor(i, 0)
            strip.show()
            time.sleep(1.0)
        except Exception as e:
            print(f"Konnte device_info nicht abrufen. Nutze fallback: {port_count} Ports. Fehler: {e}")

    # Mappings: port -> [ledIndex,...]
    port_led_map = parse_port_led_mapping(config)

    # Cleanup-Funktion, um LEDs auszuschalten bei Ctrl+C
    def cleanup_and_exit():
        print("\nBeende Programm, schalte LEDs aus.")
        for i in range(led_count):
            strip.setPixelColor(i, 0)
        strip.show()
        sys.exit(0)

    try:
        while True:
            headers = {"Authorization": f"Bearer {token}"}
            for port_id in range(1, port_count + 1):
                # VLAN abrufen
                try:
                    r = requests.get(f"{base_url}/swcfg_port?portid={port_id}", headers=headers, verify=False, timeout=2)
                    r.raise_for_status()
                    port_data = r.json().get("switchPortConfig", {})
                    vlan_id = port_data.get("portVlanId", 1)

                    # Bspw. VLAN-Farben festlegen
                    if vlan_id in vlan_color_map:
                        r_val, g_val, b_val = vlan_color_map[vlan_id]
                    else:
                        r_val, g_val, b_val = default_vlan_color
                    color = Color(r_val, g_val, b_val)

                    # Mapping
                    leds_for_this_port = port_led_map.get(port_id, [])
                    if not leds_for_this_port:
                        # skip_undefined
                        continue

                    for led_idx in leds_for_this_port:
                        if 0 <= led_idx < led_count:
                            strip.setPixelColor(led_idx, color)

                except Exception as ex:
                    print(f"Fehler bei Port {port_id}: {ex}")

            strip.show()
            time.sleep(update_interval)

    except KeyboardInterrupt:
        cleanup_and_exit()

if __name__ == "__main__":
    main()