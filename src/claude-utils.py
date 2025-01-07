import os
import json
import random
from typing import Dict, List, Tuple, Optional
from dataclasses import dataclass

# Type Definitions
RGB = Tuple[int, int, int]
PortMapping = Dict[int, List[int]]

# Constants
CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(CURRENT_DIR)
CONFIG_PATH = os.path.join(PROJECT_ROOT, 'settings', 'config.json')
SECRETS_PATH = os.path.join(PROJECT_ROOT, 'settings', 'secrets.json')

@dataclass
class MappingConfig:
    """Configuration for port mapping generation"""
    mode: str
    port_count: int
    leds_per_port: int
    gap_per_port: int = 0
    gap_start: int = 0
    gap_end: int = 0
    gap_between_rows: int = 0
    block_size: int = 0
    gap_after_block: int = 0

class ConfigManager:
    """Handles loading and managing configuration files"""
    
    @staticmethod
    def load_config() -> dict:
        """Load main configuration file"""
        try:
            with open(CONFIG_PATH, 'r') as f:
                return json.load(f)
        except FileNotFoundError:
            raise FileNotFoundError(f"Configuration file not found at {CONFIG_PATH}")
        except json.JSONDecodeError:
            raise ValueError(f"Invalid JSON in configuration file {CONFIG_PATH}")

    @staticmethod
    def load_secrets() -> dict:
        """Load secrets configuration file"""
        try:
            with open(SECRETS_PATH, 'r') as f:
                return json.load(f)
        except FileNotFoundError:
            raise FileNotFoundError(f"Secrets file not found at {SECRETS_PATH}")
        except json.JSONDecodeError:
            raise ValueError(f"Invalid JSON in secrets file {SECRETS_PATH}")

class PortMapper:
    """Handles port to LED mapping logic"""
    
    @staticmethod
    def _split_ports(port_count: int) -> Tuple[List[int], List[int]]:
        """Split ports into odd and even lists"""
        odd_ports = [p for p in range(1, port_count + 1) if p % 2 == 1]
        even_ports = [p for p in range(1, port_count + 1) if p % 2 == 0]
        return odd_ports, even_ports

    @staticmethod
    def parse_manual_mapping(mapping_str: str) -> PortMapping:
        """Parse manual port mapping string"""
        result = {}
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
            except (ValueError, TypeError):
                continue
        return result

    @classmethod
    def generate_mapping(cls, config: MappingConfig) -> PortMapping:
        """Generate port to LED mapping based on configuration"""
        if config.mode == 'linear':
            ports1, ports2 = list(range(1, config.port_count + 1)), []
            odd_reversed = even_reversed = False
        else:
            ports1, ports2 = cls._split_ports(config.port_count)
            odd_reversed = 'odd_reversed' in config.mode
            even_reversed = 'even_reversed' in config.mode
            
            if odd_reversed:
                ports1.reverse()
            if even_reversed:
                ports2.reverse()

        result = {}
        base_idx = config.gap_start
        port_counter = 0

        # Map first block (ports1)
        for port in ports1:
            if config.block_size and port_counter == config.block_size:
                base_idx += config.gap_after_block
                port_counter = 0

            leds = list(range(base_idx, base_idx + config.leds_per_port))
            if odd_reversed:
                leds.reverse()
            result[port] = leds

            base_idx += config.leds_per_port + config.gap_per_port
            port_counter += 1

        # Map second block (ports2) if exists
        if ports2:
            base_idx += config.gap_between_rows
            port_counter = 0

            for port in ports2:
                if config.block_size and port_counter == config.block_size:
                    base_idx += config.gap_after_block
                    port_counter = 0

                leds = list(range(base_idx, base_idx + config.leds_per_port))
                if even_reversed:
                    leds.reverse()
                result[port] = leds

                base_idx += config.leds_per_port + config.gap_per_port
                port_counter += 1

        return result

class VLANManager:
    """Handles VLAN color management"""
    
    @staticmethod
    def parse_rgb_string(rgb_str: str) -> RGB:
        """Parse RGB string to tuple"""
        try:
            r, g, b = map(int, rgb_str.strip().split(','))
            return (min(255, max(0, r)),
                   min(255, max(0, g)),
                   min(255, max(0, b)))
        except (ValueError, TypeError):
            return (0, 0, 255)  # Default blue

    @classmethod
    def parse_vlan_color_map(cls, mapping_str: str) -> Dict[int, RGB]:
        """Parse VLAN color mapping string"""
        result = {}
        if not mapping_str:
            return result

        for pair in mapping_str.split(';'):
            if ':' not in pair:
                continue
            try:
                vlan_str, rgb_str = pair.split(':', 1)
                vlan_id = int(vlan_str.strip())
                result[vlan_id] = cls.parse_rgb_string(rgb_str)
            except (ValueError, TypeError):
                continue
        return result

    @classmethod
    def generate_random_color(cls) -> RGB:
        """Generate random RGB color"""
        return (random.randint(0, 255),
                random.randint(0, 255),
                random.randint(0, 255))

    @classmethod
    def update_vlan_colors(cls, config: dict, vlan_ids: List[int]) -> dict:
        """Update VLAN colors in config"""
        global_map = cls.parse_vlan_color_map(config.get('vlan_color_map', ''))
        
        for vlan_id in vlan_ids:
            color_key = f"vlan{vlan_id}_color"
            if color_key in config:
                continue
                
            if vlan_id in global_map:
                r, g, b = global_map[vlan_id]
            else:
                r, g, b = cls.generate_random_color()
                
            config[color_key] = f"{r},{g},{b}"
            
        return config

    @classmethod
    def get_vlan_color(cls, vlans: List[int], config: dict,
                       default_color: RGB,
                       vlan_map: Optional[Dict[int, RGB]] = None) -> RGB:
        """Get color for VLAN"""
        if not vlans:
            return default_color

        vlan_id = vlans[0]
        color_key = f"vlan{vlan_id}_color"
        
        if color_key in config:
            return cls.parse_rgb_string(config[color_key])
            
        if vlan_map and vlan_id in vlan_map:
            return vlan_map[vlan_id]
            
        return default_color

def parse_port_led_mapping(config: dict) -> PortMapping:
    """Parse port LED mapping from config"""
    if config.get('port_mapping_mode') == 'manual':
        return PortMapper.parse_manual_mapping(config.get('port_led_mapping', ''))
        
    mapping_config = MappingConfig(
        mode=config.get('port_mapping_mode', 'linear'),
        port_count=config.get('fixed_port_count', 24),
        leds_per_port=config.get('leds_per_port', 2),
        gap_per_port=config.get('gap_per_port', 0),
        gap_start=config.get('led_gap_start', 0),
        gap_end=config.get('led_gap_end', 0),
        gap_between_rows=config.get('led_gap_between_rows', 0),
        block_size=config.get('port_block_size', 0),
        gap_after_block=config.get('led_gap_after_block', 0)
    )
    
    return PortMapper.generate_mapping(mapping_config)

# Convenience functions to maintain backward compatibility
load_config = ConfigManager.load_config
load_secrets = ConfigManager.load_secrets
parse_vlan_color_map = VLANManager.parse_vlan_color_map
parse_rgb_string = VLANManager.parse_rgb_string
parse_vlan_color_for_port = VLANManager.get_vlan_color
update_vlan_colors_from_map_and_random = VLANManager.update_vlan_colors