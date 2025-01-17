import time
import requests
import sys
import os
import subprocess
import urllib3
import threading
import json
import re
import random
from rpi_ws281x import PixelStrip, Color, ws

# Local imports from utils.py
from src.utils import (
    load_config,
    load_secrets,
    parse_port_led_mapping,
    parse_vlan_color_map,
    parse_rgb_string,
    parse_vlan_color_for_port,
    CONFIG_PATH
)

# Suppress InsecureRequestWarning for self-signed certificates
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

class SwitchMonitor:
    def __init__(self):
        """Initialize SwitchMonitor with configuration and LED strip"""
        self.config = load_config()
        self.secrets = load_secrets()
        self.setup_config_values()
        self.initialize_led_strip()
        self.stop_event = threading.Event()
        self.port_info_cache = {}
        self.token = None
        
    def setup_config_values(self):
        """Load all configuration values"""
        # Network settings
        self.ip_scan = self.config.get('ip_scan', True)
        self.switch_ip = self.config.get('switch_ip', '192.168.0.1')
        self.base_url_suffix = self.config.get('base_url_suffix', '/api/v1')
        self.subnet_prefix = self.config.get('scan_base', '10.18.254')
        self.scan_start = self.config.get('scan_range_start', 10)
        self.scan_end = self.config.get('scan_range_end', 255)
        
        # LED settings
        self.led_count = self.config.get('led_count', 48)
        self.led_pin = self.config.get('led_pin', 18)
        self.led_brightness = self.config.get('led_brightness', 255)
        
        # Operation settings
        self.update_interval = self.config.get('update_interval', 15)
        self.port_stats = self.config.get('port_stats', False)
        self.port_count = self.config.get('fixed_port_count', 24)
        self.scan_vlans = self.config.get('scan_vlans', False)
        
        # Parse port mapping
        self.port_led_map = parse_port_led_mapping(self.config)

    def initialize_led_strip(self):
        """Initialize the LED strip hardware"""
        self.strip = PixelStrip(
            self.led_count,
            self.led_pin,
            800000,  # Signal frequency
            10,      # DMA
            False,   # Invert
            self.led_brightness,
            0,       # PWM channel
            ws.WS2812_STRIP
        )
        self.strip.begin()

    def ping_ip(self, ip):
        """Ping an IP address with timeout"""
        return subprocess.call(
            ['ping', '-c', '1', '-W', '0.4', ip],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL
        ) == 0

    def scan_network(self):
        """Scan network for switch with progress bar"""
        total = self.scan_end - self.scan_start + 1
        scanned = 0

        for i in range(self.scan_start, self.scan_end + 1):
            candidate = f"{self.subnet_prefix}.{i}"
            progress = int((scanned / total) * self.led_count)

            # Update progress bar (white)
            for led_i in range(self.led_count):
                color = Color(255,255,255) if led_i < progress else 0
                self.strip.setPixelColor(led_i, color)
            self.strip.show()

            print(f"\rScanning: {candidate} ({scanned}/{total})", end="")
            if self.ping_ip(candidate):
                print(f"\nSwitch found: {candidate}")
                return candidate

            scanned += 1

        return None

    def get_vlan_info(self, vlan_id):
        """Extract VLAN name and color from config key vlanX_NAME_color"""
        for key, value in self.config.items():
            if key.startswith(f"vlan{vlan_id}_") and key.endswith("_color"):
                name = key[len(f"vlan{vlan_id}_"):-6]  # Extract NAME part
                color = list(map(int, value.split(',')))
                return name, color
        return None, (0,0,255)  # Default to blue if not found

    def detect_ports(self):
        """Detect number of switch ports and update display"""
        try:
            # Initial white LED to show activity
            self.strip.setPixelColor(0, Color(255,255,255))
            self.strip.show()

            headers = {
                "Content-Type": "application/json",
                "Authorization": f"Bearer {self.token}"
            }
            
            response = requests.get(
                f"{self.base_url}/device_info",
                headers=headers,
                verify=False,
                timeout=3
            )
            response.raise_for_status()
            
            dev_info = response.json().get("deviceInfo", {})
            total_ports = int(dev_info.get("numOfPorts", 24))
            print(f"Switch reports {total_ports} total ports.")

            # Map total ports to usable ports
            if total_ports <= 12:
                self.port_count = 8
            elif total_ports <= 24:
                self.port_count = 16
            elif total_ports <= 40:
                self.port_count = 24
            else:
                self.port_count = 40

            # Show port count in blue for 2s
            print(f"Using {self.port_count} ports.")
            for i in range(self.led_count):
                self.strip.setPixelColor(i, Color(0,0,255) if i < self.port_count else 0)
            self.strip.show()
            time.sleep(2)
            return True

        except Exception as e:
            print(f"Port detection failed: {e}")
            # Error indication in purple
            for i in range(self.led_count):
                self.strip.setPixelColor(i, Color(255,0,255) if i < self.port_count else 0)
            self.strip.show()
            time.sleep(2)
            return True

    def scan_vlans(self):
        """Scan switch for VLAN configurations and update config"""
        try:
            headers = {
                "Content-Type": "application/json",
                "Authorization": f"Bearer {self.token}"
            }
            
            response = requests.get(
                f"{self.base_url}/device_config?file=running-config",
                headers=headers,
                verify=False,
                timeout=5
            )
            response.raise_for_status()
            
            lines = response.json().get("Device-Config",{}).get("Running-Config",[])
            vlan_pattern = re.compile(r'^\s*vlan\s+name\s+(\d+)\s+"([^"]+)"')
            
            updates = {}
            for line in lines:
                match = vlan_pattern.match(line.strip())
                if match:
                    vlan_id = match.group(1)
                    vlan_name = match.group(2)
                    
                    # Generate random color if not exists
                    if f"vlan{vlan_id}_{vlan_name}_color" not in self.config:
                        r = random.randint(0,255)
                        g = random.randint(0,255)
                        b = random.randint(0,255)
                        updates[f"vlan{vlan_id}_{vlan_name}_color"] = f"{r},{g},{b}"
            
            if updates:
                # Update config
                self.config.update(updates)
                self.config["scan_vlans"] = False
                
                # Write to file
                with open(CONFIG_PATH, "w") as cf:
                    json.dump(self.config, cf, indent=2)
                print("Updated config.json with VLAN configurations")
            else:
                print("No new VLANs found in running-config")
                
        except Exception as e:
            print(f"VLAN scan failed: {e}")

    def get_port_status_color(self, speed, poe_active, blink_on):
        """Get LED color based on port status"""
        if not blink_on:
            return Color(0, 0, 255) if poe_active else Color(0, 0, 0)
        
        if speed == 5:
            return Color(0, 255, 0)  # Gigabit
        elif speed == 4:
            return Color(255, 165, 0)  # 100Mbit
        return Color(0, 0, 0)  # No link

    def update_port_info(self):
        """Thread function to update port information"""
        while not self.stop_event.is_set():
            try:
                headers = {
                    "Content-Type": "application/json",
                    "Authorization": f"Bearer {self.token}"
                }
                
                response = requests.get(
                    f"{self.base_url}/sw_portstats?portid=ALL",
                    headers=headers,
                    verify=False,
                    timeout=5
                )
                response.raise_for_status()
                
                # Update port cache
                for port_data in response.json().get("switchStatsPort", []):
                    port_id = port_data.get("portId", 0)
                    if port_id < 1 or port_id > self.port_count:
                        continue
                        
                    # Parse status
                    speed = 5 if port_data.get("speed") == 7 else (
                        4 if port_data.get("speed") in (3,4,6) else 0)
                    poe = port_data.get("poeStatus", 0) >= 2
                    vlan_id = port_data.get("portVlanId", 1)
                    
                    # Get VLAN info
                    name, color = self.get_vlan_info(vlan_id)
                    
                    # Update cache
                    self.port_info_cache[port_id] = {
                        "speed": speed,
                        "poe_active": poe,
                        "vlan_id": vlan_id,
                        "vlan_color": color
                    }
                    
            except requests.exceptions.Timeout:
                print("Timeout while connecting to switch")
                self.cleanup_and_exit()
            except Exception as e:
                print(f"Error updating port info: {e}")
                self.cleanup_and_exit()
                
            time.sleep(self.update_interval)

    def update_leds(self):
        """Thread function to update LED states"""
        blink_cycle = 0
        while not self.stop_event.is_set():
            time.sleep(0.1)
            blink_cycle += 1
            blink_on = ((blink_cycle % 2) == 0)

            for port_id in range(1, self.port_count + 1):
                leds = self.port_led_map.get(port_id, [])
                if not leds:
                    continue
                    
                info = self.port_info_cache.get(port_id, {})
                if not info:
                    continue

                vr, vg, vb = info.get("vlan_color", (0,0,255))
                speed = info.get("speed", 0)
                poe = info.get("poe_active", False)

                # Update LEDs based on mode
                if not self.port_stats:
                    # VLAN color only
                    for led_idx in leds:
                        if 0 <= led_idx < self.led_count:
                            self.strip.setPixelColor(led_idx, Color(vr, vg, vb))
                else:
                    # VLAN + Status
                    if len(leds) >= 2:
                        # First LED: VLAN
                        if 0 <= leds[0] < self.led_count:
                            self.strip.setPixelColor(leds[0], Color(vr, vg, vb))
                            
                        # Second LED: Status
                        if 0 <= leds[1] < self.led_count:
                            if speed == 0 and not poe:
                                self.strip.setPixelColor(leds[1], Color(vr, vg, vb))
                            else:
                                status = self.get_port_status_color(speed, poe, blink_on)
                                self.strip.setPixelColor(leds[1], status)
                    else:
                        # Single LED: Cycle between VLAN and status
                        led_idx = leds[0]
                        if 0 <= led_idx < self.led_count:
                            if (blink_cycle % 16) < 10:
                                self.strip.setPixelColor(led_idx, Color(vr, vg, vb))
                            else:
                                if speed == 0 and not poe:
                                    self.strip.setPixelColor(led_idx, Color(vr, vg, vb))
                                else:
                                    status = self.get_port_status_color(speed, poe, blink_on)
                                    self.strip.setPixelColor(led_idx, status)

            self.strip.show()

    def cleanup_and_exit(self):
        """Clean shutdown with visual feedback"""
        print("Error => Show all red for 1s, then 10s wait with first 10leds white => exit.")
        sys.stdout.flush()
        self.stop_event.set()
        
        # All red
        for i in range(self.led_count):
            self.strip.setPixelColor(i, Color(255,0,0))
        self.strip.show()
        time.sleep(1)
        
        # Count up in white
        for i in range(10):
            if i < self.led_count:
                self.strip.setPixelColor(i, Color(255,255,255))
            self.strip.show()
            time.sleep(1)
            
        # All off
        for i in range(self.led_count):
            self.strip.setPixelColor(i, Color(0,0,0))
        self.strip.show()
        
        print("Script exiting now")
        sys.stdout.flush()
        os._exit(1)

    def run(self):
        """Main run method"""
        try:
            # Initial white LED
            self.strip.setPixelColor(0, Color(255,255,255))
            self.strip.show()

            # Scan for switch if enabled
            if self.ip_scan:
                print("Scanning network for switch...")
                found_ip = self.scan_network()
                if found_ip:
                    self.switch_ip = found_ip
                    # Success flash (green)
                    for i in range(self.led_count):
                        self.strip.setPixelColor(i, Color(0,255,0))
                    self.strip.show()
                    time.sleep(1.0)
                else:
                    print("No switch found.")
                    self.cleanup_and_exit()
                    return

            self.base_url = f"https://{self.switch_ip}{self.base_url_suffix}"

            # Login to switch
            print("Attempting login...")
            try:
                login_data = {
                    "login": {
                        "username": self.secrets.get('username', 'admin'),
                        "password": self.secrets.get('password', 'admin')
                    }
                }
                headers = {"Content-Type": "application/json"}
                
                response = requests.post(
                    f"{self.base_url}/login",
                    json=login_data,
                    headers=headers,
                    verify=False
                )
                response.raise_for_status()
                self.token = response.json()['login']['token']
                print("Login successful")
            except Exception as e:
                print(f"Login failed: {e}")
                self.cleanup_and_exit()
                return

            # Detect ports
            if self.config.get('auto_detect_ports', True):
                if not self.detect_ports():
                    self.cleanup_and_exit()
                    return

            # Scan VLANs if enabled
            if self.scan_vlans:
                print("Scanning for VLAN configurations...")
                self.scan_vlans()

            # Clear all LEDs before starting status updates
            for i in range(self.led_count):
                self.strip.setPixelColor(i, Color(0,0,0))
            self.strip.show()

            # Initialize port info cache
            self.port_info_cache = {
                port_id: {
                    "speed": 0,
                    "poe_active": False,
                    "vlan_id": 1,
                    "vlan_color": (0,0,255)
                } for port_id in range(1, self.port_count + 1)
            }

            # Start monitoring threads
            threads = [
                threading.Thread(target=self.update_port_info, daemon=True),
                threading.Thread(target=self.update_leds, daemon=True)
            ]

            for thread in threads:
                thread.start()

            # Main loop
            while not self.stop_event.is_set():
                time.sleep(1)

        except KeyboardInterrupt:
            self.cleanup_and_exit()
        except Exception as e:
            print(f"Fatal error in main loop: {e}")
            self.cleanup_and_exit()

def main():
    """Main entry point"""
    monitor = SwitchMonitor()
    monitor.run()

if __name__ == "__main__":
    main()