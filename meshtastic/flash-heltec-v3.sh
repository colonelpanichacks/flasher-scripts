#!/bin/bash

# Meshtastic Heltec V3 Flash & Configure Script
# Downloads latest firmware, flashes device, and configures settings

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
NC='\033[0m' # No Color

# Configuration
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
DEVICE_PORT=""
FIRMWARE_DIR="$SCRIPT_DIR/firmware"
VENV_DIR="$SCRIPT_DIR/.venv"
DEVICE_TYPE="heltec-v3"
VERSION_FILE="$FIRMWARE_DIR/.current_version"
MAX_RETRIES=3
RETRY_DELAY=2

echo -e "${BLUE}========================================${NC}"
echo -e "${BLUE}  Meshtastic Heltec V3 Flash Script${NC}"
echo -e "${BLUE}========================================${NC}"
echo ""

# Error handler
error_exit() {
    echo -e "${RED}ERROR: $1${NC}" >&2
    exit 1
}

# Warning message
warn() {
    echo -e "${YELLOW}WARNING: $1${NC}"
}

# Info message
info() {
    echo -e "${CYAN}INFO: $1${NC}"
}

# Success message
success() {
    echo -e "${GREEN}$1${NC}"
}

# Retry a command with exponential backoff
retry_command() {
    local cmd="$1"
    local description="$2"
    local retries=0
    
    while [ $retries -lt $MAX_RETRIES ]; do
        if eval "$cmd"; then
            return 0
        fi
        retries=$((retries + 1))
        if [ $retries -lt $MAX_RETRIES ]; then
            warn "Attempt $retries failed for: $description. Retrying in ${RETRY_DELAY}s..."
            sleep $RETRY_DELAY
            RETRY_DELAY=$((RETRY_DELAY * 2))
        fi
    done
    
    return 1
}

# Function to find the serial port
find_port() {
    echo -e "${YELLOW}Looking for serial port...${NC}"
    
    # Try common macOS USB serial ports for ESP32-S3
    # ESP32-S3 native USB shows up as usbmodem, CP210x shows as usbserial
    local port_patterns=(
        "/dev/cu.usbmodem*"
        "/dev/cu.usbserial-*"
        "/dev/cu.SLAB_USBtoUART*"
        "/dev/cu.wchusbserial*"
        "/dev/tty.usbmodem*"
        "/dev/tty.usbserial-*"
    )
    
    # Also check Linux ports
    if [[ "$OSTYPE" == "linux-gnu"* ]]; then
        port_patterns+=(
            "/dev/ttyUSB*"
            "/dev/ttyACM*"
        )
    fi
    
    for pattern in "${port_patterns[@]}"; do
        for port in $pattern; do
            if [ -e "$port" ] && [ -c "$port" ]; then
                # Verify it's accessible
                if [ -r "$port" ] && [ -w "$port" ]; then
                    success "Found port: $port"
                    DEVICE_PORT="$port"
                    return 0
                else
                    warn "Port $port found but not accessible. May need sudo or dialout group."
                fi
            fi
        done
    done
    
    echo -e "${RED}No serial port found!${NC}"
    echo ""
    echo "Troubleshooting steps:"
    echo "  1. Connect your Heltec V3 via USB"
    echo "  2. Hold BOOT button, press RST, release BOOT after 2 sec"
    echo "  3. You may need to install CP210x drivers:"
    echo "     brew install --cask silicon-labs-cp210x-vcp-driver"
    echo ""
    echo "Available ports:"
    ls /dev/cu.* /dev/tty.usb* 2>/dev/null || echo "  None found"
    return 1
}


# Function to setup virtual environment
setup_venv() {
    echo -e "${YELLOW}Setting up Python virtual environment...${NC}"
    
    # Prefer Python 3.10-3.12 for better pyserial compatibility (3.14 has issues)
    local PYTHON_CMD="python3"
    for py in python3.10 python3.11 python3.12 python3.13; do
        if command -v "$py" &> /dev/null; then
            PYTHON_CMD="$py"
            info "Using $py for better compatibility"
            break
        fi
    done
    
    if [ ! -d "$VENV_DIR" ]; then
        info "Creating virtual environment at $VENV_DIR"
        "$PYTHON_CMD" -m venv "$VENV_DIR" || error_exit "Failed to create virtual environment"
    fi
    
    # Activate venv
    source "$VENV_DIR/bin/activate" || error_exit "Failed to activate virtual environment"
    
    success "Virtual environment activated"
}

# Function to check dependencies
check_dependencies() {
    echo -e "${YELLOW}Checking dependencies...${NC}"
    
    local missing=()
    local install_cmds=()
    
    # Check Python 3
    if ! command -v python3 &> /dev/null; then
        missing+=("python3")
        install_cmds+=("brew install python3")
    else
        local py_version=$(python3 --version 2>&1 | cut -d' ' -f2)
        info "Python version: $py_version"
    fi
    
    # Check curl
    if ! command -v curl &> /dev/null; then
        missing+=("curl")
        install_cmds+=("brew install curl")
    fi
    
    # Check jq
    if ! command -v jq &> /dev/null; then
        missing+=("jq")
        install_cmds+=("brew install jq")
    fi
    
    # Check unzip
    if ! command -v unzip &> /dev/null; then
        missing+=("unzip")
        install_cmds+=("brew install unzip")
    fi
    
    if [ ${#missing[@]} -ne 0 ]; then
        echo -e "${RED}Missing system dependencies: ${missing[*]}${NC}"
        echo "Install with:"
        for cmd in "${install_cmds[@]}"; do
            echo "  $cmd"
        done
        error_exit "Please install missing dependencies and try again."
    fi
    
    # Setup virtual environment for Python packages
    setup_venv
    
    # Check for esptool (in venv) - use 4.7.0 for better compatibility
    if ! python3 -c "import esptool" &> /dev/null; then
        info "Installing esptool and pyserial..."
        if ! pip install 'esptool==4.7.0' 'pyserial==3.5' --quiet; then
            error_exit "Failed to install esptool"
        fi
    fi
    local esptool_version=$(python3 -m esptool version 2>&1 | head -1)
    info "esptool: $esptool_version"
    
    # Check for meshtastic CLI (in venv)
    if ! command -v meshtastic &> /dev/null; then
        info "Installing meshtastic CLI..."
        if ! pip install meshtastic --quiet; then
            error_exit "Failed to install meshtastic CLI"
        fi
    fi
    local mesh_version=$(meshtastic --version 2>&1 || echo "unknown")
    info "meshtastic CLI: $mesh_version"
    
    success "All dependencies satisfied!"
    echo ""
}

# Function to get latest firmware version
get_latest_version() {
    echo -e "${YELLOW}Fetching latest Meshtastic version...${NC}"
    
    local api_response
    api_response=$(curl -s --connect-timeout 10 --max-time 30 \
        -H "Accept: application/vnd.github.v3+json" \
        "https://api.github.com/repos/meshtastic/firmware/releases/latest")
    
    if [ $? -ne 0 ] || [ -z "$api_response" ]; then
        warn "Failed to fetch from GitHub API"
        
        # Check if we have a cached version
        if [ -f "$VERSION_FILE" ]; then
            LATEST_VERSION=$(cat "$VERSION_FILE")
            warn "Using cached version: $LATEST_VERSION"
            return 0
        fi
        
        error_exit "Cannot determine firmware version. Check internet connection."
    fi
    
    LATEST_VERSION=$(echo "$api_response" | jq -r '.tag_name // empty')
    
    if [ -z "$LATEST_VERSION" ]; then
        # Check for rate limiting
        local message=$(echo "$api_response" | jq -r '.message // empty')
        if [[ "$message" == *"rate limit"* ]]; then
            warn "GitHub API rate limit exceeded"
            if [ -f "$VERSION_FILE" ]; then
                LATEST_VERSION=$(cat "$VERSION_FILE")
                warn "Using cached version: $LATEST_VERSION"
                return 0
            fi
        fi
        error_exit "Failed to parse latest version from GitHub"
    fi
    
    success "Latest version: $LATEST_VERSION"
}

# Function to check if we already have the latest firmware
check_local_firmware() {
    echo -e "${YELLOW}Checking for local firmware...${NC}"
    
    # Check if version file exists and matches
    if [ -f "$VERSION_FILE" ]; then
        local cached_version=$(cat "$VERSION_FILE")
        info "Cached version: $cached_version"
        
        if [ "$cached_version" == "$LATEST_VERSION" ]; then
            # Check if firmware files exist
            local firmware_path="$FIRMWARE_DIR/firmware-${LATEST_VERSION}"
            
            if [ -d "$firmware_path" ]; then
                # Look for the required firmware files
                local factory_bin=$(find "$firmware_path" -name "*heltec-v3*.factory.bin" -type f 2>/dev/null | head -1)
                local firmware_bin=$(find "$firmware_path" -name "firmware-heltec-v3-*.bin" -type f 2>/dev/null | head -1)
                
                if [ -n "$factory_bin" ] || [ -n "$firmware_bin" ]; then
                    success "Local firmware is up to date!"
                    return 0
                fi
            fi
        fi
    fi
    
    info "Need to download firmware"
    return 1
}

# Function to download firmware
download_firmware() {
    # Check if we already have it
    if check_local_firmware; then
        return 0
    fi
    
    echo -e "${YELLOW}Downloading firmware for Heltec V3...${NC}"
    
    mkdir -p "$FIRMWARE_DIR"
    
    # Meshtastic firmware naming: firmware-{chip}-{version_without_v}.zip
    # Heltec V3 uses ESP32-S3
    local version_num="${LATEST_VERSION#v}"  # Remove 'v' prefix
    local firmware_zip="firmware-esp32s3-${version_num}.zip"
    local download_url="https://github.com/meshtastic/firmware/releases/download/${LATEST_VERSION}/${firmware_zip}"
    local zip_path="$FIRMWARE_DIR/$firmware_zip"
    
    # Download with progress and retry
    info "Downloading from: $download_url"
    
    local download_success=false
    for attempt in 1 2 3; do
        if curl -L --progress-bar --connect-timeout 30 --max-time 300 \
            -o "$zip_path.tmp" "$download_url"; then
            
            # Verify download is a valid zip
            if file "$zip_path.tmp" | grep -q "Zip archive"; then
                mv "$zip_path.tmp" "$zip_path"
                download_success=true
                break
            else
                warn "Downloaded file is not a valid ZIP archive"
                rm -f "$zip_path.tmp"
            fi
        else
            warn "Download attempt $attempt failed"
            rm -f "$zip_path.tmp"
        fi
        
        if [ $attempt -lt 3 ]; then
            info "Retrying in 5 seconds..."
            sleep 5
        fi
    done
    
    if [ "$download_success" != "true" ]; then
        error_exit "Failed to download firmware after 3 attempts"
    fi
    
    success "Download complete!"
    
    # Extract firmware
    echo -e "${YELLOW}Extracting firmware...${NC}"
    local extract_dir="$FIRMWARE_DIR/firmware-${LATEST_VERSION}"
    
    # Clean up old extraction if exists
    rm -rf "$extract_dir"
    mkdir -p "$extract_dir"
    
    if ! unzip -q -o "$zip_path" -d "$extract_dir"; then
        error_exit "Failed to extract firmware ZIP"
    fi
    
    # Save version
    echo "$LATEST_VERSION" > "$VERSION_FILE"
    
    success "Firmware extracted!"
}

# Function to locate firmware files
locate_firmware_files() {
    echo -e "${YELLOW}Locating firmware files...${NC}"
    
    local firmware_path="$FIRMWARE_DIR/firmware-${LATEST_VERSION}"
    
    # First, try to find factory binary (easiest to flash)
    FACTORY_BIN=$(find "$firmware_path" -name "*heltec-v3*.factory.bin" -type f 2>/dev/null | head -1)
    
    if [ -n "$FACTORY_BIN" ]; then
        success "Found factory binary: $(basename "$FACTORY_BIN")"
        return 0
    fi
    
    # Otherwise, find individual files
    FIRMWARE_BIN=$(find "$firmware_path" -name "firmware-heltec-v3-*.bin" -type f 2>/dev/null | head -1)
    LITTLEFS_BIN=$(find "$firmware_path" -name "littlefs-heltec-v3-*.bin" -type f 2>/dev/null | head -1)
    BOOTLOADER_BIN=$(find "$firmware_path" -name "bootloader*.bin" -path "*heltec*" -type f 2>/dev/null | head -1)
    PARTITION_BIN=$(find "$firmware_path" -name "partition*.bin" -path "*heltec*" -type f 2>/dev/null | head -1)
    BOOT_APP_BIN=$(find "$firmware_path" -name "boot_app0.bin" -type f 2>/dev/null | head -1)
    
    if [ -z "$FIRMWARE_BIN" ]; then
        echo ""
        echo "Available firmware files:"
        find "$firmware_path" -name "*.bin" -type f | head -20
        error_exit "Could not find Heltec V3 firmware files"
    fi
    
    info "Found firmware: $(basename "$FIRMWARE_BIN")"
    [ -n "$LITTLEFS_BIN" ] && info "Found littlefs: $(basename "$LITTLEFS_BIN")"
}

# Wait for port to come back after reset
wait_for_port() {
    local timeout=${1:-15}
    local elapsed=0
    
    DEVICE_PORT=""
    while [ $elapsed -lt $timeout ]; do
        for port in /dev/cu.usbserial-* /dev/cu.usbmodem* /dev/ttyUSB* /dev/ttyACM*; do
            if [ -e "$port" ] && [ -c "$port" ]; then
                DEVICE_PORT="$port"
                return 0
            fi
        done
        sleep 1
        elapsed=$((elapsed + 1))
    done
    return 1
}

# Function to flash firmware
flash_firmware() {
    echo -e "${YELLOW}Flashing firmware to Heltec V3...${NC}"
    info "Port: $DEVICE_PORT"
    
    # ALWAYS erase flash first (clean slate)
    echo -e "${YELLOW}Erasing flash...${NC}"
    
    if ! python3 -m esptool --chip esp32-s3 --port "$DEVICE_PORT" --baud 921600 \
        --before default_reset erase_flash 2>&1; then
        error_exit "Failed to erase flash"
    fi
    
    success "Flash erased!"
    
    # Wait for device to come back after erase reset
    info "Waiting for device..."
    sleep 3
    wait_for_port 10 || error_exit "Device not found after erase"
    info "Device back on $DEVICE_PORT"
    
    # Flash the firmware
    echo -e "${YELLOW}Writing firmware...${NC}"
    
    if [ -n "$FACTORY_BIN" ]; then
        # Use factory binary (combined bootloader + app + littlefs)
        info "Using factory binary (recommended)"
        
        local flash_success=false
        for baud in 921600 460800 115200; do
            info "Trying flash at baud $baud..."
            if python3 -m esptool --chip esp32-s3 --port "$DEVICE_PORT" --baud $baud \
                --before default_reset --after hard_reset \
                write_flash --flash_mode dio --flash_freq 80m --flash_size detect \
                0x0 "$FACTORY_BIN" 2>&1; then
                flash_success=true
                break
            fi
            sleep 1
        done
        
        if [ "$flash_success" != "true" ]; then
            warn "Standard flash failed, trying with USB reset..."
            if ! python3 -m esptool --chip esp32-s3 --port "$DEVICE_PORT" --baud 115200 \
                --before usb_reset --after hard_reset \
                write_flash 0x0 "$FACTORY_BIN"; then
                error_exit "Failed to flash firmware"
            fi
        fi
    else
        # Flash individual components for Heltec V3 (BIGDB_8MB layout)
        # Offsets: firmware=0x00, bleota=0x340000, littlefs=0x670000
        info "Flashing individual components (Heltec V3 layout)..."
        
        # Find bleota-s3.bin
        local firmware_path="$FIRMWARE_DIR/firmware-${LATEST_VERSION}"
        local bleota_bin=$(find "$firmware_path" -name "bleota-s3.bin" -type f 2>/dev/null | head -1)
        
        local flash_cmd="python3 -m esptool --chip esp32-s3 --port \"$DEVICE_PORT\" --baud 921600 \
            --before default_reset --after hard_reset \
            write_flash --flash_mode dio --flash_freq 80m --flash_size detect"
        
        # Firmware at 0x00
        flash_cmd+=" 0x00 \"$FIRMWARE_BIN\""
        
        # BLE OTA at 0x340000 (for Heltec V3 / BIGDB_8MB)
        [ -n "$bleota_bin" ] && flash_cmd+=" 0x340000 \"$bleota_bin\""
        
        # LittleFS at 0x670000 (for Heltec V3 / BIGDB_8MB)
        [ -n "$LITTLEFS_BIN" ] && flash_cmd+=" 0x670000 \"$LITTLEFS_BIN\""
        
        if ! eval "$flash_cmd"; then
            error_exit "Failed to flash firmware components"
        fi
    fi
    
    success "Firmware flashed successfully!"
    echo ""
}

# Function to wait for device after flash
wait_after_flash() {
    echo -e "${YELLOW}Waiting for device to boot...${NC}"
    sleep 5
    
    # Wait for port to appear
    local timeout=30
    local elapsed=0
    
    DEVICE_PORT=""
    
    while [ $elapsed -lt $timeout ]; do
        for port in /dev/cu.usbserial-* /dev/cu.usbmodem* /dev/ttyUSB* /dev/ttyACM*; do
            if [ -e "$port" ] && [ -c "$port" ]; then
                DEVICE_PORT="$port"
                success "Found port: $DEVICE_PORT"
                sleep 2
                return 0
            fi
        done
        sleep 1
        elapsed=$((elapsed + 1))
    done
    
    warn "Device not found, please check connection"
    read -p "Press Enter when ready..."
    find_port || error_exit "Device not found"
}

# Function to run meshtastic command with retry
meshtastic_cmd() {
    local cmd="$1"
    local description="$2"
    local retries=0
    
    while [ $retries -lt $MAX_RETRIES ]; do
        if meshtastic --port "$DEVICE_PORT" $cmd 2>&1; then
            return 0
        fi
        
        retries=$((retries + 1))
        if [ $retries -lt $MAX_RETRIES ]; then
            warn "Command failed: $description. Retry $retries/$MAX_RETRIES..."
            sleep 2
        fi
    done
    
    warn "Failed after $MAX_RETRIES attempts: $description"
    return 1
}

# Function to configure device
configure_device() {
    echo -e "${YELLOW}Configuring device settings...${NC}"
    echo ""
    
    # Wait for device to be ready
    wait_after_flash
    
    # Test connection first with retries
    info "Testing connection to device..."
    local conn_attempts=0
    local max_conn_attempts=5
    
    while [ $conn_attempts -lt $max_conn_attempts ]; do
        if meshtastic --port "$DEVICE_PORT" --info >/dev/null 2>&1; then
            success "Connected to device!"
            break
        fi
        conn_attempts=$((conn_attempts + 1))
        if [ $conn_attempts -lt $max_conn_attempts ]; then
            warn "Connection attempt $conn_attempts failed, waiting..."
            sleep 2
        fi
    done
    
    if [ $conn_attempts -ge $max_conn_attempts ]; then
        error_exit "Cannot communicate with device via Meshtastic CLI"
    fi
    
    echo ""
    echo -e "${BLUE}Applying all configuration at once...${NC}"
    
    # Set ALL settings in one command
    info "Setting region and serial config..."
    meshtastic --port "$DEVICE_PORT" \
        --set lora.region US \
        --set serial.enabled true \
        --set serial.rxd 19 \
        --set serial.txd 20 \
        --set serial.baud BAUD_115200 \
        --set serial.mode TEXTMSG \
        2>&1 || warn "Some settings may have failed"
    
    sleep 2
    
    # Quick verify and retry if needed
    info "Verifying settings..."
    local config=$(meshtastic --port "$DEVICE_PORT" --info 2>&1)
    
    local needs_retry=false
    if ! echo "$config" | grep -q '"rxd": 19'; then needs_retry=true; fi
    if ! echo "$config" | grep -q '"txd": 20'; then needs_retry=true; fi
    if ! echo "$config" | grep -q 'BAUD_115200'; then needs_retry=true; fi
    
    if [ "$needs_retry" = true ]; then
        warn "Some settings didn't stick, retrying..."
        sleep 2
        meshtastic --port "$DEVICE_PORT" \
            --set serial.rxd 19 \
            --set serial.txd 20 \
            --set serial.baud BAUD_115200 \
            2>&1 || true
        sleep 2
    fi
    
    success "Configuration applied!"
    echo ""
}

# Function to verify settings
verify_settings() {
    echo -e "${YELLOW}Verifying final settings...${NC}"
    echo ""
    
    # Get full config for verification
    local config=$(meshtastic --port "$DEVICE_PORT" --info 2>&1)
    
    echo -e "${BLUE}Serial Module Configuration:${NC}"
    echo "----------------------------------------"
    echo "$config" | grep -A12 '"serial":' | head -12
    echo "----------------------------------------"
    echo ""
    
    # Verify critical settings
    local errors=0
    
    if ! echo "$config" | grep -q '"rxd": 19'; then
        echo -e "${RED}WARNING: RX pin is not set to 19${NC}"
        errors=$((errors + 1))
    fi
    
    if ! echo "$config" | grep -q '"txd": 20'; then
        echo -e "${RED}WARNING: TX pin is not set to 20${NC}"
        errors=$((errors + 1))
    fi
    
    if ! echo "$config" | grep -q 'BAUD_115200'; then
        echo -e "${RED}WARNING: Baud rate is not set to 115200${NC}"
        errors=$((errors + 1))
    fi
    
    if ! echo "$config" | grep -q '"enabled": true'; then
        echo -e "${RED}WARNING: Serial module is not enabled${NC}"
        errors=$((errors + 1))
    fi
    
    if [ $errors -gt 0 ]; then
        warn "Some settings may not have been applied correctly"
        warn "You may need to set them manually via the Meshtastic app"
    else
        success "All settings verified successfully!"
    fi
    echo ""
}

# Function to display final summary
show_summary() {
    echo -e "${GREEN}========================================${NC}"
    echo -e "${GREEN}        Setup Complete!${NC}"
    echo -e "${GREEN}========================================${NC}"
    echo ""
    echo -e "Firmware: ${CYAN}$LATEST_VERSION${NC}"
    echo -e "Device:   ${CYAN}Heltec V3${NC}"
    echo -e "Port:     ${CYAN}$DEVICE_PORT${NC}"
    echo ""
    echo -e "Configuration:"
    echo -e "  Region:      ${CYAN}US${NC}"
    echo -e "  Serial:      ${CYAN}Enabled${NC}"
    echo -e "  RX Pin:      ${CYAN}19${NC}"
    echo -e "  TX Pin:      ${CYAN}20${NC}"
    echo -e "  Baud Rate:   ${CYAN}115200${NC}"
    echo -e "  Mode:        ${CYAN}Text Message${NC}"
    echo ""
    echo "Your Heltec V3 is ready for use!"
    echo ""
}

# Cleanup function
cleanup() {
    # Remove any temp files
    rm -f "$FIRMWARE_DIR"/*.tmp 2>/dev/null
    # Deactivate venv if active
    if [ -n "$VIRTUAL_ENV" ]; then
        deactivate 2>/dev/null || true
    fi
}

# Set trap for cleanup
trap cleanup EXIT

# Print usage
usage() {
    echo "Usage: $0 [OPTIONS] [PORT]"
    echo ""
    echo "Options:"
    echo "  -h, --help        Show this help message"
    echo "  -d, --download    Download firmware only (no flash)"
    echo "  -c, --configure   Configure only (no flash)"
    echo "  -f, --force       Force download even if cached"
    echo ""
    echo "Examples:"
    echo "  $0                          # Auto-detect port, full process"
    echo "  $0 /dev/cu.usbserial-0001   # Specify port"
    echo "  $0 --download               # Download firmware only"
    echo "  $0 --configure              # Configure existing device"
    echo ""
}

# Main execution
main() {
    local download_only=false
    local configure_only=false
    local force_download=false
    local specified_port=""
    
    # Parse arguments
    while [[ $# -gt 0 ]]; do
        case $1 in
            -h|--help)
                usage
                exit 0
                ;;
            -d|--download)
                download_only=true
                shift
                ;;
            -c|--configure)
                configure_only=true
                shift
                ;;
            -f|--force)
                force_download=true
                shift
                ;;
            -*)
                echo "Unknown option: $1"
                usage
                exit 1
                ;;
            *)
                specified_port="$1"
                shift
                ;;
        esac
    done
    
    # Check dependencies (this also sets up venv)
    check_dependencies
    
    # Handle force download
    if [ "$force_download" = true ]; then
        info "Forcing fresh download..."
        rm -f "$VERSION_FILE"
    fi
    
    # Get latest version info
    get_latest_version
    
    # Download only mode
    if [ "$download_only" = true ]; then
        download_firmware
        locate_firmware_files
        success "Firmware downloaded to: $FIRMWARE_DIR/firmware-${LATEST_VERSION}"
        exit 0
    fi
    
    # Find or use specified port
    if [ -n "$specified_port" ]; then
        if [ -e "$specified_port" ]; then
            DEVICE_PORT="$specified_port"
            success "Using specified port: $DEVICE_PORT"
        else
            error_exit "Specified port does not exist: $specified_port"
        fi
    else
        if ! find_port; then
            error_exit "No device found. Connect your Heltec V3 and try again."
        fi
    fi
    
    # Configure only mode
    if [ "$configure_only" = true ]; then
        configure_device
        verify_settings
        show_summary
        exit 0
    fi
    
    # Full process
    download_firmware
    locate_firmware_files
    flash_firmware
    configure_device
    verify_settings
    show_summary
}

# Run main with all arguments
main "$@"
