import requests
import logging
import time
import ssl
import urllib3
from typing import Optional, Dict, Any
from requests.adapters import HTTPAdapter
from urllib3.util.ssl_ import create_urllib3_context
from urllib3.util.retry import Retry
from .config import Config
logger = logging.getLogger(__name__)
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

class SwitchAPIError(Exception):
    pass

class CustomHTTPAdapter(HTTPAdapter):
    def init_poolmanager(self, *args, **kwargs):
        context = create_urllib3_context(
            ciphers='DEFAULT:@SECLEVEL=1'
        )
        kwargs['ssl_context'] = context
        return super().init_poolmanager(*args, **kwargs)

class SwitchAPI:
    def __init__(self, progress_callback=None):
        self.config = Config()
        self.base_url = None
        self.token = None
        self.session = self._create_session()
        self.progress_callback = progress_callback

    def scan_network(self, subnet_prefix: str, start: int, end: int) -> str:
        total = end - start + 1
        for i in range(start, end + 1):
            if self.progress_callback:
                progress = int((i - start) / total * self.config.led_count)
                self.progress_callback(progress)
                
            ip = f"{subnet_prefix}.{i}"
            try:
                response = requests.get(f"https://{ip}", timeout=0.4, verify=False)
                if response.status_code == 200:
                    logger.info(f"Switch found at {ip}")
                    return ip
            except requests.exceptions.RequestException:
                continue
        return ""

    def _create_session(self) -> requests.Session:
        session = requests.Session()
        retry_strategy = Retry(
            total=3,
            backoff_factor=0.5,
            status_forcelist=[500, 502, 503, 504]
        )
        adapter = CustomHTTPAdapter(max_retries=retry_strategy)
        session.mount("http://", adapter)
        session.mount("https://", adapter)
        session.verify = False
        session.headers.update({
            "Content-Type": "application/json"
        })
        return session

    def _handle_response(self, response: requests.Response) -> Dict[str, Any]:
        try:
            response.raise_for_status()
            return response.json()
        except requests.exceptions.JSONDecodeError:
            raise SwitchAPIError("Invalid JSON response from switch")
        except requests.exceptions.HTTPError as e:
            if response.status_code == 401:
                raise SwitchAPIError("Authentication failed - token may be expired")
            raise SwitchAPIError(f"HTTP error occurred: {e}")
        except requests.exceptions.RequestException as e:
            raise SwitchAPIError(f"Request failed: {e}")

    def login(self) -> bool:
        try:
            response = self.session.post(f"{self.base_url}/login", json={
                "login": {
                    "username": self.config.username,
                    "password": self.config.password
                }
            })
            verify=False
            data = self._handle_response(response)
            self.token = data['login']['token']
            self.session.headers['Authorization'] = f"Bearer {self.token}"
            return True
        except Exception as e:
            logger.error(f"Login failed: {e}")
            return False

    def set_port_vlan(self, port_id: int, vlan_id: int, save_config: bool = True) -> bool:
        if not 1 <= port_id <= self.config.port_count:
            raise ValueError(f"Invalid port ID: {port_id}")
        if not 1 <= vlan_id <= 4094:
            raise ValueError(f"Invalid VLAN ID: {vlan_id}")

        try:
            # Get current config
            url = f"{self.base_url}/swcfg_port?portid={port_id}"
            response = self.session.get(url, timeout=10)
            data = self._handle_response(response)

            if "switchPortConfig" not in data:
                raise SwitchAPIError(f"Unexpected port data structure: {data}")

            # Update VLAN
            data["switchPortConfig"]["portVlanId"] = vlan_id
            
            # Send updated config
            response = self.session.post(url, json=data, timeout=10)
            self._handle_response(response)

            if save_config:
                return self.save_config()

            return True

        except SwitchAPIError:
            raise
        except Exception as e:
            logger.error(f"Error setting VLAN: {e}")
            return False

    def save_config(self, method: str = 'api') -> bool:
        try:
            if method == 'api':
                return self._save_via_api()
            elif method == 'ssh':
                return self._save_via_ssh()
            raise ValueError(f"Unsupported save method: {method}")
        except Exception as e:
            logger.error(f"Error saving config: {e}")
            return False

    def _save_via_api(self) -> bool:
        try:
            url = f"{self.base_url}/config_copy?directive=rtos"
            response = self.session.post(url, json={}, timeout=15)
            self._handle_response(response)
            logger.info("Config saved to startup-config")
            return True
        except Exception as e:
            logger.error(f"API save failed: {e}")
            return False

    def _save_via_ssh(self) -> bool:
        logger.warning("SSH save not implemented")
        return False

    def get_port_info(self, port_id: int = 0) -> Optional[Dict[str, Any]]:
        """Get info for specific port or all ports if port_id=0"""
        try:
            url = f"{self.base_url}/sw_portstats?portid={port_id}"
            response = self.session.get(url, timeout=5)
            data = self._handle_response(response)
            ports = data.get("switchStatsPort", [])
            return ports[0] if port_id > 0 and ports else ports
        except Exception as e:
            logger.error(f"Error getting port info: {e}")
            return None