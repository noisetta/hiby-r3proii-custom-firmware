#!/usr/bin/env python3
"""
HiBy DAP - Media Database Updater
Scans the SD card and rebuilds usrlocal_media.db

Compatible with macOS, Linux, and Windows.
Place in the SD card root (next to usrlocal_media.db) and run.

Requirements:
    pip install mutagen
"""

import os
import re
import sqlite3
import time
import errno
import unicodedata
from mutagen import File


# ── Configuration ─────────────────────────────────────────────────────────────

DB_NAME = "usrlocal_media.db"

AUDIO_EXT = {
    ".iso", ".dff", ".dsf", ".ape", ".flac", ".aif", ".wav",
    ".m4a", ".aac", ".mp2", ".mp3", ".ogg", ".oga", ".wma", ".opus", ".m4b",
}
PLAYLIST_EXT = {".m3u", ".m3u8"}

# Format codes confirmed from a real HiBy R3 Pro II database.
# Others derived from Windows WAVE Format Tags.
FORMAT_MAP = {
    ".flac": 61868,
    ".dsf":  54736,
    ".dff":  54736,
    ".mp3":  85,
    ".mp2":  80,
    ".wav":  1,
    ".aif":  1,
    ".aac":  255,
    ".m4a":  255,
    ".m4b":  255,
    ".wma":  353,
    ".ogg":  26447,
    ".oga":  26447,
    ".opus": 28503,
    ".ape":  21574,
    ".iso":  0,
}

LOSSY_EXT = {".mp3", ".mp2", ".aac", ".m4a", ".m4b", ".ogg", ".oga", ".wma", ".opus"}
DSD_EXT   = {".dsf", ".dff", ".iso"}
DSD_SET   = {".dsf", ".dff"}   # formats that use raw ID3 frames

# ID3 frame → easy key mapping for DSF/DFF (File(easy=True) is silently ignored)
ID3_MAP = {
    "TIT2": "title",       "TPE1": "artist",
    "TALB": "album",       "TCON": "genre",
    "TDRC": "date",        "TPE2": "albumartist",
    "TRCK": "tracknumber", "TPOS": "discnumber",
}

COVER_NAMES = {
    "cover.jpg", "folder.jpg", "front.jpg", "albumart.jpg",
    "cover.jpeg", "folder.jpeg", "front.jpeg",
    "cover.png",  "folder.png",  "front.png",
}

# Articles stripped before sort key computation.
# List derived from disassembly of the patched HiBy binary (cave at 0x41b8b0).
_ARTICLES_RE = re.compile(
    r"^(the|der|die|das|les|il|lo|la|le|el)\s+",
    flags=re.IGNORECASE,
)

# Leading punctuation stripped before articles (binary function 0x41bce0).
_PUNCT_RE = re.compile(r"""^[(."']+""")

# Track-number prefix stripped from filenames used as fallback titles.
_TRACK_PREFIX_RE = re.compile(r"^\d{1,3}\s*[-\u2013.]\s*")


# ── Helpers ───────────────────────────────────────────────────────────────────

def sanitize(s) -> str:
    """Strip embedded NUL bytes and whitespace. Prevents SQLite UNIQUE failures."""
    if s is None:
        return ""
    return str(s).replace("\x00", "").strip()


def nul(s) -> str:
    """Append the NUL terminator required by HiBy for all text fields."""
    return sanitize(s) + "\x00"


def ascii_upper(s: str) -> str:
    """
    ASCII-only uppercase: a-z → A-Z, accented characters unchanged.
    The HiBy device uses C toupper() which only operates on ASCII,
    so we replicate that behaviour for the pinyin_charater sort key.
    """
    return s.translate(str.maketrans(
        "abcdefghijklmnopqrstuvwxyz",
        "ABCDEFGHIJKLMNOPQRSTUVWXYZ",
    ))


def hiby_path(path: str, sd: str) -> str:
    """
    Convert an absolute path to a HiBy-style path (a:\\...).
    Normalises to NFC: macOS exFAT returns filenames in NFD,
    but the HiBy device stores paths in NFC in its database.
    """
    rel = os.path.relpath(path, sd)
    rel = unicodedata.normalize("NFC", rel)
    return "a:\\" + rel.replace("/", "\\")


def _normalize(text: str) -> str:
    """
    Apply the same normalization as the patched HiBy runtime sort:
      1. Strip leading punctuation: ( . " '   (binary 0x41bce0)
      2. Strip leading article: the/der/die/das/les/il/lo/la/le/el  (0x41b8b0)
    """
    s = _PUNCT_RE.sub("", text.strip())
    return _ARTICLES_RE.sub("", s)


def _sort_tier(ch: str) -> int:
    """
    Character category matching the patched binary collation (0x41bb30):
      0 = symbol / Unicode 0x2000-0x2FFF
      1 = digit  (0-9)
      2 = letter (A-Z, a-z, >= 0xC0)
    The 0x2000-0x2FFF check must come before >= 0xC0, otherwise symbols
    like U+2020 (†) are misclassified as letters.
    """
    if not ch:
        return 0
    cp = ord(ch)
    if 0x2000 <= cp <= 0x2FFF:
        return 0
    if 0x30 <= cp <= 0x39:
        return 1
    if 0x41 <= cp <= 0x5A or 0x61 <= cp <= 0x7A or cp >= 0xC0:
        return 2
    return 0


def sort_key(text: str) -> tuple:
    """Sort key replicating the patched HiBy binary: (tier, normalised_lower)."""
    norm = _normalize(text)
    if not norm:
        return (0, text.lower())
    return (_sort_tier(norm[0]), norm.lower())


def sort_character(text: str) -> str:
    """
    Compute the 'character' index field used by the HiBy alphabetical sidebar.
    Matches binary logic 0x41bce0 → 0x41b8b0.
    """
    if not text:
        return "#"
    norm = _normalize(text)
    return norm[0].upper() if norm else "#"


def quality_tier(ext: str, samplerate: int) -> str:
    """
    HiBy quality tier stored in the 'quality' field:
      0 = unknown, 1 = lossy, 2 = lossless (<=48 kHz), 3 = hi-res / DSD
    """
    if not samplerate:
        return "0"
    if ext in DSD_EXT or samplerate > 48000:
        return "3"
    if ext in LOSSY_EXT:
        return "1"
    return "2"


_cover_cache: dict = {}

def find_cover(directory: str, sd: str):
    """Return the HiBy-style path to a cover image, or None. Results are cached."""
    if directory in _cover_cache:
        return _cover_cache[directory]
    result = None
    try:
        entries = {f.lower(): f for f in os.listdir(directory)}
        for name in COVER_NAMES:
            if name in entries:
                result = hiby_path(os.path.join(directory, entries[name]), sd)
                break
    except OSError:
        pass
    _cover_cache[directory] = result
    return result


def find_lrc(audio_path: str, sd: str):
    """Return the HiBy-style path to a .lrc lyrics file, or None."""
    lrc = os.path.splitext(audio_path)[0] + ".lrc"
    return hiby_path(lrc, sd) if os.path.isfile(lrc) else None


# ── SD card detection ─────────────────────────────────────────────────────────

def find_sd():
    for d in [os.path.dirname(os.path.abspath(__file__)), os.getcwd()]:
        if os.path.exists(os.path.join(d, DB_NAME)):
            return d
    return None


# ── Tag reading ─────────────────────────────────────────────────────────────

_tag_failures: list = []  # (path, error) for files where Mutagen failed──

def _read_vorbis(audio) -> dict:
    """Read Vorbis Comment tags from a Mutagen object (EasyFLAC or native FLAC)."""
    def tag(key):
        v = audio.get(key)
        return sanitize(v[0]) if v else None
    return {k: tag(k) for k in
            ["title", "artist", "album", "genre", "albumartist",
             "date", "tracknumber", "discnumber"]}


def read_tags(file: str) -> dict:
    basename  = os.path.splitext(os.path.basename(file))[0]
    title        = basename
    artist       = "Unknown"
    album        = "Unknown"
    genre        = "Unknown"
    year         = 0
    album_artist = ""
    samplerate   = 0
    bitrate      = 0
    channels     = 2
    bitdepth     = 16
    duration     = 0
    track_num    = 0
    disc_num     = 1
    ext          = os.path.splitext(file)[1].lower()
    audio        = None

    _err = None

    def _open_file(path: str, easy: bool):
        """Open audio file, retrying with NFC/NFD path variants on ENOENT.
        On macOS exFAT, os.scandir may return a path in a different Unicode form
        than what the filesystem accepts, causing spurious file-not-found errors.
        Mutagen wraps OSError in MutagenError, so we catch Exception and inspect
        the original cause to decide whether to retry."""
        def _is_enoent(exc) -> bool:
            cause = getattr(exc, "__cause__", None) or getattr(exc, "__context__", None)
            if isinstance(cause, OSError):
                return cause.errno == errno.ENOENT
            if isinstance(exc, OSError):
                return exc.errno == errno.ENOENT
            return "No such file" in str(exc) or "ENOENT" in str(exc)

        try:
            return File(path, easy=easy)
        except Exception as e:
            if not _is_enoent(e):
                return None

        for variant in [unicodedata.normalize("NFC", path),
                        unicodedata.normalize("NFD", path)]:
            if variant != path:
                try:
                    return File(variant, easy=easy)
                except Exception:
                    pass
        return None

    # Attempt 1: Mutagen File() with NFC/NFD path fallback.
    audio = _open_file(file, easy=False if ext in DSD_SET else True)

    # Attempt 2: native FLAC() — bypasses EasyFLAC for non-standard tag layouts.
    if audio is None and ext == ".flac":
        try:
            from mutagen.flac import FLAC
            audio = FLAC(file)
        except Exception as e:
            _err = e

    # Attempt 3: TinyTag — more lenient, handles corrupt FLAC metadata blocks.
    if audio is None:
        try:
            from tinytag import TinyTag
            tt = TinyTag.get(file)
            title        = sanitize(tt.title)        or title
            artist       = sanitize(tt.artist)       or artist
            album        = sanitize(tt.album)        or album
            genre        = sanitize(tt.genre)        or genre
            album_artist = sanitize(getattr(tt, "albumartist", "") or "") or ""
            if tt.year:
                ys = str(tt.year)[:4]
                if ys.isdigit(): year = int(ys)
            if tt.track:
                try: track_num = int(str(tt.track).split("/")[0])
                except: pass
            if tt.disc:
                try: disc_num  = int(str(tt.disc).split("/")[0])
                except: pass
            if tt.samplerate: samplerate = tt.samplerate
            if tt.bitrate:    bitrate    = int(tt.bitrate * 1000)
            if tt.channels:   channels   = tt.channels
            if getattr(tt, "bitdepth", None): bitdepth = tt.bitdepth
            if tt.duration:   duration   = int(tt.duration * 1000)
            audio = "tinytag"  # sentinel: tags already applied
        except Exception as e:
            _err = e
            _tag_failures.append((file, str(_err)))

    if audio is not None and audio != "tinytag":
        try:
            if ext in DSD_SET and audio.tags:
                def _id3(key):
                    fid = next((f for f, k in ID3_MAP.items() if k == key), None)
                    if not fid:
                        return None
                    frame = audio.tags.get(fid)
                    if frame is None:
                        return None
                    text = getattr(frame, "text", None)
                    return sanitize(str(text[0])) if text else sanitize(str(frame))
                td = {k: _id3(k) for k in ID3_MAP.values()}
            else:
                td = _read_vorbis(audio)

            title        = td["title"]       or title
            artist       = td["artist"]      or artist
            album        = td["album"]       or album
            genre        = td["genre"]       or genre
            album_artist = td["albumartist"] or ""

            d = td["date"]
            if d and len(d) >= 4 and d[:4].isdigit():
                year = int(d[:4])

            tn = td["tracknumber"]
            if tn:
                try: track_num = int(tn.split("/")[0])
                except: pass

            dn = td["discnumber"]
            if dn:
                try: disc_num = int(dn.split("/")[0])
                except: pass

            info = getattr(audio, "info", None)
            if info:
                samplerate = getattr(info, "sample_rate",      0) or 0
                channels   = getattr(info, "channels",         2) or 2
                bitdepth   = (getattr(info, "bits_per_sample", 0)
                           or getattr(info, "bits_per_frame",  0)
                           or 16)
                br         = getattr(info, "bitrate", 0) or 0
                bitrate    = int(br) if br else 0
                length     = getattr(info, "length",  0) or 0
                duration   = int(length * 1000)

        except Exception:
            pass

    # If tags were not read, fall back to the filename.
    # Strip leading track-number prefix: "04 - Title" → "Title".
    title_final = sanitize(title) or basename
    if title_final == basename or title_final.startswith(basename[:3]):
        title_final = _TRACK_PREFIX_RE.sub("", title_final).strip()
    if not title_final:
        title_final = basename

    artist_final = sanitize(artist) or "Unknown"

    return {
        "title":        title_final,
        "artist":       artist_final,
        "album":        sanitize(album)        or "Unknown",
        "genre":        sanitize(genre)        or "Unknown",
        "year":         year,
        "album_artist": sanitize(album_artist) or artist_final,
        "samplerate":   samplerate,
        "bitrate":      bitrate,
        "channels":     channels,
        "bitdepth":     bitdepth,
        "duration":     duration,
        "track_num":    track_num,
        "disc_num":     disc_num,
    }


# ── Filesystem scan ───────────────────────────────────────────────────────────

def _walk(top: str):
    """
    Custom directory walker compatible with macOS exFAT and Unicode paths.

    Key issue: on macOS exFAT, reconstructing a file path as
    os.path.join(parent_dir, filename) can produce a mixed NFC/NFD path
    that neither macOS nor Python can open, even though os.scandir found
    the file. Root cause: the parent directory path (NFC after nfd2nfc)
    and the filename (raw from filesystem, possibly NFD) may be in
    different Unicode normal forms that exFAT treats as distinct.

    Fix: store e.path for both directories AND files. e.path is computed
    by the kernel from the same scandir call that found the entry, so it
    is always internally consistent and openable.
    """
    try:
        entries = list(os.scandir(top))
    except OSError:
        return

    dir_entries  = []  # (e.path, e.name)
    file_entries = []  # e.path  ← full path directly from kernel

    for e in entries:
        if e.is_dir(follow_symlinks=False):
            dir_entries.append((e.path, e.name))
        else:
            file_entries.append(e.path)

    yield top, [n for _, n in dir_entries], file_entries

    for path, name in dir_entries:
        if not name.startswith("."):
            yield from _walk(path)


def scan(sd: str):
    audio, playlists = [], []
    for root, dirs, file_paths in _walk(sd):
        dirs[:] = [d for d in dirs if not d.startswith(".")]
        for full in file_paths:
            f = os.path.basename(full)
            if f.startswith("._") or f.startswith("."):
                continue
            ext = os.path.splitext(f)[1].lower()
            if ext in AUDIO_EXT:
                audio.append(full)
            elif ext in PLAYLIST_EXT:
                playlists.append(full)
    audio.sort(key=lambda x: hiby_path(x, sd).lower())
    return audio, playlists


# ── Database rebuild ──────────────────────────────────────────────────────────

def rebuild_db(sd: str):
    _cover_cache.clear()
    conn = sqlite3.connect(os.path.join(sd, DB_NAME))
    conn.text_factory = str
    cur = conn.cursor()

    # Speed up bulk insert: no disk sync, journal in RAM.
    cur.execute("PRAGMA synchronous = OFF")
    cur.execute("PRAGMA journal_mode = MEMORY")
    cur.execute("PRAGMA cache_size = -32000")
    cur.execute("PRAGMA temp_store = MEMORY")

    t0 = time.time()
    print("Scanning SD card...")
    audio, playlists = scan(sd)
    print(f"  {len(audio)} audio files, {len(playlists)} playlists  [{time.time()-t0:.1f}s]")

    t1 = time.time()
    print("Reading tags...")

    # Catalog tables use COLLATE NOCASE, so "Queen" and "QUEEN" are the same
    # primary key in SQLite. Deduplicate case-insensitively before inserting
    # to avoid UNIQUE constraint failures.
    artists_count, albums_count, genres_count, albart_count = {}, {}, {}, {}
    artists_first, albums_first, genres_first, albart_first = {}, {}, {}, {}
    artists_canon, albums_canon, genres_canon, albart_canon = {}, {}, {}, {}
    formats_seen  = {}
    media_ctime, media_mtime, media_rows = [], [], []

    def canonical(value: str, canon_map: dict) -> str:
        key = value.lower()
        if key not in canon_map:
            canon_map[key] = value
        return canon_map[key]

    for i, file in enumerate(audio):
        if i % 500 == 0 and i > 0:
            elapsed = time.time() - t1
            eta = elapsed / i * (len(audio) - i)
            print(f"  {i}/{len(audio)}  [{elapsed:.0f}s elapsed, ~{eta:.0f}s remaining]")

        tags  = read_tags(file)
        ext   = os.path.splitext(file)[1].lower()
        hibyp = hiby_path(file, sd)

        try:
            size  = os.path.getsize(file)
            ctime = int(os.path.getctime(file))
            mtime = int(os.path.getmtime(file))
        except OSError:
            size = ctime = mtime = 0

        art     = canonical(tags["artist"],       artists_canon)
        alb     = canonical(tags["album"],        albums_canon)
        gen     = canonical(tags["genre"],        genres_canon)
        alb_art = canonical(tags["album_artist"], albart_canon)

        artists_count[art]    = artists_count.get(art, 0) + 1
        albums_count[alb]     = albums_count.get(alb, 0)  + 1
        genres_count[gen]     = genres_count.get(gen, 0)  + 1
        albart_count[alb_art] = albart_count.get(alb_art, 0) + 1

        if art     not in artists_first: artists_first[art]     = i + 1
        if alb     not in albums_first:  albums_first[alb]      = i + 1
        if gen     not in genres_first:  genres_first[gen]      = i + 1
        if alb_art not in albart_first:  albart_first[alb_art]  = i + 1

        formats_seen[ext] = i + 1
        media_ctime.append((ctime, i + 1))
        media_mtime.append((mtime, i + 1))

        media_rows.append((
            i + 1,
            nul(hibyp),
            nul(tags["title"]),
            nul(alb),
            nul(art),
            nul(gen),
            tags["year"],
            tags["disc_num"],
            tags["track_num"],
            0,
            0,
            -1,                                              # end_time: -1 for normal tracks
            -1,                                              # cue_id:   -1 for normal tracks
            sort_character(tags["title"]),
            size,
            tags["samplerate"],
            tags["bitrate"],
            tags["bitdepth"],
            tags["channels"],
            FORMAT_MAP.get(ext, 0),
            quality_tier(ext, tags["samplerate"]),
            nul(find_cover(os.path.dirname(file), sd) or ""),
            nul(find_lrc(file, sd) or ""),
            0.0, 0.0,
            ctime,
            mtime,
            nul(ascii_upper(_normalize(tags["title"]))),     # pinyin_charater: sort key
            nul(alb_art),
        ))

    total = len(audio)
    print(f"  Tags read in {time.time()-t1:.1f}s")

    if _tag_failures:
        print(f"\n  WARNING: Mutagen failed to read {len(_tag_failures)} file(s):")
        for path, err in _tag_failures:
            print(f"    {path}")
            if err:
                print(f"      {err}")
        print()

    t2 = time.time()
    print("Writing database...")

    def pinyin(s):
        return nul(ascii_upper(_normalize(s)))

    # ── MEDIA2_TABLE: all tracks, sequential IDs in filesystem path order ──
    # This is the "master" table. IDs are shared with MEDIA_TABLE.
    _INS_MEDIA = """
        INSERT INTO MEDIA_TABLE
          (id, path, name, album, artist, genre, year,
           dis_id, ck_id, has_child_file,
           begin_time, end_time, cue_id, character,
           size, sample_rate, bit_rate, bit, channel, format,
           quality, album_pic_path, lrc_path,
           track_gain, track_peak, ctime, mtime,
           pinyin_charater, album_artist)
        VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
    """
    _INS_MEDIA2 = _INS_MEDIA.replace("MEDIA_TABLE", "MEDIA2_TABLE")

    cur.execute("DELETE FROM MEDIA2_TABLE")
    cur.executemany(_INS_MEDIA2, media_rows)

    # ── MEDIA_TABLE: same data/IDs, inserted in title-sorted rowid order ──
    media_title_sorted = sorted(media_rows, key=lambda r: sort_key(sanitize(r[2])))
    cur.execute("DELETE FROM MEDIA_TABLE")
    cur.executemany(_INS_MEDIA, media_title_sorted)

    # MEDIA3_TABLE: should be empty (used internally by the device).
    cur.execute("DELETE FROM MEDIA3_TABLE")

    # ── Catalog tables: *_TABLE and *2_TABLE are IDENTICAL ──
    # ID = first MEDIA2_TABLE id for that entity (i.e. artists_first[a]).
    # Sorted by HiBy collation sort_key(), NOT Python default sort.

    artist_rows = sorted(
        [(artists_first[a], nul(a), sort_character(a), cn, 0, 0, pinyin(a))
         for a, cn in artists_count.items()],
        key=lambda r: sort_key(sanitize(r[1]))
    )
    cur.execute("DELETE FROM ARTIST_TABLE")
    cur.executemany(
        "INSERT INTO ARTIST_TABLE (id, artist, character, cn, ctime, mtime, pinyin_charater) "
        "VALUES (?,?,?,?,?,?,?)", artist_rows)
    cur.execute("DELETE FROM ARTIST2_TABLE")
    cur.executemany(
        "INSERT INTO ARTIST2_TABLE (id, artist, character, cn, ctime, mtime, pinyin_charater) "
        "VALUES (?,?,?,?,?,?,?)", artist_rows)

    album_rows = sorted(
        [(albums_first[a], nul(a), sort_character(a), cn, 0, 0, 0, pinyin(a))
         for a, cn in albums_count.items()],
        key=lambda r: sort_key(sanitize(r[1]))
    )
    cur.execute("DELETE FROM ALBUM_TABLE")
    cur.executemany(
        "INSERT INTO ALBUM_TABLE (id, album, character, cn, ctime, mtime, mqa, pinyin_charater) "
        "VALUES (?,?,?,?,?,?,?,?)", album_rows)
    cur.execute("DELETE FROM ALBUM2_TABLE")
    cur.executemany(
        "INSERT INTO ALBUM2_TABLE (id, album, character, cn, ctime, mtime, mqa, pinyin_charater) "
        "VALUES (?,?,?,?,?,?,?,?)", album_rows)

    genre_rows = sorted(
        [(genres_first[g], nul(g), sort_character(g), cn, 0, 0, pinyin(g))
         for g, cn in genres_count.items()],
        key=lambda r: sort_key(sanitize(r[1]))
    )
    cur.execute("DELETE FROM GENRE_TABLE")
    cur.executemany(
        "INSERT INTO GENRE_TABLE (id, genre, character, cn, ctime, mtime, pinyin_charater) "
        "VALUES (?,?,?,?,?,?,?)", genre_rows)
    cur.execute("DELETE FROM GENRE2_TABLE")
    cur.executemany(
        "INSERT INTO GENRE2_TABLE (id, genre, character, cn, ctime, mtime, pinyin_charater) "
        "VALUES (?,?,?,?,?,?,?)", genre_rows)

    albart_rows = sorted(
        [(albart_first[a], nul(a), sort_character(a), cn, 0, 0, 0, pinyin(a))
         for a, cn in albart_count.items()],
        key=lambda r: sort_key(sanitize(r[1]))
    )
    cur.execute("DELETE FROM ALBUM_ARTIST_TABLE")
    cur.executemany(
        "INSERT INTO ALBUM_ARTIST_TABLE "
        "(id, album_artist, character, cn, ctime, mtime, mqa, pinyin_charater) "
        "VALUES (?,?,?,?,?,?,?,?)", albart_rows)
    cur.execute("DELETE FROM ALBUM_ARTIST2_TABLE")
    cur.executemany(
        "INSERT INTO ALBUM_ARTIST2_TABLE "
        "(id, album_artist, character, cn, ctime, mtime, mqa, pinyin_charater) "
        "VALUES (?,?,?,?,?,?,?,?)", albart_rows)

    cur.execute("DELETE FROM COUNT_TABLE")
    cur.executemany("INSERT INTO COUNT_TABLE (cn) VALUES (?)",
        [(total,), (len(albums_count),), (len(artists_count),),
         (len(genres_count),), (len(albart_count),)])

    # FORMAT_TABLE and FORMAT2_TABLE: identical, ID = first media id for that format.
    fmt_rows = sorted(
        [(formats_seen[ext], ext.lstrip(".").upper()) for ext in formats_seen],
        key=lambda r: sort_key(r[1])
    )
    fmt_insert = [(mid, name, sort_character(name), 1) for mid, name in fmt_rows]
    cur.execute("DELETE FROM FORMAT_TABLE")
    cur.executemany(
        "INSERT INTO FORMAT_TABLE (id, format, character, cn) VALUES (?,?,?,?)", fmt_insert)
    cur.execute("DELETE FROM FORMAT2_TABLE")
    cur.executemany(
        "INSERT INTO FORMAT2_TABLE (id, format, character, cn) VALUES (?,?,?,?)", fmt_insert)

    cur.execute("DELETE FROM CTIME_TABLE")
    cur.executemany("INSERT INTO CTIME_TABLE (media_id) VALUES (?)",
        [(mid,) for _, mid in sorted(media_ctime, key=lambda x: (x[0], x[1]))])

    cur.execute("DELETE FROM MTIME_TABLE")
    cur.executemany("INSERT INTO MTIME_TABLE (media_id) VALUES (?)",
        [(mid,) for _, mid in sorted(media_mtime, key=lambda x: (-x[0], x[1]))])

    # PLAYLIST_TABLE and m3u_N tables are managed by the device — leave them alone.
    cur.execute("DELETE FROM M3U_TABLE")
    if playlists:
        cur.executemany(
            "INSERT INTO M3U_TABLE (id, path, name, character) VALUES (?,?,?,?)",
            [(total, nul(hiby_path(p, sd)), nul(os.path.basename(p)),
              sort_character(os.path.basename(p)))
             for p in playlists]
        )

    conn.commit()
    conn.close()

    print(f"  Database written in {time.time()-t2:.1f}s")
    print()
    print("=" * 50)
    print(f"  Done in {time.time()-t0:.1f}s")
    print(f"  Tracks:        {total}")
    print(f"  Albums:        {len(albums_count)}")
    print(f"  Artists:       {len(artists_count)}")
    print(f"  Genres:        {len(genres_count)}")
    print(f"  Album artists: {len(albart_count)}")
    print(f"  Playlists:     {len(playlists)}")
    print("=" * 50)


# ── Entry point ───────────────────────────────────────────────────────────────

def main():
    sd = find_sd()
    if not sd:
        print("ERROR: usrlocal_media.db not found.")
        print("Run the script from the SD card root or the folder containing the database.")
        return
    print(f"SD card detected: {sd}")
    rebuild_db(sd)


if __name__ == "__main__":
    main()
