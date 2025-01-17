# main.py -- put your code here!
import machine
import network
import time
import json
import neopixel
from machine import Pin, SPI
import urequests as requests

# Debug-Print-Funktion
def debug_print(msg):
    print(msg)
    
# Konstanten
LED_COUNT = 130
LED_PIN = 13
LED_BRIGHTNESS = 10
UPDATE_INTERVAL = 5

# Festes Port:LED Mapping
PORT_LEDS = {
    1: [11, 12], 3: [13, 14], 5: [15, 16], 7: [17, 18],
    9: [19, 20], 11: [21, 22], 13: [24, 25], 15: [26, 27],
    17: [28, 29], 19: [30, 31], 21: [32, 33], 23: [34, 35],
    24: [93, 92], 22: [95, 94], 20: [97, 96], 18: [99, 98],
    16: [101, 100], 14: [103, 102], 12: [106, 105], 10: [108, 107],
    8: [110, 109], 6: [112, 111], 4: [114, 113], 2: [116, 115]
}

# Festes VLAN-Color Mapping
VLAN_COLORS = {
    1: (0,0,0),
    10: (0,119,0),
    11: (0,255,0),
    12: (255,0,0),
    20: (0,0,255),
    21: (0,0,170),
    22: (0,0,119),
    30: (255,0,255),
    31: (255,0,170),
    50: (170,255,0),
    90: (255,255,0),
    99: (255,255,255)
}

class SwitchMonitor:
    def __init__(self):
        debug_print("Initializing switch monitor...")
        self.setup_network()
        self.setup_leds()
        self.port_status = {}
        
    def setup_network(self):
        """Setup network with fixed IP"""
        debug_print("Setting up network...")
        self.spi = SPI(2, baudrate=20000000, sck=Pin(18), mosi=Pin(23), miso=Pin(19))
        self.w5500 = network.WIZNET5K(self.spi, Pin(5))
        
        # Aktiviere LAN
        self.w5500.active(True)
        # Setze feste IP
        self.w5500.ifconfig(('10.18.251.1', '255.255.255.0', '10.18.251.1', '8.8.8.8'))
        
        # Warte auf Netzwerkverbindung
        timeout = 0
        while not self.w5500.isconnected() and timeout < 20:
            time.sleep(1)
            timeout += 1
            debug_print(f"Waiting for network... {timeout}")
        
        if self.w5500.isconnected():
            debug_print(f"Network connected: {self.w5500.ifconfig()}")
        else:
            debug_print("Network connection failed!")

    def setup_leds(self):
        """Initialize LED strip"""
        debug_print("Setting up LEDs...")
        self.np = neopixel.NeoPixel(Pin(LED_PIN), LED_COUNT)
        self.set_brightness(LED_BRIGHTNESS)
        
        # Test LED strip
        self.test_leds()
        
    def test_leds(self):
        """Run LED test sequence"""
        debug_print("Testing LEDs...")
        # All red
        for i in range(LED_COUNT):
            self.np[i] = (10, 0, 0)
        self.np.write()
        time.sleep(1)
        # All off
        for i in range(LED_COUNT):
            self.np[i] = (0, 0, 0)
        self.np.write()
        debug_print("LED test complete")
        
    def set_brightness(self, brightness):
        """Set global brightness factor"""
        self.brightness = brightness / 255.0
        
    def set_led_color(self, index, color):
        """Set LED color with brightness adjustment"""
        if 0 <= index < LED_COUNT:
            r, g, b = color
            r = int(r * self.brightness)
            g = int(g * self.brightness)
            b = int(b * self.brightness)
            self.np[index] = (r, g, b)

    def get_port_status(self, port):
        """Get port status from switch"""
        try:
            response = requests.get(
                f"https://10.18.254.150:8443/api/v1/swcfg_port?portid={port}",
                auth=("admin", "Aud1luma#"),
                verify=False
            )
            return response.json()
        except:
            return None

    def get_port_status_color(self, speed, poe_active, blink_on):
        """Determine LED color based on port status"""
        if not blink_on:
            return (0, 0, 255) if poe_active else (0, 0, 0)
        
        if speed == 5:  # Gigabit
            return (0, 255, 0)
        elif speed == 4:  # 100Mbit
            return (255, 165, 0)
        return (0, 0, 0)  # No link

    def update_leds(self):
        """Update all LEDs based on port status"""
        blink_cycle = time.time() % 1 > 0.5
        
        for port_id, led_indices in PORT_LEDS.items():
            # Get port status from switch
            port_info = self.get_port_status(port_id)
            if not port_info:
                continue
                
            # Parse port status
            port_data = port_info.get("switchPortConfig", {})
            speed = 5 if port_data.get("speed") == 7 else (
                4 if port_data.get("speed") in (3,4,6) else 0)
            poe = port_data.get("poeStatus", 0) >= 2
            vlan_id = port_data.get("portVlanId", 1)
            
            # Set LED colors
            if len(led_indices) >= 2:
                # First LED: VLAN color
                vlan_color = VLAN_COLORS.get(vlan_id, (0, 0, 255))
                self.set_led_color(led_indices[0], vlan_color)
                
                # Second LED: Status color
                if speed == 0 and not poe:
                    self.set_led_color(led_indices[1], vlan_color)
                else:
                    status_color = self.get_port_status_color(speed, poe, blink_cycle)
                    self.set_led_color(led_indices[1], status_color)
        
        # Update strip
        self.np.write()

    def run(self):
        """Main loop"""
        debug_print("Starting main loop...")
        while True:
            try:
                self.update_leds()
                time.sleep(UPDATE_INTERVAL)
            except Exception as e:
                debug_print(f"Error in main loop: {e}")
                # Alle LEDs rot bei Fehler
                for i in range(LED_COUNT):
                    self.set_led_color(i, (255, 0, 0))
                self.np.write()
                time.sleep(5)

def main():
    debug_print("Starting program...")
    monitor = SwitchMonitor()
    monitor.run()

if __name__ == "__main__":
    main()