##services/switch_api.py##
import requests
import logging
import time
from typing import Optional, Dict, Any
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
from .config import Config
import re

logger = logging.getLogger(__name__)

class SwitchAPIError(Exception):
    pass

class SwitchAPI:
    def __init__(self, progress_callback=None):
        self.config = Config()
        self.base_url = None
        self.token = None
        self.session = self._create_session()
        self.progress_callback = progress_callback

    def scan_network(self, subnet_prefix: str, start: int, end: int) -> str:
        total = end - start + 1
        last_progress = 0
        
        for i in range(start, end + 1):
            new_progress = int((i - start) / total * self.config.led_count)
            if self.progress_callback and new_progress != last_progress:
                self.progress_callback(new_progress)
                last_progress = new_progress

            ip = f"{subnet_prefix}.{i}"
            try:
                response = requests.get(f"https://{ip}", timeout=0.4, verify=False)
                if response.status_code == 200:
                    logger.info(f"Switch found at {ip}")
                    if self.progress_callback:
                        self.progress_callback(self.config.led_count)
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
        adapter = HTTPAdapter(max_retries=retry_strategy)
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
            data = self._handle_response(response)
            self.token = data['login']['token']
            self.session.headers['Authorization'] = f"Bearer {self.token}"
            return True
        except Exception as e:
            logger.error(f"Login failed: {e}")
            return False

    def detect_ports(self) -> bool:
        """Detect number of switch ports and map to usable ports"""
        try:
            response = self.session.get(f"{self.base_url}/device_info", timeout=3)
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
            # Fallback to config value
            return self.config.port_count

    def scan_vlans(self) -> Dict[str, str]:
        """Scan switch for VLAN configurations"""
        try:
            response = self.session.get(
                f"{self.base_url}/device_config?file=running-config",
                timeout=5
            )
            data = self._handle_response(response)
            
            lines = data.get("Device-Config",{}).get("Running-Config",[])
            vlan_pattern = re.compile(r'^\s*vlan\s+name\s+(\d+)\s+"([^"]+)"')
            
            vlan_info = {}
            for line in lines:
                match = vlan_pattern.match(line.strip())
                if match:
                    vlan_id, vlan_name = match.groups()
                    vlan_info[vlan_id] = vlan_name

            # Add default VLAN if not present
            if '1' not in vlan_info:
                vlan_info['1'] = 'Default'
                    
            return vlan_info
        except Exception as e:
            logger.error(f"VLAN scan failed: {e}")
            return {}
    
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
            response = self.session.post(url, json={"directive":"rtos"}, timeout=15)
            self._handle_response(response)
            logger.info("Config saved to startup-config")
            return True
        except Exception as e:
            logger.error(f"API save failed: {e}")
            return False
        
    def restore_backup_via_api(self) -> bool:
        try:
            url = f"{self.base_url}/config_copy?directive=btos"
            response = self.session.post(url, json={"directive":"btos"}, timeout=15)
            self._handle_response(response)
            logger.info("Backup restored to startup-config - please reboot")
            return True
        except Exception as e:
            logger.error(f"Backup restore failed: {e}")
            return False
        
    def reboot_switch(self) -> bool:
        try:
            url = f"{self.base_url}/device_reboot"
            response = self.session.post(
                url, 
                json={
                    "deviceReboot": {
                        "afterSecs": 2
                    }
                }, 
                timeout=15
            )
            self._handle_response(response)
            logger.info("Device Reboot")
            return True
        except Exception as e:
            logger.error(f"Reboot failed: {e}")
            return False
        
        
    def get_port_stats(self, port_id: int = 0) -> Optional[Dict[str, Any]]:
        """Get speed and PoE stats for specific port or all ports."""
        try:
            url = f"{self.base_url}/sw_portstats?portid={'ALL' if port_id == 0 else port_id}"
            response = self.session.get(url, timeout=5)
            stats_data = self._handle_response(response)
            return stats_data.get("switchStatsPort", [])
        except Exception as e:
            logger.error(f"Error getting port stats: {e}")
            raise SwitchAPIError(f"Failed to get port stats: {e}")

    def get_port_vlan_info(self, port_id: int) -> Optional[int]:
        """Get current VLAN ID for a specific port. Returns None on error."""
        try:
            url = f"{self.base_url}/swcfg_port?portid={port_id}"
            response = self.session.get(url, timeout=5)
            data = self._handle_response(response)
            
            if "switchPortConfig" not in data:
                raise SwitchAPIError(f"Unexpected port data structure for port {port_id}")
                
            return data["switchPortConfig"].get("portVlanId", 1)
        except Exception as e:
            logger.error(f"Error getting port VLAN info: {e}")
            return None

    def get_port_info(self, port_id: int = 0) -> Optional[Dict[str, Any]]:
        """
        Get complete info for specific port or all ports.
        Returns list of port information dictionaries.
        """
        try:
            # Get port stats first
            port_stats = self.get_port_stats(port_id)
            if not port_stats:
                return None

            # Handle single port request
            if port_id > 0:
                if not port_stats:
                    return None
                vlan_id = self.get_port_vlan_info(port_id)
                port_stats[0]["vlans"] = [vlan_id if vlan_id is not None else 1]
                return port_stats

            # For all ports: Create port dictionary and add VLANs
            port_dict = {
                port["portId"]: port 
                for port in port_stats 
                if "portId" in port and 1 <= port["portId"] <= self.config.port_count
            }

            # Get VLAN info for each port
            for curr_port_id in port_dict:
                vlan_id = self.get_port_vlan_info(curr_port_id)
                port_dict[curr_port_id]["vlans"] = [vlan_id if vlan_id is not None else 1]
                time.sleep(0.04)  # Small delay between VLAN queries

            return list(port_dict.values())

        except Exception as e:
            logger.error(f"Error getting port info: {e}")
            raise SwitchAPIError(f"Failed to get port info: {e}")