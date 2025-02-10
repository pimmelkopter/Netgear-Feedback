import time
from typing import List, Tuple, Dict, Optional
from rpi_ws281x import PixelStrip, Color, ws
import logging
from .config import Config
from .utils import ColorSystem

logger = logging.getLogger(__name__)

class LEDService:
    def __init__(self, config: Config):
        self.config = config
        logger.info("Initializing LED Service...")
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
        logger.info("Created PixelStrip object")
        self.strip.begin()
        logger.info("LED strip initialized")
        
        # Quick test
        self.strip.setPixelColor(0, Color(255,0,0))
        self.strip.show()
        time.sleep(0.1)
        self.strip.setPixelColor(0, Color(0,0,0))
        self.strip.show()

    def _set_pixel_color(self, index: int, color: tuple) -> None:
        try:
            if 0 <= index < self.config.led_count:
                self.strip.setPixelColor(index, Color(*color))
        except Exception as e:
            logger.error(f"Error setting pixel color at index {index}: {e}")

    def all_black(self) -> None:
        try:
            for i in range(self.config.led_count):
                self.strip.setPixelColor(i, Color(0,0,0))
            self.strip.show()
        except Exception as e:
            logger.error(f"Error turning LEDs off: {e}")

    def show_progress(self, progress: int) -> None:
        try:
            progress = max(0, min(progress, self.config.led_count))
            for i in range(self.config.led_count):
                color = Color(255,255,255) if i < progress else Color(0,0,0)
                self.strip.setPixelColor(i, color)
            self.strip.show()
        except Exception as e:
            logger.error(f"Error showing progress: {e}")

    def show_status(self, success: bool, duration: float = 2.0):
        try:
            color = Color(0,0,255) if success else Color(255,0,255)
            for i in range(self.config.led_count):
                self.strip.setPixelColor(i, color if i < self.config.port_count else Color(0,0,0))
            self.strip.show()
            time.sleep(duration)
        except Exception as e:
            logger.error(f"Error showing status: {e}")

    def update_port_leds(self, port_led_map: Dict[int, List[int]], 
                        port_info: Dict[int, Dict], 
                        blink_states: dict):
        try:
            # Reset all LEDs not used by ports to black
            logger.debug(f"Updating LEDs - ports: {len(port_led_map)}, info: {len(port_info)}")
            used_leds = set()
            for leds in port_led_map.values():
                used_leds.update(leds)
            
            for i in range(self.config.led_count):
                if i not in used_leds:
                    self.strip.setPixelColor(i, Color(0,0,0))

            # Update port LEDs
            for port_id, leds in port_led_map.items():
                info = port_info.get(port_id, {})
                if not info:
                    continue

                self._update_single_port_leds(
                    leds,
                    info.get("vlan_color", (0,0,255)),  # Default blue
                    info.get("speed", 0),
                    info.get("speed_color", (0,255,0)),  # Default green
                    info.get("poe_active", False),
                    blink_states['blink_on'],
                    blink_states['phase']
                )

            self.strip.show()
        except Exception as e:
            logger.error(f"Error updating port LEDs: {e}")

    def _update_single_port_leds(
        self, leds: List[int], 
        vlan_color: Tuple[int, int, int],
        speed: int,
        speed_color: Tuple[int, int, int],
        poe: bool,
        blink_on: bool,
        phase: int
    ):
        try:
            if not self.config.port_stats:
                for led_idx in leds:
                    self.strip.setPixelColor(led_idx, Color(*vlan_color))
                return

            if len(leds) >= 2:
                # Multi-LED mode
                for led_idx in leds[:-1]:
                    self.strip.setPixelColor(led_idx, Color(*vlan_color))
                
                if leds:
                    last_led = leds[-1]
                    if speed == 0:
                        self.strip.setPixelColor(last_led, Color(0,0,0))
                    elif poe:
                        if phase % 2 == 0:
                            self.strip.setPixelColor(last_led, Color(0,0,255))
                        else:
                            self.strip.setPixelColor(
                                last_led, 
                                Color(*speed_color) if blink_on else Color(0,0,0)
                            )
                    else:
                        self.strip.setPixelColor(
                            last_led,
                            Color(*speed_color) if blink_on else Color(0,0,0)
                        )
            elif len(leds) == 1:
                # Single LED mode
                first_led = leds[0]
                if speed == 0:
                    self.strip.setPixelColor(first_led, Color(*vlan_color))
                elif poe:
                    cycle_position = phase % 3
                    if cycle_position == 0:
                        self.strip.setPixelColor(first_led, Color(*vlan_color))
                    elif cycle_position == 1:
                        self.strip.setPixelColor(first_led, Color(0,0,255))
                    else:
                        self.strip.setPixelColor(
                            first_led,
                            Color(*speed_color) if blink_on else Color(0,0,0)
                        )
                else:
                    if phase % 2 == 0:
                        self.strip.setPixelColor(first_led, Color(*vlan_color))
                    else:
                        self.strip.setPixelColor(
                            first_led,
                            Color(*speed_color) if blink_on else Color(0,0,0)
                        )
        except Exception as e:
            logger.error(f"Error updating single port LEDs: {e}")

    def cleanup(self):
        try:
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
                time.sleep(0.2)

            # All off
            self.all_black()
            logger.info("LED cleanup completed")
        except Exception as e:
            logger.error(f"Error during LED cleanup: {e}")