import requests
import time
from rpi_ws281x import Color, PixelStrip, ws

# LED strip configuration:
LED_COUNT = 48          # Total number of LED pixels (2 per port for 24 ports).
LED_PIN = 18            # GPIO pin connected to the pixels (must support PWM!).
LED_FREQ_HZ = 800000    # LED signal frequency in hertz (usually 800khz).
LED_DMA = 10            # DMA channel to use for generating signal (try 10).
LED_BRIGHTNESS = 255    # Set to 0 for darkest and 255 for brightest.
LED_INVERT = False      # True to invert the signal (when using NPN transistor level shift).
LED_CHANNEL = 0
LED_STRIP = ws.WS2812_STRIP

# Mock API server configuration:
BASE_URL = "https://c8a21383-bf5e-41f3-b11e-46b83dbbcb45.mock.pstmn.io/api/v1"
LOGIN_ENDPOINT = f"{BASE_URL}/login"
PORT_ENDPOINT = f"{BASE_URL}/swcfg_port"

# Login credentials:
USERNAME = "admin"
PASSWORD = "Aud1luma#"

# Function to log in to the server and retrieve the token:
def login():
    response = requests.post(LOGIN_ENDPOINT, json={"username": USERNAME, "password": PASSWORD})
    response.raise_for_status()
    return response.json()["login"]["token"]

# Function to get VLAN information for a specific port:
def get_port_vlan(token, port_id):
    headers = {"Authorization": f"Bearer {token}"}
    response = requests.get(f"{PORT_ENDPOINT}?portid={port_id}", headers=headers)
    response.raise_for_status()
    return response.json()["switchPortConfig"]

# Function to set the color of two LEDs for a specific port:
def set_led_color(strip, port_id, color):
    led_index = (port_id - 1) * 2
    strip.setPixelColor(led_index, color)
    strip.setPixelColor(led_index + 1, color)
    strip.show()

# Main function:
def main():
    # Initialize LED strip:
    strip = PixelStrip(LED_COUNT, LED_PIN, LED_FREQ_HZ, LED_DMA, LED_INVERT, LED_BRIGHTNESS, LED_CHANNEL, LED_STRIP)
    strip.begin()

    # Login to server:
    try:
        token = login()
    except Exception as e:
        print(f"Login failed: {e}")
        return

    # Iterate through port IDs and control LEDs:
    for port_id in range(1, 25):
        try:
            port_config = get_port_vlan(token, port_id)
            vlan_id = port_config.get("portVlanId")

            if vlan_id == 100:
                set_led_color(strip, port_id, Color(255, 0, 0))  # Red for VLAN 100
            elif vlan_id == 200:
                set_led_color(strip, port_id, Color(0, 255, 0))  # Green for VLAN 200
            elif vlan_id == 1:
                set_led_color(strip, port_id, Color(0, 0, 255))
            else:
                set_led_color(strip, port_id, Color(0, 0, 0))  # Off for other VLANs

            print(f"Port {port_id}: VLAN {vlan_id} -> LEDs updated.")
        except Exception as e:
            print(f"Failed to get or update port {port_id}: {e}")

        # Optional delay for smoother updates:
        time.sleep(0.1)

if __name__ == "__main__":
    main()