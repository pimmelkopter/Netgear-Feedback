// static/js/components/SwitchHeader.js
class SwitchHeader extends HTMLElement {
    constructor() {
        super();
    }
    
    connectedCallback() {
        this.render();
    }

    render() {
        this.innerHTML = `
            <header class="bg-white rounded-lg shadow p-4 mb-6">
                <div class="flex justify-between items-center">
                    <h1 class="text-2xl font-bold">Switch VLAN Management</h1>
                    <a href="/logout" class="text-gray-600 hover:text-gray-900">Logout</a>
                </div>
            </header>
        `;
    }
}
customElements.define('switch-header', SwitchHeader);