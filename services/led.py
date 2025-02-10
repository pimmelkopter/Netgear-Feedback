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
        self._strip = None
        self._lock = threading.Lock()
        self._last_colors = []
        logger.info("Initializing LED Service...")
        try:
            self._initialize_strip()
            logger.info("LED Service initialized successfully")
        except Exception as e:
            logger.error(f"LED Service initialization failed: {e}")
            raise

    def _initialize_strip(self) -> None:
        """Initialize LED strip with config values and proper error handling"""
        try:
            logger.info(f"Initializing LED strip with {self.config.led_count} LEDs on pin {self.config.led_pin}")
            
            # Validate LED count
            if not isinstance(self.config.led_count, int) or self.config.led_count <= 0:
                raise ValueError(f"Invalid LED count: {self.config.led_count}")

            # Initialize strip
            self._strip = PixelStrip(
                self.config.led_count,
                self.config.led_pin,
                800000,
                10,
                False,
                self.config.led_brightness,
                0,
                ws.WS2812_STRIP
            )
            self._strip.begin()
            logger.info("Using rpi_ws281x library for LED control")
            
            # Initialize last colors array
            self._last_colors = [(0,0,0)] * self.config.led_count
            
            # Quick LED test - non-blocking
            self._quick_test()
            
        except Exception as e:
            logger.error(f"Failed to initialize LED strip: {e}")
            self._strip = None
            raise

    def _quick_test(self):
        """Run a quick LED test without blocking"""
        if not self._strip:
            return
            
        with self._lock:
            try:
                # Flash blue briefly
                for i in range(self.config.led_count):
                    self._set_pixel_color(i, (0,0,255))
                self._strip.show()
                time.sleep(0.1)  # Very short delay
                
                # Then turn off
                self.all_black()
                logger.info("LED test completed")
                
            except Exception as e:
                logger.error(f"Error during LED test: {e}")

    def _set_pixel_color(self, index: int, color: tuple) -> None:
        """Set LED color with bounds checking"""
        if self._strip is None:
            return

        try:
            if 0 <= index < self.config.led_count:
                if self._last_colors[index] != color:
                    self._strip.setPixelColor(index, Color(*color))
                    self._last_colors[index] = color
        except Exception as e:
            logger.error(f"Error setting pixel color at index {index}: {e}")

    def all_black(self) -> None:
        """Turn all LEDs off safely"""
        if self._strip is None:
            return

        with self._lock:
            try:
                black = (0,0,0)
                for i in range(self.config.led_count):
                    self._set_pixel_color(i, black)
                self._strip.show()
            except Exception as e:
                logger.error(f"Error turning LEDs off: {e}")

    def show_progress(self, progress: int) -> None:
        """Show progress bar in white LEDs with proper error handling"""
        if self._strip is None:
            logger.error("LED strip not initialized")
            return

        with self._lock:
            try:
                # Ensure progress is within bounds
                progress = max(0, min(progress, self.config.led_count))
                
                # Set colors
                white = (255,255,255)
                black = (0,0,0)
                
                # Update LEDs
                for i in range(self.config.led_count):
                    color = white if i < progress else black
                    if i < len(self._last_colors):  # Zusätzliche Überprüfung
                        self._set_pixel_color(i, color)
                
                # Show only if we have a valid strip
                if self._strip:
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
                
    def cleanup(self) -> None:
        """Safe cleanup sequence"""
        if self._strip is None:
            return

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
                self.all_black()
                logger.info("LED cleanup completed")
            except Exception as e:
                logger.error(f"Error during LED cleanup: {e}")