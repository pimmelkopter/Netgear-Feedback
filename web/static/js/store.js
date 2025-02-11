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
        this.debug = true;
    }

    subscribe(callback) {
        this.subscribers.add(callback);
        callback({...this.state});
        return () => this.subscribers.delete(callback);
    }

    setState(newState) {
        try {
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
        } catch (error) {
            console.error('Error updating state:', error);
        }
    }

    notify() {
        const stateCopy = {...this.state};
        this.subscribers.forEach(cb => cb(stateCopy));
    }
}

export const store = new StateStore();