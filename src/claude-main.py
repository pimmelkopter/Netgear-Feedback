import time
import requests
import sys
import os
import subprocess
import urllib3
import threading
from dataclasses import dataclass
from typing import Optional, Dict, List, Tuple
from rpi_ws281x import PixelStrip, Color, ws

from src.utils import (
    ConfigManager, 
    VLANManager,
    parse_port_led_mapping,
    RGB
)

# Suppress InsecureRequestWarning
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

@dataclass
class LEDStatus:
    """Status information for a port's LED"""
    vlan_color: RGB = (0, 0, 0)
    speed: int = 0
    poe_active: bool = False

class SwitchMonitor:
    """Handles switch monitoring and LED control"""
    
    def __init__(self):
        self.config = ConfigManager.load_config()
        self.secrets = ConfigManager.load_secrets()
        self.setup_config_values()
        self.initialize_led_strip()
        self.port_info_cache: Dict[int, LEDStatus] = {}
        self.stop_event = threading.Event()
        self.token: Optional[str] = None
        self.switch_ip: Optional[str] = None

    def setup_config_values(self):
        """Initialize configuration values"""
        self.led_count = self.config.get('led_count', 48)
        self.led_pin = self.config.get('led_pin', 18)
        self.led_brightness = self.config.get('led_brightness', 255)
        self.update_interval = self.config.get('update_interval', 15)
        self.port_count = self.config.get('fixed_port_count', 24)
        self.port_stats = self.config.get('port_stats', False)
        self.base_url_suffix = self.config.get('base_url_suffix', '/api/v1')
        
        # Network scan settings
        self.subnet_prefix = self.config.get('scan_base', '10.18.254')
        self.scan_start = self.config.get('scan_range_start', 10)
        self.scan_end = self.config.get('scan_range_end', 255)
        
    def initialize_led_strip(self):
        """Initialize the LED strip"""
        self.strip = PixelStrip(
            self.led_count,
            self.led_pin,
            800000,  # Frequency
            10,      # DMA
            False,   # Invert
            self.led_brightness,
            0,       # PWM Channel
            ws.WS2812_STRIP
        )
        self.strip.begin()
        
    @staticmethod
    def ping_ip(ip: str) -> bool:
        """Send a single ping to an IP address"""
        return subprocess.call(
            ['ping', '-c', '1', '-W', '0.4', ip],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL
        ) == 0

    def scan_network(self) -> Optional[str]:
        """Scan network for switch"""
        total = self.scan_end - self.scan_start + 1
        scanned = 0

        for i in range(self.scan_start, self.scan_end + 1):
            candidate = f"{self.subnet_prefix}.{i}"
            progress = int((scanned / total) * self.led_count)

            # Update progress bar
            for led_i in range(self.led_count):
                color = Color(255, 255, 255) if led_i < progress else 0
                self.strip.setPixelColor(led_i, color)
            self.strip.show()

            print(f"\rScanning: {candidate} ({scanned}/{total})", end="")
            if self.ping_ip(candidate):
                print(f"\nSwitch found at: {candidate}")
                return candidate

            scanned += 1
        return None

    def cleanup_and_exit(self):
        """Cleanup and exit with error indication"""
        self.stop_event.set()
        
        # All red for 1 second
        self.set_all_leds(Color(255, 0, 0))
        time.sleep(1)
        
        # Count up first 10 LEDs in white
        for i in range(min(10, self.led_count)):
            self.strip.setPixelColor(i, Color(255, 255, 255))
            self.strip.show()
            time.sleep(1)
            
        # Clear all LEDs
        self.set_all_leds(0)
        sys.exit(1)

    def set_all_leds(self, color):
        """Set all LEDs to a specific color"""
        for i in range(self.led_count):
            self.strip.setPixelColor(i, color)
        self.strip.show()

    def login_to_switch(self):
        """Authenticate with the switch"""
        headers = {"Content-Type": "application/json"}
        login_data = {
            "login": {
                "username": self.secrets.get('username', 'admin'),
                "password": self.secrets.get('password', 'admin')
            }
        }
        
        try:
            base_url = f"https://{self.switch_ip}{self.base_url_suffix}"
            response = requests.post(
                f"{base_url}/login",
                json=login_data,
                headers=headers,
                verify=False,
                timeout=5
            )
            response.raise_for_status()
            self.token = response.json()['login']['token']
            return True
        except Exception as e:
            print(f"Login failed: {e}")
            return False

    def get_port_status_color(self, speed: int, poe_active: bool, blink_on: bool) -> RGB:
        """Determine LED color based on port status"""
        if not blink_on:
            return (0, 0, 255) if poe_active else (0, 0, 0)
        
        return {
            5: (0, 255, 0),     # Gigabit
            4: (255, 165, 0),   # 100Mbit
            0: (0, 0, 0)        # No link
        }.get(speed, (0, 0, 0))

    def update_port_info(self):
        """Update port information from switch"""
        while not self.stop_event.is_set():
            try:
                headers = {"Authorization": f"Bearer {self.token}"}
                response = requests.get(
                    f"https://{self.switch_ip}{self.base_url_suffix}/sw_portstats?portid=ALL",
                    headers=headers,
                    verify=False,
                    timeout=5
                )
                response.raise_for_status()
                
                for port_data in response.json().get("switchStatsPort", []):
                    port_id = port_data.get("portId")
                    if not (1 <= port_id <= self.port_count):
                        continue
                        
                    speed = self.parse_speed(port_data)
                    poe = port_data.get("poeStatus", 0) >= 2
                    vlans = port_data.get("vlans", [])
                    vlan_color = VLANManager.get_vlan_color(
                        vlans,
                        self.config,
                        (0, 0, 255)  # default color
                    )
                    
                    self.port_info_cache[port_id] = LEDStatus(
                        vlan_color=vlan_color,
                        speed=speed,
                        poe_active=poe
                    )
                    
            except Exception as e:
                print(f"Failed to update port info: {e}")
                self.cleanup_and_exit()
                
            time.sleep(self.update_interval)

    @staticmethod
    def parse_speed(stats: dict) -> int:
        """Parse speed from port statistics"""
        if stats.get("oprState", 0) != 1:
            return 0
        speed = stats.get("speed", 0)
        if speed == 7:
            return 5  # Gigabit
        elif speed in (3, 4, 6):
            return 4  # 100Mbit
        return 0

    def update_leds(self):
        """Update LED states"""
        blink_cycle = 0
        port_led_map = parse_port_led_mapping(self.config)
        
        while not self.stop_event.is_set():
            blink_cycle = (blink_cycle + 1) % 20
            blink_on = (blink_cycle % 2) == 0

            for port_id, status in self.port_info_cache.items():
                led_indices = port_led_map.get(port_id, [])
                if not led_indices:
                    continue

                if not self.port_stats:
                    # Simple mode: show VLAN color
                    for led_idx in led_indices:
                        if 0 <= led_idx < self.led_count:
                            r, g, b = status.vlan_color
                            self.strip.setPixelColor(led_idx, Color(r, g, b))
                else:
                    # Advanced mode: show status information
                    self.update_port_leds(
                        led_indices,
                        status,
                        blink_on,
                        blink_cycle
                    )

            self.strip.show()
            time.sleep(0.1)

    def update_port_leds(self, led_indices: List[int], status: LEDStatus,
                        blink_on: bool, blink_cycle: int):
        """Update LEDs for a specific port"""
        if len(led_indices) >= 2:
            # First LED shows VLAN
            if 0 <= led_indices[0] < self.led_count:
                r, g, b = status.vlan_color
                self.strip.setPixelColor(led_indices[0], Color(r, g, b))

            # Second LED shows status
            if 0 <= led_indices[1] < self.led_count:
                if status.speed == 0 and not status.poe_active:
                    r, g, b = status.vlan_color
                else:
                    r, g, b = self.get_port_status_color(
                        status.speed,
                        status.poe_active,
                        blink_on
                    )
                self.strip.setPixelColor(led_indices[1], Color(r, g, b))
        else:
            # Single LED mode: cycle between VLAN and status
            led_idx = led_indices[0]
            if 0 <= led_idx < self.led_count:
                if blink_cycle % 16 < 10:
                    r, g, b = status.vlan_color
                else:
                    r, g, b = self.get_port_status_color(
                        status.speed,
                        status.poe_active,
                        blink_on
                    )
                self.strip.setPixelColor(led_idx, Color(r, g, b))

    def run(self):
        """Main run method"""
        # Initial LED indication
        self.strip.setPixelColor(0, Color(255, 255, 255))
        self.strip.show()

        # Find switch
        if self.config.get('ip_scan', True):
            self.switch_ip = self.scan_network()
            if not self.switch_ip:
                print("No switch found")
                self.cleanup_and_exit()
        else:
            self.switch_ip = self.config.get('switch_ip')

        # Login
        if not self.login_to_switch():
            self.cleanup_and_exit()

        # Start monitoring threads
        threads = [
            threading.Thread(target=self.update_port_info, daemon=True),
            threading.Thread(target=self.update_leds, daemon=True)
        ]
        
        for thread in threads:
            thread.start()

        # Main loop
        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            self.cleanup_and_exit()

def main():
    monitor = SwitchMonitor()
    monitor.run()

if __name__ == "__main__":
    main()