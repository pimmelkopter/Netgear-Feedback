#!/usr/bin/env bash
set -e

sudo raspi-config nonint do_wifi_country DE
sudo nmcli connection add type wifi ifname wlan0 con-name "MyHotspot" autoconnect yes \ssid "Test-AP" mode ap
sudo nmcli connection modify "MyHotspot" \802-11-wireless-security.key-mgmt wpa-psk \802-11-wireless-security.psk "netgear12345678"
sudo nmcli connection modify "MyHotspot" ipv4.method shared
sudo nmcli connection modify "MyHotspot" ipv4.addresses 192.168.0.1/24
sudo nmcli connection modify "MyHotspot" ipv6.method ignore
sudo nmcli connection up "MyHotspot"