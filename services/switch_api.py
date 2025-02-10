##services/switch_api.py##
import requests
import logging
import time
from typing import Optional, Dict, Any, Tuple
from requests.adapters import HTTPAdapter
from urllib3.util import Retry
from .config import Config
import re
import threading
from cachetools import TTLCache, cached
from functools import wraps

logger = logging.getLogger(__name__)

class SwitchAPIError(Exception):
    """Custom exception for switch API errors"""
    pass

class RetryWithBackoff:
    """Decorator for exponential backoff retry logic"""
    def __init__(self, max_retries=3, base_delay=1):
        self.max_retries = max_retries
        self.base_delay = base_delay

    def __call__(self, func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            last_exception = None
            for attempt in range(self.max_retries):
                try:
                    return func(*args, **kwargs)
                except SwitchAPIError as e:
                    last_exception = e
                    if "Authentication failed" in str(e):
                        # Force re-login on auth failure
                        if hasattr(args[0], 'login'):
                            args[0].login()
                    delay = self.base_delay * (2 ** attempt)  # exponential backoff
                    logger.warning(f"Attempt {attempt + 1} failed, retrying in {delay}s: {e}")
                    time.sleep(delay)
            raise last_exception
        return wrapper

class ConnectionPool:
    """Manages connection pool for switch API"""
    def __init__(self, pool_size=10, retry_strategy=None):
        self.adapter = HTTPAdapter(
            pool_connections=pool_size,
            pool_maxsize=pool_size,
            max_retries=retry_strategy or self._default_retry_strategy()
        )

    def _default_retry_strategy(self) -> Retry:
        return Retry(
            total=3,
            backoff_factor=0.5,
            status_forcelist=[500, 502, 503, 504],
            allowed_methods=["HEAD", "GET", "PUT", "DELETE", "OPTIONS", "TRACE"]
        )

    def create_session(self) -> requests.Session:
        """Create new session with pooling"""
        session = requests.Session()
        session.mount("http://", self.adapter)
        session.mount("https://", self.adapter)
        session.verify = False
        session.headers.update({"Content-Type": "application/json"})
        return session

class SwitchAPI:
    """Thread-safe API client for switch communication"""
    # Cache settings
    CACHE_TTL = 60  # Cache time to live in seconds
    CACHE_MAX_SIZE = 100

    def __init__(self, progress_callback=None):
        self.config = Config()
        self.base_url = None
        self._token = None
        self._token_lock = threading.Lock()
        self._connection_pool = ConnectionPool()
        self.session = self._connection_pool.create_session()
        self.progress_callback = progress_callback
        self._cache = TTLCache(maxsize=self.CACHE_MAX_SIZE, ttl=self.CACHE_TTL)
        self._cache_lock = threading.Lock()

    @property
    def token(self) -> Optional[str]:
        """Thread-safe access to API token"""
        with self._token_lock:
            return self._token

    @token.setter
    def token(self, value: Optional[str]):
        """Thread-safe token update"""
        with self._token_lock:
            self._token = value
            if value:
                self.session.headers['Authorization'] = f"Bearer {value}"
            else:
                self.session.headers.pop('Authorization', None)

    def _handle_response(self, response: requests.Response) -> Dict[str, Any]:
        """Process API response with consistent error handling"""
        try:
            response.raise_for_status()
            return response.json()
        except requests.exceptions.JSONDecodeError:
            logger.error(f"Invalid JSON response from switch: {response.text[:200]}")
            raise SwitchAPIError("Invalid JSON response from switch")
        except requests.exceptions.HTTPError as e:
            if response.status_code == 401:
                logger.error("Authentication failed - token may be expired")
                raise SwitchAPIError("Authentication failed - token may be expired")
            logger.error(f"HTTP error occurred: {e}")
            raise SwitchAPIError(f"HTTP error occurred: {e}")
        except requests.exceptions.RequestException as e:
            logger.error(f"Request failed: {e}")
            raise SwitchAPIError(f"Request failed: {e}")

    def _clear_cache(self):
        """Clear API response cache"""
        with self._cache_lock:
            self._cache.clear()

    def scan_network(self, subnet_prefix: str, start: int, end: int) -> str:
        """Scan network range for switch"""
        total = end - start + 1
        last_progress = 0

        for i in range(start, end + 1):
            # Update progress if callback exists
            new_progress = int((i - start) / total * self.config.led_count)
            if self.progress_callback and new_progress != last_progress:
                self.progress_callback(new_progress)
                last_progress = new_progress

            ip = f"{subnet_prefix}.{i}"
            try:
                response = requests.get(
                    f"https://{ip}",
                    timeout=0.4,
                    verify=False
                )
                if response.status_code == 200:
                    logger.info(f"Switch found at {ip}")
                    if self.progress_callback:
                        self.progress_callback(self.config.led_count)
                    return ip
            except requests.exceptions.RequestException:
                continue
        return ""

    @RetryWithBackoff()
    def login(self) -> bool:
        """Authenticate with switch"""
        try:
            response = self.session.post(
                f"{self.base_url}/login",
                json={
                    "login": {
                        "username": self.config.username,
                        "password": self.config.password
                    }
                },
                timeout=5
            )
            data = self._handle_response(response)
            self.token = data['login']['token']
            return True
        except Exception as e:
            logger.error(f"Login failed: {e}")
            return False

    @RetryWithBackoff()
    def detect_ports(self) -> int:
        """Detect number of switch ports"""
        try:
            response = self.session.get(
                f"{self.base_url}/device_info",
                timeout=3
            )
            data = self._handle_response(response)

            total_ports = int(data.get("deviceInfo", {}).get("numOfPorts", 24))
            logger.info(f"Switch reports {total_ports} total ports")

            # Map total ports to usable ports
            if total_ports <= 12:
                return 8
            elif total_ports <= 24:
                return 16
            elif total_ports <= 40:
                return 24
            return 40

        except Exception as e:
            logger.error(f"Port detection failed: {e}")
            return self.config.port_count

    @RetryWithBackoff()
    def scan_vlans(self) -> Dict[str, str]:
        """Scan switch for VLAN configurations"""
        try:
            response = self.session.get(
                f"{self.base_url}/device_config?file=running-config",
                timeout=5
            )
            data = self._handle_response(response)

            lines = data.get("Device-Config", {}).get("Running-Config", [])
            vlan_pattern = re.compile(r'^\s*vlan\s+name\s+(\d+)\s+"([^"]+)"')

            vlan_info = {}
            for line in lines:
                match = vlan_pattern.match(line.strip())
                if match:
                    vlan_id, vlan_name = match.groups()
                    vlan_info[vlan_id] = vlan_name

            return vlan_info
        except Exception as e:
            logger.error(f"VLAN scan failed: {e}")
            return {}

    @RetryWithBackoff()
    def set_port_vlan(self, port_id: int, vlan_id: int, save_config: bool = True) -> bool:
        """Set VLAN for specific port"""
        if not 1 <= port_id <= self.config.port_count:
            logger.error(f"Invalid port ID: {port_id}")
            raise ValueError(f"Invalid port ID: {port_id}")
        if not 1 <= vlan_id <= 4094:
            logger.error(f"Invalid VLAN ID: {vlan_id}")
            raise ValueError(f"Invalid VLAN ID: {vlan_id}")

        try:
            # Get current config
            url = f"{self.base_url}/swcfg_port?portid={port_id}"
            response = self.session.get(url, timeout=10)
            data = self._handle_response(response)

            if "switchPortConfig" not in data:
                raise SwitchAPIError(f"Unexpected port data structure")

            # Update VLAN
            data["switchPortConfig"]["portVlanId"] = vlan_id

            # Send updated config
            response = self.session.post(url, json=data, timeout=10)
            self._handle_response(response)

            # Clear cache as port config changed
            self._clear_cache()

            if save_config:
                return self.save_config()

            return True

        except SwitchAPIError:
            raise
        except Exception as e:
            logger.error(f"Error setting VLAN: {e}")
            return False

    @RetryWithBackoff()
    def save_config(self, method: str = 'api') -> bool:
        """Save switch configuration"""
        try:
            url = f"{self.base_url}/config_copy?directive=rtos"
            response = self.session.post(
                url,
                json={"directive": "rtos"},
                timeout=15
            )
            self._handle_response(response)
            logger.info("Config saved to startup-config")
            return True
        except Exception as e:
            logger.error(f"Error saving config: {e}")
            return False

    @cached(lambda self: self._cache)
    @RetryWithBackoff()
    def get_port_info(self, port_id: int = 0) -> Optional[Dict[str, Any]]:
        """Get info for specific port or all ports with caching"""
        try:
            url = f"{self.base_url}/sw_portstats?portid={'ALL' if port_id == 0 else port_id}"
            response = self.session.get(url, timeout=5)
            data = self._handle_response(response)
            ports = data.get("switchStatsPort", [])
            return ports[0] if port_id > 0 and ports else ports
        except Exception as e:
            logger.error(f"Error getting port info: {e}")
            raise SwitchAPIError(f"Failed to get port info: {e}")