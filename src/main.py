import time
import requests
import sys
import subprocess
import urllib3
import threading
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
    For LED #2, returns (r,g,b) depending on speed & PoE, plus blinking logic.
    speed=5 => gigabit -> green
    speed=4 => 100Mbit -> yellow
    speed=0 => black
    if poe_active => blink between base_color <-> blue
    else => solid base_color
    blink_on => toggles color if blinking
    """
    if speed == 5:
        base_color = (0, 255, 0)   # green
    elif speed == 4:
        base_color = (255, 165, 0) # yellow
    elif speed == 0:
        base_color = (0,0,0)       # black for no link
    else:
        base_color = (255, 165, 0) # yellow for unknown speed

    # If PoE is active and speed>0, we blink between base_color and Blue
    # If speed=0 => everything is black anyway.
    if poe_active and base_color != (0,0,0):
        # blink_on => base_color, else => Blue
        return base_color if blink_on else (0,0,255)
    else:
        # Not PoE or no link => just base_color (solid, no blink)
        #Helligkeit halbieren NUR für stats LED => r//2, g//2, b//2
        r, g, b = base_color
        base_color = (r // 2, g // 2, b // 2)
        return base_color

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
    port_stats = config.get('port_stats', False)
    leds_per_port = config.get('leds_per_port', 1)

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
        print(f"Could not retrieve device_info. Using fallback {port_count} ports. Error: {e}")

    # Determine LED mapping for ports
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

    # --- two threads for independent refresh time http_thread() und led_thread() ---

    # 1) Thread A: http_thread => 'update_interval' sek VLAN+Stats -> port_info_cache
    def http_thread():
        while True:
            time.sleep(update_interval)  # Warte das Intervall
            headers["Authorization"] = f"Bearer {token}"
            for port_id in range(1, port_count + 1):
                # VLAN
                try:
                    r_vlan = requests.get(
                        f"{base_url}/swcfg_port?portid={port_id}",
                        headers=headers, verify=False, timeout=3
                    )
                    r_vlan.raise_for_status()
                    port_cfg = r_vlan.json().get("switchPortConfig", {})
                    vlan_id = port_cfg.get("portVlanId", 1)
                    # pick color
                    if vlan_id in vlan_color_map:
                        port_info_cache[port_id]["vlan_color"] = vlan_color_map[vlan_id]
                    else:
                        port_info_cache[port_id]["vlan_color"] = default_vlan_color
                except Exception as ex:
                    print(f"Switch unreachable => Exiting: {ex}")
                    cleanup_and_exit()

                # Stats
                if port_stats:
                    try:
                        r_stat = requests.get(
                            f"{base_url}/sw_portstats?portid={port_id}",
                            headers=headers, verify=False, timeout=3
                        )
                        r_stat.raise_for_status()
                        stats_data = r_stat.json().get("switchStatsPort", {})
                        parsed_speed = parse_speed(stats_data)
                        parsed_poe = parse_poe(stats_data)
                        port_info_cache[port_id]["speed"] = parsed_speed
                        port_info_cache[port_id]["poe_active"] = parsed_poe
                    except:
                        port_info_cache[port_id]["speed"] = 0
                        port_info_cache[port_id]["poe_active"] = False
            
            def parse_speed(stats_data):
                # 1) Check if oprState != 1 => treat as no link
                opr_state = stats_data.get("oprState", -1)
                if opr_state != 1:
                    return 0  # "speed=0" => no link

                # 2) Check 'speed' field
                # Empirisch: 7 => 1G, 6 => 100M? 130 => no link?
                raw_speed = stats_data.get("speed", -1)
                if raw_speed == 7:
                    return 5  # 5 => "Gigabit" (für deine Logik)
                elif raw_speed == 3:
                    return 4  # 4 => "100Mbit"
                elif raw_speed == 130:
                    return 0
                else:
                    # fallback => unknown => treat as 4 or 0?
                    return 4
                
            def parse_poe(stats_data):
                poe_code = stats_data.get("poeStatus", 0)
                # Evtl. 2 => PoE in Usage, 1 => PoE enabled but no draw?
                # Du könntest definieren: poe_active = (poe_code >= 2)
                if poe_code >= 2:
                    return True
                else:
                    return False



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

                # VLAN color from cache
                (vr, vg, vb) = port_info_cache[port_id]["vlan_color"]

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

                    # LED #2 -> Speed/PoE
                    led_idx_2 = leds_for_port[1]
                    if 0 <= led_idx_2 < led_count:
                        stat_cycle_mod = blink_cycle % 4  # 4-cycle pattern: 2 cycles speed, 2 cycles PoE
                        if stat_cycle_mod < 2:
                            speed = port_info_cache[port_id]["speed"]
                            (sr, sg, sb) = get_port_status_color(speed, poe_active=False, blink_on=blink_on)
                            strip.setPixelColor(led_idx_2, Color(sr, sg, sb))
                        else:
                            poe = port_info_cache[port_id]["poe_active"]
                            (pr, pg, pb) = get_port_status_color(speed=0, poe_active=poe, blink_on=blink_on)
                            strip.setPixelColor(led_idx_2, Color(pr, pg, pb))
                else:
                    # only 1 LED mapped => cycle approach
                    led_idx_1 = leds_for_port[0]
                    if 0 <= led_idx_1 < led_count:
                        cycle_mod = blink_cycle % 16
                        if cycle_mod < 10:
                            strip.setPixelColor(led_idx_1, Color(vr, vg, vb))
                        elif cycle_mod % 4 < 2:
                            # 6 cycles alternating speed (2 cycles each)
                            speed = port_info_cache[port_id]["speed"]
                            (sr, sg, sb) = get_port_status_color(speed, poe_active=False, blink_on=blink_on)
                            strip.setPixelColor(led_idx_1, Color(sr, sg, sb))
                        else:
                            # 6 cycles alternating PoE (2 cycles each)
                            poe = port_info_cache[port_id]["poe_active"]
                            (pr, pg, pb) = get_port_status_color(speed=0, poe_active=poe, blink_on=blink_on)
                            strip.setPixelColor(led_idx_1, Color(pr, pg, pb))

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
