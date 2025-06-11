##services/hotspot.py##
import subprocess
import random
import string
import logging
import gpiozero as GPIO
import threading
import time
import os
from pathlib import Path
from .config import Config
from .display import DisplayService

logger = logging.getLogger(__name__)

class HotspotService:
    def __init__(self):
        self.config = Config()
        self.display = DisplayService()
        self.password = None
        self.ssid = self._generate_ssid()
        self.connection_name = "NetgearAP"
        self.active = False
        self.dnsmasq_conf_path = "/tmp/netgear-dnsmasq.conf"
        self.hostapd_conf_path = "/tmp/netgear-hostapd.conf"
        self.button_pin = self.config.get('hotspot_button_pin', 23)
        self.timeout_duration = self.config.get('hotspot_timeout', 300)  # 5 minutes in seconds
        self._timeout_timer = None
        
        # Initialize Display
        self.display.init_display()

        try:
            self._setup_gpio()
        except Exception as e:
            logger.warning(f"GPIO setup failed: {e}. Running without button support.")
            self.button_pin = None

    def _setup_gpio(self):
        """Setup GPIO for button input with proper cleanup"""
        try:
            # Cleanup any existing GPIO settings for this pin
            if self.button_pin is not None:
                try:
                    GPIO.cleanup(self.button_pin)
                except:
                    pass
            
            # Setup GPIO
            GPIO.setmode(GPIO.BCM)
            GPIO.setup(self.button_pin, GPIO.IN, pull_up_down=GPIO.PUD_UP)
            
            # Add event detection with try/except
            try:
                GPIO.add_event_detect(self.button_pin, GPIO.FALLING, 
                                    callback=self._button_callback,
                                    bouncetime=300)
            except RuntimeError:
                # If event detection fails, try removing it first
                GPIO.remove_event_detect(self.button_pin)
                GPIO.add_event_detect(self.button_pin, GPIO.FALLING, 
                                    callback=self._button_callback,
                                    bouncetime=300)
        except Exception as e:
            logger.error(f"GPIO setup error: {e}")
            raise

    def _button_callback(self, channel):
        """Handle button press"""
        if not self.active:
            logger.info("Button pressed - starting hotspot")
            self.activate_with_new_credentials()
        else:
            logger.info("Button pressed - resetting timeout")
            self._reset_timeout()

    def _generate_ssid(self) -> str:
        """Generate a simple SSID"""
        base = "NETGEAR-CONFIG-"
        suffix = ''.join(random.choices(string.ascii_uppercase + string.digits, k=4)) #or for testing suffix = ''.join("test")
        return f"{base}{suffix}"
    
    def _generate_password(self) -> str:
        if self.config.get('fixed_hotspot_password'):
            return self.config.get('fixed_hotspot_password')
        else:
            chars = string.ascii_letters + string.digits
            return ''.join(random.choices(chars, k=8))
        
    def activate_with_new_credentials(self):
        self.cleanup()
        self.ssid = self._generate_ssid()
        self.password = self._generate_password()
        return self.setup_hotspot()

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
wpa_passphrase={self.password}
wpa_key_mgmt=WPA-PSK
wpa_pairwise=TKIP
rsn_pairwise=CCMP
"""
        with open(self.hostapd_conf_path, 'w') as f:
            f.write(config)

    def setup_hotspot(self) -> bool:
        """Setup WiFi hotspot with DHCP and DNS"""
        try:
            logger.info("Setting up hotspot...")

            if not self.password:
                self.password = self._generate_password()
            
            # Existierende Dienste stoppen
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

            logger.info(f"Hotspot started with SSID: {self.ssid}")
            
            # Show QR code on display
            self.display.show_wifi_qr(self.ssid, self.password)

            # Timer für Auto-Shutdown starten
            self._reset_timeout()
            self.active = True
            
            return True

        except Exception as e:
            logger.error(f"Error setting up hotspot: {e}")
            return False

    def _reset_timeout(self):
        """Reset oder starte den Timeout-Timer"""
        if self._timeout_timer:
            self._timeout_timer.cancel()
        self._timeout_timer = threading.Timer(self.timeout_duration, self.cleanup)
        self._timeout_timer.daemon = True  # Make the timer a daemon thread
        self._timeout_timer.start()
        logger.info(f"Timeout timer reset. Will cleanup in {self.timeout_duration} seconds")

    def cleanup(self) -> bool:
        """Clean up hotspot configuration and GPIO"""
        try:
            self.active = False

            logger.info("Cleaning up hotspot...")
                
            # Timer stoppen
            if self._timeout_timer:
                self._timeout_timer.cancel()
                self._timeout_timer = None

            if self.button_pin is not None:
                try:
                    GPIO.cleanup(self.button_pin)
                except:
                    pass
            
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
            subprocess.run(["sudo", "nmcli", "radio", "wifi", "on"], check=False)
            subprocess.run(["sudo", "nmcli", "device", "wifi", "rescan"], check=False)
            
            # Reset iptables
            subprocess.run(["sudo", "iptables", "-F"], check=False)
            subprocess.run(["sudo", "iptables", "-t", "nat", "-F"], check=False)

            # Re-enable NetworkManager
            subprocess.run(["sudo", "nmcli", "radio", "wifi", "on"], check=False)
            subprocess.run(["sudo", "nmcli", "connection", "up", "Wired connection 1"], check=False)

            time.sleep(2)
            self.display.cleanup()

            logger.info("Hotspot cleaned up")
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
        
        while True:
            if self.active:
                time.sleep(1)
                continue

            if not self.setup_hotspot():
                retry_count += 1
                if retry_count >= max_retries:
                    logger.error("Max retries reached, exiting...")
                    return
                logger.error(f"Failed to start hotspot (attempt {retry_count}/{max_retries}), retrying in 30 seconds...")
                time.sleep(30)
            else:
                retry_count = 0