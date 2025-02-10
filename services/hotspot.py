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
from typing import List, Optional
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
        self.active = False

    def _generate_ssid(self) -> str:
        """Generate a unique SSID for the hotspot"""
        base_name = self.config.get('hotspot_ssid_prefix', 'NETGEAR-CONFIG')
        # Add random suffix to make it unique
        suffix = ''.join(random.choices(string.ascii_uppercase + string.digits, k=4))
        return f"{base_name}-{suffix}"

    def check_dependencies(self) -> bool:
        """Check and setup required dependencies"""
        try:
            # Ensure NetworkManager is installed
            if not os.path.exists("/usr/sbin/NetworkManager"):
                logger.error("NetworkManager is not installed")
                return False

            # Start NetworkManager if not running
            nm_status = subprocess.run(
                ["systemctl", "is-active", "NetworkManager"],
                capture_output=True,
                text=True
            )
            if "active" not in nm_status.stdout:
                logger.warning("NetworkManager is not running, attempting to start...")
                subprocess.run(["sudo", "systemctl", "start", "NetworkManager"])
                time.sleep(10)  # Give NetworkManager time to start

            # Verify NetworkManager is running
            nm_status = subprocess.run(
                ["systemctl", "is-active", "NetworkManager"],
                capture_output=True,
                text=True
            )
            if "active" not in nm_status.stdout:
                logger.error("Failed to start NetworkManager")
                return False

            # Check for required binaries
            subprocess.run(["which", "iptables"], check=True, capture_output=True)
            subprocess.run(["which", "dnsmasq"], check=True, capture_output=True)

            # Verify wlan0 interface
            wlan_status = subprocess.run(
                ["nmcli", "device", "status"], 
                capture_output=True, 
                text=True
            )
            if "wlan0" not in wlan_status.stdout:
                logger.error("wlan0 interface not found")
                return False

            return True
        except subprocess.CalledProcessError as e:
            logger.error(f"Dependency check failed: {e}")
            return False

    def _setup_network_interface(self) -> bool:
        """Prepare network interface for hotspot"""
        try:
            # Unblock WiFi
            subprocess.run(["sudo", "rfkill", "unblock", "wifi"], check=True)
            time.sleep(1)

            # Enable WiFi
            subprocess.run(["sudo", "nmcli", "radio", "wifi", "on"], check=True)
            time.sleep(1)

            # Ensure interface is up
            subprocess.run(["sudo", "ip", "link", "set", "wlan0", "up"], check=True)
            time.sleep(2)

            # Verify interface state
            result = subprocess.run(
                ["ip", "link", "show", "wlan0"],
                capture_output=True,
                text=True
            )
            if "state UP" not in result.stdout:
                logger.error("Failed to bring up wlan0 interface")
                return False

            return True
        except subprocess.CalledProcessError as e:
            logger.error(f"Network interface setup failed: {e}")
            return False

    def _create_hotspot(self) -> bool:
        """Create WiFi hotspot"""
        try:
            # Create hotspot connection
            subprocess.run([
                "sudo", "nmcli", "device", "wifi", "hotspot",
                "con-name", self.connection_name,
                "ssid", self.ssid,
                "password", "password123",  # Add a default password
                "band", "bg",
                "channel", "1"
            ], check=True)
            time.sleep(2)

            # Modify connection settings
            subprocess.run([
                "sudo", "nmcli", "connection", "modify", self.connection_name,
                "ipv4.method", "manual",
                "ipv4.addresses", "192.168.0.1/24",
                "ipv4.gateway", "192.168.0.1",
                "ipv4.dns", "8.8.8.8,8.8.4.4",
                "ipv4.never-default", "true"
            ], check=True)
            time.sleep(2)

            # Verify connection exists
            result = subprocess.run(
                ["nmcli", "connection", "show", self.connection_name],
                capture_output=True,
                text=True
            )
            if self.connection_name not in result.stdout:
                logger.error("Failed to create hotspot connection")
                return False

            return True
        except subprocess.CalledProcessError as e:
            logger.error(f"Hotspot creation failed: {e}")
            return False

    def setup_dnsmasq(self) -> bool:
        """Configure and start dnsmasq"""
        try:
            # Stop any existing dnsmasq processes
            subprocess.run(["sudo", "systemctl", "stop", "dnsmasq"], check=False)
            subprocess.run(["sudo", "killall", "dnsmasq"], check=False)
            time.sleep(2)

            # Basic dnsmasq configuration
            config = """# Basic setup
except-interface=eth0
interface=wlan0
bind-dynamic
listen-address=192.168.0.1
no-hosts
no-resolv
server=8.8.8.8
server=8.8.4.4

# DHCP configuration
dhcp-range=192.168.0.50,192.168.0.150,255.255.255.0,12h
dhcp-option=3,192.168.0.1
dhcp-option=6,192.168.0.1

# Logging
log-queries
log-dhcp
log-facility=/var/log/dnsmasq.log


# Captive portal redirects
address=/detectportal.firefox.com/192.168.0.1
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

            # Write main config
            with open('/etc/dnsmasq.conf', 'w') as f:
                f.write(config)

            # Set permissions and create log file
            subprocess.run(["sudo", "chmod", "644", "/etc/dnsmasq.conf"])
            subprocess.run(["sudo", "touch", "/var/log/dnsmasq.log"])
            subprocess.run(["sudo", "chmod", "644", "/var/log/dnsmasq.log"])

            # Start dnsmasq
            subprocess.run(["sudo", "systemctl", "enable", "dnsmasq"], check=True)
            result = subprocess.run(
                ["sudo", "systemctl", "start", "dnsmasq"],
                capture_output=True,
                text=True
            )

            if result.returncode != 0:
                logger.error(f"dnsmasq start failed: {result.stderr}")
                return False

            # Verify it's running
            time.sleep(2)
            status = subprocess.run(
                ["systemctl", "is-active", "dnsmasq"],
                capture_output=True,
                text=True
            )
            if "active" not in status.stdout:
                logger.error("dnsmasq is not running")
                return False

            return True

        except Exception as e:
            logger.error(f"Error configuring dnsmasq: {e}")
            return False

    def _build_network_commands(self) -> List[List[str]]:
        """Build NetworkManager commands for hotspot setup"""
        return [
            ["sudo", "rfkill", "unblock", "wifi"],  # Ensure WiFi is unblocked
            ["sudo", "nmcli", "radio", "wifi", "on"],  # Ensure WiFi is on
            ["sudo", "ip", "link", "set", "wlan0", "up"],  # Ensure interface is up
            ["sudo", "nmcli", "device", "wifi", "hotspot",
             "con-name", self.connection_name,
             "ssid", self.ssid,
             "band", "bg",
             "channel", "1"],
            ["sudo", "nmcli", "connection", "modify", self.connection_name,
             "ipv4.method", "manual",
             "ipv4.addresses", "192.168.0.1/24",
             "ipv4.gateway", "192.168.0.1",
             "ipv4.dns", "8.8.8.8,8.8.4.4"]
        ]

    def setup_iptables(self) -> bool:
        """Setup iptables rules for NAT"""
        try:
            # Enable IP forwarding
            with open('/proc/sys/net/ipv4/ip_forward', 'w') as f:
                f.write('1\n')

            # Clear existing rules
            subprocess.run(["sudo", "iptables", "-F"], check=True)
            subprocess.run(["sudo", "iptables", "-t", "nat", "-F"], check=True)

            # Set up NAT
            rules = [
                ["sudo", "iptables", "-t", "nat", "-A", "POSTROUTING", "-o", "eth0", "-j", "MASQUERADE"],
                ["sudo", "iptables", "-A", "FORWARD", "-i", "eth0", "-o", "wlan0", "-m", "state", "--state", "RELATED,ESTABLISHED", "-j", "ACCEPT"],
                ["sudo", "iptables", "-A", "FORWARD", "-i", "wlan0", "-o", "eth0", "-j", "ACCEPT"]
            ]
            
            for rule in rules:
                subprocess.run(rule, check=True)
            return True
        except Exception as e:
            logger.error(f"Error setting up iptables: {e}")
            return False

    def setup_hotspot(self) -> bool:
        """Setup and start the hotspot"""
        try:
            # Check dependencies first
            if not self.check_dependencies():
                return False

            # Initial cleanup to ensure clean state
            self.cleanup()
            time.sleep(2)  # Give system time to clean up
            
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

            # Wait for interface to be ready
            time.sleep(2)

            # Setup network interface
            if not self._setup_network_interface():
                return False

            # Create hotspot
            if not self._create_hotspot():
                return False

            # Setup dnsmasq
            if not self.setup_dnsmasq():
                return False

            # Setup iptables
            if not self.setup_iptables():
                return False

            # Activate connection
            subprocess.run([
                "sudo", "nmcli", "connection", "up", self.connection_name
            ], check=True)
            time.sleep(2)

            # Verify hotspot is active
            if not self.get_status():
                raise Exception("Hotspot failed to activate")

            logger.info(f"Hotspot started with SSID: {self.ssid}")
            self.active = True
            return True

        except Exception as e:
            logger.error(f"Error setting up hotspot: {e}")
            return False

    def get_status(self) -> bool:
        """Check if hotspot is running"""
        try:
            result = subprocess.run(
                ["nmcli", "device", "status"],
                capture_output=True,
                text=True
            )
            return "wifi" in result.stdout and "connected" in result.stdout
        except Exception:
            return False

    def cleanup(self) -> bool:
        """Clean up services and configurations"""
        try:
            # Stop services
            subprocess.run(["sudo", "systemctl", "stop", "dnsmasq"], check=False)
            subprocess.run(["sudo", "killall", "dnsmasq"], check=False)

            # Clean up NetworkManager connection
            subprocess.run(["sudo", "nmcli", "connection", "down", self.connection_name], check=False)
            subprocess.run(["sudo", "nmcli", "connection", "delete", self.connection_name], check=False)

            # Clean up iptables
            subprocess.run(["sudo", "iptables", "-F"], check=False)
            subprocess.run(["sudo", "iptables", "-t", "nat", "-F"], check=False)

            self.active = False
            return True
        except Exception as e:
            logger.error(f"Error during cleanup: {e}")
            return False

    def run(self):
        """Main service loop"""
        while not self._should_stop:
            if not self.setup_hotspot():
                self.retry_count += 1
                if self.retry_count >= self.max_retries:
                    logger.error("Max retries reached, exiting...")
                    break
                logger.error(f"Failed to start hotspot (attempt {self.retry_count}/{self.max_retries}), retrying in 30 seconds...")
                time.sleep(30)
                continue

            # Main monitoring loop
            while not self._should_stop:
                if not self.get_status():
                    logger.warning("Hotspot connection lost, restarting...")
                    break
                time.sleep(10)

            time.sleep(5)

        self.cleanup()