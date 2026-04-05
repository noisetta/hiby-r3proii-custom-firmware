# HiBy Mods

A collection of custom firmware modifications for HiBy digital audio players, along with documentation of the proprietary OTA firmware format for the benefit of the modding community.

This project is part of the [hiby-modding](https://github.com/hiby-modding) organization. Also see:

- [hiby_os_crack](https://github.com/hiby-modding/hiby_os_crack) by Tartarus6 — complementary firmware modding project with clean unpack/repack scripts, QEMU emulation setup, Windows support, and SOC hardware documentation.

## What This Project Does

Provides custom firmware builds and tools for modifying HiBy OS on supported devices. Modifications are built on top of the stock firmware and distributed as ready-to-flash `.upt` files.

**Current modifications in v1.3:**
- Unified Theme — modernized UI including updated system dialogs, battery icon, WiFi/BT scanning dialogs, volume bar, screensaver refinements, and navigation icons
- Alphabetical sorting — multi-language article support, symbols sort to top, updated scrollbar
- Extended Unicode font support — adds rendering for scripts not included in the stock firmware
- ADB support — root shell access via USB, enabled through a hidden easter egg

**Known Limitations:**
- Added Unicode scripts display left-to-right regardless of the script's natural reading direction — the HiBy OS text renderer does not support bidirectional text
- Characters appear in isolated forms and do not connect to each other — the OS renderer does not support contextual shaping

## Tested On

- Device: HiBy R3 Pro II (r3proii)
- Firmware version: current_version=0 (January 2026 release)
- Host OS used for building: Ubuntu / Pop!_OS (Linux)

> ⚠️ **Compatibility:** The pre-built firmware in this repository has only been
> tested on the HiBy R3 Pro II. Do not flash on other devices unless you have
> built and verified it yourself.

## Quick Install (Pre-built Firmware)

If you just want to flash the latest modifications without building from source:

1. Download `r3proii-v1.3.upt` from the [Releases](https://github.com/hiby-modding/hiby-mods/releases) section
2. Verify the checksum matches the one listed in the release notes
3. Copy it to the root of your SD card and rename it to `r3proii.upt`
4. Insert the SD card into your HiBy R3 Pro II
5. Hold **Volume Up** and press **Power** to enter the updater
6. Let it flash — it will say "Upgrading..." then "Succeeded"
7. Remove the SD card before the device reboots
8. Done

> **Note:** If something goes wrong, you can always restore by flashing the original stock firmware from HiBy's website using the same procedure.

## Enabling ADB

ADB can be enabled on any firmware version (including stock) without any modification:

1. Go to **Settings → About**
2. Tap the **"About"** text 10 times
3. A message saying "Test Mode Turned On" will appear
4. Connect the device to your PC via USB
5. Run `adb devices` to confirm the connection

To disable ADB, tap "About" 10 times again.

> **Note:** ADB and USB mass storage share the same USB interface and cannot run simultaneously. While ADB is enabled the device will not appear as a storage drive.

## Building From Source

### Requirements

```bash
sudo apt install squashfs-tools xorriso fontforge python3-fontforge p7zip-full
```

### Using the Mod Tool (Recommended)

The easiest way to build custom firmware is using the interactive mod tool:

```bash
# 1. Clone this repository
git clone https://github.com/hiby-modding/hiby-mods
cd hiby-mods

# 2. Place your stock .upt firmware in the Firmware/ folder

# 3. Run the mod tool
./tools/universal_mod_tool.sh
```

The tool will interactively ask which modifications to apply and handle all the repacking automatically.

### Manual Build

```bash
# 1. Clone this repository
git clone https://github.com/hiby-modding/hiby-mods
cd hiby-mods

# 2. Download the stock firmware from HiBy's website
# Place it at: firmware/r3proii_stock.upt

# 3. Run the build script
./tools/build_upt.sh firmware/r3proii_stock.upt firmware/r3proii-custom.upt

# 4. Flash the output file as described in Quick Install above
```

## Repository Structure

```
hiby-mods/
├── README.md
├── binaries/
│   └── Sorting Fix/          # Patched hiby_player binary
│       ├── hiby_player
│       └── Sorting Patch README.md
├── docs/
│   └── FIRMWARE_FORMAT.md    # Detailed OTA format documentation
├── themes/
│   └── Unified Theme/        # Community UI theme
├── tools/
│   ├── build_upt.sh          # Manual build script
│   ├── merge_arabic_font.py  # Font merging utility
│   ├── universal_mod_tool.sh # Interactive mod tool
│   └── MOD_TOOL.md           # Mod tool documentation
└── firmware/
    ├── r3proii-arabic.upt    # v1.0 pre-built firmware
    ├── r3proii-v1.1.upt      # v1.1 pre-built firmware
    ├── r3proii-v1.2.upt      # v1.2 pre-built firmware
    └── r3proii-v1.3.upt      # v1.3 pre-built firmware (latest)
```

## Documentation

See [docs/FIRMWARE_FORMAT.md](docs/FIRMWARE_FORMAT.md) for complete documentation of:

- The OTA update file format
- Chunk naming and hash chain system
- Squashfs build parameters
- Partition layout
- Boot sequence
- Font system
- Hardware details

This documentation was produced entirely through reverse engineering and may be useful for anyone wanting to build further modifications.

## Changelog

### v1.3
- Updated Unified Theme — expanded system dialog modernization, new icons throughout
- ADB support — fixed USB gadget conflict enabling reliable ADB connectivity

### v1.2
- Unified Theme — modernized launcher, screensaver, playing screen, stream media icons, boot logo
- Updated alphabetical sorting — multi-language article support, symbols sort to top

### v1.1
- Extended Unicode font support for scripts not included in stock firmware
- Alphabetical sorting fix — entries starting with "The" now sort correctly

### v1.0
- Initial release
- Documented OTA firmware format
- Proof of concept custom firmware build

## Disclaimer

This firmware is provided as-is with no warranty. Flashing custom firmware carries a small risk of making your device temporarily unbootable. In the event of a boot loop, you can always recover by flashing the original stock firmware from HiBy's website using the Volume Up + Power method described above.

This project is not affiliated with or endorsed by HiBy Music.

## Contributing

Contributions are welcome. Areas where help would be valuable:

- Testing on other HiBy devices that share the same firmware format
- Investigating kernel source availability (check github.com/hiby-music)
- Adding support for additional Unicode scripts
- GUI and theme modifications
- RockBox Bluetooth/WiFi integration
- Further ADB exploration and live system research
- Improving the build process

## Acknowledgements

- [@Jepl4r](https://github.com/Jepl4r) — Unified Theme, alphabetical sorting patch, mod tool
- [@Tartarus6](https://github.com/Tartarus6) — hiby_os_crack tooling and collaboration
- Noto Naskh Arabic font by Google (OFL licensed)
- HiBy Music for making a great device
- The [head-fi.org](https://head-fi.org) community
- The Reddit [r/hiby](https://reddit.com/r/hiby) community
