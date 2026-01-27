#!/bin/bash
# ESP32 Firmware Flasher Menu - Mac/Linux
# Just run this file to start

cd "$(dirname "$0")"

if command -v python3 &>/dev/null; then
    exec python3 flash.py "$@"
elif command -v python &>/dev/null; then
    exec python flash.py "$@"
else
    echo ""
    echo "ERROR: Python not found!"
    echo "Install: brew install python3 (Mac) or apt install python3 (Linux)"
    echo ""
    exit 1
fi
