Script for VLAN-ID LED Feedback for Netgear AV-Line Switches

**Requirements:**
- Raspi with pios/ pios lite, WS2812B

- **WS2812b DATA** -> **GPIO 18** (you can change this under config.json)
- **+5V** -> **5V** 
- **GND** -> **GND** 

**How to use**
- sudo apt-get update -y && sudo apt-get upgrade -y
- sudo apt-get install git -y
- git clone https://github.com/pimmelkopter/Netgear-Feedback.git
- cd Netgear-Feedback
- customize your settings with: nano config/config.json
- create secrets.json: mv config/secrets_initial.json config/secrets.json
- enter your credentials: nano config/secrets.json
- chmod +x setup/setup.sh
- ./setup/setup.sh
- if you need to change any settings in config.json just run ./update.sh afterwards

**ToDos**
- tidy up
- add poe-status functionality
- add link-status functionality
- add functionality to retrieve vlans and colors out of cfg file
- add web-gui
    - random wifi ap
    - show ports with vlan, poe and link status
    - if multiple switches are found switch-selector
    - password-protected vlan changing
    - password-protected save and reboot
    - password-protected cfg file uploader
    - logs
- test on pi zero
- port to esp32


    utils.py port mapping generator:
    Generates a dict {port_id: [ledIndices]} based on the chosen mode:
      'linear': just 1..port_count in ascending order
      'odd_even-linear': odd asc, then even asc
      'odd_even-even_reversed': odd asc, then even desc
      'odd_even-odd_reversed': odd desc, then even asc
      'odd_even-reversed': odd desc, then even desc
      (fallback => 'linear')

    Gaps:
      gap_start:     extra LED offset before the first port
      gap_end:       extra LED offset after the last port
      gap_between_rows: used only when we have separate "odd" and "even" blocks
      block_size, gap_after_block:
                      after 'block_size' ports, skip 'gap_after_block' LEDs
                      
    Returns a dict: {port_id: [ledIndex,...], ...}
    """

    E.g. 'odd_even-linear' => odd asc, even asc
        #    'odd_even-even_reversed' => odd asc, even desc, etc.

    VLAN Color map:
      """
      Expects e.g. '100:255,0,0;200:0,255,0'
      Returns a dict {100: (255,0,0), 200: (0,255,0)}
      """