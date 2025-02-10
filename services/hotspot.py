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
        
    def check_dependencies(self) -> bool:
        """Check if required packages are installed"""
        try:
            subprocess.run(["which", "iptables"], check=True, capture_output=True)
            subprocess.run(["which", "dnsmasq"], check=True, capture_output=True)
            return True
        except subprocess.CalledProcessError:
            logger.error("Missing required packages. Please install iptables and dnsmasq:")
            logger.error("sudo apt-get update && sudo apt-get install -y iptables dnsmasq")
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
            
            # Ensure dnsmasq is enabled
            subprocess.run(["sudo", "systemctl", "enable", "dnsmasq"], check=True)
            return True
        except Exception as e:
            logger.error(f"Error configuring dnsmasq: {e}")
            return False

    def setup_hotspot(self) -> bool:
        try:
            # Check dependencies first
            if not self.check_dependencies():
                return False

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

            # Configure dnsmasq first
            if not self.setup_dnsmasq():
                return False

            # Stop dnsmasq if running to ensure clean restart
            subprocess.run(["sudo", "systemctl", "stop", "dnsmasq"], check=True)
            time.sleep(1)
                
            # Start dnsmasq with error checking
            try:
                subprocess.run(
                    ["sudo", "systemctl", "start", "dnsmasq"],
                    check=True,
                    capture_output=True,
                    text=True
                )
                
                # Verify dnsmasq is running
                result = subprocess.run(
                    ["systemctl", "is-active", "dnsmasq"],
                    capture_output=True,
                    text=True
                )
                if "active" not in result.stdout:
                    raise Exception("dnsmasq failed to start")
                    
            except Exception as e:
                logger.error(f"Failed to start dnsmasq: {e}")
                # Get dnsmasq status for debugging
                try:
                    status = subprocess.run(
                        ["systemctl", "status", "dnsmasq"],
                        capture_output=True,
                        text=True
                    )
                    logger.error(f"dnsmasq status: {status.stdout}")
                except:
                    pass
                return False

            # Setup iptables only if available
            if os.path.exists("/sbin/iptables") or os.path.exists("/usr/sbin/iptables"):
                if not self.setup_iptables():
                    logger.warning("Failed to setup iptables rules")
                    # Continue anyway as this is not critical

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

    def cleanup(self) -> bool:
        try:
            # Stop services
            subprocess.run(["sudo", "systemctl", "stop", "dnsmasq"], check=False)
            
            # Clean up NetworkManager connection
            subprocess.run(["sudo", "nmcli", "connection", "down", self.connection_name], check=False)
            subprocess.run(["sudo", "nmcli", "connection", "delete", self.connection_name], check=False)
            
            # Flush iptables if available
            if os.path.exists("/sbin/iptables") or os.path.exists("/usr/sbin/iptables"):
                subprocess.run(["sudo", "iptables", "-F"], check=False)
                subprocess.run(["sudo", "iptables", "-t", "nat", "-F"], check=False)
            
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