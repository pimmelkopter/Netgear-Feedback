##services/led.py##
import time
from typing import List, Tuple, Dict, Optional, Callable
from rpi_ws281x import PixelStrip, Color, ws
import logging
from .config import Config

logger = logging.getLogger(__name__)

class LEDService:
    def __init__(self, config: Config):
        self.config = config
        self.strip = self._initialize_strip()

    def _initialize_strip(self) -> PixelStrip:
        strip = PixelStrip(
            self.config.led_count,
            self.config.led_pin,
            800000,
            10,
            False,
            self.config.led_brightness,
            0,
            ws.WS2812_STRIP
        )
        strip.begin()
        return strip
    
    def all_black(self):
        for i in range(self.config.led_count):
            self.strip.setPixelColor(i, Color(0,0,0))
        self.strip.show()

    def show_progress(self, progress: int):
        """Show progress bar in white LEDs"""
        for i in range(self.config.led_count):
            self.strip.setPixelColor(i, Color(255,255,255) if i < progress else 0)
        self.strip.show()

    def show_status(self, success: bool, duration: float = 2.0):
        """Show success/failure status"""
        color = Color(0,0,255) if success else Color(255,0,255)
        for i in range(self.config.led_count):
            self.strip.setPixelColor(i, color if i < self.config.port_count else 0)
        self.strip.show()
        time.sleep(duration)

    def update_port_leds(self, port_led_map: Dict[int, List[int]], port_info: Dict[int, Dict],blink_on:bool,show_vlan:bool):
        """Update LEDs based on port status"""

        for port_id, leds in port_led_map.items():
            info = port_info.get(port_id, {})
            if not info:
                continue

            vlan_color = info.get("vlan_color", (0,0,255))
            speed = info.get("speed", 0)
            poe = info.get("poe_active", False)

            self._update_single_port_leds(
                leds, vlan_color, speed, poe, 
                blink_on, show_vlan
            )

        self.strip.show()

    def _update_single_port_leds(
        self, leds: List[int], vlan_color: Tuple[int, int, int], 
        speed: int, poe: bool, blink_on: bool, show_vlan: bool
    ):
        """Update LEDs for a single port"""
        if not self.config.port_stats:
            for led_idx in leds:
                if 0 <= led_idx < self.config.led_count:
                    self.strip.setPixelColor(led_idx, Color(*vlan_color))
            return

        if len(leds) >= 2:
            # Two LED mode
            if 0 <= leds[0] < self.config.led_count:
                self.strip.setPixelColor(leds[0], Color(*vlan_color))
            if 0 <= leds[1] < self.config.led_count:
                if speed == 0 and not poe:
                    self.strip.setPixelColor(leds[1], Color(*vlan_color))
                else:
                    self.strip.setPixelColor(
                        leds[1], 
                        self._get_status_color(speed, poe, blink_on)
                    )
        elif len(leds) == 1:
            # Single LED mode
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
                            self._get_status_color(speed, poe, blink_on)
                        )

    def _get_status_color(self, speed: int, poe_active: bool, blink_on: bool) -> int:
        """Get LED color based on port status"""
        if not blink_on:
            return Color(0,0,255) if poe_active else Color(0,0,0)
            
        if speed == 5:
            return Color(0,255,0)      # Gigabit
        elif speed == 4:
            return Color(255,165,0)    # 100MBit
        return Color(0,0,0)           # No link

    def cleanup(self):
        """Clean shutdown sequence"""
        # All red
        for i in range(self.config.led_count):
            self.strip.setPixelColor(i, Color(255,0,0))
        self.strip.show()
        time.sleep(1)
        
        # Count up in white
        for i in range(10):
            if i < self.config.led_count:
                self.strip.setPixelColor(i, Color(255,255,255))
            self.strip.show()
            time.sleep(1)
            
        # All off
        for i in range(self.config.led_count):
            self.strip.setPixelColor(i, Color(0,0,0))
        self.strip.show()