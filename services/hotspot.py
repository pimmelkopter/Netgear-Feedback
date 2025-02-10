##services/hotspot.py##
import subprocess
import random
import string
import os
import signal
import sys
import logging
import time
import threading
from pathlib import Path
from typing import List, Optional, Dict
from .config import Config

logger = logging.getLogger(__name__)

class HotspotService:
    """Network hotspot management service with watchdog functionality"""
    def __init__(self):
        self.config = Config()
        self.ssid = self._generate_ssid()
        self.connection_name = "NetgearAP"
        self._running = True
        self._should_stop = False
        self.retry_count = 0
        self.max_retries = 3
        self._status_lock = threading.Lock()
        self._process_lock = threading.Lock()
        self._last_health_check = time.monotonic()
        self._health_check_interval = 30  # seconds
        self._watchdog_thread = None

    def _generate_ssid(self) -> str:
        """Generate unique SSID with prefix"""
        prefix = "NETGEAR_"
        suffix = ''.join(random.choices(string.ascii_uppercase + string.digits, k=6))
        return f"{prefix}{suffix}"

    def check_dependencies(self) -> bool:
        """Check if required packages are installed"""
        required_packages = ["iptables", "dnsmasq", "nmcli"]
        try:
            for package in required_packages:
                result = subprocess.run(
                    ["which", package],
                    check=True,
                    capture_output=True,
                    text=True
                )
                if not result.stdout.strip():
                    raise FileNotFoundError(f"{package} not found")
            return True
        except subprocess.CalledProcessError:
            logger.error("Missing required packages. Please install: " + 
                        " ".join(required_packages))
            return False

    def setup_dnsmasq(self) -> bool:
        """Configure and start dnsmasq"""
        config = """# Basic setup
interface=wlan0
bind-interfaces
domain-needed
bogus-priv
no-poll

# DHCP configuration
dhcp-range=192.168.0.10,192.168.0.50,255.255.255.0,24h
dhcp-option=option:router,192.168.0.1
dhcp-option=option:dns-server,192.168.0.1

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

            subprocess.run(
                ["sudo", "systemctl", "enable", "dnsmasq"],
                check=True,
                capture_output=True,
                timeout=30
            )
            return True
        except Exception as e:
            logger.error(f"Error configuring dnsmasq: {e}")
            return False

    def _build_network_commands(self) -> List[List[str]]:
        """Build NMCLI commands for hotspot setup"""
        password = self.config.get('fallback_password', 'default_password')
        return [
            ["sudo", "nmcli", "con", "add", "type", "wifi", 
             "ifname", "wlan0", 
             "con-name", self.connection_name,
             "ssid", self.ssid],
            ["sudo", "nmcli", "con", "modify", self.connection_name, 
             "802-11-wireless.mode", "ap",
             "802-11-wireless.band", "bg", 
             "ipv4.method", "shared"],
            ["sudo", "nmcli", "con", "modify", self.connection_name, 
             "wifi-sec.key-mgmt", "wpa-psk",
             "wifi-sec.psk", password],
            ["sudo", "nmcli", "radio", "wifi", "on"],
            ["sudo", "nmcli", "con", "up", self.connection_name]
        ]

    def setup_hotspot(self) -> bool:
        """Setup WiFi hotspot with error handling"""
        try:
            with self._process_lock:
                # Check dependencies first
                if not self.check_dependencies():
                    return False

                # Initial cleanup
                self.cleanup()

                # Setup NetworkManager connection with exponential backoff
                max_attempts = 3
                for attempt in range(max_attempts):
                    try:
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
                        break
                    except subprocess.CalledProcessError as e:
                        if attempt == max_attempts - 1:
                            raise
                        wait_time = 2 ** attempt
                        logger.warning(f"Command failed, retrying in {wait_time}s: {e}")
                        time.sleep(wait_time)

                # Wait for interface
                time.sleep(2)

                # Configure and start dnsmasq
                if not self.setup_dnsmasq():
                    return False

                subprocess.run(["sudo", "systemctl", "stop", "dnsmasq"], check=True)
                time.sleep(1)

                # Start dnsmasq with verification
                subprocess.run(
                    ["sudo", "systemctl", "start", "dnsmasq"],
                    check=True,
                    capture_output=True,
                    text=True
                )

                # Verify dnsmasq status
                result = subprocess.run(
                    ["systemctl", "is-active", "dnsmasq"],
                    capture_output=True,
                    text=True
                )
                if "active" not in result.stdout:
                    raise Exception("dnsmasq failed to start")

                # Setup iptables if available
                if self._has_iptables():
                    if not self.setup_iptables():
                        logger.warning("Failed to setup iptables rules")

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
            return False
        except Exception as e:
            logger.error(f"Unexpected error: {e}")
            return False

    def _has_iptables(self) -> bool:
        """Check if iptables is available"""
        return (os.path.exists("/sbin/iptables") or 
                os.path.exists("/usr/sbin/iptables"))

    def setup_iptables(self) -> bool:
        """Setup iptables rules"""
        try:
            subprocess.run(["sudo", "iptables", "-F"], check=True)
            subprocess.run(["sudo", "iptables", "-t", "nat", "-F"], check=True)
            # Add additional rules here if needed
            return True
        except subprocess.CalledProcessError as e:
            logger.error(f"Error setting up iptables: {e}")
            return False

    def cleanup(self) -> bool:
        """Clean up network configuration"""
        with self._process_lock:
            try:
                # Stop services
                subprocess.run(
                    ["sudo", "systemctl", "stop", "dnsmasq"],
                    check=False,
                    capture_output=True
                )

                # Clean up NetworkManager connection
                subprocess.run(
                    ["sudo", "nmcli", "connection", "down", self.connection_name],
                    check=False,
                    capture_output=True
                )
                subprocess.run(
                    ["sudo", "nmcli", "connection", "delete", self.connection_name],
                    check=False,
                    capture_output=True
                )

                # Flush iptables if available
                if self._has_iptables():
                    subprocess.run(["sudo", "iptables", "-F"], check=False)
                    subprocess.run(["sudo", "iptables", "-t", "nat", "-F"], check=False)

                return True
            except Exception as e:
                logger.error(f"Error during cleanup: {e}")
                return False

    def is_active(self) -> bool:
        """Check if hotspot is active"""
        with self._status_lock:
            try:
                result = subprocess.run(
                    ["nmcli", "-t", "-f", "ACTIVE", "connection", "show", self.connection_name],
                    capture_output=True,
                    text=True
                )
                return "yes" in result.stdout.lower()
            except Exception:
                return False

    def _health_check(self) -> bool:
        """Perform health check on the hotspot"""
        try:
            # Check if interface is up
            result = subprocess.run(
                ["ip", "link", "show", "wlan0"],
                capture_output=True,
                text=True
            )
            if "UP" not in result.stdout:
                return False

            # Check if dnsmasq is running
            result = subprocess.run(
                ["systemctl", "is-active", "dnsmasq"],
                capture_output=True,
                text=True
            )
            if "active" not in result.stdout:
                return False

            # Check NetworkManager connection
            return self.is_active()

        except Exception as e:
            logger.error(f"Health check failed: {e}")
            return False

    def _watchdog(self):
        """Watchdog thread to monitor hotspot health"""
        while self._running and not self._should_stop:
            current_time = time.monotonic()
            if current_time - self._last_health_check >= self._health_check_interval:
                if not self._health_check():
                    logger.warning("Health check failed, restarting hotspot")
                    if not self.setup_hotspot():
                        logger.error("Failed to restart hotspot")
                self._last_health_check = current_time
            time.sleep(1)

    def run(self):
        """Main service loop with watchdog"""
        try:
            # Start watchdog thread
            self._watchdog_thread = threading.Thread(
                target=self._watchdog,
                daemon=True,
                name="HotspotWatchdog"
            )
            self._watchdog_thread.start()

            while not self._should_stop:
                if not self.setup_hotspot():
                    self.retry_count += 1
                    if self.retry_count >= self.max_retries:
                        logger.error("Max retries reached, exiting...")
                        break
                    logger.error(f"Failed to start hotspot (attempt {self.retry_count}/{self.max_retries})")
                    time.sleep(30)
                    continue

                # Main monitoring loop
                while not self._should_stop:
                    if not self.is_active():
                        logger.warning("Hotspot connection lost, restarting...")
                        break
                    time.sleep(10)

                time.sleep(5)

        except Exception as e:
            logger.error(f"Error in main loop: {e}")
        finally:
            self.stop()

    def stop(self):
        """Stop the service gracefully"""
        self._should_stop = True
        self._running = False
        if self._watchdog_thread and self._watchdog_thread.is_alive():
            self._watchdog_thread.join(timeout=5)
        self.cleanup()