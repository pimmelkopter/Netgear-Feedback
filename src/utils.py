import json
import os

def load_json(path):
    with open(path, 'r', encoding='utf-8') as f:
        return json.load(f)

def get_config():
    config_path = os.path.join(os.path.dirname(__file__), '..', 'settings', 'config.json')
    return load_json(config_path)

def get_secrets():
    secrets_path = os.path.join(os.path.dirname(__file__), '..', 'settings', 'secrets.json')
    return load_json(secrets_path)

def hex_to_rgb(hex_str):
    # Erwartet ein String wie "#RRGGBB"
    hex_str = hex_str.lstrip('#')
    return tuple(int(hex_str[i:i+2], 16) for i in (0, 2, 4))
