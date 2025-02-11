// static/js/components/VlanSelector.js
class VlanSelector extends HTMLElement {
    constructor() {
        super();
        this.state = {
            selectedVlan: null
        };
    }

    connectedCallback() {
        store.subscribe(state => {
            this.state.selectedVlan = state.selectedVlan;
            this.render();
        });
    }

    handleVlanClick(vlanId) {
        store.setState({
            selectedVlan: this.state.selectedVlan === vlanId ? null : vlanId
        });
    }

    render() {
        const { vlans, vlanColors } = store.state;
        
        this.innerHTML = `
            <div class="bg-white rounded-lg shadow p-6 mb-6">
                <h2 class="text-xl font-semibold mb-4">VLANs</h2>
                <div class="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-6 gap-4">
                    ${Object.entries(vlans).map(([vlanId, name]) => `
                        <button class="vlan-button ${Number(vlanId) === this.state.selectedVlan ? 'selected' : ''}"
                                style="background-color: ${vlanColors[vlanId]}"
                                data-vlan="${vlanId}">
                            <div class="font-bold">${name || `VLAN ${vlanId}`}</div>
                        </button>
                    `).join('')}
                </div>
            </div>
        `;

        this.addEventListeners();
    }

    addEventListeners() {
        this.querySelectorAll('.vlan-button').forEach(button => {
            button.addEventListener('click', (e) => {
                const vlanId = Number(e.currentTarget.dataset.vlan);
                this.handleVlanClick(vlanId);
            });
        });
    }
}

customElements.define('vlan-selector', VlanSelector);