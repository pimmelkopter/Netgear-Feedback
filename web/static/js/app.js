// static/js/app.js
import { store } from './store.js';
import { SwitchAPI } from './api.js';

class AppController {
    constructor() {
        this.api = new SwitchAPI();
        this.initialize();
    }

    initialize() {
        this.setupEventListeners();
        this.loadInitialData();
        this.setupPolling();
    }

    async loadInitialData() {
        try {
            const data = await this.api.fetchPorts();
            store.setState({
                ports: data.port_vlans,
                vlans: data.vlan_names
            });
        } catch (error) {
            console.error('Initial data load failed:', error);
        }
    }

    setupPolling() {
        setInterval(async () => {
            const data = await this.api.fetchPorts();
            store.setState({ ports: data.port_vlans });
        }, 10000);
    }

    setupEventListeners() {
        store.subscribe(state => this.updateUI(state));
        
        document.addEventListener('vlan-selected', e => {
            store.setState({ selectedVlan: e.detail });
        });

        document.addEventListener('port-updated', async e => {
            const { portId, vlanId } = e.detail;
            try {
                await this.api.updatePort(portId, vlanId);
                store.setState({
                    pendingChanges: new Map(
                        [...store.state.pendingChanges].filter(([id]) => id !== portId)
                    )
                });
            } catch (error) {
                console.error('Port update failed:', error);
            }
        });
    }

    updateUI(state) {
        this.updatePortGrid(state.ports);
        this.updateVlanSelector(state.vlans);
        this.updateStatusBar(state);
    }

    updatePortGrid(ports) {
        // DOM-Update Logik hier
    }

    updateVlanSelector(vlans) {
        // DOM-Update Logik hier
    }

    updateStatusBar(state) {
        // Status-Anzeige aktualisieren
    }
}

// App initialisieren
new AppController();