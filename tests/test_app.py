import tempfile
import unittest
from pathlib import Path
from unittest import mock

from lyrics_pip import app as appmod
from lyrics_pip.lyrics import NETWORK_ERROR
from lyrics_pip.mpris import PlayerState, Track
from lyrics_pip.ui import is_visible_position

TRACK = Track("T", "A", "Al", 200.0)
KEY = ("T", "A", 200)


class FakeReader:
    def __init__(self):
        self.result = None

    def read(self):
        return self.result


class FakeWin:
    def __init__(self):
        self.statuses = []
        self.actions = []
        self.controls = []

    def set_status(self, text, action=None):
        self.statuses.append(text)
        self.actions.append(action)

    def set_song_controls(self, visible):
        self.controls.append(visible)

    def set_lyrics(self, *a):
        self.statuses.append("lyrics")

    def set_active(self, i):
        pass


def make_app():
    a = appmod.App.__new__(appmod.App)
    a.win, a.reader = FakeWin(), FakeReader()
    a.track_key, a.token, a.lyrics = KEY, 1, None
    a.current = TRACK
    a._interval, a._timer, a._misses = appmod.FAST_MS, 0, 0
    a.estimator = appmod.PositionEstimator()
    return a


class PollToleranceTest(unittest.TestCase):
    def test_brief_mpris_failures_keep_current_song(self):
        a = make_app()
        a.reader.result = None
        a._poll()
        a._poll()
        self.assertEqual(a.track_key, KEY)
        self.assertEqual(a.win.statuses, [])

    def test_third_consecutive_failure_resets_to_idle(self):
        a = make_app()
        for _ in range(3):
            a._poll()
        self.assertIsNone(a.track_key)
        self.assertEqual(a.win.statuses, [appmod.MSG_IDLE])

    def test_success_resets_failure_count(self):
        a = make_app()
        a._poll()
        a._poll()
        a.reader.result = PlayerState(TRACK, 5.0, True)
        a._poll()
        a.reader.result = None
        a._poll()
        a._poll()
        self.assertEqual(a.track_key, KEY)


class NetworkRetryTest(unittest.TestCase):
    def test_network_error_shows_retry_message_and_schedules_retry(self):
        a = make_app()
        with mock.patch.object(appmod.GLib, "timeout_add") as ta:
            a._deliver(1, NETWORK_ERROR, TRACK)
        self.assertEqual(a.win.statuses, [appmod.MSG_RETRY])
        self.assertEqual(ta.call_args[0][0], appmod.RETRY_MS)

    def test_retry_refetches_only_if_song_unchanged(self):
        a = make_app()
        with mock.patch.object(a, "_start_fetch", create=True) as sf:
            a._retry(1, KEY, TRACK)
            sf.assert_called_once_with(KEY, TRACK)
        a.token = 2  # song changed
        with mock.patch.object(a, "_start_fetch", create=True) as sf:
            a._retry(1, KEY, TRACK)
            sf.assert_not_called()


class EditAndReloadTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.dir = Path(self._tmp.name)
        self.a = make_app()
        p = mock.patch.object(appmod, "CUSTOM_DIR", self.dir)
        p.start()
        self.addCleanup(p.stop)
        sf = mock.patch.object(self.a, "_start_fetch", create=True)
        self.sf = sf.start()
        self.addCleanup(sf.stop)

    def test_not_found_offers_add_lyrics_action(self):
        self.a._deliver(1, None, TRACK)
        self.assertEqual(self.a.win.statuses, [appmod.MSG_NOT_FOUND])
        self.assertEqual(self.a.win.actions[-1], ("Tambah lirik", self.a._edit))

    def test_edit_saves_and_refetches(self):
        with mock.patch.object(appmod, "ask_lyrics_text", return_value="[00:01.00]hi"):
            self.a._edit()
        self.assertTrue((self.dir / "A - T.lrc").exists())
        self.sf.assert_called_once_with(KEY, TRACK)

    def test_edit_dialog_is_prefilled_with_existing_custom_text(self):
        (self.dir / "A - T.txt").write_text("lama\n", encoding="utf-8")
        with mock.patch.object(appmod, "ask_lyrics_text", return_value=None) as ask:
            self.a._edit()
        self.assertEqual(ask.call_args[0][2], "lama")

    def test_edit_cancel_changes_nothing(self):
        with mock.patch.object(appmod, "ask_lyrics_text", return_value=None):
            self.a._edit()
        self.assertEqual(list(self.dir.iterdir()), [])
        self.sf.assert_not_called()

    def test_edit_empty_text_removes_custom_and_refetches(self):
        (self.dir / "A - T.txt").write_text("lama\n", encoding="utf-8")
        with mock.patch.object(appmod, "ask_lyrics_text", return_value=""):
            self.a._edit()
        self.assertEqual(list(self.dir.iterdir()), [])
        self.sf.assert_called_once_with(KEY, TRACK)

    def test_edit_when_song_changed_during_dialog_saves_original_without_refetch(self):
        def ask(*_a):
            self.a.track_key = ("Lain", "B", 100)
            self.a.current = Track("Lain", "B", "", 100.0)
            return "teks"

        with mock.patch.object(appmod, "ask_lyrics_text", side_effect=ask):
            self.a._edit()
        self.assertTrue((self.dir / "A - T.txt").exists())
        self.sf.assert_not_called()

    def test_edit_save_failure_shows_message(self):
        with mock.patch.object(appmod, "ask_lyrics_text", return_value="x"), \
                mock.patch.object(appmod, "save_custom", side_effect=OSError("disk")):
            self.a._edit()
        self.assertEqual(self.a.win.statuses[-1], appmod.MSG_SAVE_FAILED)
        self.sf.assert_not_called()

    def test_edit_without_song_is_noop(self):
        self.a.current = None
        with mock.patch.object(appmod, "ask_lyrics_text") as ask:
            self.a._edit()
        ask.assert_not_called()

    def test_reload_forgets_cache_and_refetches(self):
        with mock.patch.object(appmod, "forget_cached") as forget:
            self.a._reload()
        forget.assert_called_once_with(
            appmod.clean_title(TRACK.title, TRACK.artist), TRACK.artist,
            TRACK.length, appmod.CACHE_DIR,
        )
        self.sf.assert_called_once_with(KEY, TRACK)

    def test_reload_without_song_is_noop(self):
        self.a.current = None
        with mock.patch.object(appmod, "forget_cached") as forget:
            self.a._reload()
        forget.assert_not_called()
        self.sf.assert_not_called()


class ControlsTest(unittest.TestCase):
    def test_controls_follow_song_state(self):
        a = make_app()
        a.track_key, a.current = None, None
        a.reader.result = PlayerState(TRACK, 5.0, True)
        with mock.patch.object(appmod.threading, "Thread"):
            a._poll()
        self.assertEqual(a.win.controls, [True])
        a.reader.result = None
        for _ in range(3):
            a._poll()
        self.assertEqual(a.win.controls, [True, False])


class VisiblePositionTest(unittest.TestCase):
    MON = [(0, 0, 1920, 1080)]

    def test_visible(self):
        self.assertTrue(is_visible_position(100, 100, 380, 300, self.MON))

    def test_offscreen_after_monitor_unplugged(self):
        self.assertFalse(is_visible_position(2690, 373, 380, 300, self.MON))

    def test_second_monitor_present(self):
        mons = self.MON + [(1920, 0, 1920, 1080)]
        self.assertTrue(is_visible_position(2690, 373, 380, 300, mons))

    def test_barely_on_screen_is_not_visible(self):
        self.assertFalse(is_visible_position(1900, 100, 380, 300, self.MON))


if __name__ == "__main__":
    unittest.main()
