# HiBy R3 Pro II Themes Patch

## Overview

This patch extends the theme selection UI from 2 themes to 4. The HiBy firmware internally supports up to 6 themes. The folder mapping, NAND read/write, and theme loading code all handle theme indices 1 through 6 out of the box. The only things limiting it to 2 choices were two functions: one that populates the theme list in Settings, and one that reads the currently selected theme's display name for the subtitle.

## How themes work in the firmware

When the user selects a theme, the firmware stores a 0-based index in a global settings array (`DAT_009666a0[7]`). This index is used everywhere to build resource paths:

- **litegui resources** are resolved via a pointer table at `0x7ed854` that maps indices to folder name strings (`theme1\\` through `theme6\\`). The path becomes `z:\litegui\themeN\...`.
- **layout files** are built with `sprintf("z:\\layout\\theme%d\\...", index + 1)`, producing paths like `z:\layout\theme3\main.json`.
- **The theme ID is persisted** to NAND flash (`/dev/mtd5`) as the string `theme:N` (1-based), and read back at boot by parsing the digit.

None of these mechanisms have a limit of 2 — they already work for any theme number up to at least 6. The setter function (`case 0x4` in the settings switch) stores the index with no bounds check. The NAND writer (`FUN_004822c0`) formats `theme:%d` with `index + 1` and accepts any value. The NAND reader (`FUN_00469b00`) parses digits 0–9.

### Translation strings

Theme display names are stored as translation strings in `sys_set.ini` (located in `usr/resource/str/<language>/`). When `dark_theme_enable` is set to `1` in `config.json`, the firmware reads keys `light_color` and `dark_color` for the first two theme names. When set to `0`, it reads `theme_1` and `theme_2`. The new themes use keys `theme_3` and `theme_4` regardless of the `dark_theme_enable` setting.

## What the patch changes

The patch modifies two functions and adds two string constants. Nothing else in the binary is modified.

### Patch A | New strings in rodata

Two null-terminated strings are placed in an unused zero region at VA `0x7f2d4c`:

| VA | String | Purpose |
|---|---|---|
| `0x7f2d4c` | `theme_3` | Translation key for 3rd theme display name |
| `0x7f2d54` | `theme_4` | Translation key for 4th theme display name |

### Patch B | Theme list population (`FUN_004e6d80`)

This function populates the theme selection listview in the Settings dialog. It reads display names from `sys_set.ini` and adds them to the UI list widget.

**Original behavior:** iterates over 2 key pointers (`theme_1`/`theme_2`, or `light_color`/`dark_color` when `dark_theme_enable=1`) stored on the stack, calls the list widget's add-item method for each, and returns `2`.

**Patched behavior:** iterates over 4 key pointers (`light_color`, `dark_color`, `theme_3`, `theme_4` — or `theme_1`, `theme_2`, `theme_3`, `theme_4` when `dark_theme_enable=0`) and returns `4`.

Since the rewritten function needs more instructions than the original (62 vs 56 — extra stack slots for two more key pointers, plus the code to load and store them), it doesn't fit in-place. The patch uses a **code cave** at VA `0x41c0b4` (a 16 KB zero region in the text segment) and replaces the first instruction of the original function with a `j 0x41c0b4` trampoline.

The rewritten function is a faithful reproduction of the original with these differences:

- Stack frame increased from `0xac0` to `0xad0` bytes (2 extra pointer slots + alignment).
- Saved register offsets shifted by +8 to make room for `keys[2]` and `keys[3]`.
- After storing the first two key pointers (and calling `FUN_0042f6a0(4)` to check `dark_theme_enable`, which may replace them with `light_color`/`dark_color`), the new code stores `theme_3` and `theme_4` pointers at `sp+0xaa8` and `sp+0xaac`.
- The loop end sentinel (`s4`) is set to `sp+0xab0` instead of `sp+0xaa8`, so the loop iterates 4 times.
- The return value is `4` instead of `2`.

### Patch C | Subtitle reader (at `0x4e1224`)

This code is inside a large settings handler function. It reads the **currently selected** theme's display name to show as subtitle under "UI themes" on the System settings page.

**Original behavior:** gets the current theme index via `FUN_0042a500(4)`, then:
- Index 0 → reads `light_color` (or `theme_1`) from `sys_set.ini`
- Index 1 → reads `dark_color` (or `theme_2`) from `sys_set.ini`
- Any other index → exits without writing a subtitle (subtitle stays empty)

**Patched behavior:** the `bne` instruction at `0x4e122c` (which rejected indices ≥ 2) is replaced with a `j 0x41c1b0` to a code cave that handles all 4 indices:
- Index 0 → `light_color` / `theme_1` (handled by original `beqz` at `0x4e1224`, unchanged)
- Index 1 → `dark_color` / `theme_2` (handled in cave)
- Index 2 → `theme_3` (handled in cave)
- Index 3 → `theme_4` (handled in cave)
- Any other index → exits to `0x4e101c` (no subtitle, same as original default)

Each handler calls `FUN_00427820("sys_set.ini", key, buffer, 0x7f)` to read the translation string, then jumps to the common exit at `0x4e1020`. The delay slot after each exit jump executes `lw $v0, 0xb8($sp)` (opcode `0x8FA200B8`), matching the original instruction at `0x4e124c`.

### Patch sites summary

| Location | Original | Patched | Purpose |
|---|---|---|---|
| `0x4e6d80` | `addiu sp, sp, -0xac0` | `j 0x41c0b4` | Trampoline to list cave |
| `0x4e6d84` | `lui v0, 0x82` | `nop` | Trampoline delay slot |
| `0x41c0b4`–`0x41c1a8` | zeros | 62 MIPS instructions | Rewritten list function (Patch B) |
| `0x4e122c` | `bne s1, v1, 0x4e101c` | `j 0x41c1b0` | Redirect to subtitle cave |
| `0x4e1230` | `lui a0, 0x7f` | `nop` | Delay slot cleanup |
| `0x41c1b0`–`0x41c234` | zeros | 34 MIPS instructions | Subtitle handler (Patch C) |
| `0x7f2d4c` | zeros | `theme_3\0` | New translation key (Patch A) |
| `0x7f2d54` | zeros | `theme_4\0` | New translation key (Patch A) |

Total code cave usage: 388 bytes out of 16,364 available. File size is unchanged.

## Setup

1. **In `sys_set.ini`** (under `usr/resource/str/<language>/`), add display names for the new themes:
   ```xml
   <theme_3>Theme Name</theme_3>
   <theme_4>Theme Name</theme_4>
   ```

2. **Create litegui theme folders** with your custom resources (images, colors, config):

   ```
   /usr/resource/litegui/theme3/
   /usr/resource/litegui/theme4/
   ```

3. **Create layout theme folders** with all required layout files:

   ```
   /usr/resource/layout/theme3/
   /usr/resource/layout/theme4/
   ```
   Each folder must contain the same structure as `theme1/` or `theme2/`. The simplest approach is to copy an existing theme's layout folder in its entirety and customize from there.

## What was NOT patched (and why)

- **`FUN_00469b00` / `FUN_00469d20` (boot animation):** these read the theme ID from NAND for the boot animation system. They already handle any single-digit theme ID, and the `DAT_009698c0 < 2` check at `0x469da0` is a boot animation *type* limit, not a theme limit. Modifying it causes a bootloop.
- **Theme setter (`case 0x4`):** stores the index directly with no range check — already works for indices 0–5.
- **`FUN_004822c0` (NAND writer):** formats `theme:%d` with any number — no change needed.
- **`FUN_00428d60` and related litegui path builders:** use the pointer table at `0x7ed854` which already contains entries for `theme2\\` through `theme6\\` — no change needed.
- **Layout path builders (`FUN_0042b740`, `FUN_004bac20`, `FUN_0054cfc0`):** all use `sprintf("theme%d", index+1)` — no change needed.
>Note: the boot logo can be changed by editing the **S11jpeg_display_shell** file inside `/etc/init.d`
