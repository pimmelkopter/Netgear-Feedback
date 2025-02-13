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
        self._lock = threading.Lock()
        self._cache = {}
        self._ready = threading.Event()
        
    def update(self, new_data):
        """Update cache with new port data"""
        with self._lock:
            self._cache = new_data.copy()
        self._ready.set()  # Signal that initial data is available
        
    def get(self):
        """Get current cache contents"""
        with self._lock:
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
        self._start_time = time.time()
        self._led_thread = None
        self._force_update = threading.Event()
        self._last_port_update = 0
        self._last_stats_update = 0
        self.VLAN_UPDATE_INTERVAL = 30  # 30 seconds between VLAN updates
        self.STATS_UPDATE_INTERVAL = self.config.update_interval  # Config interval for speed/PoE
        self._force_update_ports = set() 

    def trigger_port_update(self, port_id=None):
        """Force a port info update on next cycle, optionally for specific port"""
        if port_id is None:
            self._force_update.set()  # Full update
        else:
            self._force_update_ports.add(port_id)

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
            current_time = time.time()
            
            # Check update intervals
            need_vlan_update = (self._force_update.is_set() or 
                              current_time - self._last_port_update >= self.VLAN_UPDATE_INTERVAL)
            need_stats_update = (current_time - self._last_stats_update >= self.STATS_UPDATE_INTERVAL)
            
            if not (need_vlan_update or need_stats_update or self._force_update_ports):
                return
                
            # If only specific ports need updating
            if self._force_update_ports and not need_vlan_update:
                for port_id in self._force_update_ports:
                    try:
                        stats = self.api.get_port_info(port_id)  # Get single port
                        if not stats:
                            continue
                            
                        # Update cache for single port
                        self._update_port_cache(port_id, stats[0])
                    except Exception as e:
                        logger.error(f"Error updating port {port_id}: {e}")
                        
                self._force_update_ports.clear()
                return

            new_cache = {}
            current_cache = self.port_cache.get()

            # Update stats if needed
            if need_stats_update:
                port_stats = self.api.get_port_stats(0)  # 0 = all ports
                if port_stats:
                    for port_data in port_stats:
                        port_id = port_data.get("portId", 0)
                        if not 1 <= port_id <= self.config.port_count:
                            continue
                            
                        speed = self._parse_port_speed(port_data.get("speed", 0))
                        poe_active = port_data.get("poeStatus", 0) >= 2
                        
                        # Get existing VLAN info from cache
                        cache_entry = current_cache.get(port_id, {})
                        new_cache[port_id] = {
                            "speed": speed,
                            "poe_active": poe_active,
                            "vlan_id": cache_entry.get("vlan_id", 1),
                            "vlan_color": cache_entry.get("vlan_color", self._get_vlan_color(1, {}))
                        }
                    self._last_stats_update = current_time

            # Update VLANs if needed
            if need_vlan_update:
                port_info = self.api.get_port_info(0)  # Get VLAN info for all ports
                if port_info:
                    color_map = parse_vlan_color_map(self.config.get('vlan_color_map', ''))
                    for port_data in port_info:
                        port_id = port_data.get("portId", 0)
                        if not 1 <= port_id <= self.config.port_count:
                            continue
                            
                        vlans = port_data.get("vlans", [1])
                        vlan_id = vlans[0] if vlans else 1
                        
                        # Update or create cache entry
                        if port_id in new_cache:
                            new_cache[port_id]["vlan_id"] = vlan_id
                            new_cache[port_id]["vlan_color"] = self._get_vlan_color(vlan_id, color_map)
                        else:
                            # Get existing stats from cache
                            cache_entry = current_cache.get(port_id, {})
                            new_cache[port_id] = {
                                "speed": cache_entry.get("speed", 0),
                                "poe_active": cache_entry.get("poe_active", False),
                                "vlan_id": vlan_id,
                                "vlan_color": self._get_vlan_color(vlan_id, color_map)
                            }
                    self._last_port_update = current_time
                    self._force_update.clear()
                    self._force_update_ports.clear()

            # Update cache if we have new data
            if new_cache:
                self.port_cache.update(new_cache)

        except Exception as e:
            logger.error(f"Error updating port info: {e}")
            if isinstance(e, SwitchAPIError):
                self.cleanup_and_exit()

    def _update_port_cache(self, port_id: int, port_data: Dict[str, Any]):
        """Update cache for a single port"""
        try:
            current_cache = self.port_cache.get()
            
            # Parse port status
            speed = self._parse_port_speed(port_data.get("speed", 0))
            vlans = port_data.get("vlans", [1])
            vlan_id = vlans[0] if vlans else 1
            
            # Update cache entry
            current_cache[port_id] = {
                "speed": speed,
                "poe_active": port_data.get("poeStatus", 0) >= 2,
                "vlan_id": vlan_id,
                "vlan_color": self._get_vlan_color(vlan_id, {})
            }
            
            # Update cache atomically
            self.port_cache.update(current_cache)
        except Exception as e:
            logger.error(f"Error updating port cache for port {port_id}: {e}")
            raise

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
        # Start LED update thread
        self._led_thread = threading.Thread(
            target=self._led_update_loop,
            daemon=True
        )
        self._led_thread.start()
        
        while self.running:
            try:
                self.update_port_info()
            except Exception as e:
                logger.error(f"Error updating port info: {e}")
            
            # Sleep to prevent CPU hogging, but wake up for forced updates
            self._force_update.wait(timeout=0.1)

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
        return time.time() - self._start_time

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
        # Start hotspot first to set up networking
        hotspot_thread = threading.Thread(
            target=self.hotspot_service.run,
            daemon=True
        )
        hotspot_thread.start()
        self.threads.append(hotspot_thread)
        logger.info("Started hotspot service")

        # Wait for hotspot to be ready
        time.sleep(5)  # Give hotspot time to set up interfaces

        # Start web interface on 127.0.0.1:5000
        web_thread = threading.Thread(
            target=lambda: self.web_service.run(
                host='127.0.0.1',
                port=5000,
                debug=False
            ),
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

def main():
    """Main entry point"""
    manager = None
    try:
        manager = ServiceManager()
        manager.start_services()
    except KeyboardInterrupt:
        logger.info("Received shutdown signal")
        if manager:
            manager.cleanup()
    except Exception as e:
        logger.critical(f"Fatal error in main: {e}")
        if manager:
            manager.cleanup()
        sys.exit(1)

if __name__ == "__main__":
    main()