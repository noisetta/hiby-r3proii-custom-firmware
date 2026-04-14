# Done Dialog Patch for DB Manager

## Overview

This patch adds a **"Done!"** popup dialog that appears for 2 seconds after the Database Manager completes either a Save or Copy operation. Previously, the user had no visual feedback that the operation had finished.

The popup is displayed using the firmware's native `FUN_004949c0` dialog mechanism, which reads localized text from `exception.ini`.

## How It Works

The DB Manager's SET Handler calls `system()` to perform the file copy, then the Reload Routine refreshes the database and UI. This patch inserts a new **Show Done** routine between the Reload Routine and the return path: after the database has been fully reloaded and the UI refreshed, the routine displays a timed popup dialog, then returns control to the caller.

## Patches

### Patch A | Click Handler — Save view pointer (`0x41BFEC`)

The DB Manager Click Handler (at `0x41BFD0`) already stores `flag = 1` at `0x916100` when Database Manager is opened. The popup function `FUN_004949c0` requires a parent view pointer as its first argument. The Settings view pointer lives in `$s2` (a callee-saved register that persists through the entire call chain), so this patch saves it to a global at `0x916104` for the Show Done routine to use later.

The instruction block at `0x41BFEC`–`0x41C004` was reordered to make room without increasing code size:

| Address | Original | Patched | Notes |
|---|---|---|---|
| `0x41BFEC` | `or $a0, $s2, $zero` | `sw $s2, 0x6104($t0)` | Save view ptr (`$t0` = `0x00910000` from `0x41BFE0`) |
| `0x41BFFC` | `or $a3, $zero, $zero` | `addiu $a2, $a2, -26956` | Moved from delay slot at `0x41C004` |
| `0x41C004` | `addiu $a2, $a2, -26956` | `or $a0, $s2, $zero` | Moved to delay slot of `jal` at `0x41C000` |

The `$a3 = 0` setup was removed. `FUN_004aba00` does not require it — confirmed by the Font Fix Trampoline at `0x41BFA0` and the dispatch call at `0x4E19FC`, both of which omit `$a3`.

### Patch B | Reload Routine — Redirect to Show Done (`0x41C0B0`)

The Reload Routine's final jump is changed from the original return path to the new Show Done routine. The Reload Routine itself (database close, reopen, UI refresh events) runs **completely unchanged** before this jump executes:

| Address | Original | Patched |
|---|---|---|
| `0x41C0B0` | `j 0x004E331C` | `j 0x0041C0E0` |

### Patch C | `"db_done"` key string (`0x41C0D4`)

The null-terminated ASCII string `"db_done"` (8 bytes) is placed at `0x41C0D4`, in the code cave immediately after `get_language` ends at `0x41C0D0`. This string is used as the lookup key in `exception.ini`.

### Patch D | Show Done routine (`0x41C0E0`)

A 16-instruction (64-byte) routine placed at `0x41C0E0`. It allocates a small stack frame, loads the saved view pointer, calls the firmware's popup function, then continues to the original return path:

```mips
# Show Done routine — displays "Done!" popup for 2000ms
addiu  $sp, $sp, -24          # allocate stack frame
sw     $ra, 20($sp)           # save return address
sw     $zero, 16($sp)         # 5th arg (callback) = NULL
lui    $t0, 0x0091
lw     $a0, 0x6104($t0)       # a0 = saved view pointer (0x916104)
lui    $a1, 0x007F
addiu  $a1, $a1, -11184       # a1 = "exception.ini" (0x7ED450)
lui    $a2, 0x0042
addiu  $a2, $a2, -16172       # a2 = "db_done" key (0x41C0D4)
addiu  $a3, $zero, 2000       # a3 = timeout in ms
jal    0x004949C0              # FUN_004949c0 — show popup dialog
nop
lw     $ra, 20($sp)           # restore return address
addiu  $sp, $sp, 24           # restore stack
j      0x004E331C             # continue to original return path
nop
```

**Stack analysis:** When the Show Done routine runs, `$sp` points to `FUN_004e32c0`'s stack frame (the Reload Routine already restored it). Show Done allocates its own 24-byte frame for the `jal`, then deallocates it before jumping to `0x4E331C`, which performs `FUN_004e32c0`'s epilogue (`lw $ra, 28($sp)` / `lw $s0, 24($sp)` / `jr $ra` / `addiu $sp, $sp, 32`). The stack is balanced at every point.

## Global Variable

| Address | Segment | Size | Purpose |
|---|---|---|---|
| `0x916100` | BSS | 1 byte | `0` = Font Size mode, `1` = DB Manager mode (existing) |
| `0x916104` | BSS | 4 bytes | Saved parent view pointer for popup dialog (new) |

## Execution Flow

```
User taps "Save Database to SD" or "Copy Database from SD"
  → SET Handler DB path (0x41BF50)
    ├─ clears flag to 0
    ├─ system("cp ...")
    └─ j Reload Routine (0x41C070)
         ├─ lg_music_db_done()           — close database
         ├─ lg_music_db_init(...)        — reopen database
         ├─ event "1#1@[01]"             — media library refresh
         ├─ event "2#0@[06]"             — UI refresh
         ├─ lw $ra / addiu $sp           — restore stack
         └─ j Show Done (0x41C0E0)                          ← NEW
              ├─ lw $a0, saved view pointer (0x916104)
              ├─ FUN_004949c0(view, "exception.ini", "db_done", 2000, NULL)
              │   └─ reads <db_done> from exception.ini
              │   └─ shows "Done!" popup for 2 seconds
              └─ j 0x4E331C (original return path)
```

## Required Configuration

### `exception.ini`

Add the following entry in the active language section:

```
<db_done>Done!</db_done>
```

## Key Firmware Functions Referenced

| Address | Description |
|---|---|
| `0x4949C0` | `FUN_004949c0` — reads a key from an INI file and shows a timed popup dialog |

## Binary Patch Summary (Done Dialog)

Total modified bytes: **71**

```
File offset  VA          Original bytes    Patched bytes     Description
──────────────────────────────────────────────────────────────────────────
0x01BFEC     0x0041BFEC  25 20 40 02       04 61 12 AD      sw $s2, 0x6104($t0)
0x01BFFC     0x0041BFFC  25 38 00 00       B4 96 C6 24      addiu $a2 reorder
0x01C004     0x0041C004  B4 96 C6 24       25 20 40 02      or $a0, $s2, $zero
0x01C0B0     0x0041C0B0  C7 8C 13 08       38 70 10 08      j 0x41C0E0
0x01C0D4     0x0041C0D4  00 00 00 00 x2    "db_done\0"      key string (8 bytes)
0x01C0E0     0x0041C0E0  00 00 00 00 x16   (64 bytes)       Show Done routine
```

# Other patches included in the binary

This binary also contains the Sorting, DB Manager and Playlist Patches. For details see: [Sorting Patch README.md](https://github.com/hiby-modding/hiby-mods/blob/main/binaries/Sorting%20Patch/Sorting%20Patch%20README.md) , [DB Manager Patch README.md](https://github.com/hiby-modding/hiby-mods/blob/main/binaries/DB%20Manager%20Patch/DB%20Manager%20Patch%20README.md) and [Playlist Patch README.md](https://github.com/hiby-modding/hiby-mods/blob/main/binaries/Playlist%20Patch/Playlist%20Patch%20README.md)