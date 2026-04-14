# Factory Diagnostic Mode on the HiBy R3 Pro II

This guide documents the built-in factory diagnostic mode on the HiBy R3 Pro II.
This mode is intended for hardware validation and was used during manufacturing QA.
It provides a menu-driven test suite for all major hardware components.

---

> ⚠️ **WARNING: Entering factory mode will factory reset the device.**
> Settings, theme selection, and the music database (`usrlocal_media.db`) will all
> be wiped. **Back up your database before using this mode.**
>
> ```bash
> adb pull /usr/data/usrlocal_media.db ~/usrlocal_media.db.bak
> ```

---

## How to Enter Factory Mode

1. Create an empty file named exactly `hiby_linux_factory_mode` (no extension) on
   the root of the SD card
2. Insert the SD card and reboot the device
3. The factory diagnostic menu will appear on boot instead of the normal UI

The `hiby_player` binary checks only for the presence of this file — the file can
be empty. Remove the file from the SD card before rebooting again to return to
normal operation.

---

## Diagnostic Menu

The following tests are available:

| Menu item (Chinese) | Test |
|---|---|
| 序列号 | Serial number display |
| 一键测试 | One-key full test |
| 屏幕测试 | Screen (LCD) test |
| 按键测试 | Button key test |
| LED灯测试 | LED light test |
| Wi-Fi测试 | Wi-Fi (RF) test |
| 触摸测试 | Touchscreen test |
| TF卡测试 | TF/SD card test |
| OTG测试 | OTG test |

---

## Log Output

After running tests, a `log.txt` file is created on the SD card root. Each entry
records a timestamp and pass/fail result per test. Example output:

```
Thu Apr  9 17:27:28 2026-<led test success>
Thu Apr  9 17:27:46 2026-<key test success>
Thu Apr  9 17:27:53 2026-<lcd test success>
Thu Apr  9 17:28:30 2026-<tf test success>
Thu Apr  9 17:28:47 2026-<touch test success>
Thu Apr  9 17:30:13 2026-<audio test success>
Thu Apr  9 17:30:56 2026-<rf test success>
Thu Apr  9 17:30:58 2026-<bt_on test success>
```

Entries are appended on each test run. The log persists on the SD card after
exiting factory mode.

---

## Known Behaviour

- **Factory reset on entry:** The device resets settings and wipes the music
  database the moment factory mode is triggered on boot — confirmed to occur
  even without starting any tests. The `hiby_player` binary appears to require
  all settings to be at default values as a precondition for hardware testing,
  which is why the reset is unconditional.
- **No Android-style confirmation:** There is no warning prompt — the reset
  happens silently.
- **Safe to browse the menu:** Once in the mode, navigating the menu and running
  individual tests does not cause additional resets.
- **Return to normal:** Remove `hiby_linux_factory_mode` from the SD card root
  and reboot. The device will return to normal operation, but you will need to
  restore your database and reconfigure settings.

---

## Database Backup and Restore

Always back up your music database before using factory mode.

**Backup via ADB:**
```bash
adb pull /usr/data/usrlocal_media.db ~/usrlocal_media.db.bak
```

**Restore via ADB after reset:**
```bash
adb push ~/usrlocal_media.db.bak /usr/data/usrlocal_media.db
adb shell "killall hiby_player"
```

Alternatively, use the **PC Database Updater** tool to rebuild the database from
your SD card music files.
