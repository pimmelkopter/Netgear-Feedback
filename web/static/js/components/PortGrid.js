// static/js/components/PortGrid.js
import { store } from '../store.js';

export class PortGrid extends HTMLElement {
    constructor() {
        super();
        this.state = {
            selectedPort: null,
            pendingChanges: new Map()
        };
    }
    
    connectedCallback() {
        store.subscribe(state => {
            this.state.selectedVlan = state.selectedVlan;
            this.state.pendingChanges = state.pendingChanges;
            this.render();
        });
    }

    render() {
        const { ports, vlanColors, vlans } = store.state;
        
        if (!ports || Object.keys(ports).length === 0) {
            this.innerHTML = '<div class="text-center p-4">Loading ports...</div>';
            return;
        }
        
        const portElements = Object.entries(ports).map(([portId, vlanId]) => {
            const isPending = this.state.pendingChanges.has(Number(portId));
            const displayVlanId = isPending ? this.state.pendingChanges.get(Number(portId)) : vlanId;
            const vlanName = vlans[displayVlanId] || `VLAN ${displayVlanId}`;
            
            return `
                <button class="port-button ${isPending ? 'pending-change' : ''}"
                        data-port="${portId}">
                    <div class="font-bold">Port ${portId}</div>
                    <div class="text-sm">${vlanName}</div>
                </button>
            `;
        }).join('');

        this.innerHTML = `
            <div class="bg-white rounded-lg shadow p-6 mb-6">
                <h2 class="text-xl font-semibold mb-4">Ports</h2>
                <div class="grid grid-cols-4 sm:grid-cols-6 md:grid-cols-8 lg:grid-cols-12 gap-2">
                    ${portElements}
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
}

customElements.define('port-grid', PortGrid);