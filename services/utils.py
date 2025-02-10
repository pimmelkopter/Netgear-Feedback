##services/utils.py##
from typing import Dict, List, Tuple, Optional
import logging
import time
import random
import threading
from .config import Config

logger = logging.getLogger(__name__)

# Type Aliases
RGB = Tuple[int, int, int]
PortMapping = Dict[int, List[int]]

class ColorSystem:
    """Central color management system"""
    # Speed color mapping
    SPEED_COLORS = {
        0: (0, 0, 0),       # No link
        4: (255, 165, 0),   # 100Mbps
        5: (0, 255, 0)      # 1Gbps
    }
    
    # Standard VLAN colors # TODO - gefallen mir nicht
    VLAN_DEFAULTS = {
        1: (0, 0, 255),     # Default VLAN
        10: (0, 119, 0),    # Data VLAN
        20: (255, 0, 0),    # Voice VLAN
        30: (255, 0, 255),  # Guest VLAN
        40: (170, 85, 0),   # Management VLAN
        99: (255, 255, 255) # Native VLAN
    }
    
    @classmethod
    def get_speed_color(cls, speed: int) -> RGB:
        """Get standardized color for port speed"""
        return cls.SPEED_COLORS.get(speed, (0, 0, 0))
    
    @classmethod
    def get_default_vlan_color(cls, vlan_id: int) -> RGB:
        """Get default color for VLAN ID"""
        if vlan_id in cls.VLAN_DEFAULTS:
            return cls.VLAN_DEFAULTS[vlan_id]
        # Generate deterministic color for unknown VLANs
        random.seed(vlan_id)
        return (
            random.randint(50, 255),
            random.randint(50, 255),
            random.randint(50, 255)
        )

class VLANColorManager:
    """Thread-safe singleton for managing VLAN colors"""
    _instance = None
    _lock = threading.Lock()

    def __new__(cls):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        with self._lock:
            if not self._initialized:
                self.config = Config()
                self.color_cache: Dict[int, RGB] = {}
                self.refresh_cache()
                self._initialized = True

    def refresh_cache(self):
        """Rebuild color mapping cache thread-safely"""
        with self._lock:
            self.color_cache.clear()

            if self.config.scan_vlans:
                # Use vlan_color_map and generate random colors when scanning
                color_map = parse_vlan_color_map(self.config.get('vlan_color_map', ''))
                self.color_cache = color_map
            else:
                config_dict = self.config.get_config()
                
                # Parse vlanX_NAME_color entries
                for key, value in config_dict.items():
                    if key.startswith('vlan') and '_color' in key:
                        try:
                            vlan_id = int(key.replace('vlan', '').split('_')[0])
                            self.color_cache[vlan_id] = parse_rgb_string(value)
                        except (ValueError, IndexError) as e:
                            logger.error(f"Invalid VLAN color entry {key}: {e}")
                            continue

                # Fill missing entries from vlan_color_map
                color_map = parse_vlan_color_map(config_dict.get('vlan_color_map', ''))
                for vlan_id, color in color_map.items():
                    if vlan_id not in self.color_cache:
                        self.color_cache[vlan_id] = color

    def get_vlan_color(self, vlan_id: int) -> RGB:
        """Get color for VLAN ID using cached values"""
        with self._lock:
            if vlan_id in self.color_cache:
                return self.color_cache[vlan_id]

            # Get default color from ColorSystem
            default_color = ColorSystem.get_default_vlan_color(vlan_id)
            self.color_cache[vlan_id] = default_color
            return default_color

class PortMappingGenerator:
    """Generates and manages port-to-LED mappings"""
    def __init__(self, config: Config):
        self.config = config

    def generate_mapping(self) -> PortMapping:
        """Generate port to LED mapping based on configuration"""
        mode = self.config.get('port_mapping_mode', 'linear')
        
        if mode == 'manual':
            return self._parse_manual_mapping()
        
        return self._generate_automatic_mapping(mode)

    def _parse_manual_mapping(self) -> PortMapping:
        """Parse manual mapping string"""
        mapping_str = self.config.get('port_led_mapping', '')
        result: PortMapping = {}
        
        if not mapping_str:
            return result

        for mapping in mapping_str.split(';'):
            mapping = mapping.strip()
            if ':' not in mapping:
                continue
            try:
                port_part, leds_part = mapping.split(':')
                port_id = int(port_part)
                led_list = [int(x) for x in leds_part.split(',')]
                result[port_id] = led_list
            except (ValueError, TypeError) as e:
                logger.error(f"Error parsing mapping {mapping}: {e}")
                continue
                
        return result

    def _generate_automatic_mapping(self, mode: str) -> PortMapping:
        """Generate automatic port mapping"""
        config = {
            'mode': mode,
            'port_count': self.config.port_count,
            'leds_per_port': self.config.get('leds_per_port', 2),
            'gap_per_port': self.config.get('gap_per_port', 0),
            'gap_start': self.config.get('led_gap_start', 0),
            'gap_end': self.config.get('led_gap_end', 0),
            'gap_between_rows': self.config.get('led_gap_between_rows', 0),
            'block_size': self.config.get('port_block_size', 0),
            'gap_after_block': self.config.get('led_gap_after_block', 0)
        }

        if mode == 'linear':
            ports1 = list(range(1, config['port_count'] + 1))
            ports2 = []
            odd_reversed = even_reversed = False
        else:
            ports1, ports2 = self._split_ports(config['port_count'])
            odd_reversed = 'odd_reversed' in mode
            even_reversed = 'even_reversed' in mode
            if odd_reversed:
                ports1.reverse()
            if even_reversed:
                ports2.reverse()

        return self._map_ports_to_leds(ports1, ports2, odd_reversed, even_reversed, config)

    def _split_ports(self, port_count: int) -> Tuple[List[int], List[int]]:
        """Split ports into odd and even numbered lists"""
        try:
            odd = [p for p in range(1, port_count + 1) if p % 2 == 1]
            even = [p for p in range(1, port_count + 1) if p % 2 == 0]
            return odd, even
        except Exception as e:
            logger.error(f"Error splitting ports: {e}")
            return [], []

    def _map_ports_to_leds(self, ports1: List[int], ports2: List[int], 
                          odd_reversed: bool, even_reversed: bool, 
                          config: Dict) -> PortMapping:
        """Map ports to LED indices"""
        result: PortMapping = {}
        base_idx = config['gap_start']
        port_counter = 0

        for ports, reversed_flag in [(ports1, odd_reversed), (ports2, even_reversed)]:
            if ports == ports2 and ports:
                base_idx += config['gap_between_rows']
                port_counter = 0

            for port in ports:
                if config['block_size'] and port_counter == config['block_size']:
                    base_idx += config['gap_after_block']
                    port_counter = 0

                leds = list(range(base_idx, base_idx + config['leds_per_port']))
                if reversed_flag:
                    leds.reverse()
                result[port] = leds

                base_idx += config['leds_per_port'] + config['gap_per_port']
                port_counter += 1

        return result

def parse_rgb_string(rgb_str: str) -> RGB:
    """Parse RGB string format 'r,g,b' to tuple"""
    try:
        r, g, b = map(int, rgb_str.strip().split(','))
        return (
            max(0, min(r, 255)),
            max(0, min(g, 255)),
            max(0, min(b, 255))
        )
    except Exception as e:
        logger.error(f"Error parsing RGB string {rgb_str}: {e}")
        return (0, 0, 255)  # Default blue

def parse_vlan_color_map(mapping_str: str) -> Dict[int, RGB]:
    """Parse VLAN to color mapping string"""
    result: Dict[int, RGB] = {}
    if not mapping_str:
        return result

    for pair in mapping_str.split(';'):
        if ':' not in pair:
            continue
        try:
            vlan_str, rgb_str = pair.split(':', 1)
            vlan_id = int(vlan_str.strip())
            result[vlan_id] = parse_rgb_string(rgb_str)
        except (ValueError, TypeError) as e:
            logger.error(f"Error parsing VLAN color mapping {pair}: {e}")
            continue
    return result

def update_vlan_colors_from_map_and_random(config: Config, vlan_info: Dict[int, str]) -> None:
    """Update config with VLAN colors from map or generate random colors"""
    try:
        color_manager = VLANColorManager()
        updates = {}

        for vlan_id, vlan_name in vlan_info.items():
            color_key = f"vlan{vlan_id}_{vlan_name}_color"
            vlan_id = int(vlan_id)
            color = ColorSystem.get_default_vlan_color(vlan_id)
            updates[color_key] = f"{color[0]},{color[1]},{color[2]}"

        if updates:
            config_dict = config.get_config()
            config_dict.update(updates)
            config_dict['scan_vlans'] = False
            config.save_config(config_dict)
            color_manager.refresh_cache()

    except Exception as e:
        logger.error(f"Error updating VLAN colors: {e}")

def calculate_blink_states() -> Dict[str, bool]:
    """Calculate LED blink states for current time"""
    try:
        blink_cycle = (time.time() * 10) % 20
        return {
            'blink_on': (int(blink_cycle) % 2) == 0,
            'phase': (int(blink_cycle) % 16) < 10
        }
    except Exception as e:
        logger.error(f"Error calculating blink states: {e}")
        return {'blink_on': False, 'phase': False}

def parse_port_led_mapping(config: Config) -> PortMapping:
    """Parse port to LED mapping based on configuration"""
    generator = PortMappingGenerator(config)
    return generator.generate_mapping()