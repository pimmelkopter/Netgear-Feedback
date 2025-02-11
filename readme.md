Hier ist eine aktualisierte und leserlich formatierte `README.md`, die deinen Inhalt beibehält, aber besser strukturiert ist:

---

# Netgear AV-Line VLAN-ID LED Feedback

Dieses Projekt zeigt den VLAN-Status von **Netgear AV-Line Switches** mit **WS2812B LEDs** an.

## 📌 Anforderungen

- **Raspberry Pi** mit **Raspberry Pi OS (Lite empfohlen)**
- **WS2812B LED-Streifen**
- Verkabelung:
  - **DATA** -> **GPIO 18** *(konfigurierbar in `config.json`)*
  - **+5V** -> **5V**
  - **GND** -> **GND**

## 🚀 Installation & Setup

```bash
sudo apt-get update && sudo apt-get install git -y
git clone https://github.com/pimmelkopter/Netgear-Feedback.git
cd Netgear-Feedback
```

### 🔧 Konfiguration anpassen

```bash
nano config/config.json  # Einstellungen anpassen
mv config/secrets_initial.json config/secrets.json
nano config/secrets.json  # Zugangsdaten eintragen
```

### 🛠 Installation starten

```bash
chmod +x setup/setup.sh
./setup/setup.sh
```

Falls `config.json` geändert wurde, führe einfach das Update-Skript aus:

```bash
./setup/dev_tools/update.sh
```

---

## ⚙️ Port-Mapping-Modi (utils.py)

Der **Port-Mapping-Generator** (`utils.py`) erzeugt eine Zuordnung von **Switch-Ports zu LED-Indizes**.

**Verfügbare Modi:**
- `linear` → 1..port_count in aufsteigender Reihenfolge
- `odd_even-linear` → erst ungerade, dann gerade Ports (beide aufsteigend)
- `odd_even-even_reversed` → ungerade aufsteigend, gerade absteigend
- `odd_even-odd_reversed` → ungerade absteigend, gerade aufsteigend
- `odd_even-reversed` → ungerade & gerade absteigend  
*(Fallback → `linear`)*

### ➕ LED-Lücken konfigurieren
- **`gap_start`** → Offset vor dem ersten Port
- **`gap_end`** → Offset nach dem letzten Port
- **`gap_between_rows`** → Nur für getrennte ungerade/gerade Blöcke
- **`block_size, gap_after_block`** → Nach `block_size` Ports wird `gap_after_block` LEDs übersprungen

⏩ **Beispiel**:  
`odd_even-linear` → Ungerade aufsteigend, danach gerade aufsteigend  
`odd_even-even_reversed` → Ungerade aufsteigend, gerade absteigend  

---

## 🎨 VLAN-Farbzuordnung

- Definiert in `config.json` als **Mapping von VLAN-IDs zu RGB-Farben**.
- Format:  
  ```json
  "vlan_color_map": "100:255,0,0;200:0,255,0"
  ```
- Rückgabe:  
  ```python
  {100: (255,0,0), 200: (0,255,0)}
  ```

---

🔥 **Viel Spaß mit Netgear VLAN-Feedback!** 🚀