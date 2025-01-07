import random
import string
import subprocess
import os

class HotspotManager:
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
            subprocess.run(["sudo", "raspi-config", "nonint", "do_wifi_country", "DE"])
            
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
            return False, str(e)

    def stop_hotspot(self):
        """Stop the WiFi hotspot and clean up"""
        try:
            # Stop network connection
            subprocess.run(["sudo", "nmcli", "connection", "down", self.connection_name])
            
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