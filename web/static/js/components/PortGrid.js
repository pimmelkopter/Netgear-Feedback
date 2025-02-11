// static/js/components/PortGrid.js
import { store } from '../store.js';
import { SwitchAPI } from '../api.js';
export class PortGrid extends HTMLElement {
    constructor() {
        super();
        this.state = {
            selectedPort: null,
            pendingChanges: new Map()
        };
    }

    async connectedCallback() {
        // Subscribe to store before initial render
        store.subscribe(state => {
            this.state.selectedVlan = state.selectedVlan;
            this.state.pendingChanges = state.pendingChanges;
            this.render();
        });

        await this.loadData();
        this.addEventListeners();
        // Initial polling setup with error handling
        this.setupPolling();
    }

    setupPolling() {
        setInterval(async () => {
            try {
                await this.loadData();
            } catch (error) {
                console.error('Polling error:', error);
                // Handle error state if needed
            }
        }, 5000);
    }

    async loadData() {
        try {
            this.classList.add('loading');
            const api = new SwitchAPI();
            const data = await api.fetchPorts();
            
            if (data.status === 'success') {
                store.setState({
                    ports: data.port_vlans,
                    vlanColors: data.vlan_colors,
                    vlans: data.vlan_names
                });
            }
        } catch (error) {
            console.error('Failed to load port data:', error);
            this.showError('Failed to load port data');
        } finally {
            this.classList.remove('loading');
        }
    }

    showError(message) {
        const errorDiv = document.createElement('div');
        errorDiv.className = 'error-message bg-red-100 text-red-700 p-4 rounded-lg mb-4';
        errorDiv.textContent = message;
        this.insertAdjacentElement('beforebegin', errorDiv);
        setTimeout(() => errorDiv.remove(), 5000);
    }

    handlePortClick(portId) {
        if (!this.state.selectedVlan) return;
        
        const newChanges = new Map(this.state.pendingChanges);
        if (newChanges.get(portId) === this.state.selectedVlan) {
            newChanges.delete(portId);
        } else {
            newChanges.set(portId, this.state.selectedVlan);
        }
        
        store.setState({ pendingChanges: newChanges });
    }

    render() {
        const { ports, vlanColors, vlans } = store.state;
        
        this.innerHTML = `
            <div class="bg-white rounded-lg shadow p-6 mb-6">
                <h2 class="text-xl font-semibold mb-4">Ports</h2>
                <div class="grid grid-cols-4 sm:grid-cols-6 md:grid-cols-8 lg:grid-cols-12 gap-2">
                    ${Object.entries(ports).map(([portId, vlanId]) => {
                        const isPending = this.state.pendingChanges.has(Number(portId));
                        const displayVlanId = isPending ? this.state.pendingChanges.get(Number(portId)) : vlanId;
                        const backgroundColor = vlanColors[displayVlanId];
                        const vlanName = vlans[displayVlanId] || `VLAN ${displayVlanId}`;
                        
                        return `
                            <button class="port-button ${isPending ? 'pending-change' : ''}"
                                    style="background-color: ${backgroundColor}"
                                    data-port="${portId}">
                                <div class="font-bold">Port ${portId}</div>
                                <div class="text-sm">${vlanName}</div>
                            </button>
                        `;
                    }).join('')}
                </div>
            </div>
        `;

        this.addEventListeners();
    }

    addEventListeners() {
        this.querySelectorAll('.port-button').forEach(button => {
            button.addEventListener('click', (e) => {
                const portId = Number(e.currentTarget.dataset.port);
                this.handlePortClick(portId);
            });
        });
    }
}

customElements.define('port-grid', PortGrid);