##services/hotspot.py##
import subprocess
import random
import string
import os
import signal
import sys
import logging
import time
from pathlib import Path
from typing import List
from .config import Config

logger = logging.getLogger(__name__)

class HotspotService:
    def __init__(self):
        self.config = Config()
        self.ssid = self._generate_ssid()
        self.connection_name = "NetgearAP"
        self.running = True
        self.retry_count = 0
        self.max_retries = 3
        self._should_stop = False

    def _generate_ssid(self) -> str:
        chars = string.ascii_letters + string.digits
        return ''.join(random.choice(chars) for _ in range(8)) + "-netgear"

    def _build_network_commands(self) -> List[List[str]]:
        """Build NetworkManager commands for hotspot setup"""
        return [
            ["sudo", "raspi-config", "nonint", "do_wifi_country", "DE"],
            ["sudo", "nmcli", "connection", "add",
             "type", "wifi",
             "ifname", "wlan0", 
             "con-name", self.connection_name,
             "autoconnect", "yes",
             "ssid", self.ssid,
             "mode", "ap"],
            ["sudo", "nmcli", "connection", "modify", self.connection_name,
             "802-11-wireless-security.key-mgmt", "wpa-psk",
             "802-11-wireless-security.psk", self.config.password],
            ["sudo", "nmcli", "connection", "modify", self.connection_name,
             "ipv4.method", "shared"],
            ["sudo", "nmcli", "connection", "modify", self.connection_name,
             "ipv4.addresses", "192.168.0.1/24"],
            ["sudo", "nmcli", "connection", "modify", self.connection_name,
             "ipv6.method", "ignore"]
        ]

    def setup_dnsmasq(self) -> bool:
        """Configure and start dnsmasq"""
        config = """interface=wlan0
dhcp-range=192.168.0.10,192.168.0.50,255.255.255.0,24h
# Redirect all DNS queries to our IP
address=/#/192.168.0.1

# Captive portal detection URLs
address=/connectivitycheck.gstatic.com/192.168.0.1
address=/generate_204/192.168.0.1
address=/gen_204/192.168.0.1
address=/play.googleapis.com/192.168.0.1
address=/www.google.com/192.168.0.1
address=/detectportal.firefox.com/192.168.0.1
address=/success.txt.firefox.com/192.168.0.1
address=/clients3.google.com/192.168.0.1
address=/www.gstatic.com/192.168.0.1
address=/www.apple.com/192.168.0.1
address=/captive.apple.com/192.168.0.1
address=/www.msftncsi.com/192.168.0.1
address=/www.msftconnecttest.com/192.168.0.1"""

        try:
            with open('/etc/dnsmasq.conf', 'w') as f:
                f.write(config)
            return True
        except Exception as e:
            logger.error(f"Error configuring dnsmasq: {e}")
            return False

    def setup_iptables(self) -> bool:
        """Setup iptables rules for captive portal"""
        commands = [
            # Flush existing rules
            "sudo iptables -F",
            "sudo iptables -t nat -F",
            
            # Allow established connections
            "sudo iptables -A INPUT -m conntrack --ctstate ESTABLISHED,RELATED -j ACCEPT",
            
            # Allow DHCP
            "sudo iptables -A INPUT -p udp --dport 67:68 --sport 67:68 -j ACCEPT",
            
            # Allow DNS
            "sudo iptables -A INPUT -p udp --dport 53 -j ACCEPT",
            "sudo iptables -A INPUT -p tcp --dport 53 -j ACCEPT",
            
            # Redirect all HTTP traffic to local web app
            "sudo iptables -t nat -A PREROUTING -i wlan0 -p tcp --dport 80 -j DNAT --to-destination 192.168.0.1:5000",
            
            # Enable routing
            "sudo iptables -A FORWARD -i wlan0 -j ACCEPT",
            
            # Masquerade outgoing traffic
            "sudo iptables -t nat -A POSTROUTING -o eth0 -j MASQUERADE"
        ]
        
        for cmd in commands:
            try:
                subprocess.run(cmd.split(), check=True)
            except subprocess.CalledProcessError as e:
                logger.error(f"Error setting up iptables: {e}")
                return False
        return True

    def setup_hotspot(self) -> bool:
        try:
            # Initial cleanup
            self.cleanup()
            
            # Setup NetworkManager connection
            for cmd in self._build_network_commands():
                result = subprocess.run(
                    cmd,
                    check=True,
                    capture_output=True,
                    text=True,
                    timeout=30
                )
                if result.stderr:
                    logger.warning(f"Warning during command {cmd}: {result.stderr}")

            # Bring up the connection
            subprocess.run(
                ["sudo", "nmcli", "connection", "up", self.connection_name],
                check=True,
                capture_output=True,
                text=True,
                timeout=30
            )

            # Wait for interface to be ready
            time.sleep(2)

            # Configure and start dnsmasq
            if not self.setup_dnsmasq():
                return False
                
            subprocess.run(
                ["sudo", "systemctl", "restart", "dnsmasq"],
                check=True,
                timeout=10
            )

            # Setup iptables rules
            if not self.setup_iptables():
                return False

            logger.info(f"Hotspot started with SSID: {self.ssid}")
            self.retry_count = 0
            return True

        except subprocess.TimeoutExpired:
            logger.error("Command timed out")
            return False
        except subprocess.CalledProcessError as e:
            logger.error(f"Error setting up hotspot: {e}")
            if e.stderr:
                logger.error(f"Command stderr: {e.stderr}")
            if e.stdout:
                logger.error(f"Command stdout: {e.stdout}")
            return False
        except Exception as e:
            logger.error(f"Unexpected error: {e}")
            return False

    def cleanup(self) -> bool:
        try:
            # Stop services
            subprocess.run(["sudo", "systemctl", "stop", "dnsmasq"], check=False)
            
            # Clean up NetworkManager connection
            subprocess.run(["sudo", "nmcli", "connection", "down", self.connection_name], check=False)
            subprocess.run(["sudo", "nmcli", "connection", "delete", self.connection_name], check=False)
            
            # Flush iptables
            subprocess.run(["sudo", "iptables", "-F"], check=False)
            subprocess.run(["sudo", "iptables", "-t", "nat", "-F"], check=False)
            
            return True
        except Exception as e:
            logger.error(f"Error during cleanup: {e}")
            return False

    def get_status(self) -> bool:
        try:
            result = subprocess.run(
                ["nmcli", "-t", "-f", "GENERAL.STATE", "connection", "show", self.connection_name],
                capture_output=True,
                text=True,
                check=True,
                timeout=5
            )
            return "activated" in result.stdout.lower()
        except Exception:
            return False

    def stop(self):
        """Safe method to stop the service"""
        self._should_stop = True

    def run(self):
        while not self._should_stop:
            if not self.setup_hotspot():
                self.retry_count += 1
                if self.retry_count >= self.max_retries:
                    logger.error("Max retries reached, exiting...")
                    break
                logger.error(f"Failed to start hotspot (attempt {self.retry_count}/{self.max_retries}), retrying in 30 seconds...")
                time.sleep(30)
                continue

            while not self._should_stop:
                if not self.get_status():
                    logger.warning("Hotspot connection lost, restarting...")
                    break
                time.sleep(10)

            time.sleep(5)

        self.cleanup()

    def is_active(self) -> bool:
        """Check if hotspot is running"""
        try:
            result = subprocess.run(
                ["nmcli", "-t", "-f", "GENERAL.STATE", "connection", "show", self.connection_name],
                capture_output=True,
                text=True,
                check=True,
                timeout=5
            )
            return "activated" in result.stdout.lower()
        except Exception:
            return False

if __name__ == "__main__":
    try:
        service = HotspotService()
        service.run()
    except Exception as e:
        logger.critical(f"Fatal error: {e}")
        sys.exit(1)