import time
import threading
from .utils import get_config, get_secrets
from .network_scan import find_first_switch
from .api_client import APIClient
from .led_control import LEDController
from .gui import GUI

def main():
    config = get_config()
    secrets = get_secrets()

    # Netzwerk-Scan
    base_ip = find_first_switch(config['scan_base'], config['scan_range_start'], config['scan_range_end'])
    if not base_ip:
        print("Kein Switch gefunden!")
        return

    base_url = f"https://{base_ip}:8443/api/v1"
    print("Gefundener Switch:", base_url)

    # API-Client
    api = APIClient(base_url, secrets['username'], secrets['password'])
    api.login()

    # LED-Controller
    led_ctrl = LEDController(led_count=config['led_count'])

    # GUI (optional)
    gui = GUI()
    # GUI könnte in eigenem Thread laufen, hier nur exemplarisch
    # gui_thread = threading.Thread(target=gui.run)
    # gui_thread.start()

    # Hauptloop für periodische Updates
    update_interval = config.get('update_interval', 15)
    while True:
        # VLAN Zuordnungen abrufen
        # Angenommen der Switch hat z.B. 24 Ports
        # Hier könnte man anhand einer erfragten Switch-Konfiguration die Anzahl Ports ermitteln.
        for port_id in range(1, config['led_count']+1):
            try:
                port_info = api.get_port_vlan_info(port_id)
                vlan_id = port_info['switchPortConfig']['portVlanId']
                vlan_data = api.get_vlan_info(vlan_id)
                vlan_name = vlan_data['switchConfigVlan']['name']
                # Farbe pro VLAN zuweisen (hier noch statisch)
                # Später könnte man in config.json VLAN-Farben mappen, oder über GUI anpassen.
                vlan_color = config.get('default_vlan_color', '#0000FF')
                led_ctrl.set_port_vlans(port_id, [vlan_color])
            except:
                # Falls Port nicht existiert oder nicht abgefragt werden kann
                pass

        led_ctrl.update_leds()
        time.sleep(update_interval)

if __name__ == "__main__":
    main()
