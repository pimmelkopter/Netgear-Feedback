import time
from rpi_ws281x import Adafruit_NeoPixel, Color
from .utils import hex_to_rgb

class LEDController:
    def __init__(self, led_count=48, pin=18, freq_hz=800000, dma=10, brightness=255, invert=False, channel=0):
        self.strip = Adafruit_NeoPixel(led_count, pin, freq_hz, dma, invert, brightness, channel)
        self.strip.begin()
        self.led_count = led_count
        self.port_vlan_map = {}  # {port_id: [vlan_info, vlan_info...]}

    def set_port_vlans(self, port_id, vlan_colors):
        # vlan_colors: Liste von HEX Farbwerten, z.B. ["#FF0000", "#00FF00"]
        self.port_vlan_map[port_id] = vlan_colors

    def update_leds(self):
        # Wenn ein Port nur ein VLAN hat, LED in dessen Farbe anzeigen
        # Wenn mehrere VLANs, LED weiß blinken lassen
        # Hier ein einfaches Beispiel:
        for port_id, vlans in self.port_vlan_map.items():
            led_idx = port_id - 1
            if led_idx < 0 or led_idx >= self.led_count:
                continue
            if len(vlans) == 1:
                r, g, b = hex_to_rgb(vlans[0])
                self.strip.setPixelColor(led_idx, Color(r, g, b))
            else:
                # Mehrere VLANs => weiß blinkend
                # Hier: einfach weiß, später im Hauptloop blinken umsetzen
                self.strip.setPixelColor(led_idx, Color(255, 255, 255))
        self.strip.show()

    def blink_multi_vlan_ports(self, interval=0.5):
        # Hier könnte man die Mehr-VLAN-LEDs aus- und einschalten.
        # Z. B. im Hauptprogramm in einem Timer aufrufen.
        pass
