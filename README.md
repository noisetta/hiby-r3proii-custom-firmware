# HiBy R3 Pro II Custom Firmware - Arabic Font Support

This project adds Arabic text rendering support to the HiBy R3 Pro II digital audio player, and documents the proprietary OTA firmware format for the benefit of the modding community.

## What This Does

By default the HiBy R3 Pro II cannot render Arabic script — Arabic text in music file names, folder names, and metadata tags shows as boxes with X's. This firmware modification adds 252 Arabic Unicode glyphs (U+0600–U+06FF) from the open-source Noto Naskh Arabic font into the device's Thai supplementary font file, enabling correct Arabic text rendering throughout the OS.

- Arabic text in music metadata renders correctly ✓
- Arabic folder and file names render correctly ✓
- All 13 original languages including Thai remain fully functional ✓
- No other functionality is affected ✓

## Tested On

- Device: HiBy R3 Pro II (r3proii)
- Firmware version: current_version=0 (January 2026 release)
- Host OS used for building: Ubuntu / Pop!_OS (Linux)

## Quick Install (Pre-built Firmware)

If you just want Arabic support and don't want to build from source:

1. Download `r3proii-arabic.upt` from the Releases section
2. Verify the MD5 checksum matches the one listed in the release notes
3. Copy it to the root of your SD card and rename it to `r3proii.upt`
4. Insert the SD card into your HiBy R3 Pro II
5. Hold **Volume Up** and press **Power** to enter the updater
6. Let it flash — it will say "Upgrading..." then "Succeeded"
7. Remove the SD card before the device reboots
8. Done — Arabic text will now render correctly

> **Note:** If something goes wrong, you can always restore by flashing the original stock firmware from HiBy's website using the same procedure.

## Building From Source

### Requirements

```bash
sudo apt install squashfs-tools xorriso fontforge python3-fontforge
```

### Steps

```bash
# 1. Clone this repository
git clone https://github.com/YOURUSERNAME/hiby-r3proii-custom-firmware
cd hiby-r3proii-custom-firmware

# 2. Download the stock firmware from HiBy's website
# Place it at: firmware/r3proii_stock.upt

# 3. Run the build script
./tools/build_upt.sh firmware/r3proii_stock.upt firmware/r3proii-arabic.upt

# 4. Flash the output file as described in Quick Install above
```

### What the Build Script Does

1. Mounts the stock `.upt` ISO and reassembles the rootfs from delta chunks
2. Extracts the squashfs filesystem
3. Merges 252 Arabic glyphs from Noto Naskh Arabic into `Thai.ttf`
4. Repacks the squashfs with identical parameters to the original
5. Splits the new rootfs into correctly named and hashed chunks
6. Packages everything into a valid `.upt` ISO file

## Repository Structure

```
hiby-r3proii-custom-firmware/
├── README.md
├── docs/
│   └── FIRMWARE_FORMAT.md    # Detailed OTA format documentation
├── tools/
│   ├── build_upt.sh          # Complete build script
│   └── merge_arabic_font.py  # Font merging script
└── firmware/
    └── r3proii-arabic.upt    # Pre-built firmware (in Releases)
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

## Font License

The Arabic glyphs used in this modification come from **Noto Naskh Arabic** by Google, licensed under the [SIL Open Font License 1.1](https://scripts.sil.org/OFL). The font is free to use, modify and redistribute.

## Disclaimer

This firmware modification is provided as-is with no warranty. Flashing custom firmware carries a small risk of making your device temporarily unbootable. In the event of a boot loop, you can always recover by flashing the original stock firmware from HiBy's website using the Volume Up + Power method described above.

This project is not affiliated with or endorsed by HiBy Music.

## Contributing

Contributions are welcome. Areas where help would be valuable:

- Testing on other HiBy devices that share the same firmware format
- Enabling ADB (the daemon is present but disabled)
- Investigating kernel source availability (check github.com/hiby-music)
- Adding support for other scripts (Persian, Urdu, Hebrew, etc.)
- Improving the build process

## Acknowledgements

- Noto Naskh Arabic font by Google (OFL licensed)
- HiBy Music for making a great device
- The head-fi.org community for DAP enthusiasm
