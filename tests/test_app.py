import unittest
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

    def set_status(self, text):
        self.statuses.append(text)

    def set_lyrics(self, *a):
        self.statuses.append("lyrics")

    def set_active(self, i):
        pass


def make_app():
    a = appmod.App.__new__(appmod.App)
    a.win, a.reader = FakeWin(), FakeReader()
    a.track_key, a.token, a.lyrics = KEY, 1, None
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
