import os
import json
#import sys TODO

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

# ---------- Generator-Funktionen mit Gaps ----------

def generate_linear_mapping(
    port_count, leds_per_port,
    gap_start=0, gap_end=0,
    block_size=0, gap_after_block=0
):
    """
    Port 1 -> [base_idx..(base_idx+leds_per_port-1)] aufsteigend
    + led_gap_start am Anfang
    + port_block_size => nach so vielen Ports: led_gap_after_block
    + led_gap_end => nach letztem Port
    """
    result = {}
    base_idx = 0

    # 1) Gap vor erstem Port
    base_idx += gap_start

    port_counter_in_block = 0

    for p in range(1, port_count+1):
        # Blocks
        if block_size > 0 and port_counter_in_block == block_size:
            base_idx += gap_after_block
            port_counter_in_block = 0

        leds = list(range(base_idx, base_idx + leds_per_port))
        result[p] = leds
        base_idx += leds_per_port
        port_counter_in_block += 1

    # 2) Gap nach letztem Port
    base_idx += gap_end
    # (hier wird der Index nicht wirklich genutzt, aber
    #  du könntest ihn auslesen, falls du was am Ende tun willst)

    return result

def generate_odd_even_linear(
    port_count, leds_per_port,
    gap_start=0, gap_end=0,
    block_size=0, gap_after_block=0
):
    """Erst ungerade Ports aufsteigend, dann gerade aufsteigend + Gaps."""
    result = {}
    odd_ports = [p for p in range(1, port_count+1) if p % 2 == 1]
    even_ports = [p for p in range(1, port_count+1) if p % 2 == 0]
    ordered_ports = odd_ports + even_ports

    base_idx = 0
    base_idx += gap_start

    port_counter_in_block = 0

    for idx, p in enumerate(ordered_ports):
        if block_size > 0 and port_counter_in_block == block_size:
            base_idx += gap_after_block
            port_counter_in_block = 0

        leds = list(range(base_idx, base_idx + leds_per_port))
        result[p] = leds
        base_idx += leds_per_port
        port_counter_in_block += 1

    base_idx += gap_end
    return result

def generate_odd_even_even_reversed(
    port_count, leds_per_port,
    gap_start=0, gap_end=0,
    block_size=0, gap_after_block=0
):
    """Odd asc, then even desc + Gaps."""
    result = {}
    odd_ports = [p for p in range(1, port_count+1) if p % 2 == 1]
    even_ports = [p for p in range(1, port_count+1) if p % 2 == 0]
    even_ports.reverse()
    ordered_ports = odd_ports + even_ports

    base_idx = 0
    base_idx += gap_start

    port_counter_in_block = 0

    for p in ordered_ports:
        if block_size > 0 and port_counter_in_block == block_size:
            base_idx += gap_after_block
            port_counter_in_block = 0

        leds = list(range(base_idx, base_idx + leds_per_port))
        result[p] = leds
        base_idx += leds_per_port
        port_counter_in_block += 1

    base_idx += gap_end
    return result

def generate_odd_even_odd_reversed(
    port_count, leds_per_port,
    gap_start=0, gap_end=0,
    block_size=0, gap_after_block=0
):
    """Odd desc, then even asc + Gaps."""
    result = {}
    odd_ports = [p for p in range(1, port_count+1) if p % 2 == 1]
    odd_ports.reverse()
    even_ports = [p for p in range(1, port_count+1) if p % 2 == 0]
    ordered_ports = odd_ports + even_ports

    base_idx = 0
    base_idx += gap_start

    port_counter_in_block = 0

    for p in ordered_ports:
        if block_size > 0 and port_counter_in_block == block_size:
            base_idx += gap_after_block
            port_counter_in_block = 0

        leds = list(range(base_idx, base_idx + leds_per_port))
        result[p] = leds
        base_idx += leds_per_port
        port_counter_in_block += 1

    base_idx += gap_end
    return result

def generate_odd_even_reversed(
    port_count, leds_per_port,
    gap_start=0, gap_end=0,
    block_size=0, gap_after_block=0
):
    """Erst ungerade absteigend, dann gerade absteigend + Gaps."""
    result = {}
    odd_ports = [p for p in range(1, port_count+1) if p % 2 == 1]
    odd_ports.reverse()
    even_ports = [p for p in range(1, port_count+1) if p % 2 == 0]
    even_ports.reverse()

    ordered_ports = odd_ports + even_ports

    base_idx = 0
    base_idx += gap_start

    port_counter_in_block = 0

    for p in ordered_ports:
        if block_size > 0 and port_counter_in_block == block_size:
            base_idx += gap_after_block
            port_counter_in_block = 0

        leds = list(range(base_idx, base_idx + leds_per_port))
        result[p] = leds
        base_idx += leds_per_port
        port_counter_in_block += 1

    base_idx += gap_end
    return result

# ---------- parse_port_led_mapping ----------

def parse_port_led_mapping(config):
    """
    Liest config['port_mapping_mode'], config['port_led_mapping'] usw.
    Gibt ein Dict zurück, z.B. {1: [0,1], 2: [2,3], ...}
    """
    port_count = config.get('fixed_port_count', 24)
    mode = config.get('port_mapping_mode', 'linear')
    leds_per_port = config.get('leds_per_port', 2)

    # Neue Gap-Parameter:
    gap_start = config.get('led_gap_start', 0)
    gap_end = config.get('led_gap_end', 0)
    block_size = config.get('port_block_size', 0)
    gap_after_block = config.get('led_gap_after_block', 0)

    # Manuelles Mapping?
    manual_str = config.get('port_led_mapping', '')
    if mode == 'manual' and manual_str:
        result = {}
        port_mappings = manual_str.split(';')
        for pm in port_mappings:
            pm = pm.strip()
            if ':' not in pm:
                continue
            port_part, leds_part = pm.split(':')
            try:
                port_id = int(port_part)
                leds = [int(x) for x in leds_part.split(',')]
                result[port_id] = leds
            except:
                pass
        return result

    # Automatisch, je nach mode:
    if mode == 'linear':
        return generate_linear_mapping(port_count, leds_per_port,
                                       gap_start, gap_end,
                                       block_size, gap_after_block)
    elif mode == 'odd_even-linear':
        return generate_odd_even_linear(port_count, leds_per_port,
                                        gap_start, gap_end,
                                        block_size, gap_after_block)
    elif mode == 'odd_even-even_reversed':
        return generate_odd_even_even_reversed(port_count, leds_per_port,
                                               gap_start, gap_end,
                                               block_size, gap_after_block)
    elif mode == 'odd_even-odd_reversed':
        return generate_odd_even_odd_reversed(port_count, leds_per_port,
                                              gap_start, gap_end,
                                              block_size, gap_after_block)
    elif mode == 'odd_even-reversed':
        return generate_odd_even_reversed(port_count, leds_per_port,
                                          gap_start, gap_end,
                                          block_size, gap_after_block)

    # Fallback auf linear
    return generate_linear_mapping(port_count, leds_per_port,
                                   gap_start, gap_end,
                                   block_size, gap_after_block)

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