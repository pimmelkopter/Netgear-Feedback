// static/js/components/ActionBar.js
import { store } from '../store.js';
import { SwitchAPI } from '../api.js';

export class ActionBar extends HTMLElement {
    constructor() {
        super();
        this.api = new SwitchAPI();
    }

    connectedCallback() {
        store.subscribe(state => {
            this.render();
        });
    }

    render() {
        const { pendingChanges } = store.state;
        const hasPending = pendingChanges.size > 0;
        
        this.innerHTML = `
            <div class="bg-white rounded-lg shadow p-4 flex justify-between items-center sticky bottom-4">
                <div class="text-sm text-gray-600">
                    ${hasPending ? `${pendingChanges.size} changes pending` : 'Select a VLAN to begin'}
                </div>
                <div class="space-x-4">
                    <button id="cancel-button"
                            class="px-4 py-2 rounded-lg ${hasPending ? 'bg-gray-500 hover:bg-gray-600 text-white' : 'bg-gray-300 cursor-not-allowed'}"
                            ${!hasPending ? 'disabled' : ''}>
                        Cancel Changes
                    </button>
                    <button id="apply-button"
                            class="px-4 py-2 rounded-lg ${hasPending ? 'bg-green-500 hover:bg-green-600 text-white' : 'bg-gray-300 cursor-not-allowed'}"
                            ${!hasPending ? 'disabled' : ''}>
                        Apply Changes
                    </button>
                </div>
            </div>
        `;
        
        this.addEventListeners();
    }

    addEventListeners() {
        const applyButton = this.querySelector('#apply-button');
        const cancelButton = this.querySelector('#cancel-button');
        
        if (applyButton) {
            applyButton.addEventListener('click', () => {
                if (store.state.pendingChanges.size > 0) {
                    this.applyChanges();
                }
            });
        }
        
        if (cancelButton) {
            cancelButton.addEventListener('click', () => {
                if (store.state.pendingChanges.size > 0) {
                    store.setState({ pendingChanges: new Map() });
                }
            });
        }
    }

    async applyChanges() {
        try {
            const { pendingChanges } = store.state;
            for (const [portId, vlanId] of pendingChanges) {
                await this.api.updatePort(portId, vlanId);
            }
            
            const data = await this.api.fetchPorts();
            if (data.status === 'success') {
                store.setState({
                    ports: data.port_vlans,
                    vlanColors: data.vlan_colors,
                    vlans: data.vlan_names,
                    pendingChanges: new Map()
                });
            }
        } catch (error) {
            console.error('Failed to apply changes:', error);
            this.showError('Failed to apply changes');
        }
    }
}

customElements.define('action-bar', ActionBar);