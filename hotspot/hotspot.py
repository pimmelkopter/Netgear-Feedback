# hotspot_service.py
import time
import subprocess
import random
import string
import subprocess
import os
import signal
import sys

class HotspotService:
    def __init__(self):
        self.ssid = self._generate_ssid()
        self.password = "Aud1luma"
        self.connection_name = "NetgearAP"
        
    def _generate_ssid(self):
        """Generate random 8-character SSID ending with -netgear"""
        chars = string.ascii_letters + string.digits
        return ''.join(random.choice(chars) for _ in range(8)) + "-netgear"

    def _setup_dnsmasq(self):
        """Configure dnsmasq for captive portal"""
        config = """
interface=wlan0
dhcp-range=10.18.250.50,10.18.250.150,12h
address=/#/10.18.250.1
dhcp-option=3,10.18.250.1
dhcp-option=6,10.18.250.1
no-resolv
"""
        with open('/tmp/dnsmasq.conf', 'w') as f:
            f.write(config)
            
        subprocess.run(['sudo', 'systemctl', 'restart', 'dnsmasq'])

    def setup_hotspot(self):
        """Configure and start the WiFi hotspot using nmcli with captive portal"""
        try:
            # Set WiFi country
            subprocess.run(["sudo", "raspi-config", "nonint", "do_wifi_country", "DE"], check=True)
            
            # Remove existing connection if exists
            subprocess.run(["sudo", "nmcli", "connection", "delete", self.connection_name], 
                         capture_output=True)

            # Create new hotspot
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
                 "ipv4.method", "manual",
                 "ipv4.addresses", "10.18.250.1/24"],
                 
                ["sudo", "nmcli", "connection", "modify", self.connection_name,
                 "ipv6.method", "ignore"],
                 
                ["sudo", "nmcli", "connection", "up", self.connection_name]
            ]
            
            for cmd in commands:
                subprocess.run(cmd, check=True)
            print(f"Hotspot started with SSID: {self.ssid}")

            # Setup dnsmasq for captive portal
            self._setup_dnsmasq()

            # Setup iptables rules
            iptables_rules = [
                "sudo iptables -t nat -A PREROUTING -i wlan0 -p tcp --dport 80 -j DNAT --to-destination 10.18.250.1:80",
                "sudo iptables -t nat -A PREROUTING -i wlan0 -p tcp --dport 443 -j DNAT --to-destination 10.18.250.1:80",
                "sudo iptables -t nat -A POSTROUTING -o eth0 -j MASQUERADE"
            ]
            
            for rule in iptables_rules:
                subprocess.run(rule.split(), check=True)

            return True, self.ssid

        except subprocess.CalledProcessError as e:
            print(f"Error setting up hotspot: {e}")
            return False

    def cleanup(self):
        """Cleanup when service stops"""
        try:
            # Stop network connection
            subprocess.run(["sudo", "nmcli", "connection", "down", self.connection_name])
            subprocess.run(["sudo", "nmcli", "connection", "delete", self.connection_name])

            # Clear iptables rules
            subprocess.run(["sudo", "iptables", "-F"])
            subprocess.run(["sudo", "iptables", "-t", "nat", "-F"])
            
            # Stop dnsmasq
            subprocess.run(["sudo", "systemctl", "stop", "dnsmasq"])
            
            return True, None
        except subprocess.CalledProcessError as e:
            return False, str(e)

    def get_status(self):
        """Check if hotspot is running"""
        try:
            output = subprocess.check_output(
                ["nmcli", "connection", "show", "--active"], 
                universal_newlines=True
            )
            return self.connection_name in output
        except:
            return False

    def signal_handler(self, signum, frame):
        """Handle shutdown signals"""
        print("Received shutdown signal")
        self.running = False

    def run(self):
        """Main service loop"""
        signal.signal(signal.SIGTERM, self.signal_handler)
        signal.signal(signal.SIGINT, self.signal_handler)

        while self.running:
            if not self.setup_hotspot():
                print("Failed to start hotspot, retrying in 30 seconds...")
                time.sleep(30)
                continue

            # Monitor hotspot status
            while self.running:
                try:
                    # Check if connection is still active
                    result = subprocess.run(
                        ["nmcli", "-t", "-f", "GENERAL.STATE", "connection", "show", self.connection_name],
                        capture_output=True,
                        text=True
                    )
                    
                    if "activated" not in result.stdout.lower():
                        print("Hotspot connection lost, restarting...")
                        break

                except subprocess.CalledProcessError:
                    print("Error checking hotspot status, restarting...")
                    break

                time.sleep(5)

        self.cleanup()

if __name__ == "__main__":
    service = HotspotService()
    service.run()   