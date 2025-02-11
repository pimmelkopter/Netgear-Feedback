##services/utils.py##
from typing import Dict, List, Tuple, Optional
import logging
import time
import random
from .config import Config

logger = logging.getLogger(__name__)

# Type Aliases
RGB = Tuple[int, int, int]
PortMapping = Dict[int, List[int]]

class VLANColorManager:
    _instance = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance
        
    def __init__(self):
        if not self._initialized:
            self.config = Config()
            self.color_cache = {}
            self.refresh_cache()
            self._initialized = True
    
    def refresh_cache(self):
        """Rebuild the complete color mapping cache"""
        self.color_cache.clear()
        
        if self.config.scan_vlans:
            # When scanning VLANs, use vlan_color_map and generate random colors
            color_map = parse_vlan_color_map(self.config.get('vlan_color_map', ''))
            self.color_cache.update(color_map)
        else:
            # Use explicit VLAN colors from config
            config_dict = self.config.get_config()
            
            # First pass: Get colors from vlanX_NAME_color entries
            for key, value in config_dict.items():
                if key.startswith('vlan') and '_color' in key:
                    try:
                        vlan_id = int(key.split('_')[0].replace('vlan', ''))
                        color = parse_rgb_string(value)
                        self.color_cache[vlan_id] = color
                    except (ValueError, IndexError):
                        continue
            
            # Second pass: Fill missing entries from vlan_color_map
            color_map = parse_vlan_color_map(config_dict.get('vlan_color_map', ''))
            for vlan_id, color in color_map.items():
                if vlan_id not in self.color_cache:
                    self.color_cache[vlan_id] = color
    
    def get_vlan_color(self, vlan_id: int) -> RGB:
        """Get color for VLAN ID using cached values"""
        if vlan_id in self.color_cache:
            return self.color_cache[vlan_id]
        
        # Return default color if no mapping found
        default_color = parse_rgb_string(
            self.config.get('default_vlan_color', '0,0,255')
        )
        return default_color

def parse_port_led_mapping(config: Config) -> PortMapping:
    """
    Parse port to LED mapping based on configuration.
    Returns a dictionary mapping port numbers to LED indices.
    """
    if config.get('port_mapping_mode') == 'manual':
        return parse_manual_mapping(config.get('port_led_mapping', ''))

    mapping_config = {
        'mode': config.get('port_mapping_mode', 'linear'),
        'port_count': config.port_count,
        'leds_per_port': config.get('leds_per_port', 2),
        'gap_per_port': config.get('gap_per_port', 0),
        'gap_start': config.get('led_gap_start', 0),
        'gap_end': config.get('led_gap_end', 0),
        'gap_between_rows': config.get('led_gap_between_rows', 0),
        'block_size': config.get('port_block_size', 0),
        'gap_after_block': config.get('led_gap_after_block', 0)
    }
    return generate_mapping(mapping_config)

def parse_manual_mapping(mapping_str: str) -> PortMapping:
    """Parse manual mapping string in format 'port:led1,led2;port:led1,led2'"""
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
            logger.warning(f"Error parsing mapping {mapping}: {e}")
    return result

def generate_mapping(config: dict) -> PortMapping:
    """Generate port to LED mapping based on configuration"""
    if config['mode'] == 'linear':
        ports1 = list(range(1, config['port_count'] + 1))
        ports2 = []
        odd_reversed = even_reversed = False
    else:
        ports1, ports2 = _split_ports(config['port_count'])
        odd_reversed = 'odd_reversed' in config['mode']
        even_reversed = 'even_reversed' in config['mode']
        if odd_reversed:
            ports1.reverse()
        if even_reversed:
            ports2.reverse()

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

def _split_ports(port_count: int) -> Tuple[List[int], List[int]]:
    """Split ports into odd and even numbered lists"""
    odd = [p for p in range(1, port_count + 1) if p % 2 == 1]
    even = [p for p in range(1, port_count + 1) if p % 2 == 0]
    return odd, even

def parse_rgb_string(rgb_str: str) -> RGB:
    """Parse RGB string in format 'r,g,b' to tuple"""
    try:
        r, g, b = map(int, rgb_str.strip().split(','))
        return (
            max(0, min(r, 255)),
            max(0, min(g, 255)),
            max(0, min(b, 255))
        )
    except Exception as e:
        logger.warning(f"Error parsing RGB string {rgb_str}: {e}")
        return (0, 0, 255)  # Default blue

def parse_vlan_color_map(mapping_str: str) -> Dict[int, RGB]:
    """Parse VLAN to color mapping string in format 'vlan:r,g,b;vlan:r,g,b'"""
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
            logger.warning(f"Error parsing VLAN color mapping {pair}: {e}")
    return result

def update_vlan_colors_from_map_and_random(config: Config, vlan_info: Dict[int, str]) -> None:
    """Update config with VLAN colors from map or generate random colors"""
    # Get color manager instance
    color_manager = VLANColorManager()
    
    # Parse existing color map
    color_map = parse_vlan_color_map(config.get('vlan_color_map', ''))
    updates = {}
    
    for vlan_id, vlan_name in vlan_info.items():
        color_key = f"vlan{vlan_id}_{vlan_name}_color"
                        
        # Use existing color from map or generate random
        if int(vlan_id) in color_map:
            r, g, b = color_map[int(vlan_id)]
        else:
            r = random.randint(0, 255)
            g = random.randint(0, 255)
            b = random.randint(0, 255)
            
        updates[color_key] = f"{r},{g},{b}"
    
    # Update config if we have changes
    if updates:
        config_dict = config.get_config()
        config_dict.update(updates)
        config_dict['scan_vlans'] = False
        config.save_config(config_dict)
        
        # Refresh color cache after config update
        color_manager.refresh_cache()

def calculate_blink_states():
    blink_cycle = (time.time() * 10) % 20
    return {
        'blink_on': (int(blink_cycle) % 2) == 0,
        'phase': (int(blink_cycle) % 16) < 10
    }