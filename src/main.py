import time
import ssl
import requests
from requests.adapters import HTTPAdapter
import sys
import subprocess
from rpi_ws281x import PixelStrip, Color, ws
from .utils import load_config, load_secrets, parse_port_led_mapping, parse_vlan_color_map, parse_rgb_string
import urllib3
from urllib3 import poolmanager

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

class LegacyRenegotiationAdapter(HTTPAdapter):
    def init_poolmanager(self, connections, maxsize, block=False, **kwargs):
        ctx = ssl.create_default_context()
        # Zertifikatsprüfung ausschalten (Gefahr!) oder eigenes CA-Bundle nutzen
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
        
        # Unsichere Legacy-Renegotiation wieder erlauben:
        # Je nach Python 3.11-Version kann es sein, dass man OP_NO_RENEGOTIATION unsetten muss.
        # Der Wert 0x40000 entspricht ssl.OP_NO_RENEGOTIATION in vielen Builds.
        # In neueren Python-Versionen kann man ggf. ssl.OP_NO_RENEGOTIATION direkt ansprechen.
        OP_NO_RENEG = 0x40000  
        ctx.options &= ~OP_NO_RENEG  # Deaktiviert "NO_RENEGOTIATION"

        # Optional: schwächere Cipher aktivieren, falls nötig
        # ctx.set_ciphers("DEFAULT:@SECLEVEL=1")

        self.poolmanager = poolmanager.PoolManager(
            num_pools=connections,
            maxsize=maxsize,
            block=block,
            ssl_context=ctx,
            **kwargs
        )

# Danach eine Session erstellen, die diesen Adapter nutzt:
session = requests.Session()
session.mount("https://", LegacyRenegotiationAdapter())

def ping_ip(ip):
    """ Sendet einen einzelnen Ping, um zu prüfen, ob IP erreichbar ist. """
    # -c 1 => 1 Paket; -W 1 => 1 Sekunde warten
    ret = subprocess.call(['ping', '-c', '1', '-W', '1', ip], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    return (ret == 0)

def scan_for_switch(subnet_prefix="10.18.254", start=1, end=254):
    """ Scannt die IPs im angegebenen Bereich, um den ersten erreichbaren Switch zu finden. """
    for i in range(start, end+1):
        candidate = f"{subnet_prefix}.{i}"
        print(f"\rScanning:{subnet_prefix}.{i} candidate {i} of {end}", end="")
        if ping_ip(candidate):
            print(f"\nSwitch found at: {candidate}")
            return candidate
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
        scanned_ip = scan_for_switch(subnet_prefix, start, end)
        if scanned_ip:
            print(f"Switch gefunden: {scanned_ip}")
            switch_ip = scanned_ip
        else:
            print("Kein Switch gefunden, breche ab.")
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

    resp = requests.post(
        f"{base_url}/login",
        json=login_data,
        headers=headers,
        verify=False
    )
    # Login
    token = None
    try:
        resp = requests.post(f"{base_url}/login", json=login_data, headers=headers, verify=False)
        print(resp.status_code, resp.text)
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
            resp_dev = requests.get(f"{base_url}/device_info", headers=headers, verify=True)
            resp_dev.raise_for_status()
            dev_info = resp_dev.json().get("device_info", {})
            port_count = int(dev_info.get("numOfPorts", 24))
            print(f"Switch meldet {port_count} Ports.")
        except Exception as e:
            print(f"Konnte device_info nicht abrufen. Nutze fallback: {port_count} Ports. Fehler: {e}")

    # Mappings: port -> [ledIndex,...]
    port_led_map = parse_port_led_mapping(config.get('port_led_mapping', ''))

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
                    r = requests.get(f"{base_url}/swcfg_port?portid={port_id}", headers=headers, verify=True)
                    r.raise_for_status()
                    port_data = r.json().get("switchPortConfig", {})
                    vlan_id = port_data.get("portVlanId", 1)

                    # Bspw. VLAN-Farben festlegen
                    if vlan_id in vlan_color_map:
                        r_val, g_val, b_val = vlan_color_map[vlan_id]
                    else:
                        r_val, g_val, b_val = default_vlan_color
                    color = Color(r_val, g_val, b_val)

                    # LEDs für diesen Port setzen
                    leds_for_this_port = port_led_map.get(port_id, [])
                    if not leds_for_this_port:
                        # Wenn kein Mapping hinterlegt, z. B. default: 2 LEDs pro Port
                        # => LED-Paar an (port_id-1)*2 und (port_id-1)*2+1
                        led_index_base = (port_id - 1) * 2
                        leds_for_this_port = [led_index_base, led_index_base + 1]

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