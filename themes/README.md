# Themes

Community contributed UI themes for HiBy OS devices.

## Available Themes

| Theme | Author | Device | Description |
|-------|--------|--------|-------------|
| Unified Theme | [@Jepl4r](https://github.com/Jepl4r) | R3 Pro II | Modernized icons, rounded launcher, updated boot logo |

## Installing a Theme

Themes are applied by copying the modified files into your custom firmware build before repacking. Each theme folder mirrors the device filesystem structure so you know exactly where each file goes.

1. Build a base firmware using the instructions in the main README
2. Copy the theme files into your `squashfs-root` directory
3. Repack and flash as normal

## Contributing a Theme

Submit a PR with your theme files in a new subdirectory under `themes/`.

### Requirements

- **Only include modified files** — do not include unmodified stock files
- **Include a README.md** explaining what was changed and why
- **Include screenshots** showing before and after
- **Mirror the device filesystem structure** inside your theme folder

### Folder Structure

```
themes/
└── Your Theme Name/
    ├── README.md
    ├── screenshots/
    └── usr/
        └── resource/
            ├── layout/
            └── litegui/
```

### README Template

```markdown
# Theme Name

Brief description of the theme.

## Changes

- `path/to/file.view` — description of what was changed
- `path/to/image.png` — description of what was changed

## Screenshots

![Screenshot](screenshots/example.png)

## Compatibility

- Device: HiBy R3 Pro II
- Firmware version: vX.X
- Works with stock hiby_player: Yes/No
- Works with patched hiby_player: Yes/No
```
