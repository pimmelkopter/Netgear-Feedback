// static/js/store.js
class StateStore {
    constructor() {
        this.state = {
            selectedVlan: null,
            pendingChanges: new Map(),
            connectionStatus: 'checking',
            ports: [],
            vlans: []
        };
        this.subscribers = [];
    }

    subscribe(callback) {
        this.subscribers.push(callback);
        return () => {
            this.subscribers = this.subscribers.filter(cb => cb !== callback);
        };
    }

    notify() {
        this.subscribers.forEach(cb => cb(this.state));
    }

    setState(newState) {
        this.state = {...this.state, ...newState};
        this.notify();
    }
}

export const store = new StateStore();