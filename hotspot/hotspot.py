# hotspot_service.py
import time
import subprocess
import random
import string
import os
import signal
import sys
import json

class HotspotService:
    def __init__(self):
        self.ssid = self._generate_ssid()
        self.connection_name = "NetgearAP"
        self.running = True
        
        # Setup paths relative to current file
        self.project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        self.secrets_path = os.path.join(self.project_root, 'settings', 'secrets.json')
        self.password = self._load_password()
        
    def _load_password(self):
        """Load password from settings/secrets.json"""
        try:
            with open(self.secrets_path, 'r') as f:
                secrets = json.load(f)
                if not secrets.get('password'):
                    print("Warning: No password found in secrets.json, using fallback")
                    return 'netgear12345678'
                return secrets['password']
        except FileNotFoundError:
            print(f"Warning: secrets.json not found at {self.secrets_path}, using fallback password")
            return 'netgear12345678'
        except json.JSONDecodeError:
            print(f"Warning: secrets.json at {self.secrets_path} is invalid, using fallback password")
            return 'netgear12345678'
        except Exception as e:
            print(f"Unexpected error reading secrets.json: {e}")
            return 'netgear12345678'

    def _generate_ssid(self):
        """Generate random 8-character SSID ending with -netgear"""
        chars = string.ascii_letters + string.digits
        return ''.join(random.choice(chars) for _ in range(8)) + "-netgear"

    def setup_hotspot(self):
        """Configure and start the WiFi hotspot using nmcli"""
        try:
            # Set WiFi country
            subprocess.run(["sudo", "raspi-config", "nonint", "do_wifi_country", "DE"], check=True)
            
            # Remove existing connection if exists
            subprocess.run(["sudo", "nmcli", "connection", "delete", self.connection_name], 
                         capture_output=True, check=False)  # Don't fail if connection doesn't exist

            # Create new hotspot with more stable settings
            commands = [
                ["sudo", "nmcli", "connection", "add",
                 "type", "wifi",
                 "ifname", "wlan0",
                 "con-name", self.connection_name,
                 "autoconnect", "yes",
                 "ssid", self.ssid,
                 "mode", "ap"],
                
                ["sudo", "nmcli", "connection", "modify", self.connection_name,
                 "802-11-wireless-security.key-mgmt", "wpa-psk",
                 "802-11-wireless-security.psk", self.password],
                
                ["sudo", "nmcli", "connection", "modify", self.connection_name,
                 "ipv4.method", "shared"],  # Using shared instead of manual for better stability
                
                ["sudo", "nmcli", "connection", "modify", self.connection_name,
                 "ipv4.addresses", "192.168.0.1/24"],  # Using more standard IP range
                
                ["sudo", "nmcli", "connection", "modify", self.connection_name,
                 "ipv6.method", "ignore"],
                
                ["sudo", "nmcli", "connection", "up", self.connection_name]
            ]
            
            for cmd in commands:
                result = subprocess.run(cmd, check=True, capture_output=True, text=True)
                if result.stderr:
                    print(f"Warning during command {cmd[0]}: {result.stderr}")
                    
            print(f"Hotspot started with SSID: {self.ssid}")
            
            return True

        except subprocess.CalledProcessError as e:
            print(f"Error setting up hotspot: {e}")
            if e.stderr:
                print(f"Error details: {e.stderr}")
            return False

    def cleanup(self):
        """Cleanup when service stops"""
        try:
            subprocess.run(["sudo", "nmcli", "connection", "down", self.connection_name], check=False)
            subprocess.run(["sudo", "nmcli", "connection", "delete", self.connection_name], check=False)
            return True
        except subprocess.CalledProcessError as e:
            print(f"Error during cleanup: {e}")
            return False

    def get_status(self):
        """Check if hotspot is running"""
        try:
            result = subprocess.run(
                ["nmcli", "-t", "-f", "GENERAL.STATE", "connection", "show", self.connection_name],
                capture_output=True,
                text=True,
                check=True
            )
            return "activated" in result.stdout.lower()
        except subprocess.CalledProcessError:
            return False

    def signal_handler(self, signum, frame):
        """Handle shutdown signals"""
        print("Received shutdown signal")
        self.running = False

    def run(self):
        """Main service loop with improved stability"""
        signal.signal(signal.SIGTERM, self.signal_handler)
        signal.signal(signal.SIGINT, self.signal_handler)

        while self.running:
            if not self.setup_hotspot():
                print("Failed to start hotspot, retrying in 30 seconds...")
                time.sleep(30)
                continue

            # Monitor hotspot status with longer interval
            while self.running:
                if not self.get_status():
                    print("Hotspot connection lost, restarting...")
                    break
                time.sleep(10)  # Longer interval to reduce system load

            # Short delay before restart attempt
            time.sleep(5)

        self.cleanup()

if __name__ == "__main__":
    service = HotspotService()
    service.run()