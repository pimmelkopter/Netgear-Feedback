import time
import sys
import urllib3
import threading
from queue import Queue
from typing import Dict, Any
from rpi_ws281x import PixelStrip, Color, ws
import logging
from services.utils import (
    parse_port_led_mapping,
    parse_vlan_color_map,
    parse_vlan_color_for_port
)
from services.config import Config
from services.switch_api import SwitchAPI, SwitchAPIError

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

class SwitchMonitor:
    def __init__(self):
        self.config = Config()
        self.strip = None
        self.initialize_led_strip()
        self.stop_event = threading.Event()
        self.port_info_cache: Dict[int, Dict[str, Any]] = {}
        self.update_queue = Queue()
        self.api = None

    def initialize_led_strip(self):
        self.strip = PixelStrip(
            self.config.led_count,
            self.config.led_pin,
            800000,
            10,
            False,
            self.config.led_brightness,
            0,
            ws.WS2812_STRIP
        )
        self.strip.begin()

    def _update_progress_leds(self, progress: int):
        for i in range(self.config.led_count):
            self.strip.setPixelColor(i, Color(255,255,255) if i < progress else 0)
        self.strip.show()

    def _show_port_detection_status(self, success: bool):
        color = Color(0,0,255) if success else Color(255,0,255)
        for i in range(self.config.led_count):
            self.strip.setPixelColor(i, color if i < self.config.port_count else 0)
        self.strip.show()
        time.sleep(2)

    def detect_ports(self) -> bool:
        try:
            port_info = self.api.get_port_info(1)
            if not port_info:
                return False
                
            self._show_port_detection_status(True)
            return True
            
        except Exception as e:
            logger.error(f"Port detection failed: {e}")
            self._show_port_detection_status(False)
            return False

    def update_port_info(self):
        while not self.stop_event.is_set():
            try:
                stats = self.api.get_port_info(0)  # 0 = all ports
                if not stats:
                    raise SwitchAPIError("Failed to get port stats")
                    
                for port_data in stats:
                    port_id = port_data.get("portId", 0)
                    if not 1 <= port_id <= self.config.port_count:
                        continue
                        
                    speed = self._parse_port_speed(port_data.get("speed", 0))
                    self.port_info_cache[port_id] = {
                        "speed": speed,
                        "poe_active": port_data.get("poeStatus", 0) >= 2,
                        "vlan_id": port_data.get("portVlanId", 1)
                    }
                    
            except Exception as e:
                logger.error(f"Error updating port info: {e}")
                if isinstance(e, SwitchAPIError):
                    self.cleanup_and_exit()
                    return
                    
            time.sleep(self.config.update_interval)

    def _parse_port_speed(self, raw_speed: int) -> int:
        if raw_speed == 7:
            return 5  # Gigabit
        if raw_speed in (3,4,6):
            return 4  # 100Mbit
        return 0  # No link

    def update_leds(self):
        blink_cycle = 0
        color_map = parse_vlan_color_map(self.config.get('vlan_color_map', ''))
        
        while not self.stop_event.is_set():
            try:
                blink_cycle = (blink_cycle + 1) % 20
                blink_on = (blink_cycle % 2) == 0
                
                self._process_led_updates(blink_on, color_map)
                self.strip.show()
                
            except Exception as e:
                logger.error(f"LED update error: {e}")
                
            time.sleep(0.1)

    def _process_led_updates(self, blink_on: bool, color_map: Dict[int, tuple]):
        port_led_map = parse_port_led_mapping(self.config)
        for port_id in range(1, self.config.port_count + 1):
            leds = port_led_map.get(port_id, [])
            info = self.port_info_cache.get(port_id, {})
            
            vlan_id = info.get("vlan_id", 1)
            vlan_color = parse_vlan_color_for_port(
                [vlan_id], 
                self.config,
                (0,0,255),
                color_map
            )
            
            speed = info.get("speed", 0)
            poe = info.get("poe_active", False)
            
            self._update_port_leds(
                leds, vlan_color, speed, poe, 
                blink_on, blink_cycle % 16 < 10
            )

    def _update_port_leds(
        self, leds: list, vlan_color: tuple, 
        speed: int, poe: bool, blink_on: bool, 
        show_vlan: bool
    ):
        if not self.config.port_stats:
            for led_idx in leds:
                if 0 <= led_idx < self.config.led_count:
                    self.strip.setPixelColor(led_idx, Color(*vlan_color))
            return
            
        if len(leds) >= 2:
            if 0 <= leds[0] < self.config.led_count:
                self.strip.setPixelColor(leds[0], Color(*vlan_color))
            if 0 <= leds[1] < self.config.led_count:
                if speed == 0 and not poe:
                    self.strip.setPixelColor(leds[1], Color(*vlan_color))
                else:
                    self.strip.setPixelColor(
                        leds[1], 
                        self._get_port_status_color(speed, poe, blink_on)
                    )
        elif len(leds) == 1:
            led_idx = leds[0]
            if 0 <= led_idx < self.config.led_count:
                if show_vlan:
                    self.strip.setPixelColor(led_idx, Color(*vlan_color))
                else:
                    if speed == 0 and not poe:
                        self.strip.setPixelColor(led_idx, Color(*vlan_color))
                    else:
                        self.strip.setPixelColor(
                            led_idx,
                            self._get_port_status_color(speed, poe, blink_on)
                        )

    def _get_port_status_color(self, speed: int, poe_active: bool, blink_on: bool) -> int:
        if not blink_on:
            return Color(0,0,255) if poe_active else Color(0,0,0)
            
        if speed == 5:
            return Color(0,255,0)      # Gigabit
        elif speed == 4:
            return Color(255,165,0)    # 100MBit
        return Color(0,0,0)           # No link

    def cleanup_and_exit(self):
        logger.error("Critical error => shutting down")
        self.stop_event.set()
        
        for i in range(self.config.led_count):
            self.strip.setPixelColor(i, Color(255,0,0))
        self.strip.show()
        time.sleep(1)
        
        for i in range(10):
            if i < self.config.led_count:
                self.strip.setPixelColor(i, Color(255,255,255))
            self.strip.show()
            time.sleep(1)
            
        for i in range(self.config.led_count):
            self.strip.setPixelColor(i, Color(0,0,0))
        self.strip.show()
        
        logger.info("Exiting now")
        sys.exit(1)

    def run(self):
        try:
            self.strip.setPixelColor(0, Color(255,255,255))
            self.strip.show()
            
            self.api = SwitchAPI()
            if not self.api.login():
                self.cleanup_and_exit()
                return
                
            if self.config.get('auto_detect_ports', True):
                if not self.detect_ports():
                    self.cleanup_and_exit()
                    return
                    
            if self.config.scan_vlans:
                self.api.scan_switch_vlans()
                
            self.port_info_cache = {
                pid: {
                    "speed": 0,
                    "poe_active": False,
                    "vlan_id": 1
                }
                for pid in range(1, self.config.port_count + 1)
            }
            
            for i in range(self.config.led_count):
                self.strip.setPixelColor(i, Color(0,0,0))
            self.strip.show()
            
            workers = [
                threading.Thread(target=self.update_port_info, daemon=True),
                threading.Thread(target=self.update_leds, daemon=True)
            ]
            for worker in workers:
                worker.start()
                
            while not self.stop_event.is_set():
                time.sleep(1)
                
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