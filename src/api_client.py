import requests
import time

class APIClient:
    def __init__(self, base_url, username, password):
        self.base_url = base_url
        self.token = None
        self.token_expiry = 0
        self.username = username
        self.password = password

    def login(self):
        url = f"{self.base_url}/login"
        data = {"username": self.username, "password": self.password}
        resp = requests.post(url, json=data, verify=False)
        resp.raise_for_status()
        json_data = resp.json()
        self.token = json_data['login']['token']
        self.token_expiry = time.time() + json_data['login']['expires']
        return self.token

    def ensure_token(self):
        if not self.token or time.time() > self.token_expiry:
            self.login()

    def get_port_vlan_info(self, port_id):
        self.ensure_token()
        url = f"{self.base_url}/swcfg_port?portid={port_id}"
        headers = {"Authorization": f"Bearer {self.token}"}
        resp = requests.get(url, headers=headers, verify=False)
        resp.raise_for_status()
        return resp.json()

    def get_vlan_info(self, vlan_id):
        self.ensure_token()
        url = f"{self.base_url}/swcfg_vlan?vlanid={vlan_id}"
        headers = {"Authorization": f"Bearer {self.token}"}
        resp = requests.get(url, headers=headers, verify=False)
        resp.raise_for_status()
        return resp.json()

    def set_port_vlan(self, port_id, vlan_id, vlan_name):
        self.ensure_token()
        url = f"{self.base_url}/swcfg_port?portid={port_id}"
        headers = {"Authorization": f"Bearer {self.token}"}
        data = {
            "switchConfigVlan": {
                "vlanId": vlan_id,
                "name": vlan_name
            }
        }
        resp = requests.post(url, json=data, headers=headers, verify=False)
        resp.raise_for_status()
        return resp.json()
