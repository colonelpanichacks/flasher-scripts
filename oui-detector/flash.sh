#!/bin/bash

# OUI Spy Detector - Standalone Flash Script
# Flashes firmware to ESP32-S3 (Seeed XIAO ESP32S3)

echo "=========================================="
echo "  OUI Spy Detector Flasher"
echo "=========================================="
echo ""

# Get the directory where the script is located
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
cd "$SCRIPT_DIR"

# Check and install esptool if needed
echo "[*] Checking dependencies..."
if ! command -v esptool.py &> /dev/null; then
    echo "[!] esptool.py not found!"
    echo ""
    echo "[>] Installing esptool..."
    
    # Try to install via pip
    if command -v pip3 &> /dev/null; then
        echo "    Using pip3 to install esptool..."
        pip3 install --user esptool
    elif command -v pip &> /dev/null; then
        echo "    Using pip to install esptool..."
        pip install --user esptool
    elif command -v brew &> /dev/null; then
        echo "    Using Homebrew to install esptool..."
        brew install esptool
    else
        echo "[x] ERROR: Cannot install esptool automatically!"
        echo ""
        echo "    Please install Python and pip first:"
        echo "    $ brew install python3"
        echo ""
        echo "    Then run this script again."
        exit 1
    fi
    
    # Check if installation succeeded
    if ! command -v esptool.py &> /dev/null; then
        echo ""
        echo "[x] ERROR: esptool installation failed!"
        echo ""
        echo "    Please install manually:"
        echo "    $ pip3 install esptool"
        exit 1
    fi
    
    echo "[+] esptool installed successfully!"
    echo ""
else
    echo "[+] esptool found"
fi

# Note about drivers (ESP32-S3 with native USB doesn't need extra drivers on macOS)
echo "[+] ESP32-S3 uses native USB (no extra drivers needed on macOS)"
echo ""

# Find the USB port
echo "[*] Searching for connected device..."
PORT=$(ls /dev/cu.usbmodem* 2>/dev/null | head -n 1)

if [ -z "$PORT" ]; then
    echo "[x] ERROR: No ESP32-S3 device found!"
    echo ""
    echo "    Please:"
    echo "    1. Connect your ESP32-S3 device via USB"
    echo "    2. Wait a few seconds for it to be recognized"
    echo "    3. Run this script again"
    echo ""
    echo "    Troubleshooting:"
    echo "    - Try a different USB cable (must support data)"
    echo "    - Try a different USB port"
    echo "    - Check System Information > USB to see if device appears"
    exit 1
fi

echo "[+] Found device on: $PORT"
echo ""

# Check for firmware files
if [ ! -f "firmware.bin" ] || [ ! -f "bootloader.bin" ] || [ ! -f "partitions.bin" ]; then
    echo "[x] ERROR: Missing firmware files!"
    echo "    Expected files in current directory:"
    echo "    - firmware.bin"
    echo "    - bootloader.bin"
    echo "    - partitions.bin"
    exit 1
fi

echo "[+] Found all firmware files"
echo ""
echo "[>] Flashing device..."
echo "    This will take about 15-20 seconds..."
echo ""

# Flash the firmware
esptool.py --chip esp32s3 --port "$PORT" --baud 921600 \
    --before default_reset --after hard_reset write_flash \
    -z --flash_mode dio --flash_freq 80m --flash_size 8MB \
    0x0 bootloader.bin \
    0x8000 partitions.bin \
    0x10000 firmware.bin

if [ $? -eq 0 ]; then
    echo ""
    echo "=========================================="
    echo "    [+] FLASH SUCCESSFUL!"
    echo "=========================================="
    echo ""
    echo "    Your OUI Spy Detector is ready to use!"
    echo "    Device will automatically restart."
else
    echo ""
    echo "=========================================="
    echo "    [x] FLASH FAILED!"
    echo "=========================================="
    echo ""
    echo "    Try:"
    echo "    - Unplug and reconnect the device"
    echo "    - Hold BOOT button while connecting (if available)"
    echo "    - Try a different USB cable or port"
    echo "    - Run the script again"
    exit 1
fi
