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

    def update_port_leds(self, port_led_map: Dict[int, List[int]], 
                        port_info: Dict[int, Dict], blink_states: dict):
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
                blink_states['blink_on'], blink_states['phase']
            )

        self.strip.show()

    def _update_single_port_leds(
        self, leds: List[int], vlan_color: Tuple[int, int, int], 
        speed: int, poe: bool, blink_on: bool, phase: int
    ):
        """Update LEDs for a single port"""
        if not self.config.port_stats:
            # Wenn keine Port-Stats, zeige nur VLAN-Farbe
            for led_idx in leds:
                if 0 <= led_idx < self.config.led_count:
                    self.strip.setPixelColor(led_idx, Color(*vlan_color))
            return

        if len(leds) >= 2:
            # Mehrere LEDs: Alle außer letzte zeigen VLAN
            for led_idx in leds[:-1]:
                if 0 <= led_idx < self.config.led_count:
                    self.strip.setPixelColor(led_idx, Color(*vlan_color))
            
            # Letzte LED: POE/Speed Indikation
            if 0 <= leds[-1] < self.config.led_count:
                if speed == 0:  # Kein Link
                    self.strip.setPixelColor(leds[-1], Color(0,0,0))
                else:
                    if poe:  # POE aktiv: zwischen POE und Speed wechseln
                        if blink_on:
                            self.strip.setPixelColor(leds[-1], self._get_speed_color(speed))
                        else:
                            self.strip.setPixelColor(leds[-1], Color(0,0,255))  # POE Blau
                    else:  # Kein POE: nur Speed
                        if blink_on:
                            self.strip.setPixelColor(leds[-1], self._get_speed_color(speed))
                        else:
                            self.strip.setPixelColor(leds[-1], Color(0,0,0))

        elif len(leds) == 1:
            # Single LED Mode
            led_idx = leds[0]
            if 0 <= led_idx < self.config.led_count:
                if speed == 0:  # Kein Link
                    self.strip.setPixelColor(led_idx, Color(*vlan_color))
                else:
                    if poe:  # POE aktiv: 3-Phasen Zyklus
                        if phase == 0:
                            self.strip.setPixelColor(led_idx, Color(*vlan_color))
                        elif phase == 1:
                            self.strip.setPixelColor(led_idx, Color(0,0,255))  # POE Blau
                        else:
                            if blink_on:
                                self.strip.setPixelColor(led_idx, self._get_speed_color(speed))
                            else:
                                self.strip.setPixelColor(led_idx, Color(0,0,0))

                    else:  # Kein POE: VLAN/VLAN/Speed
                        if phase < 2:
                            self.strip.setPixelColor(led_idx, Color(*vlan_color))
                        else:
                            if blink_on:
                                self.strip.setPixelColor(led_idx, self._get_speed_color(speed))
                            else:
                                self.strip.setPixelColor(led_idx, Color(0,0,0))

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