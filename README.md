# ESP32 Firmware Flasher

Cross-platform flasher for ESP32 devices. Works on **Windows**, **macOS**, and **Linux**.

## Quick Start

**Windows:** Double-click `flash.bat`

**Mac/Linux:** 
```bash
chmod +x flash.sh
./flash.sh
```

## Available Firmware

| Option | Name | Description |
|--------|------|-------------|
| 1 | Meshtastic-Heltec-V3 | Downloads latest stable, flashes & configures |
| 2 | OUI Spy Detector | Flashes local firmware |
| 3 | Mesh-Detect-RemoteID | Flashes local firmware |

## Requirements

- Python 3.8+
- USB drivers (CP210x or CH340 if needed)

Dependencies install automatically on first run.

## Usage

1. Run `flash.bat` (Windows) or `./flash.sh` (Mac/Linux)
2. Select firmware (1, 2, or 3)
3. Connect device via USB
4. Press ENTER to flash
5. Repeat for multiple devices
6. Press B to go back to menu

## Troubleshooting

**Device not found:** Install USB drivers (CP210x/CH340), try different cable/port

**Flash failed:** Hold BOOT, press RST, release BOOT (enters bootloader)

**Linux permission denied:** `sudo usermod -a -G dialout $USER` then log out/in

## Structure

```
├── flash.bat           # Windows
├── flash.sh            # Mac/Linux
├── flash.py            # Main menu
├── requirements.txt
├── flashers/           # Flasher scripts
│   ├── flash_meshtastic.py
│   ├── flash_oui_detector.py
│   └── flash_remoteid.py
└── bins/               # Firmware files
    ├── oui-detector/
    └── remoteid/
```

## License

MIT, see [LICENSE](LICENSE).
