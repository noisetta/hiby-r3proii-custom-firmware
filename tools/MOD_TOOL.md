# HiBy OS Firmware Modder & Repacker

Automated cross-platform Bash script designed to unpack, modify, and repack firmware files (`.upt`) for HiBy OS devices (specifically tailored and tested for the HiBy R3 Pro II). 

This tool easily allows the user to apply custom themes and patched binaries without manually dealing with SquashFS extraction, MD5 hash chaining, or ISO repacking.

## Features
* **Cross-Platform:** Fully compatible with both **macOS** and **Linux**. It automatically detects your OS and adapts its commands.

* **Dynamic Menus:** Automatically detects any custom binaries or themes you place in the respective folders—no hardcoding or script editing required.

* **Safe Repacking:** Calculates the exact MD5 hash chains required by the HiBy bootloader to ensure successful flashing without soft-bricks.

* **macOS Junk Cleanup:** Automatically removes invisible Apple system files (`.DS_Store`, `._*`) from the filesystem before sealing the firmware.

---

## Prerequisites & Dependencies

To run this script, your system needs a few standard command-line tools installed. 

### Linux (Debian / Ubuntu / Mint)
Open your terminal and run:
```bash
sudo apt update && sudo apt install -y p7zip-full squashfs-tools genisoimage coreutils
```

### Linux (Arch / Manjaro)
Open your terminal and run:
```bash
sudo pacman -S p7zip squashfs-tools cdrtools coreutils
```

### macOS (via Homebrew)
If you don't have Homebrew installed, get it from [brew.sh](https://brew.sh/). Then, open your terminal and run:
```bash
brew install squashfs cdrtools coreutils
```
---

## Directory Structure

Before running the script, make sure your working directory is organized exactly like this:

```text
Main folder/
│
├── Tools/				      
│   ├── universal_mod_tool.sh     # This is the tool to modify the firmware.
│   ├── merge_arabic_font.py
│   └── build_upt.sh
│
├── Firmware/                     # This folder contains the modifiable base Firmwares
│   ├── r3proii.upt 
│   └── r3proii-arabic.upt
│
├── Binaries/                     # Put your custom patched binaries here
│   ├── Sorting Fix/
│   │   └── hiby_player           # The executable file MUST be named 'hiby_player'
│   └── Another_Mod/
│       └── hiby_player
│
└── Themes/                       # Put your custom themes here
    ├── Theme 1/
    │   └── ...                   # (Folders and UI files go here)
    └── Theme 2/
    └── ...

```

> Note:
> 
> You can add as many theme or binary folders as you want. The script will automatically read the folder names and offer them as choices in the interactive menu.

---

## How to Use

> This instrutions apply to the **universal-mod-tool** shell script.

1. **Prepare your files:**
   
   Ensure the `.upt` firmware files are inside the `Firmware` folder.
   Place any themes or patched binaries you want to use in their respective folders.
   
2. **Make the script executable:**
    
   > You only need to do this once and **only** if the terminal shows a `permission denied` error
 
   Open your terminal, navigate to your project folder, and run:
   ```bash
   chmod +x mod-tool.sh
   ```
   
3. **Run the script:**

   ```bash
   ./mod-tool.sh
   ```
   
4. **Follow the interactive prompts:**
   
   * Choose which base firmware to extract.
   * Type `y` to apply a patched binary and select one from the list.
   * Type `y` to apply a custom theme and select one from the list.

5. **Flashing the firmware:**
   
   Once the script finishes successfully, a new file named **`r3proii.upt`** will be generated in your main project folder.

   * Copy the `r3proii.upt` file to the root of your MicroSD card
   * Insert it into the player
   * Go into the settings and start the system update process by clicking on `Firmware update` --> `Via SD_Card`
   
---

# ⚠️ Disclaimer
> Modifying device firmware always carries a risk. Make sure your device has enough battery before flashing. The creator of this script is not responsible for bricked devices or loss of data. Use at your own risk.
