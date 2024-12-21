import os
import json
import sys

# Bestimmt den absoluten Pfad zum project-root (eine Ebene über diesem Script).
CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(CURRENT_DIR)

CONFIG_PATH = os.path.join(PROJECT_ROOT, 'settings', 'config.json')
SECRETS_PATH = os.path.join(PROJECT_ROOT, 'settings', 'secrets.json')

def load_config():
    with open(CONFIG_PATH, 'r') as f:
        return json.load(f)

def load_secrets():
    with open(SECRETS_PATH, 'r') as f:
        return json.load(f)

def parse_port_led_mapping(mapping_str):
    """
    Erwartet z.B. '1:1,2;2:3,4;3:7,8'
    Gibt ein Dict zurück, z.B. {1: [1,2], 2: [3,4], 3: [7,8]}
    """
    result = {}
    if not mapping_str:
        return result
    port_mappings = mapping_str.split(';')
    for pm in port_mappings:
        # pm z.B. '1:1,2'
        port_part, leds_part = pm.split(':')
        port_id = int(port_part)
        leds = [int(x) for x in leds_part.split(',')]
        result[port_id] = leds
    return result

def parse_vlan_color_map(mapping_str):
    """
    Erwartet z.B. '100:255,0,0;200:0,255,0'
    Gibt ein Dict zurück, z.B. {100: (255,0,0), 200: (0,255,0)}
    """
    result = {}
    if not mapping_str:
        return result
    pairs = mapping_str.split(';')
    for p in pairs:
        # p z.B. '100:255,0,0'
        if ':' not in p:
            continue
        vlan_str, rgb_str = p.split(':', 1)
        vlan_id = int(vlan_str.strip())
        rgb_parts = [c.strip() for c in rgb_str.split(',')]
        if len(rgb_parts) == 3:
            try:
                r, g, b = map(int, rgb_parts)
                result[vlan_id] = (r, g, b)
            except ValueError:
                pass
    return result

def parse_rgb_string(rgb_str):
    """
    Erwartet z.B. '255,0,0'
    Gibt ein Tuple (255,0,0) zurück.
    """
    parts = [c.strip() for c in rgb_str.split(',')]
    if len(parts) == 3:
        try:
            r, g, b = map(int, parts)
            return (r, g, b)
        except ValueError:
            pass
    # Fallback auf Blau:
    return (0, 0, 255)