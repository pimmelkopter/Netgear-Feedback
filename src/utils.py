import os
import json

# Paths for config
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

# ---Port Mapping Generator---
def generate_port_mapping(mode,
                          port_count,
                          leds_per_port,
                          gap_per_port=0,
                          gap_start=0,
                          gap_end=0,
                          gap_between_rows=0,
                          block_size=0,
                          gap_after_block=0):

    # Default linear:
    ports1 = list(range(1, port_count+1))
    ports2 = []

    if mode.startswith('odd_even'):
        # Split odd vs even
        odd_ports  = [p for p in range(1, port_count+1) if p % 2 == 1]
        even_ports = [p for p in range(1, port_count+1) if p % 2 == 0]

        # Check for reversed variants:
        if 'odd_reversed' in mode:
            odd_ports.reverse()
        if 'even_reversed' in mode:
            even_ports.reverse()

        ports1 = odd_ports
        ports2 = even_ports

    elif mode != 'linear': # fallback => treat unknown modes as 'linear'
        pass

    result = {}
    base_idx = gap_start  # initial offset
    port_counter_in_block = 0

    # ---------- FIRST BLOCK (ports1) ----------
    for p in ports1:
        # check if we hit a block boundary
        if block_size > 0 and port_counter_in_block == block_size:
            base_idx += gap_after_block
            port_counter_in_block = 0

        leds = list(range(base_idx, base_idx + leds_per_port))
        result[p] = leds

        base_idx += leds_per_port
        base_idx += gap_per_port
        port_counter_in_block += 1

    # ---------- SECOND BLOCK (ports2) + add gap_between_rows first ---------- 
    if ports2:
        base_idx += gap_between_rows
        port_counter_in_block = 0  # reset block counter for second row

        for p in ports2:
            if block_size > 0 and port_counter_in_block == block_size:
                base_idx += gap_after_block
                port_counter_in_block = 0

            leds = list(range(base_idx, base_idx + leds_per_port))
            result[p] = leds

            base_idx += leds_per_port
            base_idx += gap_per_port
            port_counter_in_block += 1

    # ---------- OFF LEDs ath the end if neccessary gap_end ----------
    base_idx += gap_end

    return result


def parse_port_led_mapping(config):
    port_count       = config.get('fixed_port_count', 24)
    mode             = config.get('port_mapping_mode', 'linear')
    leds_per_port    = config.get('leds_per_port', 2)
    gap_per_port     = config.get('gap_per_port',0)
    gap_start        = config.get('led_gap_start', 0)
    gap_end          = config.get('led_gap_end', 0)
    gap_between_rows = config.get('led_gap_between_rows', 0)
    block_size       = config.get('port_block_size', 0)
    gap_after_block  = config.get('led_gap_after_block', 0)

    # Manual mapping if mode == 'manual'
    manual_str = config.get('port_led_mapping', '')
    if mode == 'manual' and manual_str:
        result = {}
        for pm in manual_str.split(';'):
            pm = pm.strip()
            if ':' not in pm:
                continue
            port_part, leds_part = pm.split(':')
            try:
                pid = int(port_part)
                led_list = [int(x) for x in leds_part.split(',')]
                result[pid] = led_list
            except:
                pass
        return result

    # Auto:
    return generate_port_mapping(
        mode,
        port_count,
        leds_per_port,
        gap_per_port,
        gap_start,
        gap_end,
        gap_between_rows,
        block_size,
        gap_after_block
    )


def parse_vlan_color_map(mapping_str):
    result = {}
    if not mapping_str:
        return result
    pairs = mapping_str.split(';')
    for p in pairs:
        if ':' not in p:
            continue
        vlan_str, rgb_str = p.split(':', 1)
        try:
            vid = int(vlan_str.strip())
            rgb_parts = [c.strip() for c in rgb_str.split(',')]
            if len(rgb_parts) == 3:
                r, g, b = map(int, rgb_parts)
                result[vid] = (r, g, b)
        except:
            pass
    return result

def parse_rgb_string(rgb_str):
    parts = [c.strip() for c in rgb_str.split(',')]
    if len(parts) == 3:
        try:
            r, g, b = map(int, parts)
            return (r, g, b)
        except:
            pass
    return (0, 0, 255) #Fallback Blue
