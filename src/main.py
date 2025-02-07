import time
import sys
import urllib3
import logging
from typing import Dict, Any
from services.config import Config
from services.switch_api import SwitchAPI, SwitchAPIError
from services.led import LEDService
from services.utils import (
    parse_port_led_mapping,
    parse_vlan_color_map,
    parse_vlan_color_for_port,
    update_vlan_colors_from_map_and_random,
    calculate_blink_states
)

# Logging setup
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Disable SSL warnings
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

class SwitchMonitor:
    def __init__(self):
        """Initialize monitor with configuration and services"""
        self.config = Config()
        self.led_service = LEDService(self.config)
        self.api = None
        self.port_info_cache: Dict[int, Dict[str, Any]] = {}
        self.running = True

    def scan_network(self) -> bool:
        """Scan network for switch with visual progress"""
        logger.info("Starting network scan...")
        total = self.config.scan_range_end - self.config.scan_range_start + 1
        
        def update_progress(progress: int):
            led_progress = int((progress / total) * self.config.led_count)
            self.led_service.show_progress(led_progress)
            
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
                update_vlan_colors_from_map_and_random(self.config, list(vlan_info.keys()))
                self.config.scan_vlans = False  # Disable future scans
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
            
            for port_data in stats:
                port_id = port_data.get("portId", 0)
                if not 1 <= port_id <= self.config.port_count:
                    continue
                    
                # Parse port status
                speed = self._parse_port_speed(port_data.get("speed", 0))
                vlan_id = port_data.get("portVlanId", 1)
                
                # Update cache with status and color
                self.port_info_cache[port_id] = {
                    "speed": speed,
                    "poe_active": port_data.get("poeStatus", 0) >= 2,
                    "vlan_id": vlan_id,
                    "vlan_color": self._get_vlan_color(vlan_id, color_map)
                }
                
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
        return parse_vlan_color_for_port(
            [vlan_id],
            self.config,
            (0,0,255),  # Default blue
            color_map
        )

    def main_loop(self):
        """Main monitoring loop"""
        port_led_map = parse_port_led_mapping(self.config)
        last_update = 0
        
        while self.running:
            current_time = time.time()
            
            # Update port info at configured interval
            if current_time - last_update >= self.config.update_interval:
                self.update_port_info()
                last_update = current_time
            
            # Calculate blink states
            blink_states = calculate_blink_states()
            
            # Update LEDs
            self.led_service.update_port_leds(port_led_map, self.port_info_cache, blink_states['blink_on'], blink_states["show_vlan"])
            
            # Small sleep to prevent CPU hogging
            time.sleep(0.1)

    def cleanup_and_exit(self):
        """Clean shutdown sequence"""
        logger.error("Critical error => shutting down")
        self.running = False
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

            # Initialize port info cache
            self.port_info_cache = {
                pid: {
                    "speed": 0,
                    "poe_active": False,
                    "vlan_id": 1,
                    "vlan_color": (0,0,255)
                }
                for pid in range(1, self.config.port_count + 1)
            }

            # Start main monitoring loop
            self.main_loop()

        except KeyboardInterrupt:
            logger.info("KeyboardInterrupt => Exiting")
            self.cleanup_and_exit()
        except Exception as e:
            logger.error(f"Fatal error in main loop: {e}")
            self.cleanup_and_exit()

def main():
    monitor = SwitchMonitor()
    monitor.run()

if __name__ == "__main__":
    main()