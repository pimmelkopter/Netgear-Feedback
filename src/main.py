##src/main.py##
import time
import sys
import urllib3
import logging
import threading
from queue import Queue
from typing import Dict, Any
from services.config import Config
from services.hotspot import HotspotService
from services.webinterface import WebService
from services.switch_api import SwitchAPI, SwitchAPIError
from services.led import LEDService
from services.utils import (
    parse_port_led_mapping,
    parse_vlan_color_map,
    update_vlan_colors_from_map_and_random,
    calculate_blink_states,
    VLANColorManager
)

# Logging setup
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Disable SSL warnings
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

class PortCache:
    """Simple thread-safe cache for port information"""
    def __init__(self):
        self._cache = {}
        self._ready = threading.Event()
        
    def update(self, new_data):
        """Update cache with new port data"""
        self._cache = new_data.copy()
        self._ready.set()  # Signal that initial data is available
        
    def get(self):
        """Get current cache contents"""
        return self._cache.copy()
        
    def wait_ready(self, timeout=None):
        """Wait until cache has initial data"""
        return self._ready.wait(timeout)

class SwitchMonitor:
    def __init__(self):
        """Initialize monitor with configuration and services"""
        self.config = Config()
        self.led_service = LEDService(self.config)
        self.api = None
        self.port_cache = PortCache()
        self.running = True
        self._start_time = time
        self._led_thread = None

    def _led_update_loop(self):
        """Dedicated LED update loop"""
        port_led_map = parse_port_led_mapping(self.config)
        last_led_update = 0
        LED_UPDATE_INTERVAL = 0.1

        # Wait for initial port data
        if not self.port_cache.wait_ready(timeout=30):
            logger.error("Timeout waiting for initial port data")
            return

        while self.running:
            current_time = time.time()
            
            if current_time - last_led_update >= LED_UPDATE_INTERVAL:
                try:
                    # Get current port info from cache
                    port_info = self.port_cache.get()
                    
                    # Calculate blink states
                    blink_states = calculate_blink_states()
                    
                    # Update LEDs
                    self.led_service.update_port_leds(
                        port_led_map, 
                        port_info, 
                        blink_states
                    )
                    last_led_update = current_time
                except Exception as e:
                    logger.error(f"Error updating LEDs: {e}")
            
            # Small sleep to prevent CPU hogging
            time.sleep(0.01)

    def scan_network(self) -> bool:
        """Scan network for switch with visual progress"""
        logger.info("Starting network scan...")
        total = self.config.scan_range_end - self.config.scan_range_start + 1
        last_progress = 0

        def update_progress(progress: int):
            nonlocal last_progress
            led_progress = int((progress / total) * self.config.led_count)
            if led_progress != last_progress:
                self.led_service.show_progress(led_progress)
                last_progress = led_progress
            
        self.api = SwitchAPI(progress_callback=update_progress)
        
        found_ip = self.api.scan_network(
            self.config.scan_base,
            self.config.scan_range_start,
            self.config.scan_range_end
        )
        
        if found_ip:
            self.config.switch_ip = found_ip
            self.api.base_url = f"https://{found_ip}{self.config.base_url_suffix}"
            logger.info(f"Found switch at {found_ip}")
            return True
            
        logger.error("No switch found during scan")
        return False

    def setup_api(self) -> bool:
        """Initialize API connection"""
        if not self.api:
            self.api = SwitchAPI()
            self.api.base_url = f"https://{self.config.switch_ip}{self.config.base_url_suffix}"
        
        if not self.api.login():
            logger.error("Login failed")
            return False
            
        return True

    def detect_ports(self) -> bool:
        """Detect and verify switch ports"""
        try:
            # Get port count from switch
            port_count = self.api.detect_ports()
            if not port_count:
                return False
                
            # Show success/failure status
            self.led_service.show_status(True)
            return True
            
        except Exception as e:
            logger.error(f"Port detection failed: {e}")
            self.led_service.show_status(False)
            return False

    def scan_vlans(self):
        """Scan and update VLAN configurations"""
        if not self.config.scan_vlans:
            return
            
        try:
            logger.info("Scanning for VLAN configurations...")
            vlan_info = self.api.scan_vlans()
            
            if vlan_info:
                # Update config with new VLAN colors
                update_vlan_colors_from_map_and_random(self.config, vlan_info)
                logger.info("Updated VLAN configurations")
                
        except Exception as e:
            logger.error(f"VLAN scan failed: {e}")

    def update_port_info(self):
        """Update port information cache"""
        try:
            stats = self.api.get_port_info(0)  # 0 = all ports
            if not stats:
                raise SwitchAPIError("Failed to get port stats")
                
            color_map = parse_vlan_color_map(self.config.get('vlan_color_map', ''))
            
            new_cache = {}
            for port_data in stats:
                port_id = port_data.get("portId", 0)
                if not 1 <= port_id <= self.config.port_count:
                    continue
                    
                # Parse port status
                speed = self._parse_port_speed(port_data.get("speed", 0))
                vlan_id = port_data.get("portVlanId", 1)
                
                # Update cache with status and color
                new_cache[port_id] = {
                    "speed": speed,
                    "poe_active": port_data.get("poeStatus", 0) >= 2,
                    "vlan_id": vlan_id,
                    "vlan_color": self._get_vlan_color(vlan_id, color_map)
                }
            
            # Update cache atomically
            self.port_cache.update(new_cache)
                
        except Exception as e:
            logger.error(f"Error updating port info: {e}")
            if isinstance(e, SwitchAPIError):
                self.cleanup_and_exit()

    def _parse_port_speed(self, raw_speed: int) -> int:
        """Convert raw speed value to normalized speed level"""
        if raw_speed == 7:
            return 5  # Gigabit
        if raw_speed in (3,4,6):
            return 4  # 100Mbit
        return 0  # No link

    def _get_vlan_color(self, vlan_id: int, color_map: Dict[int, tuple]) -> tuple:
        """Get color for VLAN ID"""
        color_manager = VLANColorManager()
        return color_manager.get_vlan_color(vlan_id)

    def main_loop(self):
        """Main monitoring loop"""
        last_update = 0
        
        # Start LED update thread
        self._led_thread = threading.Thread(
            target=self._led_update_loop,
            daemon=True
        )
        self._led_thread.start()
        
        while self.running:
            current_time = time.time()
            
            # Update port info at configured interval
            if current_time - last_update >= self.config.update_interval:
                try:
                    self.update_port_info()
                    last_update = current_time
                except Exception as e:
                    logger.error(f"Error updating port info: {e}")
            
            # Sleep to prevent CPU hogging
            time.sleep(0.1)  # Longer sleep is fine here since we're just updating cache

    def is_connected(self) -> bool:
        """Check if switch is connected"""
        if not self.api:
            return False
        try:
            # Schneller Test-Call zum Switch
            self.api.get_port_info(1)
            return True
        except Exception:
            return False

    def get_uptime(self) -> float:
        """Get uptime in seconds"""
        return time.time() - self._start_time  # _start_time in __init__ setzen

    def cleanup_and_exit(self):
        """Clean shutdown sequence"""
        logger.error("Critical error => shutting down")
        self.running = False
        # LED thread will stop automatically since it's a daemon thread
        self.led_service.cleanup()
        sys.exit(1)

    def run(self):
        """Main run sequence"""
        try:
            # Initial status LED
            self.led_service.show_progress(1)

            # Scan for switch if enabled
            if self.config.ip_scan and not self.scan_network():
                self.cleanup_and_exit()
                return

            # Setup API connection
            if not self.setup_api():
                self.cleanup_and_exit()
                return

            # Detect ports if enabled
            if self.config.get('auto_detect_ports', True):
                if not self.detect_ports():
                    self.cleanup_and_exit()
                    return

            # Scan VLANs if enabled
            self.scan_vlans()

            # Clear ALL LEDs before starting normal operation
            self.led_service.all_black()

            # Initialize port info cache with defaults
            initial_cache = {
                pid: {
                    "speed": 0,
                    "poe_active": False,
                    "vlan_id": 1,
                    "vlan_color": (0,0,255)
                }
                for pid in range(1, self.config.port_count + 1)
            }
            self.port_cache.update(initial_cache)

            # Start main monitoring loop
            self.main_loop()

        except KeyboardInterrupt:
            logger.info("KeyboardInterrupt => Exiting")
            self.cleanup_and_exit()
        except Exception as e:
            logger.error(f"Fatal error in main loop: {e}")
            self.cleanup_and_exit()

class ServiceManager:
    def __init__(self):
        self.config = Config()
        self.hotspot_service = HotspotService()
        self.switch_monitor = SwitchMonitor()
        self.web_service = WebService(self.switch_monitor, self.hotspot_service)
        
        # Thread-Management
        self.threads = []

    def start_services(self):
        """Start all services"""
        # Start hotspot
        hotspot_thread = threading.Thread(
            target=self.hotspot_service.run,
            daemon=True
        )
        hotspot_thread.start()
        self.threads.append(hotspot_thread)
        logger.info("Started hotspot service")

        # Start web interface
        web_thread = threading.Thread(
            target=lambda: self.web_service.run(host='0.0.0.0', port=5000),
            daemon=True
        )
        web_thread.start()
        self.threads.append(web_thread)
        logger.info("Started web interface")

        # Start switch monitor (main thread)
        self.switch_monitor.run()

    def cleanup(self):
        """Cleanup all services"""
        logger.info("Cleaning up services...")
        self.hotspot_service.cleanup()
        self.switch_monitor.cleanup_and_exit()
        # Web service cleanup nicht nötig da daemon=True

def main():
    """Main entry point"""
    try:
        manager = ServiceManager()
        manager.start_services()
    except KeyboardInterrupt:
        logger.info("Received shutdown signal")
        manager.cleanup()
    except Exception as e:
        logger.critical(f"Fatal error in main: {e}")
        manager.cleanup()
        sys.exit(1)

if __name__ == "__main__":
    main()