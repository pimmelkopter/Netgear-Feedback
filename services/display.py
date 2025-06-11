##services/display.py##
import qrcode
from PIL import Image, ImageDraw, ImageFont
import logging
from typing import Optional
from .lcd.LCD_1in44 import LCD_1in44
import time
import threading

logger = logging.getLogger(__name__)

class DisplayService:
    def __init__(self):
        self.lcd = None
        self.initialized = False
        self.backlight_on = False
        self.backlight_lock = threading.Lock()

    def init_display(self):
        """Initialize the LCD display"""
        try:
            self.lcd = LCD_1in44.LCD()
            self.lcd.LCD_Init(LCD_1in44.SCAN_DIR_DFT)
            self.lcd.LCD_Clear()
            self.set_Backlight(False)
            self.initialized = True
            return True
        except Exception as e:
            logger.error(f"Failed to initialize LCD display: {e}")
            self.initialized = False
            return False
        
    def set_backlight(self, on: bool):
        with self._backlight_lock:
            if self.initialized and self.lcd:
                self.lcd.bl_DutyCycle(100 if on else 0)
                self.backlight_on = on
        
    def show_wifi_qr(self, ssid: str, password: str, ip_address: str= "192.168.0.1"):
        """Generate and display a QR code for WiFi credentials"""
        if not self.initialized:
            return
        
        try:
            self.set_backlight(True)

            # Generate QR code
            wifi_string = f"WIFI:T:WPA;S:{ssid};P:{password};;"

            qr = qrcode.QRCode(
                version=1,
                error_correction=qrcode.constants.ERROR_CORRECT_L,
                box_size=2,
                border=4,
            )
            qr.add_data(wifi_string)
            qr.make(fit=True)

            # Create image
            qr_img = qr.make_image(fill_color="black", back_color="white")

            # Create display image
            image = Image.new("RGB", (128, 128), "WHITE")

            # Resize QR code to fit display
            qr_img = qr_img.resize((100, 100))
            image.paste(qr_img, (14, 5))

            # Add text
            draw = ImageDraw.Draw(image)
            draw.text((10, 108), ssid[:16], fill="BLACK")
            draw.text((10, 118), f"IP: {ip_address}", fill="BLACK")

            # Display the image
            self.lcd.LCD_ShowImage(image, 0, 0)
        
        except Exception as e:
            logger.error(f"Failed to show WiFi QR code: {e}")

    def show_vlan_menu(self, port: int, vlan: int, mode: str, has_changes: bool):
        if not self.initialized:
            return
        
        try:
            self.set_backlight(True)

            image = Image.new("RGB", (128,128), "WHITE")
            draw = ImageDraw.Draw(image)

            title = "VLAN Config" + (" *" if has_changes else "")
            draw.text((20, 5), title, fill="BLACK")

            port_y = 30
            if mode == 'port':
                draw.text((10, port_y), "<", fill="BLACK")
                draw.text((110, port_y), ">", fill="BLACK")
                draw.rectangle((25, port_y-2, 103, port_y+12), outline="BLACK")

            port_text = f"Port: {port}" 
            draw.text((35, port_y), port_text, fill="BLACK")

            vlan_y = 55
            if mode == 'vlan':
                draw.text((10, vlan_y), "<", fill="BLACK")
                draw.text((110, vlan_y), ">", fill="BLACK")
                draw.rectangle((25, vlan_y-2, 103, vlan_y+12), outline="BLACK")

            vlan_text = f"VLAN: {vlan}"
            draw.text((35, vlan_y), vlan_text, fill="BLACK")
            
            # Instructions
            draw.text((5, 85), "KEY1:Exit", fill="BLACK")
            draw.text((5, 98), "KEY2:Mode", fill="BLACK")
            draw.text((5, 111), "KEY3:Apply", fill="BLACK")
            
            # Show on display
            self.lcd.LCD_ShowImage(image, 0, 0)
            
        except Exception as e:
            logger.error(f"Error showing VLAN menu: {e}")
    
    def show_restore_menu(self, code_entered: int, code_length: int, remaining_time: int):
        """Display restore backup menu"""
        if not self.initialized:
            return
            
        try:
            self.set_backlight(True)
            
            # Create display image
            image = Image.new("RGB", (128, 128), "WHITE")
            draw = ImageDraw.Draw(image)
            
            # Title
            draw.text((15, 10), "Restore Backup?", fill="BLACK")
            
            # Instructions
            draw.text((10, 35), "Enter code:", fill="BLACK")
            
            # Progress indicators
            indicator_y = 55
            for i in range(code_length):
                x = 10 + i * 22
                if i < code_entered:
                    draw.ellipse((x, indicator_y, x+15, indicator_y+15), fill="BLACK")
                else:
                    draw.ellipse((x, indicator_y, x+15, indicator_y+15), outline="BLACK")
            
            # Countdown
            draw.text((40, 85), f"Time: {remaining_time}s", fill="BLACK")
            
            # Code hint (small text)
            draw.text((5, 110), "Use joystick", fill="GRAY")
            
            # Show on display
            self.lcd.LCD_ShowImage(image, 0, 0)
            
        except Exception as e:
            logger.error(f"Error showing restore menu: {e}")
    
    def show_message(self, message: str, duration: float = 2.0):
        """Show a simple message on display"""
        if not self.initialized:
            return
            
        try:
            self.set_backlight(True)
            
            # Create display image
            image = Image.new("RGB", (128, 128), "WHITE")
            draw = ImageDraw.Draw(image)
            
            # Center the message
            lines = message.split('\n')
            y_offset = 50 - (len(lines) * 10)
            
            for i, line in enumerate(lines):
                draw.text((10, y_offset + i*20), line, fill="BLACK")
            
            # Show on display
            self.lcd.LCD_ShowImage(image, 0, 0)
            
            # Auto-clear after duration
            if duration > 0:
                threading.Timer(duration, self.clear_display).start()
            
        except Exception as e:
            logger.error(f"Error showing message: {e}")
    
    def clear_display(self):
        """Clear display and turn off backlight"""
        if self.initialized and self.lcd:
            self.lcd.LCD_Clear()
            self.set_backlight(False)            

    def cleanup(self):
        """Cleanup the display resources"""
        if self.lcd:
            self.lcd.module_exit()
            self.clear_display()
        logger.info("Display resources cleaned up.")