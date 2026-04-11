#!/usr/bin/env python3
"""
HiBy DAP - Media Database Updater (GUI)
Scans the SD card and rebuilds usrlocal_media.db

Compatible with macOS, Linux, and Windows.
Requirements: pip install mutagen customtkinter Pillow
"""

import io
import os
import re
import sqlite3
import sys
import time
import errno
import unicodedata
import threading
import customtkinter as ctk
from mutagen import File


# ── Configuration ─────────────────────────────────────────────────────────────

DB_NAME = "usrlocal_media.db"
ART_TARGET_SIZE = (360, 360)

AUDIO_EXT = {
    ".iso", ".dff", ".dsf", ".ape", ".flac", ".aif", ".wav",
    ".m4a", ".aac", ".mp2", ".mp3", ".ogg", ".oga", ".wma", ".opus", ".m4b",
}
PLAYLIST_EXT = {".m3u", ".m3u8"}

FORMAT_MAP = {
    ".flac": 61868, ".dsf": 54736, ".dff": 54736, ".mp3": 85, ".mp2": 80,
    ".wav": 1, ".aif": 1, ".aac": 255, ".m4a": 255, ".m4b": 255, ".wma": 353,
    ".ogg": 26447, ".oga": 26447, ".opus": 28503, ".ape": 21574, ".iso": 0,
}

LOSSY_EXT = {".mp3", ".mp2", ".aac", ".m4a", ".m4b", ".ogg", ".oga", ".wma", ".opus"}
DSD_EXT   = {".dsf", ".dff", ".iso"}
DSD_SET   = {".dsf", ".dff"}

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

_ARTICLES_RE = re.compile(
    r"^(the|der|die|das|les|il|lo|la|le|el)\s+",
    flags=re.IGNORECASE,
)
_PUNCT_RE = re.compile(r"""^[(."']+""")
_TRACK_PREFIX_RE = re.compile(r"^\d{1,3}\s*[-\u2013.]\s*")


# ── Helpers ───────────────────────────────────────────────────────────────────

def sanitize(s) -> str:
    if s is None:
        return ""
    return str(s).replace("\x00", "").strip()

def nul(s) -> str:
    return sanitize(s) + "\x00"

def ascii_upper(s: str) -> str:
    return s.translate(str.maketrans(
        "abcdefghijklmnopqrstuvwxyz",
        "ABCDEFGHIJKLMNOPQRSTUVWXYZ",
    ))

def hiby_path(path: str, sd: str) -> str:
    rel = os.path.relpath(path, sd)
    rel = unicodedata.normalize("NFC", rel)
    return "a:\\" + rel.replace("/", "\\")

def _normalize(text: str) -> str:
    s = _PUNCT_RE.sub("", text.strip())
    return _ARTICLES_RE.sub("", s)

def _sort_tier(ch: str) -> int:
    if not ch: return 0
    cp = ord(ch)
    if 0x2000 <= cp <= 0x2FFF: return 0
    if 0x30 <= cp <= 0x39:     return 1
    if 0x41 <= cp <= 0x5A or 0x61 <= cp <= 0x7A or cp >= 0xC0: return 2
    return 0

def sort_key(text: str) -> tuple:
    norm = _normalize(text)
    if not norm: return (0, text.lower())
    return (_sort_tier(norm[0]), norm.lower())

def sort_character(text: str) -> str:
    if not text: return "#"
    norm = _normalize(text)
    return norm[0].upper() if norm else "#"

def quality_tier(ext: str, samplerate: int) -> str:
    if not samplerate: return "0"
    if ext in DSD_EXT or samplerate > 48000: return "3"
    if ext in LOSSY_EXT: return "1"
    return "2"

_cover_cache: dict = {}

def find_cover(directory: str, sd: str):
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
    lrc = os.path.splitext(audio_path)[0] + ".lrc"
    return hiby_path(lrc, sd) if os.path.isfile(lrc) else None


# ── Album art embed / resize ──────────────────────────────────────────────────

_PIL_AVAILABLE = False
try:
    from PIL import Image as _PILImage
    _PIL_AVAILABLE = True
except ImportError:
    pass

_art_embed_cache: dict = {}
_art_embed_failures: list = []


def _resize_to_jpeg(data: bytes) -> bytes:
    img = _PILImage.open(io.BytesIO(data))
    if img.mode == "RGBA":
        bg = _PILImage.new("RGB", img.size, (255, 255, 255))
        bg.paste(img, mask=img.split()[3])
        img = bg
    elif img.mode != "RGB":
        img = img.convert("RGB")
    img = img.resize(ART_TARGET_SIZE, _PILImage.LANCZOS)
    out = io.BytesIO()
    img.save(out, format="JPEG", quality=90, optimize=True)
    return out.getvalue()


def _load_folder_art(directory: str) -> bytes | None:
    try:
        entries = {f.lower(): f for f in os.listdir(directory)}
        for name in COVER_NAMES:
            if name in entries:
                with open(os.path.join(directory, entries[name]), "rb") as f:
                    return f.read()
    except OSError:
        pass
    return None


def _get_embedded_art(filepath: str, ext: str) -> bytes | None:
    try:
        if ext == ".flac":
            from mutagen.flac import FLAC
            audio = FLAC(filepath)
            if audio.pictures:
                return audio.pictures[0].data
        elif ext == ".mp3":
            from mutagen.id3 import ID3
            tags = ID3(filepath)
            for tag in tags.values():
                if tag.FrameID == "APIC":
                    return tag.data
    except Exception:
        pass
    return None


def _embed_flac(filepath: str, art_bytes: bytes) -> bool:
    try:
        from mutagen.flac import FLAC, Picture
        audio = FLAC(filepath)
        pic = Picture()
        pic.type = 3
        pic.mime = "image/jpeg"
        pic.data = art_bytes
        img = _PILImage.open(io.BytesIO(art_bytes))
        pic.width, pic.height = img.size
        pic.depth = 24
        audio.clear_pictures()
        audio.add_picture(pic)
        audio.save()
        return True
    except Exception as e:
        _art_embed_failures.append((filepath, str(e)))
        return False


def _embed_mp3(filepath: str, art_bytes: bytes) -> bool:
    try:
        from mutagen.id3 import ID3, APIC
        from mutagen.id3 import error as ID3Error
        from mutagen.mp3 import MP3
        try:
            tags = ID3(filepath)
        except ID3Error:
            audio = MP3(filepath)
            audio.add_tags()
            tags = audio.tags
        tags.delall("APIC")
        tags.add(APIC(
            encoding=3,
            mime="image/jpeg",
            type=3,
            desc="Cover",
            data=art_bytes,
        ))
        tags.save(filepath)
        return True
    except Exception as e:
        _art_embed_failures.append((filepath, str(e)))
        return False


def embed_art(filepath: str, ext: str, directory: str) -> bool:
    if not _PIL_AVAILABLE or ext not in (".flac", ".mp3"):
        return False
    if directory not in _art_embed_cache:
        raw = _load_folder_art(directory)
        if raw is None:
            raw = _get_embedded_art(filepath, ext)
        if raw is not None:
            try:
                _art_embed_cache[directory] = _resize_to_jpeg(raw)
            except Exception as e:
                _art_embed_cache[directory] = None
                _art_embed_failures.append((filepath, f"resize error: {e}"))
        else:
            _art_embed_cache[directory] = None
    art_bytes = _art_embed_cache[directory]
    if art_bytes is None:
        return False
    if ext == ".flac":
        return _embed_flac(filepath, art_bytes)
    elif ext == ".mp3":
        return _embed_mp3(filepath, art_bytes)
    return False


# ── Volume detection ──────────────────────────────────────────────────────────

def list_volumes():
    volumes = []
    if os.name == "nt":
        import ctypes as ct
        bitmask = ct.windll.kernel32.GetLogicalDrives()
        for letter in "ABCDEFGHIJKLMNOPQRSTUVWXYZ":
            if bitmask & 1:
                drive = f"{letter}:\\"
                dtype = ct.windll.kernel32.GetDriveTypeW(drive)
                if dtype in (2, 3):
                    try:
                        label_buf = ct.create_unicode_buffer(256)
                        ct.windll.kernel32.GetVolumeInformationW(
                            drive, label_buf, 256, None, None, None, None, 0)
                        label = label_buf.value or letter
                    except Exception:
                        label = letter
                    if os.path.isdir(drive):
                        volumes.append((drive, f"{label} ({drive.rstrip(chr(92))})"))
            bitmask >>= 1
    elif hasattr(os, "uname") and os.uname().sysname == "Darwin":
        vol_root = "/Volumes"
        if os.path.isdir(vol_root):
            for name in sorted(os.listdir(vol_root)):
                path = os.path.join(vol_root, name)
                if os.path.isdir(path) and not name.startswith("."):
                    volumes.append((path, name))
    else:
        user = os.environ.get("USER", "")
        for base in [f"/media/{user}", "/mnt", f"/run/media/{user}"]:
            if os.path.isdir(base):
                try:
                    for d in sorted(os.listdir(base)):
                        path = os.path.join(base, d)
                        if os.path.isdir(path):
                            volumes.append((path, d))
                except OSError:
                    pass
    return volumes


# ── Tag reading ───────────────────────────────────────────────────────────────

_tag_failures: list = []

def _read_vorbis(audio) -> dict:
    def tag(key):
        v = audio.get(key)
        return sanitize(v[0]) if v else None
    return {k: tag(k) for k in
            ["title", "artist", "album", "genre", "albumartist",
             "date", "tracknumber", "discnumber"]}

def read_tags(file: str) -> dict:
    basename  = os.path.splitext(os.path.basename(file))[0]
    title = basename; artist = "Unknown"; album = "Unknown"; genre = "Unknown"
    year = 0; album_artist = ""; samplerate = 0; bitrate = 0; channels = 2
    bitdepth = 16; duration = 0; track_num = 0; disc_num = 1
    ext = os.path.splitext(file)[1].lower()
    audio = None; _err = None

    def _open_file(path, easy):
        def _is_enoent(exc):
            cause = getattr(exc, "__cause__", None) or getattr(exc, "__context__", None)
            if isinstance(cause, OSError): return cause.errno == errno.ENOENT
            if isinstance(exc, OSError): return exc.errno == errno.ENOENT
            return "No such file" in str(exc) or "ENOENT" in str(exc)
        try: return File(path, easy=easy)
        except Exception as e:
            if not _is_enoent(e): return None
        for variant in [unicodedata.normalize("NFC", path),
                        unicodedata.normalize("NFD", path)]:
            if variant != path:
                try: return File(variant, easy=easy)
                except Exception: pass
        return None

    audio = _open_file(file, easy=False if ext in DSD_SET else True)

    if audio is None and ext == ".flac":
        try:
            from mutagen.flac import FLAC
            audio = FLAC(file)
        except Exception as e: _err = e

    if audio is None:
        try:
            from tinytag import TinyTag
            tt = TinyTag.get(file)
            title = sanitize(tt.title) or title
            artist = sanitize(tt.artist) or artist
            album = sanitize(tt.album) or album
            genre = sanitize(tt.genre) or genre
            album_artist = sanitize(getattr(tt, "albumartist", "") or "") or ""
            if tt.year:
                ys = str(tt.year)[:4]
                if ys.isdigit(): year = int(ys)
            if tt.track:
                try: track_num = int(str(tt.track).split("/")[0])
                except: pass
            if tt.disc:
                try: disc_num = int(str(tt.disc).split("/")[0])
                except: pass
            if tt.samplerate: samplerate = tt.samplerate
            if tt.bitrate: bitrate = int(tt.bitrate * 1000)
            if tt.channels: channels = tt.channels
            if getattr(tt, "bitdepth", None): bitdepth = tt.bitdepth
            if tt.duration: duration = int(tt.duration * 1000)
            audio = "tinytag"
        except Exception as e:
            _err = e; _tag_failures.append((file, str(_err)))

    if audio is not None and audio != "tinytag":
        try:
            if ext in DSD_SET and audio.tags:
                def _id3(key):
                    fid = next((f for f, k in ID3_MAP.items() if k == key), None)
                    if not fid: return None
                    frame = audio.tags.get(fid)
                    if frame is None: return None
                    text = getattr(frame, "text", None)
                    return sanitize(str(text[0])) if text else sanitize(str(frame))
                td = {k: _id3(k) for k in ID3_MAP.values()}
            else:
                td = _read_vorbis(audio)
            title = td["title"] or title; artist = td["artist"] or artist
            album = td["album"] or album; genre = td["genre"] or genre
            album_artist = td["albumartist"] or ""
            d = td["date"]
            if d and len(d) >= 4 and d[:4].isdigit(): year = int(d[:4])
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
                samplerate = getattr(info, "sample_rate", 0) or 0
                channels = getattr(info, "channels", 2) or 2
                bitdepth = (getattr(info, "bits_per_sample", 0)
                         or getattr(info, "bits_per_frame", 0) or 16)
                br = getattr(info, "bitrate", 0) or 0
                bitrate = int(br) if br else 0
                length = getattr(info, "length", 0) or 0
                duration = int(length * 1000)
        except Exception: pass

    title_final = sanitize(title) or basename
    if title_final == basename or title_final.startswith(basename[:3]):
        title_final = _TRACK_PREFIX_RE.sub("", title_final).strip()
    if not title_final: title_final = basename
    artist_final = sanitize(artist) or "Unknown"

    return {
        "title": title_final, "artist": artist_final,
        "album": sanitize(album) or "Unknown", "genre": sanitize(genre) or "Unknown",
        "year": year, "album_artist": sanitize(album_artist) or artist_final,
        "samplerate": samplerate, "bitrate": bitrate, "channels": channels,
        "bitdepth": bitdepth, "duration": duration,
        "track_num": track_num, "disc_num": disc_num,
    }


# ── Filesystem scan ───────────────────────────────────────────────────────────

def _walk(top):
    try: entries = list(os.scandir(top))
    except OSError: return
    dir_entries, file_entries = [], []
    for e in entries:
        if e.is_dir(follow_symlinks=False): dir_entries.append((e.path, e.name))
        else: file_entries.append(e.path)
    yield top, [n for _, n in dir_entries], file_entries
    for path, name in dir_entries:
        if not name.startswith("."): yield from _walk(path)

def scan_files(sd):
    audio, playlists = [], []
    for root, dirs, file_paths in _walk(sd):
        dirs[:] = [d for d in dirs if not d.startswith(".")]
        for full in file_paths:
            f = os.path.basename(full)
            if f.startswith("._") or f.startswith("."): continue
            ext = os.path.splitext(f)[1].lower()
            if ext in AUDIO_EXT: audio.append(full)
            elif ext in PLAYLIST_EXT: playlists.append(full)
    audio.sort(key=lambda x: hiby_path(x, sd).lower())
    return audio, playlists


# ── Database rebuild (with progress callback) ─────────────────────────────────

def rebuild_db(sd, embed_art_enabled=True, on_progress=None, on_status=None):
    _cover_cache.clear()
    _art_embed_cache.clear()
    _art_embed_failures.clear()
    _tag_failures.clear()

    conn = sqlite3.connect(os.path.join(sd, DB_NAME))
    conn.text_factory = str; cur = conn.cursor()
    cur.execute("PRAGMA synchronous = OFF")
    cur.execute("PRAGMA journal_mode = MEMORY")
    cur.execute("PRAGMA cache_size = -32000")
    cur.execute("PRAGMA temp_store = MEMORY")

    t0 = time.time()
    if on_status: on_status("Scanning SD card...")
    audio, playlists = scan_files(sd)
    if on_status: on_status(f"Found {len(audio)} audio files, {len(playlists)} playlists")

    # ── Album art embed/resize pass ───────────────────────────────────────────
    art_embedded = 0
    if embed_art_enabled and _PIL_AVAILABLE:
        if on_status: on_status("Embedding album art (360×360)...")
        for i, file in enumerate(audio):
            ext = os.path.splitext(file)[1].lower()
            if ext in (".flac", ".mp3"):
                if on_progress: on_progress(i, len(audio) * 2)  # art pass = first half
                if embed_art(file, ext, os.path.dirname(file)):
                    art_embedded += 1
        if on_status: on_status(f"Art embedded in {art_embedded} files")

    if on_status: on_status("Reading tags...")
    artists_count, albums_count, genres_count, albart_count = {}, {}, {}, {}
    artists_first, albums_first, genres_first, albart_first = {}, {}, {}, {}
    artists_canon, albums_canon, genres_canon, albart_canon = {}, {}, {}, {}
    formats_seen = {}; media_ctime, media_mtime, media_rows = [], [], []

    def canonical(value, canon_map):
        key = value.lower()
        if key not in canon_map: canon_map[key] = value
        return canon_map[key]

    total_steps = len(audio) * 2 if (embed_art_enabled and _PIL_AVAILABLE) else len(audio)
    offset = len(audio) if (embed_art_enabled and _PIL_AVAILABLE) else 0

    for i, file in enumerate(audio):
        if on_progress: on_progress(offset + i, total_steps)
        tags = read_tags(file); ext = os.path.splitext(file)[1].lower()
        hibyp = hiby_path(file, sd)
        try:
            size = os.path.getsize(file)
            ctime = int(os.path.getctime(file)); mtime = int(os.path.getmtime(file))
        except OSError: size = ctime = mtime = 0

        art = canonical(tags["artist"], artists_canon)
        alb = canonical(tags["album"], albums_canon)
        gen = canonical(tags["genre"], genres_canon)
        alb_art = canonical(tags["album_artist"], albart_canon)

        artists_count[art] = artists_count.get(art, 0) + 1
        albums_count[alb] = albums_count.get(alb, 0) + 1
        genres_count[gen] = genres_count.get(gen, 0) + 1
        albart_count[alb_art] = albart_count.get(alb_art, 0) + 1

        if art not in artists_first: artists_first[art] = i + 1
        if alb not in albums_first: albums_first[alb] = i + 1
        if gen not in genres_first: genres_first[gen] = i + 1
        if alb_art not in albart_first: albart_first[alb_art] = i + 1

        formats_seen[ext] = i + 1
        media_ctime.append((ctime, i + 1)); media_mtime.append((mtime, i + 1))
        media_rows.append((
            i + 1, nul(hibyp), nul(tags["title"]), nul(alb), nul(art),
            nul(gen), tags["year"], tags["disc_num"], tags["track_num"],
            0, 0, -1, -1, sort_character(tags["title"]),
            size, tags["samplerate"], tags["bitrate"], tags["bitdepth"],
            tags["channels"], FORMAT_MAP.get(ext, 0),
            quality_tier(ext, tags["samplerate"]),
            nul(find_cover(os.path.dirname(file), sd) or ""),
            nul(find_lrc(file, sd) or ""), 0.0, 0.0, ctime, mtime,
            nul(ascii_upper(_normalize(tags["title"]))), nul(alb_art),
        ))

    total = len(audio)
    if on_status: on_status("Writing database...")
    if on_progress: on_progress(total_steps, total_steps)

    def pinyin(s): return nul(ascii_upper(_normalize(s)))

    _INS = """INSERT INTO MEDIA_TABLE
        (id, path, name, album, artist, genre, year, dis_id, ck_id,
         has_child_file, begin_time, end_time, cue_id, character,
         size, sample_rate, bit_rate, bit, channel, format, quality,
         album_pic_path, lrc_path, track_gain, track_peak, ctime, mtime,
         pinyin_charater, album_artist)
        VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)"""
    _INS2 = _INS.replace("MEDIA_TABLE", "MEDIA2_TABLE")

    cur.execute("DELETE FROM MEDIA2_TABLE"); cur.executemany(_INS2, media_rows)
    media_sorted = sorted(media_rows, key=lambda r: sort_key(sanitize(r[2])))
    cur.execute("DELETE FROM MEDIA_TABLE"); cur.executemany(_INS, media_sorted)
    cur.execute("DELETE FROM MEDIA3_TABLE")

    for tbl, col, rows_data in [
        ("ARTIST", "artist", artists_count), ("GENRE", "genre", genres_count)]:
        first = artists_first if tbl == "ARTIST" else genres_first
        rows = sorted([(first[k], nul(k), sort_character(k), cn, 0, 0, pinyin(k))
                       for k, cn in rows_data.items()], key=lambda r: sort_key(sanitize(r[1])))
        for t in [f"{tbl}_TABLE", f"{tbl}2_TABLE"]:
            cur.execute(f"DELETE FROM {t}")
            cur.executemany(f"INSERT INTO {t} (id, {col}, character, cn, ctime, mtime, pinyin_charater) VALUES (?,?,?,?,?,?,?)", rows)

    for tbl, col, rows_data, first in [
        ("ALBUM", "album", albums_count, albums_first),
        ("ALBUM_ARTIST", "album_artist", albart_count, albart_first)]:
        rows = sorted([(first[k], nul(k), sort_character(k), cn, 0, 0, 0, pinyin(k))
                       for k, cn in rows_data.items()], key=lambda r: sort_key(sanitize(r[1])))
        for t in [f"{tbl}_TABLE", f"{tbl}2_TABLE"]:
            cur.execute(f"DELETE FROM {t}")
            cur.executemany(f"INSERT INTO {t} (id, {col}, character, cn, ctime, mtime, mqa, pinyin_charater) VALUES (?,?,?,?,?,?,?,?)", rows)

    cur.execute("DELETE FROM COUNT_TABLE")
    cur.executemany("INSERT INTO COUNT_TABLE (cn) VALUES (?)",
        [(total,), (len(albums_count),), (len(artists_count),),
         (len(genres_count),), (len(albart_count),)])

    fmt_rows = sorted([(formats_seen[e], e.lstrip(".").upper()) for e in formats_seen],
                      key=lambda r: sort_key(r[1]))
    fmt_ins = [(m, n, sort_character(n), 1) for m, n in fmt_rows]
    for t in ["FORMAT_TABLE", "FORMAT2_TABLE"]:
        cur.execute(f"DELETE FROM {t}")
        cur.executemany(f"INSERT INTO {t} (id, format, character, cn) VALUES (?,?,?,?)", fmt_ins)

    cur.execute("DELETE FROM CTIME_TABLE")
    cur.executemany("INSERT INTO CTIME_TABLE (media_id) VALUES (?)",
        [(m,) for _, m in sorted(media_ctime, key=lambda x: (x[0], x[1]))])
    cur.execute("DELETE FROM MTIME_TABLE")
    cur.executemany("INSERT INTO MTIME_TABLE (media_id) VALUES (?)",
        [(m,) for _, m in sorted(media_mtime, key=lambda x: (-x[0], x[1]))])

    cur.execute("DELETE FROM M3U_TABLE")
    if playlists:
        cur.executemany("INSERT INTO M3U_TABLE (id, path, name, character) VALUES (?,?,?,?)",
            [(total, nul(hiby_path(p, sd)), nul(os.path.basename(p)),
              sort_character(os.path.basename(p))) for p in playlists])

    conn.commit(); conn.close()
    return {
        "tracks": total, "albums": len(albums_count), "artists": len(artists_count),
        "genres": len(genres_count), "album_artists": len(albart_count),
        "playlists": len(playlists), "elapsed": time.time() - t0,
        "art_embedded": art_embedded,
        "art_failures": len(_art_embed_failures),
        "tag_failures": list(_tag_failures),
    }


# ── GUI ───────────────────────────────────────────────────────────────────────

class App(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.title("HiBy Database Updater")
        self.geometry("540x540")
        self.resizable(False, False)

        pad = ctk.CTkFrame(self, fg_color="transparent")
        pad.pack(fill="both", expand=True, padx=28, pady=24)

        ctk.CTkLabel(pad, text="HiBy Database Updater",
                     font=ctk.CTkFont(size=24, weight="bold")).pack(anchor="w")
        ctk.CTkLabel(pad, text="Rebuild usrlocal_media.db from your SD card",
                     font=ctk.CTkFont(size=13),
                     text_color=("gray50", "gray60")).pack(anchor="w", pady=(0, 14))

        # Drive selector row
        drive_frame = ctk.CTkFrame(pad, fg_color="transparent")
        drive_frame.pack(fill="x", pady=(0, 6))
        ctk.CTkLabel(drive_frame, text="SD Card:",
                     font=ctk.CTkFont(size=14)).pack(side="left", padx=(0, 10))
        self._volumes = list_volumes()
        display, default_idx = self._build_volume_list()
        self._combo_var = ctk.StringVar()
        self._combo = ctk.CTkComboBox(drive_frame, values=display,
                                       variable=self._combo_var,
                                       state="readonly", width=320,
                                       font=ctk.CTkFont(size=13))
        self._combo.pack(side="left", fill="x", expand=True)
        if default_idx >= 0:
            self._combo.set(display[default_idx])
        elif display:
            self._combo.set(display[0])
        ctk.CTkButton(drive_frame, text="↻", width=36, height=36,
                      font=ctk.CTkFont(size=16),
                      command=self._refresh_volumes).pack(side="left", padx=(8, 0))

        # Album art checkbox
        self._embed_art_var = ctk.BooleanVar(value=_PIL_AVAILABLE)
        art_frame = ctk.CTkFrame(pad, fg_color="transparent")
        art_frame.pack(fill="x", pady=(8, 2))
        self._art_checkbox = ctk.CTkCheckBox(
            art_frame,
            text="Embed & resize album art to 360×360px (FLAC/MP3)",
            variable=self._embed_art_var,
            font=ctk.CTkFont(size=13),
            state="normal" if _PIL_AVAILABLE else "disabled",
        )
        self._art_checkbox.pack(anchor="w")
        if not _PIL_AVAILABLE:
            ctk.CTkLabel(art_frame,
                         text="  ⚠ Pillow not installed — run: pip install Pillow",
                         font=ctk.CTkFont(size=11),
                         text_color=("orange", "orange")).pack(anchor="w")

        # Start button
        self._start_btn = ctk.CTkButton(
            pad, text="Start", height=44,
            font=ctk.CTkFont(size=16, weight="bold"),
            command=self._on_start)
        self._start_btn.pack(fill="x", pady=(14, 10))

        # Status label
        self._status_var = ctk.StringVar(value="Select your SD card and press Start")
        ctk.CTkLabel(pad, textvariable=self._status_var,
                     font=ctk.CTkFont(family="monospace", size=12),
                     text_color=("gray40", "gray60")).pack(anchor="w")

        # Progress bar
        self._progress = ctk.CTkProgressBar(pad, height=10)
        self._progress.pack(fill="x", pady=(8, 14))
        self._progress.set(0)

        # Results textbox
        self._result_box = ctk.CTkTextbox(
            pad, height=160,
            font=ctk.CTkFont(family="monospace", size=13),
            state="disabled", activate_scrollbars=False)
        self._result_box.pack(fill="both", expand=True)

    def _build_volume_list(self):
        display = []
        default_idx = -1
        for i, (path, label) in enumerate(self._volumes):
            has_db = os.path.exists(os.path.join(path, DB_NAME))
            tag = "  ✓ DB" if has_db else ""
            display.append(f"{label}  —  {path}{tag}")
            if has_db and default_idx == -1:
                default_idx = i
        return display, default_idx

    def _refresh_volumes(self):
        self._volumes = list_volumes()
        display, default_idx = self._build_volume_list()
        self._combo.configure(values=display)
        if default_idx >= 0:
            self._combo.set(display[default_idx])
        elif display:
            self._combo.set(display[0])

    def _get_selected_volume(self):
        current = self._combo_var.get()
        for i, (path, label) in enumerate(self._volumes):
            has_db = os.path.exists(os.path.join(path, DB_NAME))
            tag = "  ✓ DB" if has_db else ""
            if f"{label}  —  {path}{tag}" == current:
                return path
        return None

    def _on_start(self):
        sd_path = self._get_selected_volume()
        if not sd_path:
            self._show_error("Please select a drive.")
            return
        if not os.path.exists(os.path.join(sd_path, DB_NAME)):
            self._show_error(
                f"{DB_NAME} not found on the selected drive.\n\n"
                f"The SD card must contain the database file\n"
                f"(copy one from the device first).")
            return

        self._start_btn.configure(state="disabled")
        self._combo.configure(state="disabled")
        self._art_checkbox.configure(state="disabled")
        self._progress.set(0)
        self._result_box.configure(state="normal")
        self._result_box.delete("0.0", "end")
        self._result_box.configure(state="disabled")

        embed = self._embed_art_var.get() and _PIL_AVAILABLE
        thread = threading.Thread(target=self._worker, args=(sd_path, embed), daemon=True)
        thread.start()

    def _worker(self, sd_path, embed_art_enabled):
        try:
            result = rebuild_db(sd_path,
                                embed_art_enabled=embed_art_enabled,
                                on_progress=self._on_progress,
                                on_status=self._on_status)
            self.after(0, self._on_done, result)
        except Exception as e:
            self.after(0, self._on_error, str(e))

    def _on_progress(self, current, total):
        if total > 0:
            self.after(0, self._set_progress, current, total)

    def _set_progress(self, current, total):
        self._progress.set(current / total)

    def _on_status(self, msg):
        self.after(0, self._status_var.set, msg)

    def _on_done(self, result):
        self._progress.set(1.0)
        self._status_var.set("Done!")

        text = (
            f"  Completed in {result['elapsed']:.1f}s\n"
            f"\n"
            f"  Tracks:         {result['tracks']}\n"
            f"  Albums:         {result['albums']}\n"
            f"  Artists:        {result['artists']}\n"
            f"  Genres:         {result['genres']}\n"
            f"  Album Artists:  {result['album_artists']}\n"
            f"  Playlists:      {result['playlists']}\n"
        )
        if result["art_embedded"] > 0:
            text += f"\n  Art embedded:   {result['art_embedded']} files\n"
        if result["art_failures"] > 0:
            text += f"  ⚠ Art errors:   {result['art_failures']} files\n"
        if result["tag_failures"]:
            text += f"\n  ⚠ {len(result['tag_failures'])} file(s) could not be read\n"

        self._result_box.configure(state="normal")
        self._result_box.delete("0.0", "end")
        self._result_box.insert("0.0", text)
        self._result_box.configure(state="disabled")

        self._start_btn.configure(state="normal")
        self._combo.configure(state="readonly")
        self._art_checkbox.configure(state="normal" if _PIL_AVAILABLE else "disabled")

    def _on_error(self, msg):
        self._progress.set(0)
        self._status_var.set("Error!")
        self._result_box.configure(state="normal")
        self._result_box.delete("0.0", "end")
        self._result_box.insert("0.0", f"  Error: {msg}\n")
        self._result_box.configure(state="disabled")
        self._start_btn.configure(state="normal")
        self._combo.configure(state="readonly")
        self._art_checkbox.configure(state="normal" if _PIL_AVAILABLE else "disabled")

    def _show_error(self, msg):
        from tkinter import messagebox
        messagebox.showerror("Error", msg)


if __name__ == "__main__":
    ctk.set_appearance_mode("system")
    ctk.set_default_color_theme("blue")
    app = App()
    app.mainloop()
