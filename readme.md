Script for VLAN-ID LED Feedback for Netgear AV-Line Switches

Requirements:
Raspi with pios/ pios lite, WS2812B

- **WS2812b DATA** -> **GPIO 18** (you can change this under config.json)
- **+5V** -> **5V** 
- **GND** -> **GND** 

git clone repository
cd into cloned repository
nano settings/config.json
customize your settings

chmod +x setup/setup.sh
./setup/setup.sh
if you need a hotspot for ssh access ./setup/fixed-hotspot.sh
nano settings/secrets.json
enter your credentials
./update.sh

if you need to change any settings in config.json just run ./update.sh afterwards

ToDos
-tidy up
-add poe-status functionality
-add link-status functionality
-add functionality to retrieve vlans and colors out of cfg file
-add web-gui
    - random wifi ap
    - show ports with vlan, poe and link status
    - if multiple switches are found switch-selector
    - password-protected vlan changing
    - password-protected save and reboot
    - password-protected cfg file uploader
    - logs
-test on pi zero
-port to esp32