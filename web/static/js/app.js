import { store } from './store.js';
import { SwitchAPI } from './api.js';
import './components/PortGrid.js';
import './components/VlanSelector.js';
import './components/ActionBar.js';

class AppController {
    constructor() {
        this.api = new SwitchAPI();
        this.initialize();
    }

    async initialize() {
        try {
            const data = await this.api.fetchPorts();
            if (data.status === 'success') {
                store.setState({
                    ports: data.port_vlans,
                    vlanColors: data.vlan_colors,
                    vlans: data.vlan_names
                });
            }
        } catch (error) {
            console.error('Failed to initialize:', error);
        }
    }
}

// Initialize app when DOM is ready
document.addEventListener('DOMContentLoaded', () => {
    new AppController();
});
