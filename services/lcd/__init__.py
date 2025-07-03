"""
LCD‑Treiber‑Sub­paket.

Stellt den Treiber für das 1.44‑Zoll‑Waveshare‑HAT sowie
die dazugehörigen Konstanten direkt im Paket­namen bereit.
"""

# ---------------------------------------------------------
# Öffentliche Re‑Exports
# ---------------------------------------------------------
from .LCD_1in44 import (
    LCD,              # Klassenname im Originalmodul
    SCAN_DIR_DFT,     # Standard‑Scanrichtung
    L2R_U2D, L2R_D2U, R2L_U2D, R2L_D2U,
    U2D_L2R, U2D_R2L, D2U_L2R, D2U_R2L
)

# Alias, damit Aufrufe wie LCD_1in44(...) oder lcd.LCD_1in44 funktionieren
LCD_1in44 = LCD

__all__ = [
    "LCD",
    "LCD_1in44",
    "SCAN_DIR_DFT",
    "L2R_U2D", "L2R_D2U", "R2L_U2D", "R2L_D2U",
    "U2D_L2R", "U2D_R2L", "D2U_L2R", "D2U_R2L",
]
