import subprocess
import random
import string
import logging
import time
from .config import Config

logger = logging.getLogger(__name__)

class HotspotService:
    def __init__(self):
        self.config = Config()
        self.ssid = self._generate_ssid()
        self.connection_name = "NetgearAP"
        self._should_stop = False
        self.active = False

    def _generate_ssid(self) -> str:
        """Generate a simple SSID"""
        base = "NETGEAR-CONFIG-"
        suffix = ''.join(random.choices(string.ascii_uppercase + string.digits, k=4))
        return f"{base}{suffix}"

    def setup_hotspot(self) -> bool:
        """Setup a basic WiFi hotspot"""
        try:
            # Delete old connection if exists
            subprocess.run(
                ["sudo", "nmcli", "connection", "delete", self.connection_name],
                check=False
            )

            # Create new hotspot
            subprocess.run([
                "sudo", "nmcli", "device", "wifi", "hotspot",
                "con-name", self.connection_name,
                "ssid", self.ssid,
                "band", "bg",
                "password", "password123"
            ], check=True)

            # Set IP configuration
            subprocess.run([
                "sudo", "nmcli", "connection", "modify", self.connection_name,
                "ipv4.method", "shared"
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
            subprocess.run(
                ["sudo", "nmcli", "connection", "delete", self.connection_name],
                check=False
            )
            self.active = False
            return True
        except Exception as e:
            logger.error(f"Error during cleanup: {e}")
            return False

    def is_active(self) -> bool:
        """Check if hotspot is active"""
        try:
            result = subprocess.run(
                ["nmcli", "connection", "show", "--active", self.connection_name],
                capture_output=True,
                text=True
            )
            return self.connection_name in result.stdout
        except:
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

            # Main monitoring loop
            while not self._should_stop:
                if not self.is_active():
                    logger.warning("Hotspot connection lost, restarting...")
                    break
                time.sleep(10)

        self.cleanup()