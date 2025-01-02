import time
import requests
import sys
import subprocess
import urllib3
import threading
import random   # für zufällige Farben, falls gewünscht
import json
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
    """ Sends one ping with 0.4s timeout. Returns True if reachable. """
    return (
        subprocess.call(
            ['ping', '-c', '1', '-W', '0.4', ip],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL
        ) == 0
    )

def scan_for_switch(subnet_prefix, start, end, strip=None, led_count=48):
    """
    Scans IP range [start..end] in 'subnet_prefix' (e.g. "10.18.254").
    If 'strip' is given, shows a white progress bar. Returns first IP or None.
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

def get_port_status_color(speed, poe_active, blink_on):
    """
    Determines the LED color for speed and PoE with blinking logic.
    - Base color is always black.
    - Blinks between speed (green/orange/black) and PoE (blue/black) if active.
    """
    base_color = (0, 0, 0)  # Always start with black

    if blink_on:
        # When blink_on is True, show the speed color
        if speed == 5:
            return (0, 255, 0)  # green (Gigabit)
        elif speed == 4:
            return (255, 165, 0)  # orange (100Mbit)
        else:
            return base_color  # black (no link)
    else:
        # When blink_on is False, show PoE color if active
        if poe_active:
            return (0, 0, 255)  # blue (PoE active)
        else:
            return base_color  # black (no PoE)


def main():
    config = load_config()
    secrets = load_secrets()

    ip_scan          = config.get('ip_scan', True)
    switch_ip        = config.get('switch_ip', '192.168.0.1')
    base_url_suffix  = config.get('base_url_suffix', '/api/v1')
    led_count        = config.get('led_count', 48)
    led_pin          = config.get('led_pin', 18)
    led_brightness   = config.get('led_brightness', 255)
    default_vlan_str = config.get('default_vlan_color', '0,0,255')
    vlan_map_str     = config.get('vlan_color_map', '')
    update_interval  = config.get('update_interval', 15)
    start            = config.get('scan_range_start', 10)
    end              = config.get('scan_range_end', 255)
    subnet_prefix    = config.get('scan_base', '10.18.254')
    port_stats       = config.get('port_stats', False)
    leds_per_port    = config.get('leds_per_port', 1)
    scan_vlans       = config.get('scan_vlans', False)

    # Init LED strip
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

    # Parse VLAN color map & default color # TODO
    vlan_color_map = parse_vlan_color_map(vlan_map_str)
    default_vlan_color = parse_rgb_string(default_vlan_str)

    # If ip_scan is True, try to find the first reachable switch
    if ip_scan:
        print("Scanning network for first reachable switch...")
        found_ip = scan_for_switch(subnet_prefix, start, end, strip=strip, led_count=led_count)
        if found_ip:
            print(f"Switch found: {found_ip}")
            switch_ip = found_ip
            # success flash (green)
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
        r_login = requests.post(f"{base_url}/login", json=login_data, headers=headers, verify=False)
        r_login.raise_for_status()
        token = r_login.json()['login']['token']
    except Exception as e:
        print(f"Login failed => Exiting: {e}")
        sys.exit(1)

    print("Login successful. Token acquired.")

    # Auto-detect number of ports
    auto_detect_ports = config.get('auto_detect_ports', True)
    port_count = config.get('fixed_port_count', 24)

    try:
        if auto_detect_ports:
            headers["Authorization"] = f"Bearer {token}"
            r_dev = requests.get(f"{base_url}/device_info", headers=headers, verify=False, timeout=3)
            r_dev.raise_for_status()
            dev_info = r_dev.json().get("device_info", {})
            port_count = int(dev_info.get("numOfPorts", port_count))
            print(f"Switch reports {port_count} ports.")
            # Show port count in blue for 1s
            for i in range(led_count):
                strip.setPixelColor(i, Color(0,0,255) if i < port_count else 0)
            strip.show()
            time.sleep(1.0)
    except Exception as e:
        print(f"Could not get device_info => fallback {port_count}. Error: {e}")

    # --- Neu: optional VLAN config parse from running-config
    if scan_vlans:
        try:
            # device_config?file=running-config
            headers["Authorization"] = f"Bearer {token}"
            rc = requests.get(f"{base_url}/device_config?file=running-config",
                              headers=headers, verify=False, timeout=5)
            rc.raise_for_status()
            lines = rc.json().get("Device-Config",{}).get("Running-Config",[])
            # parse lines => look for 'vlan name XX "SOME"' pattern
            import re
            vlan_name_pattern = re.compile(r'^\s*vlan\s+name\s+(\d+)\s+"([^"]+)"')
            found_something = False

            for line in lines:
                m = vlan_name_pattern.match(line.strip())
                if m:
                    found_something = True
                    vlan_id_str = m.group(1)
                    vlan_name   = m.group(2)
                    # set config["vlanXX_name"] = ...
                    key_name  = f"vlan{vlan_id_str}_name"
                    config[key_name] = vlan_name

                    # set config["vlanXX_color"] = random or default
                    # falls user schon config hat => nicht überschreiben
                    color_key = f"vlan{vlan_id_str}_color"
                    if color_key not in config:
                        # generate random color or do a simple next color
                        # z.B. random R,G,B up to 255
                        r_ = random.randint(0,255)
                        g_ = random.randint(0,255)
                        b_ = random.randint(0,255)
                        config[color_key] = f"{r_},{g_},{b_}"

            if found_something:
                # set scan_vlans => false
                config["scan_vlans"] = False
                # now write config to disk
                from .utils import CONFIG_PATH
                with open(CONFIG_PATH,"w") as cf:
                    json.dump(config,cf, indent=2)
                print("Updated config.json with VLAN names/colors, scan_vlans => false.")
            else:
                print("No VLAN lines found in running-config?")
        except Exception as ex:
            print(f"Could not parse running-config for VLANs: {ex}")

    # parse LED-mapping
    port_led_map = parse_port_led_mapping(config)

    # Prepare a cache for each port, so we don't spam requests in LED-loop
    port_info_cache = {
        port_id: {
            "vlan_color": (0,0,0),  # (r,g,b) from VLAN
            "speed": 0,
            "poe_active": False
        } for port_id in range(1, port_count+1)
    }
    
    # Clear all LEDs once, so only mapped ports are set later
    for i in range(led_count):
        strip.setPixelColor(i, 0)
    strip.show()

    def cleanup_and_exit():
        """Shuts down all LEDs and exits."""
        print("\nShutting down LEDs...")
        for j in range(led_count):
            strip.setPixelColor(j, 0)
        strip.show()
        sys.exit(0)

    # parse all ports speed, poe, VLAN
    def parse_speed(stats_json):
        """Return 5 => gigabit, 4 => 100Mbit, 0 => no link."""
        if stats_json.get("oprState",0) !=1:
            return 0
        raw_speed = stats_json.get("speed",0)
        if raw_speed == 7:
            return 5
        elif raw_speed in (3,4,6):
            return 4
        else:
            return 0

    def parse_poe(stats_json):
        # poeStatus >=2 => usage
        return (stats_json.get("poeStatus",0) >=2)

    def parse_vlan_color_for_port(vlans): #TODO  lieber in utils
        """
        We pick the first VLAN in the list, then see if config has "vlanXX_color".
        If so parse that, else default_vlan_color.
        """
        if not vlans:
            return default_vlan_color
        first_vlan = vlans[0]
        color_key  = f"vlan{first_vlan}_color"
        if color_key in config:
            c_str = config[color_key]
            return parse_rgb_string(c_str)
        else:
            # fallback
            return default_vlan_color

    # Thread A => HTTP
    def http_thread():
        while True:
            time.sleep(update_interval)
            try:
                headers["Authorization"] = f"Bearer {token}"
                # single request: /sw_portstats?portid=ALL
                rsp = requests.get(f"{base_url}/sw_portstats?portid=ALL",
                                   headers=headers, verify=False, timeout=5)
                rsp.raise_for_status()
                arr = rsp.json().get("switchStatsPort",[])
                # arr is a list => each item has portId, speed, poeStatus, vlans, ...
                for item in arr:
                    pid  = item.get("portId", 0)
                    if pid<1 or pid> port_count:
                        continue
                    s    = parse_speed(item)
                    poe  = parse_poe(item)
                    # determine VLAN color from item["vlans"]
                    vlans_list = item.get("vlans",[])
                    c = parse_vlan_color_for_port(vlans_list)

                    port_info_cache[pid]["speed"]      = s
                    port_info_cache[pid]["poe_active"] = poe
                    port_info_cache[pid]["vlan_color"] = c
            except Exception as ex:
                print(f"HTTP error => Exiting: {ex}")
                cleanup_and_exit()

    # 2) Thread B: led_thread => alle 0.1s => LED updates (blinking)
    def led_thread():
        blink_cycle = 0
        while True:
            time.sleep(0.1)
            blink_cycle += 1
            blink_on = ((blink_cycle % 2) == 0)  # toggles at 5Hz

            for port_id in range(1, port_count+1):
                leds_for_port = port_led_map.get(port_id, [])
                if not leds_for_port:
                    continue
                # read from cache
                (vr,vg,vb) = port_info_cache[port_id]["vlan_color"]
                speed   = port_info_cache[port_id]["speed"]
                poe   = port_info_cache[port_id]["poe_active"]

                # if port_stats=False => all mapped leds => VLAN color
                if not port_stats:
                    for led_idx in leds_for_port:
                        if 0 <= led_idx < led_count:
                            strip.setPixelColor(led_idx, Color(vr, vg, vb))
                    continue

                # else => port_stats = True
                if len(leds_for_port) >= 2:
                    # LED #1 -> VLAN
                    led_idx_1 = leds_for_port[0]
                    if 0 <= led_idx_1 < led_count:
                        strip.setPixelColor(led_idx_1, Color(vr, vg, vb))

                    # LED #2 => Stats
                    led_idx_2 = leds_for_port[1]

                    # bei speed=0 & poe=false => show VLAN on both
                    if speed==0 and poe==False:
                        if 0<=led_idx_2<led_count:
                            strip.setPixelColor(led_idx_2,Color(vr,vg,vb))
                    else:
                        (sr,sg,sb) = get_port_status_color(speed, poe, blink_on)
                        if 0<=led_idx_2<led_count:
                            strip.setPixelColor(led_idx_2, Color(sr,sg,sb))

                else:
                    # Single LED: Cycle between VLAN and Speed/PoE
                    led_idx_1 = leds_for_port[0]
                    cycle_mod = blink_cycle % 16
                    if cycle_mod < 10:
                        # VLAN color for 10 cycles
                        strip.setPixelColor(led_idx_1, Color(vr, vg, vb))
                    else:
                        # Stats
                        if speed==0 and poe==False:
                            strip.setPixelColor(led_idx, Color(vr,vg,vb))
                        else:
                            (sr,sg,sb)=get_port_status_color(speed,poe,blink_on)
                            strip.setPixelColor(led_idx, Color(sr,sg,sb))

            strip.show()

    # Start both threads
    t_http = threading.Thread(target=http_thread, daemon=True)
    t_led  = threading.Thread(target=led_thread, daemon=True)

    t_http.start()
    t_led.start()

    # main thread just waits
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        cleanup_and_exit()

if __name__ == "__main__":
    main()
