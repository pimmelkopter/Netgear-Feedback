# Netgear AV-Line VLAN-ID LED Feedback
**For Netgear M4250 Series**

## Features

- **Netgear Visual Feedback via LEDs**: Displays assigned VLAN, port link status, and POE active indicator.
- **Netgear VLAN Assignment via Web GUI over WiFi**
- **Save, Reboot, and Load Backup-Config Functionality via WiFi**



**Functions:**
- **Network Scan**: Scans for a switch or a fixed IP address (e.g., OBB Port).
- **Port Detection**: Automatically determines the number of ports on the switch.
- **Flexible LED Mapping Modes**: Offers various LED mapping modes depending on the wiring setup.
- **Single LED Mode**: Cycles between VLAN color, POE-active status, and link speed (green for gigabit, orange for 100 Mbit).
- **Dynamic VLAN Color Assignment**: When `scan_vlans=true` is set in the configuration, it fetches VLAN colors and names from the switch’s config file, then disables further scanning and writes the discovered VLANs into the config for later adjustment.
- **Fixed VLAN Colors**: Alternatively, it can work with predefined VLAN colors.
- **Port Statistics**: Updates port (link and POE) status at a configurable interval (default: 5 seconds).
- **VLAN Updates**: Occur every 30 seconds or when updated via the web GUI.
- **Hotspot Timeout**: Hotspot will turn off after 5 minutes - can be changed in config.json

**Upcoming Features:**
- Support for multiple switches on the network.
- Porting to ESP32 with an Ethernet interface.

> **Note:** Although most of the code was written with the help of chatbots, I have invested a significant amount of my free time in this project. If you wish to use the code commercially, please send me an email.

---

## 📌 Requirements

- **Raspberry Pi** with **Raspberry Pi OS** (Lite is recommended)
- **WS2812B LED Strip**
- Wiring:
  - **DATA** → **GPIO 18** *(configurable in `config.json`)*
  - **+5V** → **5V**
  - **GND** → **GND**

---

## 🚀 Installation & Setup

```bash
sudo apt-get update && sudo apt-get install git -y
git clone https://github.com/pimmelkopter/Netgear-Feedback.git
cd Netgear-Feedback
```

🔧 Adjust Configuration

```bash
nano config/config.json  # Customize settings as needed
mv config/secrets_initial.json config/secrets.json
nano config/secrets.json  # Enter your netgear-switch credentials
```

🛠 Start Installation

```bash
chmod +x setup/setup.sh
./setup/setup.sh
```

If you change config.json, simply run the update script:

```bash
./setup/dev_tools/update.sh
```

---

## ⚙️ Port-Mapping-Modes (utils.py)

The **Port-Mapping-Generator** (`utils.py`) creates an association between **Switch-Ports and LEDs** depending on your setup - check **config.json** for this.

**Available Modes:**
- `linear` → Ports 1..port_count in ascending order
- `odd_even-linear` → First odd-numbered ports, then even-numbered ports (both in ascending order)
- `odd_even-even_reversed` → Odd-numbered ports in ascending order, even-numbered ports in descending order
- `odd_even-odd_reversed` → Odd-numbered ports in descending order, even-numbered ports in ascending order
- `odd_even-reversed` → Both odd and even ports in descending order  
*(Fallback → `linear`)*

### ➕ Configuring LED Gaps
- **`gap_start`** → Offset before the first port
- **`gap_end`** → Offset after the last port
- **`gap_between_rows`** → Only for separate odd/even blocks
- **`block_size, gap_after_block`** → After `block_size` ports skip `gap_after_block` LEDs 

⏩ **Beispiel**:  
`odd_even-linear` → Odd ports ascending, then even ports ascending  
`odd_even-even_reversed` → Odd ports ascending, even ports descending 

---

## 🎨 VLAN-Farbzuordnung

- Defined in `config.json` as a **Mapping from VLAN-IDs to RGB-Colors**.
- If you use `scan_vlans=true` **VLAN Names** will be pulled from the device config and mapped to vlan_color_map.
- Format:  
  ```json
  "vlan_color_map": "100:255,0,0;200:0,255,0"
  ```
- Parsed into:  
  ```python
  {100: (255,0,0), 200: (0,255,0)}
  ```

---
