// static/js/app.js
import { store } from './store.js';
import { SwitchAPI } from './api.js';
import './components/SwitchHeader.js';
import './components/PortGrid.js';
import './components/VlanSelector.js';
import './components/ActionBar.js';

class AppController {
    constructor() {
        this.api = new SwitchAPI();
        console.log('AppController initialized');
        this.initialize();
    }

    async initialize() {
        try {
            console.log('Fetching initial data...');
            const data = await this.api.fetchPorts();
            console.log('Received data:', data);
            
            if (data.status === 'success') {
                store.setState({
                    ports: data.port_vlans,
                    vlanColors: data.vlan_colors,
                    vlans: data.vlan_names
                });
            }
        } catch (error) {
            console.error('Failed to initialize:', error);
            // Show error message to user
            const main = document.querySelector('main');
            if (main) {
                main.innerHTML = `
                    <div class="bg-red-100 text-red-700 p-4 rounded-lg">
                        Failed to load switch data. Please try refreshing the page.
                    </div>
                `;
            }
        }
    }
}

// Initialize app when DOM is ready
document.addEventListener('DOMContentLoaded', () => {
    new AppController();
});