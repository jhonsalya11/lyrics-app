import signal
import threading
import time
from pathlib import Path

import gi

gi.require_version("Gtk", "3.0")
from gi.repository import GLib, Gtk  # noqa: E402

from .clock import PositionEstimator
from .instance import acquire_single_instance
from .lrc import active_index
from .custom import CUSTOM_DIR, read_custom_text, resolve_lyrics, save_custom
from .lyrics import NETWORK_ERROR, clean_title, forget_cached
from .mpris import MprisReader
from .ui import LyricsWindow, ask_lyrics_text

CACHE_DIR = Path.home() / ".cache" / "lyrics-pip"
FAST_MS = 250
SLOW_MS = 1000
IDLE_MS = 2000
MAX_MISSES = 3
RETRY_MS = 20000

MSG_IDLE = "Tidak ada lagu diputar"
MSG_SEARCHING = "Mencari lirik..."
MSG_NOT_FOUND = "Lirik tidak ditemukan"
MSG_RETRY = "Gagal memuat lirik, mencoba lagi..."
MSG_SAVE_FAILED = "Gagal menyimpan lirik"


class App:
    def __init__(self):
        self.win = LyricsWindow()
        self.reader = MprisReader()
        self.estimator = PositionEstimator()
        self.track_key = None
        self.token = 0
        self.lyrics = None
        self.current = None
        self._interval = FAST_MS
        self._timer = 0
        self._misses = 0

        self.win.on_edit = self._edit
        self.win.on_reload = self._reload
        self.win.connect("destroy", lambda *_: Gtk.main_quit())
        self.win.set_status(MSG_IDLE)
        self.win.show_all()
        self._schedule(FAST_MS)

    # ---- polling -------------------------------------------------------
    def _schedule(self, ms: int) -> None:
        if self._timer:
            GLib.source_remove(self._timer)
        self._interval = ms
        self._timer = GLib.timeout_add(ms, self._tick)

    def _tick(self) -> bool:
        try:
            wanted = self._poll()
        except Exception:
            wanted = IDLE_MS
        if wanted != self._interval:
            self._schedule(wanted)
            return False
        return True

    def _poll(self) -> int:
        state = self.reader.read()
        if state is None or state.track is None:
            # Tolerate brief MPRIS hiccups (e.g. Firefox stalled under memory
            # pressure): only give up after several consecutive misses.
            self._misses += 1
            if self.track_key is None:
                return IDLE_MS
            if self._misses >= MAX_MISSES:
                self._reset(MSG_IDLE)
                return IDLE_MS
            return FAST_MS
        self._misses = 0

        track = state.track
        key = (track.title, track.artist, round(track.length))
        if key != self.track_key:
            self._start_fetch(key, track)

        if self.lyrics is not None and self.lyrics.synced:
            pos = self.estimator.update(state.position, time.monotonic(), state.playing)
            self.win.set_active(active_index(self.lyrics.lines, pos))
        return FAST_MS if state.playing else SLOW_MS

    def _reset(self, message: str) -> None:
        self.token += 1
        self.track_key = None
        self.current = None
        self.lyrics = None
        self.win.set_song_controls(False)
        self.win.set_status(message)

    # ---- fetching ------------------------------------------------------
    def _start_fetch(self, key, track) -> None:
        self.token += 1
        token = self.token
        self.track_key = key
        self.current = track
        self.lyrics = None
        self.estimator = PositionEstimator()
        self.win.set_song_controls(True)
        self.win.set_status(MSG_SEARCHING)

        def work():
            result = resolve_lyrics(
                clean_title(track.title, track.artist), track.artist, track.album,
                track.length, CACHE_DIR, CUSTOM_DIR,
            )
            GLib.idle_add(self._deliver, token, result, track)

        threading.Thread(target=work, daemon=True).start()

    def _deliver(self, token, result, track) -> bool:
        if token != self.token:  # song changed while downloading: drop it
            return False
        if result is NETWORK_ERROR:
            self.lyrics = None
            self.win.set_status(MSG_RETRY)
            GLib.timeout_add(RETRY_MS, self._retry, token, self.track_key, track)
            return False
        self.lyrics = result
        if result is None:
            self.win.set_status(MSG_NOT_FOUND, action=("Tambah lirik", self._edit))
        else:
            self.win.set_lyrics(result, track.title, track.artist)
        return False


    def _edit(self) -> None:
        track, key = self.current, self.track_key
        if track is None:
            return
        title = clean_title(track.title, track.artist)
        heading = f"{track.title} — {track.artist}" if track.artist else track.title
        initial = read_custom_text(title, track.artist, CUSTOM_DIR)
        while True:
            text = ask_lyrics_text(self.win, heading, initial)
            if text is None:
                return
            try:
                save_custom(title, track.artist, text, CUSTOM_DIR)
                break
            except OSError as e:
                # Keep what the user pasted and leave the lyrics view alone.
                heading = f"{MSG_SAVE_FAILED}: {e.strerror or e}\n{track.title}"
                initial = text
        if self.track_key == key:  # song may have changed while the dialog was open
            self._start_fetch(key, track)

    def _reload(self) -> None:
        track = self.current
        if track is None:
            return
        forget_cached(
            clean_title(track.title, track.artist), track.artist, track.length, CACHE_DIR
        )
        self._start_fetch(self.track_key, track)

    def _retry(self, token, key, track) -> bool:
        if token == self.token and key == self.track_key:  # same song still playing
            self._start_fetch(key, track)
        return False


def main() -> None:
    lock = acquire_single_instance(CACHE_DIR / "instance.lock")
    if lock is None:
        return  # already running; keep the single window
    app = App()

    def quit_cleanly():
        app.win.close()  # runs delete-event, which saves window position/size/opacity
        return False

    GLib.unix_signal_add(GLib.PRIORITY_DEFAULT, signal.SIGINT, quit_cleanly)
    GLib.unix_signal_add(GLib.PRIORITY_DEFAULT, signal.SIGTERM, quit_cleanly)
    Gtk.main()
    lock.close()


if __name__ == "__main__":
    main()
