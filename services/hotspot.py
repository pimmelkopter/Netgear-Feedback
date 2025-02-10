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
        self._commands = self._build_commands()
        self._should_stop = False
        self.active = False

    def _generate_ssid(self) -> str:
        chars = string.ascii_letters + string.digits
        return ''.join(random.choice(chars) for _ in range(8)) + "-netgear"

    def _build_commands(self) -> List[List[str]]:
        """Build nmcli commands for hotspot setup"""
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
             "ipv4.dns", "192.168.0.1"],  # Set DNS Server
            ["sudo", "nmcli", "connection", "modify", self.connection_name,
             "ipv6.method", "ignore"],
            ["sudo", "nmcli", "connection", "up", self.connection_name]
        ]

    def setup_iptables(self) -> bool:
        """Setup NAT rules with iptables"""
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
        try:
            # Check if a connection is up
            subprocess.run(
                ["sudo", "nmcli", "connection", "delete", self.connection_name],
                capture_output=True,
                check=False  # Ignore errors during deletion
            )

            # Setup NetworkManager connection
            for cmd in self._commands[1:]:
                result = subprocess.run(
                    cmd, 
                    check=True, 
                    capture_output=True, 
                    text=True,
                    timeout=30
                )
                if result.stderr:
                    logger.warning(f"Warning during command {cmd}: {result.stderr}")

            # Setup iptables rules
            if not self.setup_iptables():
                logger.warning("Failed to setup iptables rules")
                # Continue anyway as this is not critical

            logger.info(f"Hotspot started with SSID: {self.ssid}")
            self.retry_count = 0
            self.active = True
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
            # Clean up NetworkManager connection
            for cmd in [
                ["sudo", "nmcli", "connection", "down", self.connection_name],
                ["sudo", "nmcli", "connection", "delete", self.connection_name]
            ]:
                subprocess.run(cmd, check=False, timeout=10)

            # Clean up iptables
            subprocess.run(["sudo", "iptables", "-F"], check=False)
            subprocess.run(["sudo", "iptables", "-t", "nat", "-F"], check=False)

            self.active = False
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

    def signal_handler(self, signum, frame):
        logger.info(f"Received shutdown signal {signum}")
        self.running = False

    def stop(self):
        """Method to safely stop the service"""
        self._should_stop = True

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