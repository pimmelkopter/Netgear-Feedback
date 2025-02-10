import subprocess
import random
import string
import logging
import time
import os
from pathlib import Path
from .config import Config

logger = logging.getLogger(__name__)

class HotspotService:
    def __init__(self):
        self.config = Config()
        self.ssid = self._generate_ssid()
        self.connection_name = "NetgearAP"
        self._should_stop = False
        self.active = False
        self.dnsmasq_conf_path = "/tmp/netgear-dnsmasq.conf"
        self.hostapd_conf_path = "/tmp/netgear-hostapd.conf"

    def _generate_ssid(self) -> str:
        """Generate a simple SSID"""
        base = "NETGEAR-CONFIG-"
        suffix = ''.join(random.choices(string.ascii_uppercase + string.digits, k=4))
        return f"{base}{suffix}"

    def _create_dnsmasq_config(self):
        """Create dnsmasq configuration for DHCP and DNS"""
        config = f"""
interface=wlan0
bind-interfaces
server=8.8.8.8
domain-needed
bogus-priv
dhcp-range=192.168.0.50,192.168.0.150,12h
dhcp-option=3,192.168.0.1
dhcp-option=6,192.168.0.1
address=/#/192.168.0.1
"""
        with open(self.dnsmasq_conf_path, 'w') as f:
            f.write(config)

    def _create_hostapd_config(self):
        """Create hostapd configuration for the access point"""
        config = f"""
interface=wlan0
driver=nl80211
ssid={self.ssid}
hw_mode=g
channel=7
wmm_enabled=0
macaddr_acl=0
auth_algs=1
ignore_broadcast_ssid=0
wpa=2
wpa_passphrase={self.config.password}
wpa_key_mgmt=WPA-PSK
wpa_pairwise=TKIP
rsn_pairwise=CCMP
"""
        with open(self.hostapd_conf_path, 'w') as f:
            f.write(config)

    def setup_hotspot(self) -> bool:
        """Setup WiFi hotspot with DHCP and DNS"""
        try:
            # Stop potentially running services
            subprocess.run(["sudo", "systemctl", "stop", "dnsmasq"], check=False)
            subprocess.run(["sudo", "systemctl", "stop", "hostapd"], check=False)
            subprocess.run(["sudo", "killall", "dnsmasq"], check=False)
            subprocess.run(["sudo", "killall", "hostapd"], check=False)

            # Stop NetworkManager from managing wlan0
            subprocess.run(["sudo", "nmcli", "radio", "wifi", "off"], check=False)
            subprocess.run(["sudo", "rfkill", "unblock", "wifi"], check=False)

            # Configure wlan0 interface
            subprocess.run(["sudo", "ip", "link", "set", "dev", "wlan0", "down"], check=True)
            subprocess.run(["sudo", "ip", "addr", "flush", "dev", "wlan0"], check=True)
            subprocess.run(["sudo", "ip", "addr", "add", "192.168.0.1/24", "dev", "wlan0"], check=True)
            subprocess.run(["sudo", "ip", "link", "set", "dev", "wlan0", "up"], check=True)

            # Create configurations
            self._create_dnsmasq_config()
            self._create_hostapd_config()

            # Start dnsmasq
            subprocess.run(["sudo", "dnsmasq", "-C", self.dnsmasq_conf_path], check=True)

            # Start hostapd
            subprocess.Popen(["sudo", "hostapd", self.hostapd_conf_path])
            time.sleep(2)  # Wait for hostapd to start

            # Enable IP forwarding and set up NAT
            subprocess.run(["sudo", "sysctl", "net.ipv4.ip_forward=1"], check=True)
            subprocess.run([
                "sudo", "iptables", "-t", "nat", "-A", "POSTROUTING",
                "-o", "eth0", "-j", "MASQUERADE"
            ], check=True)
            subprocess.run([
                "sudo", "iptables", "-A", "FORWARD",
                "-i", "eth0", "-o", "wlan0",
                "-m", "state", "--state", "RELATED,ESTABLISHED",
                "-j", "ACCEPT"
            ], check=True)
            subprocess.run([
                "sudo", "iptables", "-A", "FORWARD",
                "-i", "wlan0", "-o", "eth0",
                "-j", "ACCEPT"
            ], check=True)

            self.active = True
            logger.info(f"Hotspot started with SSID: {self.ssid}")
            return True

        except Exception as e:
            logger.error(f"Error setting up hotspot: {e}")
            return False

    def cleanup(self) -> bool:
        """Clean up hotspot configuration"""
        try:
            # Stop services
            subprocess.run(["sudo", "systemctl", "stop", "dnsmasq"], check=False)
            subprocess.run(["sudo", "systemctl", "stop", "hostapd"], check=False)
            subprocess.run(["sudo", "killall", "dnsmasq"], check=False)
            subprocess.run(["sudo", "killall", "hostapd"], check=False)

            # Remove configurations
            if os.path.exists(self.dnsmasq_conf_path):
                os.remove(self.dnsmasq_conf_path)
            if os.path.exists(self.hostapd_conf_path):
                os.remove(self.hostapd_conf_path)

            # Reset wlan0
            subprocess.run(["sudo", "ip", "link", "set", "dev", "wlan0", "down"], check=False)
            subprocess.run(["sudo", "ip", "addr", "flush", "dev", "wlan0"], check=False)
            
            # Reset iptables
            subprocess.run(["sudo", "iptables", "-F"], check=False)
            subprocess.run(["sudo", "iptables", "-t", "nat", "-F"], check=False)

            # Re-enable NetworkManager
            subprocess.run(["sudo", "nmcli", "radio", "wifi", "on"], check=False)

            self.active = False
            return True

        except Exception as e:
            logger.error(f"Error during cleanup: {e}")
            return False

    def is_active(self) -> bool:
        """Check if hotspot is active"""
        try:
            # Check if hostapd is running
            hostapd_running = subprocess.run(
                ["pgrep", "hostapd"],
                capture_output=True
            ).returncode == 0

            # Check if dnsmasq is running
            dnsmasq_running = subprocess.run(
                ["pgrep", "dnsmasq"],
                capture_output=True
            ).returncode == 0

            # Check if IP is configured
            ip_configured = subprocess.run(
                ["ip", "addr", "show", "wlan0"],
                capture_output=True,
                text=True
            ).stdout.find("192.168.0.1") != -1

            return hostapd_running and dnsmasq_running and ip_configured

        except Exception:
            return False

    def run(self):
        """Main service loop"""
        retry_count = 0
        max_retries = 3

        while not self._should_stop:
            if not self.setup_hotspot():
                retry_count += 1
                if retry_count >= max_retries:
                    logger.error("Max retries reached, exiting...")
                    break
                logger.error(f"Failed to start hotspot (attempt {retry_count}/{max_retries}), retrying in 30 seconds...")
                time.sleep(30)
                continue

            retry_count = 0  # Reset retry count on successful setup

            # Main monitoring loop
            while not self._should_stop:
                if not self.is_active():
                    logger.warning("Hotspot connection lost, restarting...")
                    break
                time.sleep(10)

        self.cleanup()