"""The countdown of the hold time: what happens when it reaches 0% and sound comes after it."""
import os
import sys
import unittest
from datetime import datetime, timedelta

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from support import *  # noqa: F401,F403

METHODS = ["_tick_interaction_countdown", "_finish_interaction_countdown", "get_seconds_since_last_interaction",
           "_holding_percentage_for"]
HOLD = 15


class FakeInteraction:
    def __init__(self, calls, button_only=False, muted=False, speaking=False, transcribing=False):
        self.calls, self.button_only, self.muted = calls, button_only, muted
        self.speaking, self.transcribing = speaking, transcribing

    def is_microphone_muted(self): return self.muted
    def is_wake_up_button_wanted_exclusively(self): return self.button_only
    def is_transcriber_busy(self): return self.transcribing
    def is_vad_detected(self): return self.speaking
    def is_chatbot_busy(self): return False
    def is_speaker_busy(self): return False
    def is_background_display_busy(self): return False
    def show_interaction_holding_percentage(self, percentage): self.calls.append(("show", percentage))
    def set_idle_mode_on(self): self.calls.append("idle on")

    def mute_microphone(self, input_stream=None):
        self.muted = True
        self.calls.append("mute")


def app(percentage, seconds_since=20, **interaction):
    Holder = methods_of("pitxu/main.py", METHODS, {"datetime": datetime, "TerminalColor": type("T", (), {"ORANGE": "", "END": ""})})
    a = Holder()
    a.calls = []
    a._xlog = Log()
    a._interaction = FakeInteraction(a.calls, **interaction)
    a._input_stream = None
    a._seconds_to_hold_interaction_answer = HOLD
    a._last_interaction_paused_seconds = 0
    a._last_interaction_datetime = datetime.now() - timedelta(seconds=seconds_since)
    a._last_processed_interaction_percentage = percentage
    a._dictate = type("D", (), {"get_ongoing_transcription": lambda self: ""})()

    def end_listening(reason, mute=True, clear_bar=False):
        a.calls.append(("end", reason, mute, clear_bar))
        if clear_bar:
            a._last_processed_interaction_percentage = -1
    a._end_listening_phase = end_listening
    return a


class ZeroPercentTests(unittest.TestCase):

    def test_01_the_0_percent_jump_stops_the_microphone_when_only_the_button_is_wanted(self):
        a = app(percentage=5, button_only=True)
        a._tick_interaction_countdown()
        self.assertEqual(a.calls, [("show", 0), "mute"])
        self.assertEqual(a._last_processed_interaction_percentage, 0)

    def test_02_the_voice_modes_keep_the_microphone_for_the_trigger_words(self):
        a = app(percentage=5, button_only=False)
        a._tick_interaction_countdown()
        self.assertEqual(a.calls, [("show", 0)])

    def test_03_with_the_microphone_stopped_the_cleanup_still_happens_and_does_not_mute_twice(self):
        a = app(percentage=5, button_only=True)
        a._tick_interaction_countdown()          # the jump
        a.calls.clear()
        a._tick_interaction_countdown()          # the tick after: muted, so the countdown does not run, the cleanup does
        self.assertEqual(a.calls, ["idle on", ("end", "hold time over", False, True)])
        a.calls.clear()
        a._tick_interaction_countdown()          # and it happens once
        self.assertEqual(a.calls, [])

    def test_04_without_the_button_only_mode_the_cleanup_is_unchanged(self):
        a = app(percentage=0, button_only=False)
        a._tick_interaction_countdown()
        self.assertEqual(a.calls, ["idle on", ("end", "hold time over", False, True)])
        a = app(percentage=0, button_only=True)   # a start of the app: not muted yet, the cleanup mutes
        a._tick_interaction_countdown()
        self.assertEqual(a.calls, ["idle on", ("end", "hold time over", True, True)])

    def test_05_sound_after_the_0_percent_does_not_keep_the_countdown_alive(self):
        # What the log showed: the speech started 0.5 s after the 0%, and the countdown stayed for the whole transcription.
        for kind in [{"speaking": True}, {"transcribing": True}]:
            a = app(percentage=0, **kind)
            a._tick_interaction_countdown()
            self.assertEqual(a.calls, ["idle on", ("end", "hold time over", False, True)], kind)
            self.assertEqual(a._last_interaction_paused_seconds, 0, kind)

    def test_06_speech_that_started_before_the_0_percent_still_pauses_the_end(self):
        for kind in [{"speaking": True}, {"transcribing": True}]:
            a = app(percentage=3, **kind)         # the hold time is over, the bar shows its last LEDs
            a._tick_interaction_countdown()
            self.assertEqual(a.calls, [], kind)    # nothing ends, nothing is muted in the middle of the sentence
            self.assertEqual(a._last_interaction_paused_seconds, 1, kind)
            self.assertEqual(a._last_processed_interaction_percentage, 3, kind)

    def test_07_nothing_to_clean_when_somebody_woke_pitxu_up_or_it_was_already_clean(self):
        a = app(percentage=0, seconds_since=2, button_only=True, muted=True)   # a new interaction is going on
        a._tick_interaction_countdown()
        self.assertEqual(a.calls, [])
        a = app(percentage=-1, button_only=True, muted=True)
        a._tick_interaction_countdown()
        self.assertEqual(a.calls, [])

    def test_08_inside_the_hold_time_it_counts_as_always(self):
        a = app(percentage=90, seconds_since=2)
        a._tick_interaction_countdown()
        self.assertEqual(a.calls[0][0], "show")
        self.assertGreater(a._last_processed_interaction_percentage, 0)


if __name__ == "__main__":
    unittest.main()
