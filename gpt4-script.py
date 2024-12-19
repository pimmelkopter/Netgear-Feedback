import time
import requests
import subprocess
from rpi_ws281x import PixelStrip, Color

# LED-Strip Konfiguration
LED_COUNT = 48  # Anzahl der LEDs = max. Ports
LED_PIN = 18  # GPIO-Pin
LED_FREQ_HZ = 800000  # LED-Signal-Frequenz
LED_DMA = 10  # DMA-Kanal
LED_BRIGHTNESS = 255  # Helligkeit
LED_INVERT = False  # Signal-Invertierung
LED_CHANNEL = 0  # Kanal

# Switch-API Konfiguration
BASE_URL = "https://10.18.254.150:8443/api/v1"
USERNAME = "admin"
PASSWORD = "Aud1luma#"

# Helper-Funktionen
def scan_network():
    active_ips = []
    for i in range(10, 256):
        ip = f"10.18.254.{i}"
        response = subprocess.run(["ping", "-c", "1", "-W", "1", ip], stdout=subprocess.DEVNULL)
        if response.returncode == 0:
            active_ips.append(ip)
    return active_ips

def login_to_switch():
    try:
        response = requests.post(f"{BASE_URL}/login", json={"username": USERNAME, "password": PASSWORD}, verify=False)
        if response.status_code == 200 and response.json().get("resp", {}).get("status") == "success":
            return response.json()["login"]["token"]
    except Exception as e:
        print(f"Login fehlgeschlagen: {e}")
    return None

def get_port_vlan_mappings(token, num_ports=48):
    headers = {"Authorization": f"Bearer {token}"}
    vlan_mappings = {}
    for port in range(1, num_ports + 1):
        try:
            response = requests.get(f"{BASE_URL}/swcfg_port?portid={port}", headers=headers, verify=False)
            if response.status_code == 200:
                port_vlan = response.json()["switchPortConfig"]["portVlanId"]
                vlan_mappings[port] = port_vlan
            else:
                break
        except Exception as e:
            print(f"Fehler beim Abrufen von Port {port}: {e}")
            break
    return vlan_mappings

def set_led_colors(strip, vlan_mappings, vlan_colors):
    for port, vlan_id in vlan_mappings.items():
        color = vlan_colors.get(vlan_id, (0, 0, 0))  # Standardfarbe Schwarz
        strip.setPixelColor(port - 1, Color(*color))  # GRB
    strip.show()

def main():
    # LED-Strip initialisieren
    strip = PixelStrip(LED_COUNT, LED_PIN, LED_FREQ_HZ, LED_DMA, LED_INVERT, LED_BRIGHTNESS, LED_CHANNEL)
    strip.begin()

    # Netzwerkscan
    print("Netzwerkscan läuft...")
    active_ips = scan_network()
    print(f"Aktive IPs gefunden: {active_ips}")

    # Login
    token = login_to_switch()
    if not token:
        print("Fehler beim Login. Beende...")
        return

    # VLAN-Zuordnungen und Farben
    vlan_colors = {}  # Beispiel: {1: (0, 255, 0), 2: (255, 0, 0)}
    try:
        vlan_mappings = get_port_vlan_mappings(token)
        print(f"VLAN-Zuordnungen: {vlan_mappings}")

        # LEDs initialisieren
        set_led_colors(strip, vlan_mappings, vlan_colors)

        # Periodisches Update
        while True:
            vlan_mappings = get_port_vlan_mappings(token)
            set_led_colors(strip, vlan_mappings, vlan_colors)
            time.sleep(15)  # Alle 15 Sekunden aktualisieren
    except KeyboardInterrupt:
        print("Beendet...")
        for i in range(LED_COUNT):
            strip.setPixelColor(i, Color(0, 0, 0))
        strip.show()

if __name__ == "__main__":
    main()
