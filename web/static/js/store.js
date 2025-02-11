// static/js/store.js
export class StateStore {
    constructor() {
        this.state = {
            selectedVlan: null,
            pendingChanges: new Map(),
            connectionStatus: 'checking',
            ports: {},
            vlans: {},
            vlanColors: {}
        };
        this.subscribers = new Set();
    }

    subscribe(callback) {
        this.subscribers.add(callback);
        callback(this.state);
        return () => this.subscribers.delete(callback);
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