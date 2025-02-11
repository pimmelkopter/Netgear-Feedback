// static/js/api.js
export class SwitchAPI {
    constructor() {
        this.baseURL = '/api';
    }

    async fetchPorts() {
        const response = await fetch(`${this.baseURL}/refresh`, {
            method: 'POST',
            headers: {'Content-Type': 'application/json'}
        });
        return response.json();
    }

    async updatePort(portId, vlanId) {
        const response = await fetch(`${this.baseURL}/switch/port/${portId}`, {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({vlan: vlanId})
        });
        return response.json();
    }
}