# main.py (MicroPython auf ESP32)

# Feste Netzwerk-Einstellungen
WIFI_SSID = "MyAP"
WIFI_PASS = "secret123"
STATIC_IP = "192.168.100.50"
GATEWAY   = "192.168.100.1"
NETMASK   = "255.255.255.0"

# VLAN-Farben (als Dictionary)
VLAN_COLORS = {
    1:  (0,0,0),
    10: (0,119,0),
    11: (0,255,0),
    # ...
    99: (255,255,255)
}

# LED-Zuweisungen
PORT_LED_MAP = {
    1: [0,1],
    2: [2,3],
    # ...
}

import network
import neopixel
import time
import urequests  # MicroPython-Bibliothek, vereinfacht "requests"

def setup_ethernet():
    # Falls Sie Ethernet via SPI verwenden oder
    # notfalls WLAN, je nach Board:
    pass

def main():
    setup_ethernet()

    # Hier fester Switch: z. B. "192.168.100.10"
    # Keine Ping-Logik nötig, da feste IP
    switch_ip = "192.168.100.10"

    # HTTP Request an Switch:
    url = "http://{}/api/v1/login".format(switch_ip)
    # oder "https://" falls SSL möglich
    data = {
       "login": {
         "username": "admin",
         "password": "Aud1luma#"
       }
    }

    try:
        # Achtung: MicroPython SSL/TLS kann eingeschränkt sein
        resp = urequests.post(url, json=data)
        print("Login status:", resp.status_code)
        print("Login response:", resp.text)
        resp.close()
    except Exception as e:
        print("Login fehlgeschlagen:", e)
        return

    # LED-Setup
    np = neopixel.NeoPixel(pin=4, n=48)  # z.B. 48 LEDs an Pin GPIO4
    # Update LED-Farben
    for port_id, led_indices in PORT_LED_MAP.items():
        # Feste VLAN-ID (vereinfacht):
        vlan_id = 1  # testweise
        color = VLAN_COLORS.get(vlan_id, (0,0,255))  # default: blau
        for led_idx in led_indices:
            np[led_idx] = color
    np.write()

    # Fertig, in einer Endlosschleife o. Ä. könnte man periodisch was machen
    while True:
        time.sleep(5)

main()
