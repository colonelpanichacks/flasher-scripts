#!/usr/bin/env python3
"""
ESP32 Firmware Flasher - Main Menu
Optimized for flashing multiple devices in sequence
"""

import os
import platform
import subprocess
import sys
from pathlib import Path

# =============================================================================
# Cross-platform colors
# =============================================================================

class Colors:
    def __init__(self):
        self.enabled = self._supports_color()
        if self.enabled and platform.system() == "Windows":
            self._enable_windows_ansi()
    
    def _supports_color(self):
        if os.getenv("NO_COLOR"):
            return False
        return hasattr(sys.stdout, "isatty") and sys.stdout.isatty()
    
    def _enable_windows_ansi(self):
        try:
            import ctypes
            kernel32 = ctypes.windll.kernel32
            kernel32.SetConsoleMode(kernel32.GetStdHandle(-11), 7)
        except:
            self.enabled = False
    
    def _w(self, code, text):
        return f"\033[{code}m{text}\033[0m" if self.enabled else text
    
    def red(self, t): return self._w("91", t)
    def green(self, t): return self._w("92", t)
    def yellow(self, t): return self._w("93", t)
    def blue(self, t): return self._w("94", t)
    def magenta(self, t): return self._w("95", t)
    def cyan(self, t): return self._w("96", t)
    def white(self, t): return self._w("97", t)
    def dim(self, t): return self._w("90", t)
    def bold(self, t): return self._w("1", t)

c = Colors()

SCRIPT_DIR = Path(__file__).parent.resolve()

# =============================================================================
# Utilities
# =============================================================================

def clear():
    os.system('cls' if platform.system() == 'Windows' else 'clear')

def pause(msg="Press ENTER to continue..."):
    try:
        input(f"\n  {c.dim(msg)}")
    except:
        pass

def list_ports():
    """List available serial ports."""
    print(f"\n  {c.cyan('Scanning for serial ports...')}\n")
    
    ports = []
    if platform.system() == "Windows":
        try:
            import serial.tools.list_ports
            for p in serial.tools.list_ports.comports():
                ports.append((p.device, p.description))
        except ImportError:
            print(c.yellow("  pyserial not installed. Run option [I] first."))
            return
    else:
        dev = Path("/dev")
        for pattern in ["cu.usbmodem*", "cu.usbserial-*", "ttyUSB*", "ttyACM*"]:
            for p in dev.glob(pattern):
                ports.append((str(p), ""))
    
    if ports:
        print(f"  {c.green('Found:')}\n")
        for device, desc in sorted(ports):
            if desc:
                print(f"    {c.cyan(device):20} {c.dim(desc)}")
            else:
                print(f"    {c.cyan(device)}")
    else:
        print(c.yellow("  No serial ports found. Connect a device and try again."))

def install_deps():
    """Install required packages."""
    print(f"\n  {c.cyan('Installing dependencies...')}\n")
    pkgs = ["esptool>=4.7.0", "pyserial>=3.5", "meshtastic>=2.3.0"]
    for pkg in pkgs:
        print(f"  Installing {pkg}...", end=" ", flush=True)
        try:
            subprocess.run([sys.executable, "-m", "pip", "install", pkg, "-q"], 
                         check=True, timeout=120, capture_output=True)
            print(c.green("OK"))
        except:
            print(c.red("FAILED"))
    print(f"\n  {c.green('Done!')}")

# =============================================================================
# Flasher Functions
# =============================================================================

def run_flasher(script_path, args=None):
    """Run a flasher script."""
    if args is None:
        args = []
    
    if not script_path.exists():
        print(c.red(f"\n  Script not found: {script_path}"))
        return False
    
    cmd = [sys.executable, str(script_path)] + args
    
    try:
        result = subprocess.run(cmd)
        return result.returncode == 0
    except KeyboardInterrupt:
        print(f"\n  {c.yellow('Cancelled')}")
        return False
    except Exception as e:
        print(c.red(f"\n  Error: {e}"))
        return False

def flash_loop(name, script_path, args=None):
    """Flash loop - keeps flashing until user exits."""
    count = 0
    
    while True:
        clear()
        print(f"""
  {c.blue('=' * 58)}
  {c.bold(c.white(f'  {name.upper()} FLASH MODE'))}
  {c.blue('=' * 58)}

  {c.dim(f'Devices flashed this session: {c.cyan(str(count))}')}

  {c.yellow('[ENTER]')} Flash next device
  {c.yellow('[B]')}     Back to main menu

  {c.blue('-' * 58)}
        """)
        
        try:
            choice = input(f"  {c.green('>')} ").strip().upper()
        except (EOFError, KeyboardInterrupt):
            break
        
        if choice == 'B':
            break
        
        # Any other input (including empty) = flash
        print(f"\n  {c.cyan('=' * 58)}")
        print(f"  {c.bold('FLASHING...')}")
        print(f"  {c.cyan('=' * 58)}\n")
        
        success = run_flasher(script_path, args)
        
        if success:
            count += 1
            print(f"\n  {c.green('=' * 58)}")
            print(f"  {c.bold(c.green(f'  SUCCESS! Total flashed: {count}'))}")
            print(f"  {c.green('=' * 58)}")
        else:
            print(f"\n  {c.red('=' * 58)}")
            print(f"  {c.bold(c.red('  FLASH FAILED - Check connection and try again'))}")
            print(f"  {c.red('=' * 58)}")
        
        print(f"\n  {c.dim('Connect next device and press ENTER, or B to go back')}")
        try:
            choice = input(f"  {c.green('>')} ").strip().upper()
            if choice == 'B':
                break
        except:
            break
    
    return count

# =============================================================================
# Main Menu
# =============================================================================

def main_menu():
    clear()
    print(f"""
  {c.blue('+' + '=' * 56 + '+')}
  {c.blue('|')}{c.bold(c.white('          ESP32 FIRMWARE FLASHER'))}{' ' * 22}{c.blue('|')}
  {c.blue('+' + '=' * 56 + '+')}

  {c.dim(f'Platform: {platform.system()} | Python: {sys.version.split()[0]}')}

  {c.cyan('-' * 58)}
  {c.bold('  SELECT FIRMWARE:')}
  {c.cyan('-' * 58)}

    {c.yellow('[1]')}  {c.bold('Meshtastic-Heltec-V3')}
         {c.dim('Downloads latest stable, flashes & configures')}

    {c.yellow('[2]')}  {c.bold('OUI Spy Detector')}
         {c.dim('Flashes local firmware')}

    {c.yellow('[3]')}  {c.bold('Mesh-Detect-RemoteID')}
         {c.dim('Flashes local firmware')}

  {c.cyan('-' * 58)}
  {c.bold('  UTILITIES:')}
  {c.cyan('-' * 58)}

    {c.magenta('[P]')}  List Serial Ports
    {c.magenta('[I]')}  Install Dependencies

    {c.red('[Q]')}  Quit

  {c.cyan('-' * 58)}
    """)

def check_and_install_deps():
    """Check for required packages and install if missing."""
    missing = []
    
    try:
        import serial
    except ImportError:
        missing.append("pyserial")
    
    try:
        import esptool
    except ImportError:
        missing.append("esptool")
    
    if missing:
        print(f"\n  {c.yellow('Missing dependencies:')} {', '.join(missing)}")
        print(f"  {c.cyan('Installing automatically...')}\n")
        
        pkgs = ["esptool>=4.7.0", "pyserial>=3.5", "meshtastic>=2.3.0"]
        for pkg in pkgs:
            print(f"  Installing {pkg}...", end=" ", flush=True)
            try:
                subprocess.run(
                    [sys.executable, "-m", "pip", "install", pkg, "-q"],
                    check=True, timeout=120, capture_output=True
                )
                print(c.green("OK"))
            except Exception as e:
                print(c.red("FAILED"))
        
        print(f"\n  {c.green('Dependencies installed!')}")
        pause()

def main():
    # Auto-install missing dependencies
    check_and_install_deps()
    
    while True:
        main_menu()
        
        try:
            choice = input(f"  {c.green('Enter choice:')} ").strip().upper()
        except (EOFError, KeyboardInterrupt):
            break
        
        if choice == 'Q':
            break
        
        elif choice == '1':
            total = flash_loop(
                "Meshtastic-Heltec-V3",
                SCRIPT_DIR / "flashers" / "flash_meshtastic.py",
                ["--device", "heltec-v3"]
            )
            if total > 0:
                print(f"\n  {c.green(f'Session complete. Flashed {total} device(s).')}")
                pause()
        
        elif choice == '2':
            total = flash_loop(
                "OUI Spy Detector",
                SCRIPT_DIR / "flashers" / "flash_oui_detector.py"
            )
            if total > 0:
                print(f"\n  {c.green(f'Session complete. Flashed {total} device(s).')}")
                pause()
        
        elif choice == '3':
            total = flash_loop(
                "Mesh-Detect-RemoteID",
                SCRIPT_DIR / "flashers" / "flash_remoteid.py"
            )
            if total > 0:
                print(f"\n  {c.green(f'Session complete. Flashed {total} device(s).')}")
                pause()
        
        elif choice == 'P':
            list_ports()
            pause()
        
        elif choice == 'I':
            install_deps()
            pause()
        
        else:
            print(f"\n  {c.red('Invalid choice')}")
            pause()
    
    clear()
    print(f"\n  {c.green('Goodbye!')}\n")

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print(f"\n\n  {c.yellow('Interrupted')}")
        sys.exit(0)
