# Media Database Updater

Python script that scans the SD card of the HiByOS based DAPs and rebuilds the `usrlocal_media.db` database in a format compatible with the device.

**Compatibility:** macOS · Linux · Windows
**Required dependency:** `mutagen` — `pip install mutagen`
**Optional dependency:** `tinytag` — `pip install tinytag` (fallback for files with corrupt metadata)
**Optional dependency:** `Pillow` — `pip install Pillow` (required for album art embed/resize)

---

## Usage

```bash
python Update_Database.py
```

No arguments required. The script auto-detects the SD card and starts immediately.

If Pillow is installed, the script will prompt whether to embed and resize album art before building the database.

### SD Card Detection

Detection follows this priority order:

1. Script's own directory
2. Current working directory (`cwd`)
3. Auto-detection: if exactly one mounted volume contains `usrlocal_media.db`, it is used automatically
4. Interactive selection: numbered list of all mounted volumes, with indication of which ones already contain the database

> **Note:** The SD card must already contain the `usrlocal_media.db` file (copy it from the device before running the script for the first time). If the file is not present on the selected volume, the script asks for confirmation before continuing.

**Search paths by OS:**

| OS | Paths |
|----|-------|
| macOS | `/Volumes/*` |
| Linux | `/media/$USER/*`, `/mnt/*`, `/run/media/$USER/*` |
| Windows | Drive letters A–Z (type 2 = removable, type 3 = fixed) |

---

## Album Art Embedding

When Pillow is installed, the script can embed and resize cover art directly into FLAC and MP3 files before rebuilding the database.

**Target size:** 360×360px — the native display area of the R3 Pro II screen. Oversized art wastes RAM and can cause navigation lag.

**Source priority (per album folder):**
1. Folder image — `cover.jpg`, `folder.jpg`, `front.jpg`, `albumart.jpg` (and `.jpeg` / `.png` variants)
2. Existing embedded art — extracted from the first file in the folder that has it

Art is resized using the Lanczos algorithm and saved as JPEG (quality 90) before embedding. RGBA/PNG images are composited onto a white background before conversion. Results are cached per directory, so albums with many tracks only resize once.

Files for which art embed fails are counted and reported in the summary.

> **Note:** Only FLAC and MP3 files are supported for embedding. Other formats are skipped.

---

## Supported Formats

### Audio

| Extension | Codec | Format code | Category |
|-----------|-------|-------------|----------|
| `.flac` | FLAC | 61868 (0xF1AC) | Lossless |
| `.dsf` / `.dff` | DSD | 54736 (0xD5D0) | DSD / Hi-Res |
| `.mp3` | MPEG Layer 3 | 85 | Lossy |
| `.mp2` | MPEG Layer 2 | 80 | Lossy |
| `.wav` / `.aif` | PCM | 1 | Lossless |
| `.aac` / `.m4a` / `.m4b` | AAC | 255 | Lossy |
| `.wma` | WMA | 353 | Lossy |
| `.ogg` / `.oga` | Vorbis | 26447 | Lossy |
| `.opus` | Opus | 28503 | Lossy |
| `.ape` | Monkey's Audio | 21574 | Lossless |
| `.iso` | SACD ISO | 0 | DSD |

Format codes are derived from a real HiBy R3 Pro II database and Windows WAVE Format Tags.

### Playlists

`.m3u`, `.m3u8` — inserted into `M3U_TABLE`. The `PLAYLIST_TABLE` and `m3u_N` tables are managed by the device and are left untouched.

---

## Tag Reading

Tag reading uses three progressive attempts:

1. **Mutagen** `File()` with `easy=True` (Vorbis Comment for FLAC/OGG/OPUS; raw ID3 frames for DSF/DFF via `ID3_MAP`)
2. **`mutagen.flac.FLAC()`** — fallback for FLAC files with non-standard metadata layouts that EasyFLAC cannot handle
3. **TinyTag** — final fallback, more lenient with corrupt metadata blocks

In all three cases, if the path causes an `ENOENT` error, the script retries with NFC and NFD variants of the path (required on macOS exFAT, which may return filenames in an NFD form different from what Mutagen expects).

Files for which all three attempts fail are recorded in `_tag_failures` and reported at the end of execution with a yellow warning.

### Title Fallback

If no title is available in the tags, the filename without extension is used, with optional removal of leading track-number prefixes (`04 - Title` → `Title`).

### Extracted Fields

| DB field | Source tag | Default |
|----------|-----------|---------|
| `name` | `title` | Filename |
| `artist` | `artist` | `"Unknown"` |
| `album` | `album` | `"Unknown"` |
| `genre` | `genre` | `"Unknown"` |
| `year` | `date` (first 4 characters) | `0` |
| `album_artist` | `albumartist` | value of `artist` |
| `ck_id` | `tracknumber` (part before `/`) | `0` |
| `dis_id` | `discnumber` (part before `/`) | `1` |
| `sample_rate` | `info.sample_rate` | `0` |
| `bit_rate` | `info.bitrate` | `0` |
| `bit` | `info.bits_per_sample` / `bits_per_frame` | `16` |
| `channel` | `info.channels` | `2` |

---

## Filesystem Scan

Uses a custom walker (`_walk`) based on `os.scandir` instead of `os.walk`, required for macOS exFAT. The issue: reconstructing a path with `os.path.join(parent, filename)` can produce a mixed NFC/NFD string that neither macOS nor Python can open. By using `e.path` directly from `scandir`, the path is always in the form returned by the kernel and therefore always openable.

Hidden files and directories (prefixed with `.`) are ignored, including macOS `._*` files.

Audio files are sorted by their HiBy-style path in lowercase (`a:\...`) to determine the sequential ID assignment order.

---

## HiBy-Style Paths

All paths stored in the database use the Windows format `a:\folder\file.flac`.

Conversion is handled by `hiby_path()`:
- The relative path from the SD card root is computed with `os.path.relpath`
- `/` separators are replaced with `\`
- The path is NFC-normalized (macOS exFAT paths are in NFD)
- `a:\` is prepended

All text fields in the DB are NUL-terminated (`\x00`), appended by the `nul()` function.

---

## Collation and Sorting

The script faithfully replicates the collation logic of the HiBy firmware (binary with sorting patch).

### Normalization Pipeline

1. **Punctuation strip** (`_PUNCT_RE`, replicates binary function `0x41bce0`): removes leading `( . " '` characters
2. **Article strip** (`_ARTICLES_RE`, replicates `0x41b8b0`): removes leading articles `the, der, die, das, les, il, lo, la, le, el` (case-insensitive). `a` / `an` are deliberately excluded.

### Sort Tiers

The `_sort_tier()` function replicates the binary collation at `0x41bb30`:

| Tier | Characters |
|------|-----------|
| `0` — symbols | Punctuation, Unicode `0x2000–0x2FFF` |
| `1` — digits | `0–9` |
| `2` — letters | `A–Z`, `a–z`, codepoints `≥ 0xC0` |

> The `0x2000–0x2FFF` range is checked before the `≥ 0xC0` test to prevent symbols like `†` (U+2020) from being misclassified as letters.

The final sort key is the tuple `(tier, normalized_lowercase_text)`.

### `character` Field (Alphabetical Sidebar)

The first character of the normalized text, uppercased. Returns `#` if the text is empty or normalization produces an empty string.

### `pinyin_charater` Field

ASCII-only sort key: the normalized text is uppercased only for `a–z` characters, leaving accented characters unchanged (replicates C `toupper()`).

---

## Catalog Deduplication

Catalog tables (`ARTIST_TABLE`, `ALBUM_TABLE`, etc.) use `COLLATE NOCASE`, so `"Queen"` and `"QUEEN"` would conflict on a `UNIQUE` key. The `canonical()` function deduplicates before insertion: the first form of a value encountered during the scan is used for all subsequent occurrences with the same lowercase value.

---

## Database Structure

### Tables Written by the Script

| Table | Contents |
|-------|----------|
| `MEDIA_TABLE` | All tracks, sorted by title (using HiBy collation) |
| `MEDIA2_TABLE` | Same data and same IDs, in filesystem path order |
| `MEDIA3_TABLE` | Emptied (internal device use) |
| `ARTIST_TABLE` / `ARTIST2_TABLE` | Artists, ID = first `media_id` for that artist |
| `ALBUM_TABLE` / `ALBUM2_TABLE` | Albums |
| `GENRE_TABLE` / `GENRE2_TABLE` | Genres |
| `ALBUM_ARTIST_TABLE` / `ALBUM_ARTIST2_TABLE` | Album artists |
| `FORMAT_TABLE` / `FORMAT2_TABLE` | File formats, ID = first `media_id` for that format |
| `COUNT_TABLE` | Counters: tracks, albums, artists, genres, album artists |
| `CTIME_TABLE` | `media_id` sorted by creation date ascending |
| `MTIME_TABLE` | `media_id` sorted by modification date descending |
| `M3U_TABLE` | Playlists found on the SD card |

The duplicate tables (`*_TABLE` + `*2_TABLE`) contain identical data — this is a HiBy firmware requirement.

### Special Fields in MEDIA_TABLE

| Field | Value for normal tracks |
|-------|------------------------|
| `end_time` | `-1` |
| `cue_id` | `-1` |
| `begin_time` | `0` |
| `has_child_file` | `0` |

The `-1` values distinguish normal tracks from CUE sheet tracks, which use `cue_id` and `end_time` to indicate the offset within the container file.

### Cover Art and LRC

- **Cover art:** searched in the audio file's directory using prioritized filenames: `cover.jpg`, `folder.jpg`, `front.jpg`, `albumart.jpg` (and `.jpeg` / `.png` variants). Results are cached per directory.
- **LRC:** file with the same base name as the audio file and `.lrc` extension in the same folder.

### `quality` Field

| Value | Meaning |
|-------|---------|
| `"0"` | Unknown sample rate |
| `"1"` | Lossy (MP3, AAC, OGG, OPUS, WMA…) |
| `"2"` | Lossless ≤ 48 kHz |
| `"3"` | Hi-Res (> 48 kHz) or DSD |

---

## SQLite Optimizations

The following PRAGMAs are set before each bulk operation:

```sql
PRAGMA synchronous = OFF
PRAGMA journal_mode = MEMORY
PRAGMA cache_size = -32000
PRAGMA temp_store = MEMORY
```

All inserts use `executemany()` with pre-built lists of tuples.

---

## Console Output

```
Scanning SD card...
  1842 audio files, 12 playlists  [0.3s]
Embedding album art (360×360)...
  Art embedded in 1821 files  [12.4s]
Reading tags...
  Tags read in 4.2s
Writing database...
  Database written in 0.8s

==================================================
  Done in 17.7s
  Tracks:        1842
  Albums:         187
  Artists:         94
  Genres:          12
  Album artists:   91
  Playlists:       12
  Art embedded:  1821 files
==================================================
```

Warnings for unreadable tag files or art embed failures are printed in yellow before the write phase.
