# Taking Screenshots on the HiBy R3 Pro II

This guide documents how to capture screenshots from the HiBy R3 Pro II via ADB
by reading the Linux framebuffer device directly. No additional software is required
on the device itself.

---

## Requirements

- ADB enabled firmware (any hiby-modding release)
- `adb` and `ffmpeg` installed on your Linux/Mac/Windows (WSL) machine
- USB cable

```bash
# Install on Ubuntu/Debian/Pop!_OS
sudo apt install adb ffmpeg
```

---

## Setup

1. On the R3 Pro II, go to **Settings → USB** and set the mode to **Dock**
2. Connect the device via USB
3. Verify ADB sees the device:

```bash
adb devices
```

You should see a device listed with status `device`. If it shows `unauthorized`,
disconnect and reconnect — the device may auto-authorize without prompting since
it runs bare Linux rather than full Android.

---

## Capturing a Screenshot

```bash
adb shell "cat /dev/fb0" > /tmp/fb.raw && ffmpeg -y \
  -vcodec rawvideo -f rawvideo \
  -pix_fmt rgb565le \
  -s 480x720 \
  -i /tmp/fb.raw \
  -frames:v 1 -update 1 \
  ~/Downloads/hiby_shot.png
```

The file will be saved to `~/Downloads/hiby_shot.png`. Change the output path as needed.

### Framebuffer technical details

| Property | Value |
|---|---|
| Device | `/dev/fb0` |
| Pixel format | `rgb565le` (16-bit, little-endian) |
| Buffer dimensions | 480×720 (double-buffered: two 480×360 frames stacked) |
| Stride | 960 bytes/row |
| Active frame | First 480 rows (rows 0–479) |

---

## Theme and Color Notes

### Use Light theme for accurate colors

The **Dark theme** on this firmware renders UI elements in a pink/magenta color
that is faithfully captured by the framebuffer — it is not a capture artifact.
If you expect grey buttons and get pink, that is what the Dark theme actually
looks like in the framebuffer.

Switch to **Light theme** (Settings → UI Themes → Light) for screenshots with
accurate, neutral colors.

### Theme color setting

The **Theme color** option in settings defines an accent color overlay. If enabled,
this color will appear in captured screenshots exactly as rendered on screen.

---

## Known Limitations

### IPU-rendered content will not capture correctly

The R3 Pro II uses the **Ingenic IPU** (Image Processing Unit) to composite certain
graphical elements directly to the display hardware, bypassing the `/dev/fb0`
framebuffer entirely. This content cannot be captured via this method and will
appear as horizontal glitch lines or corrupted color blocks in screenshots.

**Affected screens:**
- Main launcher (app grid icons)
- Music browser category grid (All, Files, Albums, Artists, Genres icons)
- Album art thumbnails in list views
- Now playing screen album art

**Unaffected screens (capture perfectly):**
- All text-based settings menus
- System settings
- Playback settings (MSEB, EQ, PEQ, filters)
- Now playing screen UI chrome (without album art)
- File browser (text list view)
- Any screen consisting primarily of text and simple UI elements

### Workaround for IPU screens

Use a physical camera to photograph icon-heavy screens. The framebuffer method
is best suited to settings and menu documentation.

### "Packet corrupt" warning in ffmpeg

ffmpeg will print a `Packet corrupt` warning during conversion. This is harmless —
it occurs because the raw framebuffer size (691,204 bytes) is not an exact multiple
of the expected frame size. The output image is unaffected.

---

## Quick Reference Script

Save as `hiby-screenshot.sh` and `chmod +x` it:

```bash
#!/usr/bin/env bash
# Usage: ./hiby-screenshot.sh [output.png]
OUTPUT="${1:-hiby_$(date +%Y%m%d_%H%M%S).png}"
adb shell "cat /dev/fb0" > /tmp/fb.raw && \
ffmpeg -y -vcodec rawvideo -f rawvideo -pix_fmt rgb565le -s 480x720 \
  -i /tmp/fb.raw -frames:v 1 -update 1 "$OUTPUT" 2>/dev/null && \
echo "Saved: $OUTPUT"
```

---

## Examples of Clean Captures

Screens that produce clean, accurate screenshots:

- Settings → Play (MSEB, Equalizer, PEQ, filters)
- Settings → System (screensaver, firmware update, about)
- Settings → UI Themes
- File browser (text list)
- Now playing (UI elements only, no album art region)

Screens that require a physical camera:

- Main launcher grid
- Music → category selection grid
- Any view showing album art thumbnails
