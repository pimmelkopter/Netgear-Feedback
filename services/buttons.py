##services/buttons.py##
import gpiozero as GPIO
import time
import threading
import logging
from typing import Callable, Dict, Optional, Set, Tuple
from datetime import datetime

logger = logging.getLogger(__name__)

class ButtonService:
    """Service to handle button inputs from the 1.44inch LCD HAT"""
    
    # GPIO Pin definitions from documentation
    BUTTON_PINS = {
        'KEY1': 21,
        'KEY2': 20,
        'KEY3': 16,
        'UP': 6,
        'DOWN': 19,
        'LEFT': 5,
        'RIGHT': 26,
        'PRESS': 13
    }
    
    def __init__(self, hotspot_callback: Optional[Callable] = None, 
                 display_callback: Optional[Callable] = None,
                 switch_api_callback: Optional[Callable] = None):
        """
        Initialize button service
        
        Args:
            hotspot_callback: Function to call for hotspot actions
            display_callback: Function to call for display updates
            switch_api_callback: Function to call for switch API actions
        """
        self.hotspot_callback = hotspot_callback
        self.display_callback = display_callback
        self.switch_api_callback = switch_api_callback
        
        # Button state tracking
        self.button_states = {btn: False for btn in self.BUTTON_PINS}
        self.button_press_times = {btn: 0 for btn in self.BUTTON_PINS}
        self.pressed_buttons: Set[str] = set()
        
        # Menu state
        self.menu_active = False
        self.menu_mode = None  # 'vlan_edit', 'restore_backup'
        self.vlan_edit_state = {
            'selected_port': 1,
            'selected_vlan': 1,
            'edit_mode': 'port',  # 'port' or 'vlan'
            'pending_changes': {},  # port_id: vlan_id
            'original_vlans': {}  # port_id: original_vlan_id
        }
        
        # Restore backup state
        self.restore_state = {
            'code_sequence': [],
            'expected_code': ['UP', 'RIGHT', 'DOWN', 'LEFT', 'PRESS'],
            'timeout_start': None
        }
        
        # Threading
        self._running = False
        self._monitor_thread = None
        self._lock = threading.Lock()
        
        # Display sleep state
        self.display_sleeping = True
        self.last_activity = time.time()
        self.sleep_timeout = 60  # seconds
        
        # GPIO setup flag
        self.gpio_initialized = False
        
    def init_gpio(self) -> bool:
        """Initialize GPIO pins for button inputs"""
        try:
            # Check if already initialized
            if self.gpio_initialized:
                return True
                
            GPIO.setmode(GPIO.BCM)
            GPIO.setwarnings(False)
            
            # Setup all button pins as inputs with pull-up resistors
            for button_name, pin in self.BUTTON_PINS.items():
                try:
                    GPIO.setup(pin, GPIO.IN, pull_up_down=GPIO.PUD_UP)
                    logger.info(f"Initialized {button_name} on GPIO{pin}")
                except Exception as e:
                    logger.error(f"Failed to setup {button_name} on GPIO{pin}: {e}")
                    
            self.gpio_initialized = True
            return True
            
        except Exception as e:
            logger.error(f"GPIO initialization failed: {e}")
            return False
    
    def start(self):
        """Start button monitoring"""
        if not self.init_gpio():
            logger.warning("Button service starting without GPIO support")
            return
            
        self._running = True
        self._monitor_thread = threading.Thread(target=self._monitor_buttons, daemon=True)
        self._monitor_thread.start()
        logger.info("Button service started")
    
    def stop(self):
        """Stop button monitoring"""
        self._running = False
        if self._monitor_thread:
            self._monitor_thread.join(timeout=1)
        if self.gpio_initialized:
            GPIO.cleanup(list(self.BUTTON_PINS.values()))
        logger.info("Button service stopped")
    
    def _monitor_buttons(self):
        """Main button monitoring loop"""
        while self._running:
            try:
                current_time = time.time()
                
                # Check each button
                for button_name, pin in self.BUTTON_PINS.items():
                    is_pressed = GPIO.input(pin) == 0  # Active low
                    
                    with self._lock:
                        # Button press detection
                        if is_pressed and not self.button_states[button_name]:
                            # Button just pressed
                            self.button_states[button_name] = True
                            self.button_press_times[button_name] = current_time
                            self.pressed_buttons.add(button_name)
                            self._on_button_press(button_name)
                            
                        elif not is_pressed and self.button_states[button_name]:
                            # Button just released
                            self.button_states[button_name] = False
                            press_duration = current_time - self.button_press_times[button_name]
                            self.pressed_buttons.discard(button_name)
                            self._on_button_release(button_name, press_duration)
                
                # Check for long press conditions
                self._check_long_press_conditions(current_time)
                
                # Check display sleep timeout
                if not self.display_sleeping and (current_time - self.last_activity) > self.sleep_timeout:
                    self._sleep_display()
                
                time.sleep(0.01)  # 10ms polling rate
                
            except Exception as e:
                logger.error(f"Error in button monitor: {e}")
                time.sleep(0.1)
    
    def _on_button_press(self, button: str):
        """Handle button press events"""
        logger.debug(f"Button pressed: {button}")
        self.last_activity = time.time()
        
        # Wake display on any button press
        if self.display_sleeping:
            self._wake_display()
            return
        
        # Handle menu navigation
        if self.menu_active:
            if self.menu_mode == 'vlan_edit':
                self._handle_vlan_menu_input(button, 'press')
            elif self.menu_mode == 'restore_backup':
                self._handle_restore_input(button)
    
    def _on_button_release(self, button: str, duration: float):
        """Handle button release events"""
        logger.debug(f"Button released: {button} (held for {duration:.2f}s)")
        
        # Don't process releases in menus
        if self.menu_active:
            return
    
    def _check_long_press_conditions(self, current_time: float):
        """Check for special long press combinations"""
        with self._lock:
            # Check KEY1 + KEY3 for restore backup
            if 'KEY1' in self.pressed_buttons and 'KEY3' in self.pressed_buttons:
                press_time = min(
                    current_time - self.button_press_times['KEY1'],
                    current_time - self.button_press_times['KEY3']
                )
                if press_time >= 10.0 and not self.menu_active:
                    self._start_restore_backup_menu()
            
            # Check KEY2 for VLAN edit menu
            if 'KEY2' in self.pressed_buttons and not self.menu_active:
                press_time = current_time - self.button_press_times['KEY2']
                if press_time >= 5.0:
                    self._start_vlan_edit_menu()
    
    def _wake_display(self):
        """Wake the display and activate hotspot"""
        self.display_sleeping = False
        self.last_activity = time.time()
        
        if self.display_callback:
            self.display_callback('wake')
        
        # Activate hotspot with new credentials
        if self.hotspot_callback:
            self.hotspot_callback('activate_new')
    
    def _sleep_display(self):
        """Put display to sleep"""
        self.display_sleeping = True
        
        if self.display_callback:
            self.display_callback('sleep')
    
    def _start_vlan_edit_menu(self):
        """Start VLAN edit menu"""
        self.menu_active = True
        self.menu_mode = 'vlan_edit'
        
        # Get current port VLANs
        if self.switch_api_callback:
            port_vlans = self.switch_api_callback('get_port_vlans')
            self.vlan_edit_state['original_vlans'] = port_vlans.copy()
            self.vlan_edit_state['selected_vlan'] = port_vlans.get(1, 1)
        
        self._update_vlan_display()
        logger.info("Started VLAN edit menu")
    
    def _handle_vlan_menu_input(self, button: str, event_type: str):
        """Handle input in VLAN edit menu"""
        if event_type != 'press':
            return
            
        state = self.vlan_edit_state
        
        if button == 'KEY1':  # Escape
            self._exit_vlan_menu(save=False)
            
        elif button == 'KEY2':  # Mode toggle
            state['edit_mode'] = 'vlan' if state['edit_mode'] == 'port' else 'port'
            self._update_vlan_display()
            
        elif button == 'KEY3':  # Enter/Save
            if state['pending_changes']:
                self._save_vlan_changes()
            else:
                # Apply current selection
                port = state['selected_port']
                vlan = state['selected_vlan']
                if port not in state['pending_changes'] or state['pending_changes'][port] != vlan:
                    state['pending_changes'][port] = vlan
                    self._update_vlan_display()
            
        elif button in ['LEFT', 'RIGHT']:
            if state['edit_mode'] == 'port':
                # Navigate ports
                max_port = 24  # TODO: Get from config
                if button == 'LEFT':
                    state['selected_port'] = max(1, state['selected_port'] - 1)
                else:
                    state['selected_port'] = min(max_port, state['selected_port'] + 1)
                
                # Update selected VLAN to current port's VLAN
                current_vlan = state['pending_changes'].get(
                    state['selected_port'],
                    state['original_vlans'].get(state['selected_port'], 1)
                )
                state['selected_vlan'] = current_vlan
                
            else:  # VLAN mode
                # Navigate VLANs
                available_vlans = [1, 10, 11, 12, 20, 21, 22, 30, 31, 50, 90, 99]  # TODO: Get from config
                current_idx = available_vlans.index(state['selected_vlan']) if state['selected_vlan'] in available_vlans else 0
                
                if button == 'LEFT':
                    new_idx = (current_idx - 1) % len(available_vlans)
                else:
                    new_idx = (current_idx + 1) % len(available_vlans)
                
                state['selected_vlan'] = available_vlans[new_idx]
            
            self._update_vlan_display()
    
    def _update_vlan_display(self):
        """Update VLAN edit menu display"""
        if not self.display_callback:
            return
            
        state = self.vlan_edit_state
        has_changes = bool(state['pending_changes'])
        
        display_data = {
            'type': 'vlan_menu',
            'port': state['selected_port'],
            'vlan': state['selected_vlan'],
            'mode': state['edit_mode'],
            'has_changes': has_changes,
            'pending_changes': state['pending_changes']
        }
        
        self.display_callback('update_menu', display_data)
    
    def _save_vlan_changes(self):
        """Save VLAN changes to switch"""
        if self.switch_api_callback and self.vlan_edit_state['pending_changes']:
            success = self.switch_api_callback('set_port_vlans', self.vlan_edit_state['pending_changes'])
            if success:
                logger.info(f"Saved VLAN changes: {self.vlan_edit_state['pending_changes']}")
                self._exit_vlan_menu(save=True)
            else:
                logger.error("Failed to save VLAN changes")
                if self.display_callback:
                    self.display_callback('show_error', "Failed to save changes")
    
    def _exit_vlan_menu(self, save: bool = False):
        """Exit VLAN edit menu"""
        self.menu_active = False
        self.menu_mode = None
        
        if not save:
            self.vlan_edit_state['pending_changes'].clear()
        
        self.vlan_edit_state['selected_port'] = 1
        self.vlan_edit_state['edit_mode'] = 'port'
        
        if self.display_callback:
            self.display_callback('clear_menu')
        
        logger.info("Exited VLAN edit menu")
    
    def _start_restore_backup_menu(self):
        """Start restore backup menu"""
        self.menu_active = True
        self.menu_mode = 'restore_backup'
        self.restore_state['code_sequence'] = []
        self.restore_state['timeout_start'] = time.time()
        
        # Get expected code from config
        if self.switch_api_callback:
            config_code = self.switch_api_callback('get_restore_code')
            if config_code:
                self.restore_state['expected_code'] = config_code.split(',')
        
        self._update_restore_display()
        logger.info("Started restore backup menu")
    
    def _handle_restore_input(self, button: str):
        """Handle input in restore backup menu"""
        # Map joystick buttons to directions
        direction_map = {
            'UP': 'UP',
            'DOWN': 'DOWN',
            'LEFT': 'LEFT',
            'RIGHT': 'RIGHT',
            'PRESS': 'PRESS'
        }
        
        if button in direction_map:
            self.restore_state['code_sequence'].append(direction_map[button])
            self._update_restore_display()
            
            # Check if code is complete
            if len(self.restore_state['code_sequence']) == len(self.restore_state['expected_code']):
                if self.restore_state['code_sequence'] == self.restore_state['expected_code']:
                    self._execute_restore_backup()
                else:
                    self._exit_restore_menu(success=False)
    
    def _update_restore_display(self):
        """Update restore backup display"""
        if not self.display_callback:
            return
            
        remaining_time = 10 - (time.time() - self.restore_state['timeout_start'])
        
        if remaining_time <= 0:
            self._exit_restore_menu(success=False)
            return
        
        display_data = {
            'type': 'restore_menu',
            'code_entered': len(self.restore_state['code_sequence']),
            'code_length': len(self.restore_state['expected_code']),
            'remaining_time': int(remaining_time)
        }
        
        self.display_callback('update_menu', display_data)
    
    def _execute_restore_backup(self):
        """Execute restore backup"""
        if self.switch_api_callback:
            if self.display_callback:
                self.display_callback('show_message', "Restoring backup...")
                
            success = self.switch_api_callback('restore_backup')
            self._exit_restore_menu(success=success)
    
    def _exit_restore_menu(self, success: bool = False):
        """Exit restore backup menu"""
        self.menu_active = False
        self.menu_mode = None
        
        if self.display_callback:
            if success:
                self.display_callback('show_message', "Backup restored! Rebooting...")
            else:
                self.display_callback('clear_menu')
        
        logger.info(f"Exited restore menu (success: {success})")
    
    def set_expected_restore_code(self, code: str):
        """Set the expected restore code sequence"""
        self.restore_state['expected_code'] = code.upper().split(',')
        logger.info(f"Set restore code sequence: {self.restore_state['expected_code']}")
    
    def is_menu_active(self) -> bool:
        """Check if any menu is currently active"""
        return self.menu_active
    
    def get_button_states(self) -> Dict[str, bool]:
        """Get current button states"""
        with self._lock:
            return self.button_states.copy()