import re
import urllib.request
from pathlib import Path

from .lrc import parse_lrc
from .lyrics import Lyrics, fetch_lyrics

CUSTOM_DIR = Path(__file__).resolve().parent.parent / "lyrics"
_UNSAFE = re.compile(r'[<>:"/\\|?*\x00-\x1f]')
_MAX_NAME = 150


def _clean_part(text: str) -> str:
    return _UNSAFE.sub("_", text or "").lstrip(". ").strip()


def safe_filename(artist: str, title: str) -> str:
    a, t = _clean_part(artist), _clean_part(title)
    name = f"{a} - {t}" if a and t else (a or t)
    return name[:_MAX_NAME].rstrip() or "untitled"


def _paths(title, artist, directory):
    base = Path(directory) / safe_filename(artist, title)
    return base.with_name(base.name + ".lrc"), base.with_name(base.name + ".txt")


def _read(path: Path):
    try:
        return path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return None


def _plain(text: str):
    lines = text.replace("\r\n", "\n").strip().splitlines()
    return [(0.0, ln.strip()) for ln in lines]


def load_custom(title: str, artist: str, directory) -> "Lyrics | None":
    lrc, txt = _paths(title, artist, directory)
    for path in (lrc, txt):
        text = _read(path)
        if text is None or not text.strip():
            continue
        synced = parse_lrc(text)
        if synced:
            return Lyrics(synced, True)
        return Lyrics(_plain(text), False)
    return None


def read_custom_text(title: str, artist: str, directory) -> str:
    lrc, txt = _paths(title, artist, directory)
    for path in (lrc, txt):
        text = _read(path)
        if text is not None:
            return text.replace("\r\n", "\n").strip()  # same normalisation as save_custom
    return ""


def save_custom(title: str, artist: str, text: str, directory) -> "Path | None":
    """Save pasted lyrics; empty text deletes this song's custom file. May raise OSError."""
    lrc, txt = _paths(title, artist, directory)
    text = (text or "").replace("\r\n", "\n").strip()
    if not text:
        lrc.unlink(missing_ok=True)
        txt.unlink(missing_ok=True)
        return None
    target, other = (lrc, txt) if parse_lrc(text) else (txt, lrc)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(text + "\n", encoding="utf-8")
    other.unlink(missing_ok=True)
    return target


def resolve_lyrics(title, artist, album, duration, cache_dir, custom_dir,
                   opener=urllib.request.urlopen):
    """Custom file first (it always wins), then cache/LRCLIB."""
    custom = load_custom(title, artist, custom_dir)
    if custom is not None:
        return custom
    return fetch_lyrics(title, artist, album, duration, cache_dir, opener=opener)
