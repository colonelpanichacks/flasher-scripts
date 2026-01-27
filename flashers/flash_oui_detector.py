#!/usr/bin/env python3
"""
OUI Spy Detector Flasher - Cross-platform firmware flasher
Supports: Windows, macOS, Linux
Device: Seeed XIAO ESP32S3
"""

import os
import platform
import re
import sys
import time
from pathlib import Path

# =============================================================================
# Cross-platform colored output
# =============================================================================

class Colors:
    """Cross-platform colored terminal output."""
    
    def __init__(self):
        self.enabled = self._supports_color()
        if self.enabled and platform.system() == "Windows":
            self._enable_windows_ansi()
    
    def _supports_color(self) -> bool:
        if os.getenv("NO_COLOR"):
            return False
        if os.getenv("FORCE_COLOR"):
            return True
        return hasattr(sys.stdout, "isatty") and sys.stdout.isatty()
    
    def _enable_windows_ansi(self):
        try:
            import ctypes
            kernel32 = ctypes.windll.kernel32
            kernel32.SetConsoleMode(kernel32.GetStdHandle(-11), 7)
        except Exception:
            self.enabled = False
    
    def _wrap(self, code: str, text: str) -> str:
        return f"\033[{code}m{text}\033[0m" if self.enabled else text
    
    def red(self, text: str) -> str:
        return self._wrap("0;31", text)
    
    def green(self, text: str) -> str:
        return self._wrap("0;32", text)
    
    def yellow(self, text: str) -> str:
        return self._wrap("1;33", text)
    
    def blue(self, text: str) -> str:
        return self._wrap("0;34", text)


colors = Colors()


def info(msg: str):
    print(f"[*] {msg}")


def success(msg: str):
    print(f"{colors.green('[+]')} {msg}")


def warn(msg: str):
    print(f"{colors.yellow('[!]')} {msg}")


def error(msg: str):
    print(f"{colors.red('[x]')} {msg}", file=sys.stderr)


def header(msg: str):
    print(f"\n{colors.blue('='*50)}")
    print(f"{colors.blue(msg.center(50))}")
    print(f"{colors.blue('='*50)}\n")


# =============================================================================
# Serial Port Detection
# =============================================================================

def find_serial_ports():
    """Find available serial ports on any platform."""
    ports = []
    system = platform.system()
    
    if system == "Windows":
        try:
            import serial.tools.list_ports
            for port in serial.tools.list_ports.comports():
                desc_lower = (port.description or "").lower()
                if any(x in desc_lower for x in ["usb", "serial", "uart", "cp210", "ch340", "ftdi", "esp"]):
                    ports.append(port.device)
        except ImportError:
            # Fallback: check common COM ports
            import serial
            for i in range(1, 33):
                port = f"COM{i}"
                try:
                    s = serial.Serial(port)
                    s.close()
                    ports.append(port)
                except Exception:
                    pass
    
    elif system == "Darwin":  # macOS
        dev_path = Path("/dev")
        for pattern in ["cu.usbmodem*", "cu.usbserial-*"]:
            ports.extend(str(p) for p in dev_path.glob(pattern))
    
    else:  # Linux
        dev_path = Path("/dev")
        for pattern in ["ttyUSB*", "ttyACM*"]:
            ports.extend(str(p) for p in dev_path.glob(pattern))
    
    return sorted(set(ports))


def select_port(specified_port=None):
    """Find and select a serial port."""
    if specified_port:
        return specified_port
    
    info("Searching for connected devices...")
    ports = find_serial_ports()
    
    if not ports:
        error("No serial ports found!")
        print("\nTroubleshooting:")
        print("  1. Connect your ESP32-S3 device via USB")
        print("  2. Wait a few seconds for it to be recognized")
        if platform.system() == "Windows":
            print("  3. Check Device Manager for COM ports")
        else:
            print("  3. Check /dev for ttyUSB* or ttyACM* devices")
        sys.exit(1)
    
    selected = ports[0]
    success(f"Found device on: {selected}")
    return selected


# =============================================================================
# Flashing
# =============================================================================

def check_esptool():
    """Ensure esptool is available."""
    try:
        import esptool
        return True
    except ImportError:
        error("esptool not found!")
        print("\nInstall with: pip install esptool")
        return False


def flash_firmware(port: str, script_dir: Path):
    """Flash firmware to device."""
    header("OUI Spy Detector Flasher")
    
    # Check firmware files in bins/oui-detector/
    bins_dir = script_dir.parent / "bins" / "oui-detector"
    firmware_bin = bins_dir / "firmware.bin"
    bootloader_bin = bins_dir / "bootloader.bin"
    partitions_bin = bins_dir / "partitions.bin"
    
    missing = []
    if not firmware_bin.exists():
        missing.append("firmware.bin")
    if not bootloader_bin.exists():
        missing.append("bootloader.bin")
    if not partitions_bin.exists():
        missing.append("partitions.bin")
    
    if missing:
        error(f"Missing firmware files: {', '.join(missing)}")
        print(f"\nExpected files in: {bins_dir}")
        sys.exit(1)
    
    success("Found all firmware files")
    info(f"Port: {port}")
    
    # Import esptool
    try:
        import esptool
    except ImportError:
        error("esptool not installed. Run: pip install esptool")
        sys.exit(1)
    
    print(f"\n{colors.yellow('Flashing device...')}")
    print("This will take about 15-20 seconds...\n")
    
    # Flash
    try:
        flash_args = [
            "--chip", "esp32s3",
            "--port", port,
            "--baud", "921600",
            "--before", "default_reset",
            "--after", "hard_reset",
            "write_flash",
            "-z",
            "--flash_mode", "dio",
            "--flash_freq", "80m",
            "--flash_size", "8MB",
            "0x0", str(bootloader_bin),
            "0x8000", str(partitions_bin),
            "0x10000", str(firmware_bin)
        ]
        esptool.main(flash_args)
        
        print()
        header("FLASH SUCCESSFUL!")
        print("Your OUI Spy Detector is ready to use!")
        print("Device will automatically restart.")
        
    except Exception as e:
        print()
        header("FLASH FAILED!")
        error(str(e))
        print("\nTroubleshooting:")
        print("  - Unplug and reconnect the device")
        print("  - Hold BOOT button while connecting")
        print("  - Try a different USB cable or port")
        sys.exit(1)


def main():
    import argparse
    
    parser = argparse.ArgumentParser(description="OUI Spy Detector Flasher")
    parser.add_argument("--port", "-p", help="Serial port (auto-detect if not specified)")
    args = parser.parse_args()
    
    if not check_esptool():
        sys.exit(1)
    
    script_dir = Path(__file__).parent.resolve()
    port = select_port(args.port)
    flash_firmware(port, script_dir)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print(f"\n{colors.yellow('Interrupted by user')}")
        sys.exit(130)
