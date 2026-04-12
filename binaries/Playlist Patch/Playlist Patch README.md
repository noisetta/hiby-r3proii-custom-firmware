# Playlist Three-Dot Menu Fix

## Bug Description

On the Playlist page, the three-dot menu (⋮) for each playlist was off by one:

- **Playlist 1** (first m3u playlist): no three-dot icon visible
- **Playlist 2** (second m3u playlist): three-dot icon visible, but clicking it opened the menu for **Playlist 1**
- **Playlist 3** (third m3u playlist): three-dot icon visible, but clicking it opened the menu for **Playlist 2**
- And so on for every subsequent playlist

The entire sub-button system: rendering, click detection, and menu targeting was shifted by one position.

## Root Cause

The Playlist page (`FUN_004c18c0`) builds its list by adding **3 fixed items** at the top (Create, Save playlist, Load playlist), followed by the user's m3u playlists from the database.

However, `FUN_0042a500(5)`, a system settings getter, returns a non-null value on this device (the language/locale pointer stored at `DAT_009666a0[2]`). Multiple code paths use this result as a boolean: if non-null, they assume there are **4 fixed items** instead of 3, producing an off-by-one error in three independent locations:

1. **Click handler** (`0x4B3134`): when clicking the three-dot button, subtracts 4 instead of 3 from the visual index to compute the m3u playlist index, causing the menu to target the wrong playlist.

2. **Click gate** (`0x4B32B8`): compares the visual index against 4 instead of 3 to decide whether the clicked item is a fixed item (no menu) or a playlist (show menu), preventing the first playlist's three-dot area from responding to taps.

3. **Rendering** (`0x4B92D0`): compares the visual index against 4 instead of 3 to decide whether to draw the three-dot icon, causing the icon to not appear on the first playlist.

All three share the same pattern:

```
jal  FUN_0042a500       # call system settings getter
addiu a0, zero, 5       # arg = 5 (language/locale)
...
addiu v1, zero, 3       # v1 = 3
addiu a0, zero, 4       # a0 = 4
movz  a0, v1, v0        # if (result == NULL) a0 = 3; else a0 = 4
```

Since `FUN_0042a500(5)` returns non-null (the language pointer), `a0` is always set to 4 but the playlist page only has 3 fixed items.

## Fix

The fix consists of 6 patches, using a total of 145 modified bytes across the binary:

### Patch A | Neutralize `FUN_0042a500` case 5 (root cause)

| Address | Original | Patched |
|---------|----------|---------|
| `0x42A9B8` | `lw v0, 8(v0)` | `or v0, zero, zero` |

The case 5 handler in `FUN_0042a500`'s switch statement now returns NULL (0) instead of reading `DAT_009666a0[2]`. This makes the three playlist/rendering callers take the `offset = 3` path.

### Patch B | `get_language` code cave

A 7-instruction function is placed in a zero-padded region at `0x41C0B4` that reads `DAT_009666a0[2]` directly, bypassing `FUN_0042a500`:

```mips
lui   v0, 0x0096          # load high half of DAT_009666a0 address
lw    v0, 0x66A0(v0)      # v0 = DAT_009666a0 (base pointer)
beq   v0, zero, ret       # if base is null, return 0
nop
lw    v0, 8(v0)           # v0 = DAT_009666a0[2] (language value)
ret:
jr    ra                  # return
nop
```

This function returns the exact same value that `FUN_0042a500` case 5 used to return, preserving full language/locale functionality for all non-playlist callers.

### Patch C | Redirect language callers

All 31 non-playlist callers of `FUN_0042a500(5)` are redirected to the `get_language` code cave. Each call site is patched from:

```mips
jal   FUN_0042a500        # was: call system settings getter
addiu a0, zero, 5         # was: arg = 5
```

to:

```mips
jal   get_language         # now: call direct language reader
nop                        # delay slot (arg not needed)
```

These callers handle language selection, locale string lookup, UI text paths, and radio button state, all continue to receive the real language value.

### Patches D, E, F | Offset corrections

These three patches change the hardcoded `4` to `3` in each of the three playlist code paths. While Patch A already ensures the `movz` selects 3, these patches provide redundant safety:

| Patch | Address | Original | Patched | Context |
|-------|---------|----------|---------|---------|
| D | `0x4B3144` | `addiu a0, zero, 4` | `addiu a0, zero, 3` | Click handler offset |
| E | `0x4B32C4` | `addiu a1, zero, 4` | `addiu a1, zero, 3` | Click gate threshold |
| F | `0x4B92DC` | `addiu a0, zero, 4` | `addiu a0, zero, 3` | Rendering threshold |

## Binary Patch Summary

All offsets are relative to the start of the ELF file (file offsets). The ELF base address is `0x400000`.

```
File offset  VA          Original bytes   Patched bytes    Description
─────────────────────────────────────────────────────────────────────────
0x01C0B4     0x0041C0B4  00 00 00 00 ...  (28 bytes)       get_language code cave
0x02A9B8     0x0042A9B8  08 00 42 8C      25 10 00 00      case 5 → return NULL
0x0B3144     0x004B3144  04 00 04 24      03 00 04 24      click handler: 4→3
0x0B32C4     0x004B32C4  04 00 05 24      03 00 05 24      click gate: 4→3
0x0B92DC     0x004B92DC  04 00 04 24      03 00 04 24      rendering: 4→3
+ 31 call sites redirected from jal 0x42A500 to jal 0x41C0B4
```

## Testing Checklist

- [x] Three-dot icon appears on all playlists, including the first one
- [x] Clicking three-dot opens the menu for the correct playlist
- [x] Language selection works (can change language)
- [x] Language radio button indicator shows the correct selection
- [x] Playlist Create / Save / Load buttons work normally
- [x] No three-dot icon on the fixed items (Create, Save, Load)
