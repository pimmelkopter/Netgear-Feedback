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

    def _generate_ssid(self) -> str:
        chars = string.ascii_letters + string.digits
        return ''.join(random.choice(chars) for _ in range(8)) + "-netgear"

    def _build_commands(self) -> List[List[str]]:
        """Build nmcli commands for hotspot setup"""
        return [
            ["sudo", "raspi-config", "nonint", "do_wifi_country", "DE"],
            ["sudo", "nmcli", "connection", "delete", self.connection_name],
            ["sudo", "nmcli", "connection", "add",
             "type", "wifi",
             "ifname", "*",  # Wildcard statt festes wlan0
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
             "ipv6.method", "ignore"],
            ["sudo", "nmcli", "connection", "up", self.connection_name]
        ]

    def setup_hotspot(self) -> bool:
        try:
            # Check if a connection is up
            check_cmd = ["sudo", "nmcli", "connection", "show", self.connection_name]
            if subprocess.run(check_cmd, capture_output=True).returncode == 0:
                # If connection is up - delete it
                delete_cmd = ["sudo", "nmcli", "connection", "delete", self.connection_name]
                subprocess.run(delete_cmd, check=True, capture_output=True)
            

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
            for cmd in [
                ["sudo", "nmcli", "connection", "down", self.connection_name],
                ["sudo", "nmcli", "connection", "delete", self.connection_name]
            ]:
                subprocess.run(cmd, check=False, timeout=10)
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
        """Methode zum sicheren Beenden des Services"""
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