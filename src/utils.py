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