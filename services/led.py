##services/led.py##
import time
from typing import List, Tuple, Dict, Optional, Callable
from rpi_ws281x import PixelStrip, Color, ws
import logging
from .config import Config
from .utils import VLANColorManager

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

    def update_port_leds(self, port_led_map: Dict[int, List[int]], 
                        port_info: Dict[int, Dict], blink_states: dict):
        """Update LEDs based on port status"""
        for port_id, leds in port_led_map.items():
            info = port_info.get(port_id, {})
            if not info:
                # If no info, use default VLAN 1
                info = {
                    "vlan_id": 1,
                    "speed": 0,
                    "poe_active": False,
                    "vlan_color": (0, 0, 0)  # Default to black for unmapped ports
                }

            # Get the correct color based on VLAN
            color_manager = VLANColorManager()
            vlan_color = color_manager.get_vlan_color(info.get("vlan_id", 1))
            
            # Use the resolved color and other port info
            self._update_single_port_leds(
                leds, 
                vlan_color,
                info.get("speed", 0),
                info.get("poe_active", False),
                blink_states['blink_on'],
                blink_states['phase']
            )

        self.strip.show()

    def _update_single_port_leds(
        self, leds: List[int], vlan_color: Tuple[int, int, int], 
        speed: int, poe: bool, blink_on: bool, phase: int
    ):
        """Update LEDs for a single port based on configured leds_per_port"""
        if not self.config.port_stats:
            # If no port stats, show only VLAN color
            for led_idx in leds:
                if 0 <= led_idx < self.config.led_count:
                    self.strip.setPixelColor(led_idx, Color(*vlan_color))
            return

        # Check configured mode instead of actual LED list length
        configured_leds_per_port = self.config.get('leds_per_port', 1)
        
        if configured_leds_per_port >= 2:
            # Multi-LED Mode
            
            # All LEDs except last show VLAN color
            for led_idx in leds[:-1]:
                if 0 <= led_idx < self.config.led_count:
                    self.strip.setPixelColor(led_idx, Color(*vlan_color))
            
            # Last LED: POE/Speed indication
            if leds and 0 <= leds[-1] < self.config.led_count:
                last_led = leds[-1]
                if speed == 0:
                    # No link - LED stays black
                    self.strip.setPixelColor(last_led, Color(0,0,0))
                elif poe:
                    # POE active: alternate between POE and Speed
                    if phase % 2 == 0:
                        self.strip.setPixelColor(last_led, Color(0,0,255))  # POE Blue
                    else:
                        # Speed blink sub-phase
                        self.strip.setPixelColor(last_led, 
                            self._get_speed_color(speed) if blink_on else Color(0,0,0))
                else:
                    # Just speed blinking, no alternation
                    self.strip.setPixelColor(last_led, 
                        self._get_speed_color(speed) if blink_on else Color(0,0,0))

        else:
            # Single LED Mode
            if leds and 0 <= leds[0] < self.config.led_count:
                first_led = leds[0]
                
                if speed == 0:
                    # No connection - show VLAN color
                    self.strip.setPixelColor(first_led, Color(*vlan_color))
                elif poe:
                    # POE active - 3-way cycle
                    cycle_position = phase % 3
                    if cycle_position == 0:
                        self.strip.setPixelColor(first_led, Color(*vlan_color))
                    elif cycle_position == 1:
                        self.strip.setPixelColor(first_led, Color(0,0,255))  # POE
                    else:
                        self.strip.setPixelColor(first_led, 
                            self._get_speed_color(speed) if blink_on else Color(0,0,0))
                else:
                    # Just connection - alternate VLAN and speed
                    if phase % 2 == 0:
                        self.strip.setPixelColor(first_led, Color(*vlan_color))
                    else:
                        self.strip.setPixelColor(first_led, 
                            self._get_speed_color(speed) if blink_on else Color(0,0,0))

    def _get_speed_color(self, speed: int) -> int:
        """Get LED color based on port speed"""
        if speed == 5:
            return Color(0,255,0)      # Gigabit: Green
        elif speed == 4:
            return Color(255,165,0)    # 100MBit: Orange
        return Color(0,0,0)           # No Link: Black

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