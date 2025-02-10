##src/main.py##
import time
import sys
import urllib3
import logging
import threading
from typing import Dict, Any, Optional
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
    VLANColorManager,
    ColorSystem,
    PortMappingGenerator
)

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Disable SSL warnings
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

class SwitchMonitor:
    """Main switch monitoring service"""
    def __init__(self):
        self.config = Config()
        self.led_service = LEDService(self.config)
        self.api: Optional[SwitchAPI] = None
        self.port_info_cache: Dict[int, Dict[str, Any]] = {}
        self._running = True
        self._should_stop = False
        self._start_time = time.monotonic()
        self._status_lock = threading.Lock()
        self._cache_lock = threading.Lock()

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
        try:
            if not self.api:
                self.api = SwitchAPI()
                self.api.base_url = f"https://{self.config.switch_ip}{self.config.base_url_suffix}"

            if not self.api.login():
                logger.error("Login failed")
                return False

            return True
        except Exception as e:
            logger.error(f"API setup failed: {e}")
            return False

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
        """Update port information cache thread-safely"""
        try:
            stats = self.api.get_port_info(0)  # Uses API caching automatically
            if not stats:
                raise SwitchAPIError("Failed to get port stats")

            new_cache = {}
            color_map = parse_vlan_color_map(self.config.get('vlan_color_map', ''))

            for port_data in stats:
                port_id = port_data.get("portId", 0)
                if not 1 <= port_id <= self.config.port_count:
                    continue
                    
                # Parse port status
                speed = self._parse_port_speed(port_data.get("speed", 0))
                vlan_id = port_data.get("portVlanId", 1)

                # Use ColorSystem for speed colors
                speed_color = ColorSystem.get_speed_color(speed)

                new_cache[port_id] = {
                    "speed": speed,
                    "speed_color": speed_color,
                    "poe_active": port_data.get("poeStatus", 0) >= 2,
                    "vlan_id": vlan_id,
                    "vlan_color": self._get_vlan_color(vlan_id, color_map)
                }

            with self._cache_lock:
                self.port_info_cache = new_cache

        except Exception as e:
            logger.error(f"Error updating port info: {e}")
            if isinstance(e, SwitchAPIError):
                self.stop()

    def _parse_port_speed(self, raw_speed: int) -> int:
        """Convert raw speed value to normalized speed level"""
        if raw_speed == 7:
            return 5  # Gigabit
        if raw_speed in (3,4,6):
            return 4  # 100Mbit
        return 0  # No link

    def _get_vlan_color(self, vlan_id: int, color_map: Dict[int, tuple]) -> tuple:
        """Get color for VLAN ID using ColorSystem"""
        color_manager = VLANColorManager()
        return color_manager.get_vlan_color(vlan_id)

    def main_loop(self):
        """Main monitoring loop with adaptive timing"""
        generator = PortMappingGenerator(self.config)
        port_led_map = generator.generate_mapping()
        
        last_update = time.monotonic()
        last_led_update = time.monotonic()
        LED_UPDATE_INTERVAL = 0.1

        while self._running and not self._should_stop:
            current_time = time.monotonic()
            
            # Calculate timing
            time_since_update = current_time - last_update
            time_since_led = current_time - last_led_update
            
            # Adaptive sleep based on next required action
            next_update = min(
                self.config.update_interval - time_since_update,
                LED_UPDATE_INTERVAL - time_since_led
            )
            sleep_time = max(0.01, next_update)
            time.sleep(sleep_time)
            
            try:
                # Update port info at configured interval
                if time_since_update >= self.config.update_interval:
                    self.update_port_info()
                    last_update = current_time

                # Update LEDs at fixed interval
                if time_since_led >= LED_UPDATE_INTERVAL:
                    blink_states = calculate_blink_states()
                    with self._cache_lock:
                        self.led_service.update_port_leds(
                            port_led_map,
                            self.port_info_cache.copy(),
                            blink_states
                        )
                    last_led_update = current_time

            except Exception as e:
                logger.error(f"Error in main loop: {e}")
                if isinstance(e, SwitchAPIError):
                    self.stop()
                    break

    def is_connected(self) -> bool:
        """Check if switch is connected"""
        with self._status_lock:
            if not self.api:
                return False
            try:
                self.api.get_port_info(1)
                return True
            except Exception:
                return False

    def get_uptime(self) -> float:
        """Get uptime in seconds"""
        return time.monotonic() - self._start_time

    def stop(self):
        """Stop the service gracefully"""
        logger.info("Stopping switch monitor...")
        self._should_stop = True

    def cleanup(self):
        """Clean shutdown sequence"""
        logger.info("Cleaning up...")
        self._running = False
        self.led_service.cleanup()

    def run(self):
        """Main run sequence with error handling"""
        try:
            self.led_service.show_progress(1)

            # Scan for switch if enabled
            if self.config.ip_scan and not self.scan_network():
                self.cleanup()
                return

            # Setup API connection
            if not self.setup_api():
                self.cleanup()
                return

            # Detect ports if enabled
            if self.config.get('auto_detect_ports', True):
                if not self.detect_ports():
                    self.cleanup()
                    return

            # Scan VLANs if enabled and all black before port-status
            self.scan_vlans()
            self.led_service.all_black()

            # Initialize port info cache with default values
            with self._cache_lock:
                self.port_info_cache = {
                    pid: {
                        "speed": 0,
                        "speed_color": ColorSystem.SPEED_COLORS[0],
                        "poe_active": False,
                        "vlan_id": 1,
                        "vlan_color": ColorSystem.VLAN_DEFAULTS[1]
                    }
                    for pid in range(1, self.config.port_count + 1)
                }

            # Start main monitoring loop
            self.main_loop()

        except KeyboardInterrupt:
            logger.info("Received shutdown signal")
            self.cleanup()
        except Exception as e:
            logger.error(f"Fatal error in main loop: {e}")
            self.cleanup()
            sys.exit(1)

class ServiceManager:
    """Manages all application services"""
    def __init__(self):
        self.config = Config()
        self.hotspot_service = HotspotService()
        self.switch_monitor = SwitchMonitor()
        self.web_service = WebService(self.switch_monitor, self.hotspot_service)
        self.threads = []
        self._stop_event = threading.Event()

    def start_services(self):
        """Start all services with proper error handling"""
        try:
            # Start hotspot
            hotspot_thread = threading.Thread(
                target=self.hotspot_service.run,
                daemon=True,
                name="HotspotService"
            )
            hotspot_thread.start()
            self.threads.append(hotspot_thread)
            logger.info("Started hotspot service")

            # Start web interface
            web_thread = threading.Thread(
                target=lambda: self.web_service.run(host='0.0.0.0', port=5000),
                daemon=True,
                name="WebService"
            )
            web_thread.start()
            self.threads.append(web_thread)
            logger.info("Started web interface")

            # Start switch monitor (main thread)
            self.switch_monitor.run()

        except Exception as e:
            logger.error(f"Error starting services: {e}")
            self.cleanup()
            raise

    def cleanup(self):
        """Clean shutdown of all services"""
        logger.info("Cleaning up services...")
        self._stop_event.set()
        self.hotspot_service.cleanup()
        self.switch_monitor.cleanup()

def main():
    """Main entry point with error handling"""
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