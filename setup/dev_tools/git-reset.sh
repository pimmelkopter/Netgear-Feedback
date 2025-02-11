#!/bin/bash
set -euo pipefail

# Colors for better readability
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

# Directory setup
PROJECT_DIR="$(cd "$(dirname "$0")/../.." && pwd)"
CONFIG_FILE="${PROJECT_DIR}/config/config.json"

# Helper functions
log() { echo -e "${GREEN}[+]${NC} $1"; }
warn() { echo -e "${YELLOW}[!]${NC} $1"; }
error() { echo -e "${RED}[!]${NC} $1" >&2; }

# Save current network configuration
save_network_config() {
    log "Saving current network configuration..."
    # Store current NetworkManager connections
    nmcli -t -f NAME,UUID,TYPE con show > /tmp/nm_connections_backup
}

# Restore network configuration from config.json
restore_network_config() {
    log "Restoring network configuration from config.json..."
    
    # Stop services that might interfere
    sudo systemctl stop switch_monitor.service hostapd.service dnsmasq.service

    if [ -f "$CONFIG_FILE" ]; then
        local DHCP=$(jq -r '.dhcp // "true"' "$CONFIG_FILE")
        local FIXED_IP=$(jq -r '.fixed_ip // ""' "$CONFIG_FILE")
        local FIXED_GW=$(jq -r '.fixed_gw // ""' "$CONFIG_FILE")
        local DNS_SERVER=$(jq -r '.dns_server // "8.8.8.8"' "$CONFIG_FILE")
        
        # Configure ethernet based on config
        if [ "$DHCP" = "false" ] && [ -n "$FIXED_IP" ]; then
            log "Setting up static IP configuration..."
            sudo nmcli con delete "Wired connection 1" 2>/dev/null || true
            sudo nmcli con add type ethernet con-name "Wired connection 1" ifname eth0 \
                ipv4.method manual \
                ipv4.addresses "$FIXED_IP" \
                ipv4.gateway "$FIXED_GW" \
                ipv4.dns "$DNS_SERVER" \
                ipv6.method ignore
        else
            log "Setting up DHCP configuration..."
            sudo nmcli con delete "Wired connection 1" 2>/dev/null || true
            sudo nmcli con add type ethernet con-name "Wired connection 1" ifname eth0 \
                ipv4.method auto \
                ipv6.method ignore
        fi
        
        # Activate the connection
        sudo nmcli con up "Wired connection 1" || true
    else
        error "Config file not found!"
        return 1
    fi
}

# Check internet connectivity
check_internet() {
    local timeout=30
    local count=0
    
    while [ $count -lt $timeout ]; do
        if ping -c 1 -W 1 8.8.8.8 >/dev/null 2>&1; then
            return 0
        fi
        count=$((count + 1))
        sleep 1
    done
    
    return 1
}

# Setup temporary internet connection via ethernet
setup_ethernet() {
    warn "Please connect ethernet cable to internet source"
    warn "You have 10 seconds to switch cables..."
    sleep 10
    
    log "Setting up temporary ethernet connection..."
    sudo nmcli radio wifi off
    sudo nmcli con delete "Wired connection 1" 2>/dev/null || true
    sudo nmcli con add type ethernet con-name "Wired connection 1" ifname eth0 \
        ipv4.method auto \
        ipv6.method ignore
    
    sudo nmcli con up "Wired connection 1"
    
    if ! check_internet; then
        error "Failed to establish internet connection via ethernet"
        return 1
    fi
    
    return 0
}

# Setup temporary internet connection via WiFi
setup_wifi() {
    log "Stopping Switch Monitor, hostapd and dnsmasq services..."
    sudo systemctl stop switch_monitor.service hostapd.service dnsmasq.service
    
    sudo nmcli radio wifi on
    sudo nmcli device wifi rescan
    
    # Show available networks
    log "Available WiFi networks:"
    nmcli device wifi list
    
    # Get WiFi credentials
    read -p "Enter WiFi SSID: " SSID
    read -s -p "Enter WiFi password: " PASSWORD
    echo
    
    log "Connecting to WiFi network..."
    if ! sudo nmcli device wifi connect "$SSID" password "$PASSWORD"; then
        error "Failed to connect to WiFi"
        return 1
    fi
    
    if ! check_internet; then
        error "Failed to establish internet connection via WiFi"
        return 1
    fi
    
    return 0
}

# Perform git update
do_git_update() {
    log "Performing git update..."
    cd "$PROJECT_DIR"
    
    # Stash any local changes
    git stash -u
    
    # Fetch and reset
    if ! git fetch origin raspberrypi; then
        error "Failed to fetch updates"
        return 1
    fi
    
    if ! git reset --hard origin/raspberrypi; then
        error "Failed to reset to origin/raspberrypi"
        return 1
    }
    
    return 0
}

# Main function
main() {
    # Check if running as root
    if [ "$(id -u)" -eq 0 ]; then
        error "Please do not run as root"
        exit 1
    }
    
    # Menu
    echo "Please select update method:"
    echo "1) Ethernet (temporarily disconnect from switch)"
    echo "2) WiFi (temporarily disable hotspot)"
    echo "Q) Quit"
    
    read -p "Choice (1/2/Q): " choice
    
    case $choice in
        1)
            # Save current config
            save_network_config
            
            # Setup ethernet
            if ! setup_ethernet; then
                error "Failed to setup ethernet connection"
                restore_network_config
                exit 1
            fi
            
            # Perform update
            if ! do_git_update; then
                error "Update failed"
                restore_network_config
                exit 1
            fi
            
            # Run update script
            log "Running update script..."
            chmod +x "${PROJECT_DIR}/setup/dev_tools/update.sh"
            "${PROJECT_DIR}/setup/dev_tools/update.sh"
            ;;
            
        2)
            # Save current config
            save_network_config
            
            # Setup WiFi
            if ! setup_wifi; then
                error "Failed to setup WiFi connection"
                restore_network_config
                exit 1
            fi
            
            # Perform update
            if ! do_git_update; then
                error "Update failed"
                restore_network_config
                exit 1
            fi
            
            # Run update script
            log "Running update script..."
            chmod +x "${PROJECT_DIR}/setup/dev_tools/update.sh"
            "${PROJECT_DIR}/setup/dev_tools/update.sh"
            ;;
            
        [Qq])
            log "Update cancelled"
            exit 0
            ;;
            
        *)
            error "Invalid choice"
            exit 1
            ;;
    esac

    # Show final status
    log "Update completed successfully"
    git rev-parse HEAD
    log "Please verify git status matches expected version"
}

# Run main function
main