##services/config.py##
from pathlib import Path
from typing import Dict, Optional, Any
import json
import logging
import threading

logger = logging.getLogger(__name__)

class Config:
    """Thread-safe singleton configuration manager"""
    _instance = None
    _lock = threading.Lock()
    _config: Dict = {}
    _secrets: Dict = {}

    def __new__(cls):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:  # Double-check pattern
                    cls._instance = super().__new__(cls)
                    cls._load()
        return cls._instance

    def get_config(self) -> dict:
        """Return complete config dictionary"""
        return self._config.copy()  # Return copy to prevent direct modification

    def save_config(self, config: dict):
        """Save config to file with thread safety"""
        with self._lock:
            self._config = config
            try:
                base_path = Path(__file__).parent.parent
                with open(base_path / 'config' / 'config.json', 'w') as f:
                    json.dump(config, f, indent=2)
            except Exception as e:
                logger.error(f"Failed to save config: {e}")
                raise

    @classmethod
    def _load(cls) -> None:
        """Load configuration from files with error handling"""
        base_path = Path(__file__).parent.parent
        try:
            # Load main config
            config_path = base_path / 'config' / 'config.json'
            with open(config_path) as f:
                cls._config = json.load(f)
            # Load secrets
            secrets_path = base_path / 'config' / 'secrets.json'
            with open(secrets_path) as f:
                cls._secrets = json.load(f)
        except FileNotFoundError as e:
            logger.error(f"Config file not found: {e}")
            raise
        except json.JSONDecodeError as e:
            logger.error(f"Invalid JSON in config: {e}")
            raise
        except Exception as e:
            logger.error(f"Unexpected error loading config: {e}")
            raise

    def get(self, key: str, default: Any = None) -> Any:
        """Thread-safe access to config values"""
        with self._lock:
            return self._config.get(key, default)

    # Core properties with consistent error handling and defaults
    @property
    def switch_ip(self) -> str:
        with self._lock:
            return str(self._config.get('switch_ip', ''))

    @switch_ip.setter
    def switch_ip(self, value: str):
        with self._lock:
            self._config['switch_ip'] = value

    @property
    def base_url_suffix(self) -> str:
        with self._lock:
            return str(self._config.get('base_url_suffix', ':8443/api/v1'))

    @property
    def led_count(self) -> int:
        with self._lock:
            try:
                return int(self._config.get('led_count', 48))
            except (ValueError, TypeError) as e:
                logger.error(f"Invalid led_count value: {e}")
                return 48

    @property
    def led_pin(self) -> int:
        with self._lock:
            try:
                return int(self._config.get('led_pin', 18))
            except (ValueError, TypeError) as e:
                logger.error(f"Invalid led_pin value: {e}")
                return 18

    @property
    def led_brightness(self) -> int:
        with self._lock:
            try:
                return int(self._config.get('led_brightness', 255))
            except (ValueError, TypeError) as e:
                logger.error(f"Invalid led_brightness value: {e}")
                return 255

    @property
    def port_count(self) -> int:
        with self._lock:
            try:
                return int(self._config.get('fixed_port_count', 24))
            except (ValueError, TypeError) as e:
                logger.error(f"Invalid port_count value: {e}")
                return 24

    @port_count.setter
    def port_count(self, value: int):
        with self._lock:
            try:
                self._config['fixed_port_count'] = int(value)
            except (ValueError, TypeError) as e:
                logger.error(f"Invalid port_count value: {e}")
                
    @property
    def update_interval(self) -> int:
        with self._lock:
            try:
                return int(self._config.get('update_interval', 15))
            except (ValueError, TypeError) as e:
                logger.error(f"Invalid update_interval value: {e}")
                return 15

    @property
    def scan_vlans(self) -> bool:
        with self._lock:
            return bool(self._config.get('scan_vlans', False))

    @scan_vlans.setter
    def scan_vlans(self, value: bool):
        with self._lock:
            self._config['scan_vlans'] = bool(value)

    @property
    def port_stats(self) -> bool:
        with self._lock:
            return bool(self._config.get('port_stats', False))

    # Network scanning properties
    @property
    def ip_scan(self) -> bool:
        with self._lock:
            return bool(self._config.get('ip_scan', True))

    @property
    def scan_base(self) -> str:
        with self._lock:
            return str(self._config.get('scan_base', '10.18.254'))

    @property
    def scan_range_start(self) -> int:
        with self._lock:
            try:
                return int(self._config.get('scan_range_start', 145))
            except (ValueError, TypeError) as e:
                logger.error(f"Invalid scan_range_start value: {e}")
                return 145

    @property
    def scan_range_end(self) -> int:
        with self._lock:
            try:
                return int(self._config.get('scan_range_end', 160))
            except (ValueError, TypeError) as e:
                logger.error(f"Invalid scan_range_end value: {e}")
                return 160

    # Authentication properties
    @property
    def username(self) -> str:
        with self._lock:
            return str(self._secrets.get('username', ''))

    @property
    def password(self) -> str:
        with self._lock:
            return str(self._secrets.get('password', ''))