##services/led.py##
import time
from typing import List, Tuple, Dict, Optional
from rpi_ws281x import PixelStrip, Color, ws
import logging
import threading
from .utils import ColorSystem

logger = logging.getLogger(__name__)

class LEDService:
    """Thread-safe LED control service"""
    def __init__(self, config):
        self.config = config
        self._strip = self._initialize_strip()
        self._lock = threading.Lock()
        self._last_colors = []  # Cache last colors to prevent unnecessary updates

    def _initialize_strip(self) -> PixelStrip:
        """Initialize LED strip with config values"""
        try:
            strip = PixelStrip(
                self.config.led_count,
                self.config.led_pin,
                800000,  # Standard frequency
                10,     # DMA channel
                False,  # Invert signal
                self.config.led_brightness,
                0,      # Channel
                ws.WS2812_STRIP
            )
            strip.begin()
            self._last_colors = [(0,0,0)] * self.config.led_count
            return strip
        except Exception as e:
            logger.error(f"Failed to initialize LED strip: {e}")
            raise

    def _set_pixel_color(self, index: int, color: Tuple[int, int, int]):
        """Set LED color with change detection"""
        if 0 <= index < self.config.led_count:
            if self._last_colors[index] != color:
                self._strip.setPixelColor(index, Color(*color))
                self._last_colors[index] = color

    def all_black(self):
        """Turn all LEDs off"""
        with self._lock:
            try:
                black = (0,0,0)
                for i in range(self.config.led_count):
                    self._set_pixel_color(i, black)
                self._strip.show()
            except Exception as e:
                logger.error(f"Error turning LEDs off: {e}")

    def show_progress(self, progress: int):
        """Show progress bar in white LEDs with bounds checking"""
        with self._lock:
            try:
                # Ensure progress is within valid bounds
                progress = max(0, min(progress, self.config.led_count))
                
                white = (255, 255, 255)
                black = (0, 0, 0)
                
                for i in range(self.config.led_count):
                    self._set_pixel_color(i, white if i < progress else black)
                
                self._strip.show()
            except Exception as e:
                logger.error(f"Error showing progress: {e}")
                # Log additional debug information
                logger.debug(f"Progress: {progress}, LED count: {self.config.led_count}")

    def show_status(self, success: bool, duration: float = 2.0):
        """Show success/failure status"""
        with self._lock:
            try:
                color = ColorSystem.VLAN_DEFAULTS[1] if success else (255,0,255)
                black = (0,0,0)
                for i in range(self.config.led_count):
                    self._set_pixel_color(i, color if i < self.config.port_count else black)
                self._strip.show()
                time.sleep(duration)
            except Exception as e:
                logger.error(f"Error showing status: {e}")

    def update_port_leds(self, port_led_map: Dict[int, List[int]], 
                        port_info: Dict[int, Dict], 
                        blink_states: dict):
        """Update LEDs based on port status"""
        with self._lock:
            try:
                # Reset all LEDs not used by ports to black
                used_leds = set()
                for leds in port_led_map.values():
                    used_leds.update(leds)
                
                for i in range(self.config.led_count):
                    if i not in used_leds:
                        self._set_pixel_color(i, (0,0,0))

                # Update port LEDs
                for port_id, leds in port_led_map.items():
                    info = port_info.get(port_id, {})
                    if not info:
                        continue

                    self._update_single_port_leds(
                        leds,
                        info.get("vlan_color", ColorSystem.VLAN_DEFAULTS[1]),
                        info.get("speed", 0),
                        info.get("speed_color", ColorSystem.SPEED_COLORS[0]),
                        info.get("poe_active", False),
                        blink_states['blink_on'],
                        blink_states['phase']
                    )

                self._strip.show()
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
        """Update LEDs for a single port"""
        if not self.config.port_stats:
            self._set_simple_vlan_color(leds, vlan_color)
            return

        configured_leds_per_port = self.config.get('leds_per_port', 1)

        if configured_leds_per_port >= 2:
            self._update_multi_led_mode(
                leds, vlan_color, speed, speed_color, poe, blink_on, phase
            )
        else:
            self._update_single_led_mode(
                leds, vlan_color, speed, speed_color, poe, blink_on, phase
            )

    def _set_simple_vlan_color(self, leds: List[int], vlan_color: Tuple[int, int, int]):
        """Set basic VLAN color for port LEDs"""
        for led_idx in leds:
            self._set_pixel_color(led_idx, vlan_color)

    def _update_multi_led_mode(
        self, leds: List[int],
        vlan_color: Tuple[int, int, int],
        speed: int,
        speed_color: Tuple[int, int, int],
        poe: bool,
        blink_on: bool,
        phase: int
    ):
        """Update port in multi-LED mode"""
        # VLAN color on all LEDs except last
        for led_idx in leds[:-1]:
            self._set_pixel_color(led_idx, vlan_color)

        # Last LED: POE/Speed indication
        if leds:
            last_led = leds[-1]
            if speed == 0:
                self._set_pixel_color(last_led, (0,0,0))
            elif poe:
                if phase % 2 == 0:
                    self._set_pixel_color(last_led, (0,0,255))  # POE indicator
                else:
                    self._set_pixel_color(
                        last_led, 
                        speed_color if blink_on else (0,0,0)
                    )
            else:
                self._set_pixel_color(
                    last_led,
                    speed_color if blink_on else (0,0,0)
                )

    def _update_single_led_mode(
        self, leds: List[int],
        vlan_color: Tuple[int, int, int],
        speed: int,
        speed_color: Tuple[int, int, int],
        poe: bool,
        blink_on: bool,
        phase: int
    ):
        """Update port in single-LED mode"""
        if not leds:
            return

        first_led = leds[0]
        if speed == 0:
            self._set_pixel_color(first_led, vlan_color)
        elif poe:
            cycle_position = phase % 3
            if cycle_position == 0:
                self._set_pixel_color(first_led, vlan_color)
            elif cycle_position == 1:
                self._set_pixel_color(first_led, (0,0,255))  # POE indicator
            else:
                self._set_pixel_color(
                    first_led,
                    speed_color if blink_on else (0,0,0)
                )
        else:
            if phase % 2 == 0:
                self._set_pixel_color(first_led, vlan_color)
            else:
                self._set_pixel_color(
                    first_led,
                    speed_color if blink_on else (0,0,0)
                )

    def cleanup(self):
        """Clean shutdown sequence"""
        with self._lock:
            try:
                # All red
                red = (255,0,0)
                for i in range(self.config.led_count):
                    self._set_pixel_color(i, red)
                self._strip.show()
                time.sleep(1)

                # Count up in white
                white = (255,255,255)
                for i in range(10):
                    if i < self.config.led_count:
                        self._set_pixel_color(i, white)
                    self._strip.show()
                    time.sleep(0.2)

                # All off
                black = (0,0,0)
                for i in range(self.config.led_count):
                    self._set_pixel_color(i, black)
                self._strip.show()
            except Exception as e:
                logger.error(f"Error during LED cleanup: {e}")