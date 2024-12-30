import time
import requests
import sys
import subprocess
import urllib3
from rpi_ws281x import PixelStrip, Color, ws

# Local imports from your utils.py
from .utils import (
    load_config,
    load_secrets,
    parse_port_led_mapping,
    parse_vlan_color_map,
    parse_rgb_string
)

# Suppress InsecureRequestWarning for self-signed certificates
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

def ping_ip(ip):
    """
    Sends a single ping to check if the given IP is reachable.
    Uses '-c 1' (1 packet) and '-W 0.4' (0.4s timeout).
    """
    return (
        subprocess.call(
            ['ping', '-c', '1', '-W', '0.4', ip],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL
        ) == 0
    )

def scan_for_switch(subnet_prefix, start, end, strip=None, led_count=48):
    """
    Scans the IP range [start..end] under subnet_prefix (e.g. "10.18.254").
    If 'strip' is provided, shows a white progress bar over 'led_count' LEDs.
    Returns the first IP that responds to ping or None if none found.
    """
    total = end - start + 1
    scanned = 0

    for i in range(start, end + 1):
        candidate = f"{subnet_prefix}.{i}"
        progress = int((scanned / total) * led_count)

        # Update progress bar on the LED strip (white for scanned portion)
        if strip is not None:
            for led_i in range(led_count):
                color = Color(255,255,255) if led_i < progress else 0
                strip.setPixelColor(led_i, color)
            strip.show()

        print(f"\rScanning: {candidate} ({scanned}/{total})", end="")
        if ping_ip(candidate):
            print(f"\nSwitch found at: {candidate}")
            return candidate

        scanned += 1

    print()  # move to next line if none found
    return None

def main():
    config = load_config()
    secrets = load_secrets()

    # Basic settings from config
    ip_scan = config.get('ip_scan', True)
    switch_ip = config.get('switch_ip', '192.168.0.1')  # fallback
    base_url_suffix = config.get('base_url_suffix', '/api/v1')
    led_count = config.get('led_count', 48)
    led_pin = config.get('led_pin', 18)
    led_brightness = config.get('led_brightness', 255)
    default_vlan_str = config.get('default_vlan_color', '0,0,255')
    vlan_map_str = config.get('vlan_color_map', '')
    update_interval = config.get('update_interval', 15)
    start = config.get('scan_range_start', 10)
    end = config.get('scan_range_end', 255)
    subnet_prefix = config.get('scan_base', '10.18.254')

    # Initialize the LED strip
    strip = PixelStrip(
        led_count,
        led_pin,
        800000,  # WS2812 signal frequency
        10,      # DMA
        False,   # invert
        led_brightness,
        0,       # pi pwm channel
        ws.WS2812_STRIP
    )
    strip.begin()

    # Indicate script is running (LED[0] = white)
    strip.setPixelColor(0, Color(255,255,255))
    strip.show()

    # Parse VLAN color map & default color
    vlan_color_map = parse_vlan_color_map(vlan_map_str)
    default_vlan_color = parse_rgb_string(default_vlan_str)

    # If ip_scan is True, try to find the first reachable switch
    if ip_scan:
        print("Scanning the network for the first reachable switch...")
        found_ip = scan_for_switch(subnet_prefix, start, end, strip=strip, led_count=led_count)
        if found_ip:
            print(f"Switch found: {found_ip}")
            switch_ip = found_ip
            # Short success animation (all green)
            for i in range(led_count):
                strip.setPixelColor(i, Color(0,255,0))
            strip.show()
            time.sleep(1.0)
        else:
            print("No switch found. Restarting script in 10 seconds.")
            # Turn on one red LED per second
            for sec in range(10):
                if sec < led_count:
                    strip.setPixelColor(sec, Color(255,0,0))
                strip.show()
                time.sleep(1)
            print("Script exiting (should be restarted via systemd or manually).")
            sys.exit(1)
    else:
        print(f"Using configured switch IP: {switch_ip}")

    base_url = f"https://{switch_ip}{base_url_suffix}"

    # Prepare login
    username = secrets.get('username', 'admin')
    password = secrets.get('password', 'admin')
    headers = { "Content-Type": "application/json" }
    login_data = { "login": { "username": username, "password": password } }

    # Attempt login
    token = None
    try:
        resp = requests.post(f"{base_url}/login", json=login_data, headers=headers, verify=False)
        resp.raise_for_status()
        token = resp.json()['login']['token']
    except Exception as e:
        print(f"Login failed: {e}")
        sys.exit(1)

    print("Login successful, token acquired.")

    # Auto-detect number of ports
    auto_detect_ports = config.get('auto_detect_ports', True)
    port_count = config.get('fixed_port_count', 24)
    if auto_detect_ports:
        try:
            headers["Authorization"] = f"Bearer {token}"
            resp_dev = requests.get(f"{base_url}/device_info", headers=headers, verify=False)
            resp_dev.raise_for_status()
            dev_info = resp_dev.json().get("device_info", {})
            port_count = int(dev_info.get("numOfPorts", port_count))
            print(f"Switch reports {port_count} ports.")
            # Show port count in blue for 1s
            for i in range(led_count):
                strip.setPixelColor(i, Color(0,0,255) if i < port_count else 0)
            strip.show()
            time.sleep(1.0)
        except Exception as e:
            print(f"Could not retrieve device_info. Using fallback {port_count} ports. Error: {e}")

    # Determine LED mapping for ports
    port_led_map = parse_port_led_mapping(config)

    def cleanup_and_exit():
        """Turns off all LEDs and exits."""
        print("\nShutting down LEDs...")
        for i in range(led_count):
            strip.setPixelColor(i, 0)
        strip.show()
        sys.exit(0)

    # Clear all LEDs once, so only mapped ports are set later
    for i in range(led_count):
        strip.setPixelColor(i, 0)
    strip.show()

    try:
        while True:
            # Periodically update VLAN colors for each port
            headers["Authorization"] = f"Bearer {token}"
            for port_id in range(1, port_count + 1):
                try:
                    r = requests.get(
                        f"{base_url}/swcfg_port?portid={port_id}",
                        headers=headers,
                        verify=False,
                        timeout=2
                    )
                    r.raise_for_status()
                    port_data = r.json().get("switchPortConfig", {})
                    vlan_id = port_data.get("portVlanId", 1)

                    # Determine port color
                    if vlan_id in vlan_color_map:
                        (r_val, g_val, b_val) = vlan_color_map[vlan_id]
                    else:
                        (r_val, g_val, b_val) = default_vlan_color

                    color = Color(r_val, g_val, b_val)

                    # Update assigned LED(s) for this port
                    leds_for_port = port_led_map.get(port_id, [])
                    for led_idx in leds_for_port:
                        if 0 <= led_idx < led_count:
                            strip.setPixelColor(led_idx, color)

                except Exception as ex:
                    print(f"Error on port {port_id}: {ex}")

            strip.show()
            time.sleep(update_interval)

    except KeyboardInterrupt:
        cleanup_and_exit()

if __name__ == "__main__":
    main()
