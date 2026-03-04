#!/bin/bash
 
# Configuration
INTERFACE="wlp3s0"       # Replace with your WiFi interface (e.g., wlan0)
SSID="MyHomeWiFi"        # Replace with your WiFi SSID
PASSWORD="MyWiFiPass123" # Replace with your WiFi password
MAX_RETRIES=3            # Max reconnection attempts
PING_TARGET="8.8.8.8"    # Server to ping for connectivity
LOG_FILE="$HOME/wifi-reconnect.log"
 
# Function to log messages
log() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] $1" >> "$LOG_FILE"
}
 
# Check if WiFi is connected
check_connection() {
    ping -c 1 -W 2 "$PING_TARGET" > /dev/null 2>&1
    return $?
}
 
# Main logic
log "=== Starting WiFi reconnection check ==="
 
if check_connection; then
    log "WiFi is connected. Exiting."
    exit 0
else
    log "WiFi disconnected. Attempting reconnection..."
    retry_count=0
    connected=false
 
    # Retry up to MAX_RETRIES times
    while [ $retry_count -lt $MAX_RETRIES ]; do
        retry_count=$((retry_count + 1))
        log "Retry $retry_count/$MAX_RETRIES: Connecting to $SSID..."
 
        # Attempt to reconnect using NetworkManager
        # First, ensure the interface is up
        sudo ip link set "$INTERFACE" up > /dev/null 2>&1
        
        # Connect to the WiFi network (uses NM connection profile)
        nmcli device connect "$INTERFACE" > /dev/null 2>&1
        # Alternative: If using a saved connection profile, use:
        # nmcli connection up "$SSID" > /dev/null 2>&1
 
        # Wait 5 seconds for connection to stabilize
        sleep 5
 
        # Check if reconnection succeeded
        if check_connection; then
            log "Successfully reconnected after $retry_count retries!"
            connected=true
            break
        else
            log "Retry $retry_count failed."
        fi
    done
 
    if [ "$connected" = false ]; then
        log "Failed to reconnect after $MAX_RETRIES retries. Giving up."
        exit 1
    fi
fi
 
log "=== Reconnection check complete ==="