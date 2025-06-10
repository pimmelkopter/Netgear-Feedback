##services/config.py##
from pathlib import Path
from typing import Dict, Optional, Any
import threading
import json
import logging

logger = logging.getLogger(__name__)

class Config:
    _instance = None
    _lock = threading.Lock()
    _config: Dict = {}
    _secrets: Dict = {}
    
    def __new__(cls):
        with cls._lock:
            if cls._instance is None:
                cls._instance = super().__new__(cls)
                cls._load()
        return cls._instance
    
    def get_config(self) -> dict:
        """Return complete config dictionary"""
        return self._config

    def save_config(self, config: dict):
        """Save config to file"""
        self._config = config
        base_path = Path(__file__).parent.parent
        with open(base_path / 'config' / 'config.json', 'w') as f:
            json.dump(config, f, indent=2)

    @classmethod
    def _load(cls) -> None:
        base_path = Path(__file__).parent.parent
        try:
            with open(base_path / 'config' / 'config.json') as f:
                cls._config = json.load(f)
            with open(base_path / 'config' / 'secrets.json') as f:
                cls._secrets = json.load(f)
            cls._validate()
        except Exception as e:
            logger.error(f"Config load error: {e}")
            raise

    @classmethod
    def _validate(cls) -> None:
        required = ['led_count', 'led_pin', 'switch_ip']
        missing = [field for field in required if field not in cls._config]
        if missing:
            raise ValueError(f"Missing required config fields: {', '.join(missing)}")

    @property
    def switch_ip(self) -> str:
        return self._config.get('switch_ip', '')
    
    @switch_ip.setter  # Nur switch_ip hat einen Setter
    def switch_ip(self, value: str):
        self._config['switch_ip'] = value

    @property
    def base_url_suffix(self) -> str:
        return self._config.get('base_url_suffix', ':8443/api/v1')

    @property
    def led_count(self) -> int:
        return int(self._config.get('led_count', 48))

    @property
    def led_pin(self) -> int:
        return int(self._config.get('led_pin', 18))

    @property
    def led_brightness(self) -> int:
        return int(self._config.get('led_brightness', 255))

    @property
    def port_count(self) -> int:
        return int(self._config.get('fixed_port_count', 24))
    
    @port_count.setter
    def port_count(self, value: int):
        self._config['fixed_port_count'] = value

    @property
    def update_interval(self) -> int:
        return int(self._config.get('update_interval', 15))

    @property
    def scan_vlans(self) -> bool:
        return bool(self._config.get('scan_vlans', False))
    
    @scan_vlans.setter
    def scan_vlans(self, value: bool):
        self._config['scan_vlans'] = value

    @property
    def port_stats(self) -> bool:
        return bool(self._config.get('port_stats', False))

    @property
    def username(self) -> str:
        return self._secrets.get('username', '')

    @property
    def password(self) -> str:
        return self._secrets.get('password', '')

    def get(self, key: str, default: Any = None) -> Any:
        return self._config.get(key, default)
    
    @property
    def ip_scan(self) -> bool:
        return bool(self._config.get('ip_scan', True))

    @property
    def scan_base(self) -> str:
        return self._config.get('scan_base', '10.18.254')

    @property
    def scan_range_start(self) -> int:
        return int(self._config.get('scan_range_start', 145))

    @property
    def scan_range_end(self) -> int:
        return int(self._config.get('scan_range_end', 160))
    
    @property
    def locked_ports(self) -> list:
        """Get list of locked ports that cannot be modified via web interface"""
        return self._config.get('locked_ports', [])

    @property
    def hotspot_button_pin(self) -> int:
        """Get GPIO pin number for hotspot control button"""
        return int(self._config.get('hotspot_button_pin', 23))
    
    @property
    def hotspot_timeout(self) -> str:
        """ Get hotspot timeout"""
        return str(self._config.get('hotspot_timeout', 300))