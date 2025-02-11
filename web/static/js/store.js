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
        
        // Debug logging für State Changes
        this.debug = true;
    }

    subscribe(callback) {
        this.subscribers.add(callback);
        // Initial call with current state
        callback({...this.state});
        return () => this.subscribers.delete(callback);
    }

    notify() {
        const stateCopy = {...this.state};
        this.subscribers.forEach(cb => cb(stateCopy));
    }

    setState(newState) {
        const oldState = {...this.state};
        this.state = {...this.state, ...newState};
        
        if (this.debug) {
            console.log('State updated:', {
                old: oldState,
                new: this.state,
                changed: Object.keys(newState)
            });
        }
        
        this.notify();
    }

    // Helper method to check if we have valid data
    hasValidData() {
        return (
            Object.keys(this.state.ports).length > 0 &&
            Object.keys(this.state.vlans).length > 0 &&
            Object.keys(this.state.vlanColors).length > 0
        );
    }
}

export const store = new StateStore();