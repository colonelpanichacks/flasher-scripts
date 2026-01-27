#!/usr/bin/env python3
"""
Meshtastic Universal Flasher - Cross-platform firmware flasher and configurator
Supports: Windows, macOS, Linux
Devices: Heltec V3, T-Beam, T-Deck, and other ESP32-S3 based Meshtastic devices

Downloads latest stable firmware, flashes device, and configures settings.
"""

import argparse
import json
import os
import platform
import re
import shutil
import subprocess
import sys
import tempfile
import time
import zipfile
from pathlib import Path
from typing import Optional, List, Tuple
from urllib.request import urlopen, Request
from urllib.error import URLError, HTTPError

# =============================================================================
# Configuration
# =============================================================================

GITHUB_API_URL = "https://api.github.com/repos/meshtastic/firmware/releases/latest"
FIRMWARE_BASE_URL = "https://github.com/meshtastic/firmware/releases/download"

# Device configurations: device_name -> (chip_type, firmware_pattern, flash_offset)
SUPPORTED_DEVICES = {
    "heltec-v3": {
        "chip": "esp32-s3",
        "firmware_pattern": r"heltec-v3.*\.factory\.bin$",
        "flash_offset": 0x0,
        "description": "Heltec WiFi LoRa 32 V3",
    },
    "heltec-v2": {
        "chip": "esp32",
        "firmware_pattern": r"heltec-v2.*\.factory\.bin$",
        "flash_offset": 0x0,
        "description": "Heltec WiFi LoRa 32 V2",
    },
    "tbeam": {
        "chip": "esp32",
        "firmware_pattern": r"tbeam.*\.factory\.bin$",
        "flash_offset": 0x0,
        "description": "LILYGO T-Beam",
    },
    "tbeam-s3": {
        "chip": "esp32-s3",
        "firmware_pattern": r"tbeam-s3.*\.factory\.bin$",
        "flash_offset": 0x0,
        "description": "LILYGO T-Beam S3",
    },
    "t-deck": {
        "chip": "esp32-s3",
        "firmware_pattern": r"t-deck.*\.factory\.bin$",
        "flash_offset": 0x0,
        "description": "LILYGO T-Deck",
    },
    "station-g2": {
        "chip": "esp32-s3",
        "firmware_pattern": r"station-g2.*\.factory\.bin$",
        "flash_offset": 0x0,
        "description": "Meshtastic Station G2",
    },
}

DEFAULT_DEVICE = "heltec-v3"

# Meshtastic configuration defaults
DEFAULT_CONFIG = {
    "region": "US",
    "serial_enabled": True,
    "serial_rxd": 19,
    "serial_txd": 20,
    "serial_baud": "BAUD_115200",
    "serial_mode": "TEXTMSG",
}

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
        """Check if terminal supports colors."""
        if os.getenv("NO_COLOR"):
            return False
        if os.getenv("FORCE_COLOR"):
            return True
        return hasattr(sys.stdout, "isatty") and sys.stdout.isatty()
    
    def _enable_windows_ansi(self):
        """Enable ANSI escape codes on Windows 10+."""
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
    
    def cyan(self, text: str) -> str:
        return self._wrap("0;36", text)
    
    def bold(self, text: str) -> str:
        return self._wrap("1", text)


colors = Colors()


def info(msg: str):
    print(f"{colors.cyan('INFO:')} {msg}")


def success(msg: str):
    print(f"{colors.green('✓')} {msg}")


def warn(msg: str):
    print(f"{colors.yellow('WARNING:')} {msg}")


def error(msg: str):
    print(f"{colors.red('ERROR:')} {msg}", file=sys.stderr)


def header(msg: str):
    print(f"\n{colors.blue('='*50)}")
    print(f"{colors.blue(msg.center(50))}")
    print(f"{colors.blue('='*50)}\n")


# =============================================================================
# Serial Port Detection (Cross-platform)
# =============================================================================

def find_serial_ports() -> List[str]:
    """Find available serial ports on any platform."""
    ports = []
    system = platform.system()
    
    if system == "Windows":
        ports = _find_windows_ports()
    elif system == "Darwin":  # macOS
        ports = _find_macos_ports()
    else:  # Linux and others
        ports = _find_linux_ports()
    
    return ports


def _find_windows_ports() -> List[str]:
    """Find COM ports on Windows."""
    ports = []
    
    # Method 1: Try serial.tools.list_ports (most reliable)
    try:
        import serial.tools.list_ports
        for port in serial.tools.list_ports.comports():
            # Filter for likely ESP32 devices
            desc_lower = (port.description or "").lower()
            if any(x in desc_lower for x in ["usb", "serial", "uart", "cp210", "ch340", "ftdi", "esp"]):
                ports.append(port.device)
        if ports:
            return sorted(ports, key=lambda x: int(re.search(r'\d+', x).group()) if re.search(r'\d+', x) else 0)
    except ImportError:
        pass
    
    # Method 2: Registry scan
    try:
        import winreg
        key = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r"HARDWARE\DEVICEMAP\SERIALCOMM")
        i = 0
        while True:
            try:
                _, port, _ = winreg.EnumValue(key, i)
                ports.append(port)
                i += 1
            except OSError:
                break
        winreg.CloseKey(key)
    except Exception:
        pass
    
    # Method 3: Brute force check common COM ports
    if not ports:
        for i in range(1, 33):
            port = f"COM{i}"
            try:
                import serial
                s = serial.Serial(port)
                s.close()
                ports.append(port)
            except Exception:
                pass
    
    return ports


def _find_macos_ports() -> List[str]:
    """Find serial ports on macOS."""
    ports = []
    dev_path = Path("/dev")
    
    patterns = [
        "cu.usbmodem*",      # ESP32-S3 native USB
        "cu.usbserial-*",    # CP210x, FTDI
        "cu.SLAB_USBtoUART*", # Silicon Labs
        "cu.wchusbserial*",  # CH340
    ]
    
    for pattern in patterns:
        ports.extend(str(p) for p in dev_path.glob(pattern))
    
    return sorted(set(ports))


def _find_linux_ports() -> List[str]:
    """Find serial ports on Linux."""
    ports = []
    dev_path = Path("/dev")
    
    patterns = [
        "ttyUSB*",     # USB-Serial adapters
        "ttyACM*",     # Arduino/ESP32-S3
        "ttyAMA*",     # Raspberry Pi
    ]
    
    for pattern in patterns:
        ports.extend(str(p) for p in dev_path.glob(pattern))
    
    return sorted(set(ports))


def select_port(auto: bool = True, specified_port: Optional[str] = None) -> str:
    """Find and select a serial port."""
    
    if specified_port:
        info(f"Using specified port: {specified_port}")
        return specified_port
    
    print(f"{colors.yellow('Searching for connected devices...')}")
    ports = find_serial_ports()
    
    if not ports:
        error("No serial ports found!")
        print("\nTroubleshooting:")
        if platform.system() == "Windows":
            print("  1. Connect your device via USB")
            print("  2. Check Device Manager for COM ports")
            print("  3. Install CP210x or CH340 drivers if needed")
            print("     - CP210x: https://www.silabs.com/developers/usb-to-uart-bridge-vcp-drivers")
            print("     - CH340: https://www.wch.cn/downloads/CH341SER_EXE.html")
        else:
            print("  1. Connect your device via USB")
            print("  2. Hold BOOT button, press RST, then release BOOT")
            print("  3. Check if you need to add user to dialout group (Linux)")
        sys.exit(1)
    
    if len(ports) == 1 or auto:
        selected = ports[0]
        success(f"Found device on: {selected}")
        return selected
    
    # Multiple ports - let user choose
    print("\nMultiple ports found. Please select:")
    for i, port in enumerate(ports, 1):
        print(f"  {i}. {port}")
    
    while True:
        try:
            choice = input(f"\nEnter number (1-{len(ports)}): ").strip()
            idx = int(choice) - 1
            if 0 <= idx < len(ports):
                return ports[idx]
        except (ValueError, KeyboardInterrupt):
            pass
        print("Invalid selection. Try again.")


# =============================================================================
# Firmware Download
# =============================================================================

def get_latest_version() -> Tuple[str, dict]:
    """Fetch latest stable Meshtastic firmware version from GitHub."""
    print(f"{colors.yellow('Fetching latest Meshtastic version...')}")
    
    try:
        req = Request(GITHUB_API_URL, headers={
            "Accept": "application/vnd.github.v3+json",
            "User-Agent": "Meshtastic-Flasher/1.0"
        })
        
        with urlopen(req, timeout=30) as response:
            data = json.loads(response.read().decode())
        
        version = data.get("tag_name")
        if not version:
            raise ValueError("No tag_name in response")
        
        success(f"Latest version: {version}")
        return version, data
    
    except (URLError, HTTPError, json.JSONDecodeError, ValueError) as e:
        error(f"Failed to fetch version: {e}")
        sys.exit(1)


def download_firmware(version: str, device: str, firmware_dir: Path) -> Path:
    """Download and extract firmware for the specified device."""
    device_config = SUPPORTED_DEVICES.get(device)
    if not device_config:
        error(f"Unknown device: {device}")
        sys.exit(1)
    
    chip = device_config["chip"]
    version_num = version.lstrip("v")
    
    # Determine firmware package name based on chip
    if chip == "esp32-s3":
        firmware_zip = f"firmware-esp32s3-{version_num}.zip"
    elif chip == "esp32":
        firmware_zip = f"firmware-esp32-{version_num}.zip"
    else:
        firmware_zip = f"firmware-{chip}-{version_num}.zip"
    
    download_url = f"{FIRMWARE_BASE_URL}/{version}/{firmware_zip}"
    zip_path = firmware_dir / firmware_zip
    extract_dir = firmware_dir / f"firmware-{version}"
    version_file = firmware_dir / ".current_version"
    
    # Check cache
    if version_file.exists() and extract_dir.exists():
        cached_version = version_file.read_text().strip()
        if cached_version == version:
            # Find the factory binary
            factory_bin = find_firmware_file(extract_dir, device_config["firmware_pattern"])
            if factory_bin:
                success("Using cached firmware (up to date)")
                return factory_bin
    
    # Download
    print(f"{colors.yellow('Downloading firmware...')}")
    info(f"URL: {download_url}")
    
    firmware_dir.mkdir(parents=True, exist_ok=True)
    
    try:
        req = Request(download_url, headers={"User-Agent": "Meshtastic-Flasher/1.0"})
        
        with urlopen(req, timeout=300) as response:
            total_size = int(response.headers.get("Content-Length", 0))
            downloaded = 0
            chunk_size = 8192
            
            with open(zip_path, "wb") as f:
                while True:
                    chunk = response.read(chunk_size)
                    if not chunk:
                        break
                    f.write(chunk)
                    downloaded += len(chunk)
                    
                    if total_size:
                        pct = (downloaded / total_size) * 100
                        bar_len = 40
                        filled = int(bar_len * downloaded / total_size)
                        bar = "█" * filled + "░" * (bar_len - filled)
                        print(f"\r  [{bar}] {pct:.1f}%", end="", flush=True)
        
        print()  # Newline after progress bar
        success("Download complete!")
    
    except (URLError, HTTPError) as e:
        error(f"Download failed: {e}")
        sys.exit(1)
    
    # Extract
    print(f"{colors.yellow('Extracting firmware...')}")
    
    if extract_dir.exists():
        shutil.rmtree(extract_dir)
    extract_dir.mkdir(parents=True)
    
    try:
        with zipfile.ZipFile(zip_path, "r") as zf:
            zf.extractall(extract_dir)
        success("Extraction complete!")
    except zipfile.BadZipFile:
        error("Downloaded file is not a valid ZIP archive")
        sys.exit(1)
    
    # Save version
    version_file.write_text(version)
    
    # Find the factory binary
    factory_bin = find_firmware_file(extract_dir, device_config["firmware_pattern"])
    if not factory_bin:
        error(f"Could not find firmware for {device}")
        print("\nAvailable firmware files:")
        for f in extract_dir.rglob("*.bin"):
            print(f"  {f.name}")
        sys.exit(1)
    
    return factory_bin


def find_firmware_file(extract_dir: Path, pattern: str) -> Optional[Path]:
    """Find firmware file matching pattern in extracted directory."""
    regex = re.compile(pattern, re.IGNORECASE)
    
    for f in extract_dir.rglob("*.bin"):
        if regex.search(f.name):
            return f
    
    return None


# =============================================================================
# Flashing (via esptool)
# =============================================================================

def check_esptool():
    """Ensure esptool is available."""
    try:
        import esptool
        info(f"esptool version: {esptool.__version__}")
        return True
    except ImportError:
        error("esptool not found!")
        print("\nInstall with: pip install esptool")
        return False


def flash_firmware(port: str, device: str, firmware_path: Path, erase: bool = True):
    """Flash firmware to device using esptool."""
    device_config = SUPPORTED_DEVICES.get(device)
    chip = device_config["chip"]
    offset = device_config["flash_offset"]
    
    header(f"Flashing {device_config['description']}")
    
    info(f"Port: {port}")
    info(f"Chip: {chip}")
    info(f"Firmware: {firmware_path.name}")
    
    # Import esptool
    try:
        import esptool
    except ImportError:
        error("esptool not installed. Run: pip install esptool")
        sys.exit(1)
    
    # Erase flash first (recommended for clean install)
    if erase:
        print(f"\n{colors.yellow('Erasing flash...')}")
        try:
            erase_args = [
                "--chip", chip,
                "--port", port,
                "--baud", "921600",
                "--before", "default_reset",
                "erase_flash"
            ]
            esptool.main(erase_args)
            success("Flash erased!")
        except Exception as e:
            warn(f"Erase failed (may be okay): {e}")
        
        # Wait for device to come back
        print(f"{colors.yellow('Waiting for device to reconnect...')}")
        time.sleep(3)
        
        # Re-detect port
        new_ports = find_serial_ports()
        if new_ports and port not in new_ports:
            port = new_ports[0]
            info(f"Device reconnected on: {port}")
    
    # Flash firmware
    print(f"\n{colors.yellow('Writing firmware...')}")
    
    # Try different baud rates
    baud_rates = ["921600", "460800", "115200"]
    flash_success = False
    
    for baud in baud_rates:
        try:
            info(f"Trying baud rate: {baud}")
            flash_args = [
                "--chip", chip,
                "--port", port,
                "--baud", baud,
                "--before", "default_reset",
                "--after", "hard_reset",
                "write_flash",
                "--flash_mode", "dio",
                "--flash_freq", "80m",
                "--flash_size", "detect",
                hex(offset), str(firmware_path)
            ]
            esptool.main(flash_args)
            flash_success = True
            break
        except Exception as e:
            warn(f"Flash at {baud} baud failed: {e}")
            time.sleep(1)
    
    if not flash_success:
        error("Failed to flash firmware!")
        print("\nTroubleshooting:")
        print("  1. Hold BOOT button, press RST, then release BOOT")
        print("  2. Try a different USB cable")
        print("  3. Try a different USB port")
        sys.exit(1)
    
    success("Firmware flashed successfully!")


# =============================================================================
# Device Configuration (via Meshtastic CLI)
# =============================================================================

def check_meshtastic_cli() -> bool:
    """Check if meshtastic CLI is available."""
    try:
        result = subprocess.run(
            [sys.executable, "-m", "meshtastic", "--version"],
            capture_output=True, text=True, timeout=10
        )
        if result.returncode == 0:
            info(f"meshtastic CLI: {result.stdout.strip()}")
            return True
    except Exception:
        pass
    
    # Try direct command
    try:
        result = subprocess.run(
            ["meshtastic", "--version"],
            capture_output=True, text=True, timeout=10
        )
        if result.returncode == 0:
            info(f"meshtastic CLI: {result.stdout.strip()}")
            return True
    except Exception:
        pass
    
    warn("meshtastic CLI not found. Configuration will be skipped.")
    print("Install with: pip install meshtastic")
    return False


def wait_for_device_ready(port: str, timeout: int = 45) -> bool:
    """Wait for device to boot and be ready for communication."""
    print(f"{colors.yellow('Waiting for device to boot...')}")
    
    start_time = time.time()
    while time.time() - start_time < timeout:
        try:
            result = subprocess.run(
                [sys.executable, "-m", "meshtastic", "--port", port, "--info"],
                capture_output=True, text=True, timeout=15
            )
            if result.returncode == 0 and "owner" in result.stdout.lower():
                success("Device is ready!")
                return True
        except Exception:
            pass
        
        time.sleep(2)
        remaining = int(timeout - (time.time() - start_time))
        print(f"  Waiting... ({remaining}s remaining)", end="\r")
    
    print()
    warn("Device not responding. It may still be booting.")
    return False


def run_meshtastic_cmd(port: str, args: List[str], description: str) -> bool:
    """Run a meshtastic CLI command."""
    cmd = [sys.executable, "-m", "meshtastic", "--port", port] + args
    
    for attempt in range(3):
        try:
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
            if result.returncode == 0:
                return True
            if attempt < 2:
                warn(f"{description} - attempt {attempt + 1} failed, retrying...")
                time.sleep(2)
        except subprocess.TimeoutExpired:
            warn(f"{description} - timed out")
        except Exception as e:
            warn(f"{description} - error: {e}")
    
    return False


def configure_device(port: str, config: dict):
    """Configure the Meshtastic device."""
    header("Configuring Device")
    
    if not check_meshtastic_cli():
        return
    
    # Wait for device to be ready
    if not wait_for_device_ready(port):
        warn("Proceeding with configuration anyway...")
    
    # Build configuration command
    config_args = []
    
    # Region
    if config.get("region"):
        config_args.extend(["--set", "lora.region", config["region"]])
    
    # Serial module settings
    if config.get("serial_enabled"):
        config_args.extend(["--set", "serial.enabled", "true"])
    
    if config.get("serial_rxd") is not None:
        config_args.extend(["--set", "serial.rxd", str(config["serial_rxd"])])
    
    if config.get("serial_txd") is not None:
        config_args.extend(["--set", "serial.txd", str(config["serial_txd"])])
    
    if config.get("serial_baud"):
        config_args.extend(["--set", "serial.baud", config["serial_baud"]])
    
    if config.get("serial_mode"):
        config_args.extend(["--set", "serial.mode", config["serial_mode"]])
    
    # Apply configuration
    print(f"{colors.yellow('Applying configuration...')}")
    
    if run_meshtastic_cmd(port, config_args, "Configuration"):
        success("Configuration applied!")
    else:
        warn("Some configuration may have failed. Please verify settings.")
    
    time.sleep(2)
    
    # Verify configuration
    verify_configuration(port, config)


def verify_configuration(port: str, config: dict):
    """Verify device configuration."""
    print(f"\n{colors.yellow('Verifying configuration...')}")
    
    try:
        result = subprocess.run(
            [sys.executable, "-m", "meshtastic", "--port", port, "--info"],
            capture_output=True, text=True, timeout=30
        )
        
        if result.returncode != 0:
            warn("Could not verify configuration")
            return
        
        output = result.stdout
        
        # Check settings
        checks = [
            (f'"rxd": {config.get("serial_rxd")}', "Serial RX pin"),
            (f'"txd": {config.get("serial_txd")}', "Serial TX pin"),
            (config.get("serial_baud", "").replace("BAUD_", ""), "Baud rate"),
            ('"enabled": true', "Serial enabled"),
        ]
        
        all_good = True
        for pattern, name in checks:
            if pattern and pattern in output:
                success(f"{name}: OK")
            else:
                warn(f"{name}: NOT VERIFIED")
                all_good = False
        
        if all_good:
            success("All settings verified!")
        
        # Print serial config section
        print(f"\n{colors.blue('Serial Module Configuration:')}")
        print("-" * 40)
        
        # Extract serial section from JSON output
        try:
            # Find serial section in output
            if '"serial":' in output:
                start = output.find('"serial":')
                # Find the matching closing brace
                brace_count = 0
                end = start
                for i, c in enumerate(output[start:], start):
                    if c == '{':
                        brace_count += 1
                    elif c == '}':
                        brace_count -= 1
                        if brace_count == 0:
                            end = i + 1
                            break
                serial_section = output[start:end]
                print(serial_section)
        except Exception:
            pass
        
        print("-" * 40)
    
    except Exception as e:
        warn(f"Verification failed: {e}")


# =============================================================================
# Main
# =============================================================================

def show_summary(version: str, device: str, port: str, config: dict):
    """Display final summary."""
    header("Setup Complete!")
    
    print(f"  Firmware:    {colors.cyan(version)}")
    print(f"  Device:      {colors.cyan(SUPPORTED_DEVICES[device]['description'])}")
    print(f"  Port:        {colors.cyan(port)}")
    print()
    print("  Configuration:")
    print(f"    Region:      {colors.cyan(config.get('region', 'N/A'))}")
    print(f"    Serial:      {colors.cyan('Enabled' if config.get('serial_enabled') else 'Disabled')}")
    print(f"    RX Pin:      {colors.cyan(str(config.get('serial_rxd', 'N/A')))}")
    print(f"    TX Pin:      {colors.cyan(str(config.get('serial_txd', 'N/A')))}")
    print(f"    Baud Rate:   {colors.cyan(config.get('serial_baud', 'N/A').replace('BAUD_', ''))}")
    print(f"    Mode:        {colors.cyan(config.get('serial_mode', 'N/A'))}")
    print()
    print(f"{colors.green('Your device is ready to use!')}")
    print()


def install_dependencies():
    """Install required Python packages."""
    packages = ["esptool>=4.7.0", "pyserial>=3.5", "meshtastic>=2.3.0"]
    
    print(f"{colors.yellow('Installing dependencies...')}")
    for pkg in packages:
        try:
            subprocess.run(
                [sys.executable, "-m", "pip", "install", pkg, "--quiet"],
                check=True, timeout=120
            )
            success(f"Installed: {pkg}")
        except Exception as e:
            warn(f"Failed to install {pkg}: {e}")


def main():
    parser = argparse.ArgumentParser(
        description="Universal Meshtastic Firmware Flasher",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s                           # Auto-detect, flash Heltec V3
  %(prog)s --device tbeam            # Flash T-Beam
  %(prog)s --port COM3               # Use specific port (Windows)
  %(prog)s --port /dev/ttyUSB0       # Use specific port (Linux)
  %(prog)s --download-only           # Download firmware only
  %(prog)s --configure-only          # Configure without flashing
  %(prog)s --no-configure            # Flash without configuring
  %(prog)s --install-deps            # Install Python dependencies

Supported devices:
""" + "\n".join(f"  {k:15} - {v['description']}" for k, v in SUPPORTED_DEVICES.items())
    )
    
    parser.add_argument("--device", "-d", choices=SUPPORTED_DEVICES.keys(),
                        default=DEFAULT_DEVICE, help="Device type (default: heltec-v3)")
    parser.add_argument("--port", "-p", help="Serial port (auto-detect if not specified)")
    parser.add_argument("--download-only", action="store_true",
                        help="Download firmware only, don't flash")
    parser.add_argument("--configure-only", action="store_true",
                        help="Configure only, don't flash")
    parser.add_argument("--no-configure", action="store_true",
                        help="Flash without configuring")
    parser.add_argument("--no-erase", action="store_true",
                        help="Don't erase flash before writing")
    parser.add_argument("--force", "-f", action="store_true",
                        help="Force re-download even if cached")
    parser.add_argument("--install-deps", action="store_true",
                        help="Install required Python packages")
    parser.add_argument("--region", default=DEFAULT_CONFIG["region"],
                        help=f"LoRa region (default: {DEFAULT_CONFIG['region']})")
    parser.add_argument("--list-ports", action="store_true",
                        help="List available serial ports and exit")
    
    args = parser.parse_args()
    
    # Header
    header("Meshtastic Universal Flasher")
    info(f"Platform: {platform.system()} {platform.release()}")
    info(f"Python: {sys.version.split()[0]}")
    
    # Install dependencies
    if args.install_deps:
        install_dependencies()
        return
    
    # List ports
    if args.list_ports:
        ports = find_serial_ports()
        if ports:
            print("Available serial ports:")
            for p in ports:
                print(f"  {p}")
        else:
            print("No serial ports found")
        return
    
    # Setup paths
    script_dir = Path(__file__).parent.resolve()
    firmware_dir = script_dir / "firmware"
    
    # Force re-download
    if args.force:
        version_file = firmware_dir / ".current_version"
        if version_file.exists():
            version_file.unlink()
            info("Cleared firmware cache")
    
    # Check esptool
    if not args.configure_only and not args.download_only:
        if not check_esptool():
            print("\nInstall with: pip install esptool")
            print("Or run: python flash_meshtastic.py --install-deps")
            sys.exit(1)
    
    # Get latest version
    version, _ = get_latest_version()
    
    # Download firmware
    if not args.configure_only:
        firmware_path = download_firmware(version, args.device, firmware_dir)
        info(f"Firmware: {firmware_path}")
        
        if args.download_only:
            success(f"Firmware downloaded to: {firmware_path}")
            return
    
    # Find port
    port = select_port(auto=True, specified_port=args.port)
    
    # Flash
    if not args.configure_only:
        flash_firmware(port, args.device, firmware_path, erase=not args.no_erase)
        
        # Wait a bit for device to reboot
        time.sleep(5)
        
        # Re-detect port (may have changed after flash)
        ports = find_serial_ports()
        if ports and port not in ports:
            port = ports[0]
            info(f"Device reconnected on: {port}")
    
    # Configure
    config = DEFAULT_CONFIG.copy()
    config["region"] = args.region
    
    if not args.no_configure:
        configure_device(port, config)
    
    # Summary
    show_summary(version, args.device, port, config)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print(f"\n{colors.yellow('Interrupted by user')}")
        sys.exit(130)
    except Exception as e:
        error(f"Unexpected error: {e}")
        raise
