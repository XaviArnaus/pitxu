"""Xtime: the conversions that the app shares."""
import datetime as datetime_module
import logging
import types
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from support import *  # noqa: F401,F403
from pitxu.lib.utils.xtime import Xtime  # noqa: E402

D = datetime_module.datetime


class XtimeTests(unittest.TestCase):

    def test_01_datetime_to_str_uses_the_format_or_the_default(self):
        moment = D(2030, 5, 10, 14, 30, 45)
        self.assertEqual(Xtime.datetime_to_str(moment), "2030-05-10 14:30:45")
        self.assertEqual(Xtime.datetime_to_str(moment, "%Y-%m-%d %H:%M"), "2030-05-10 14:30")
        self.assertEqual(Xtime.datetime_to_str(moment, "%H:%M"), "14:30")

    def test_02_it_is_the_counterpart_of_str_to_datetime(self):
        moment = D(2030, 5, 10, 14, 30, 45)
        self.assertEqual(Xtime.str_to_datetime(Xtime.datetime_to_str(moment)), moment)
        self.assertEqual(Xtime.datetime_to_str(Xtime.str_to_datetime("2030-1-5", "%Y-%m-%d"), "%Y-%m-%d"), "2030-01-05")

    def test_03_add_time_moves_forward_and_back(self):
        moment = D(2030, 5, 10, 14, 30, 45)
        self.assertEqual(Xtime.add_time(moment, days=1), D(2030, 5, 11, 14, 30, 45))
        self.assertEqual(Xtime.add_time(moment, days=-7), D(2030, 5, 3, 14, 30, 45))
        self.assertEqual(Xtime.add_time(moment, hours=10, minutes=-30, seconds=15), D(2030, 5, 11, 0, 1, 0))
        self.assertEqual(Xtime.add_time(moment), moment)

    def test_04_seconds_between_is_negative_when_the_end_is_before(self):
        a, b = D(2030, 5, 10, 14, 30, 0), D(2030, 5, 10, 14, 32, 30)
        self.assertEqual(Xtime.seconds_between(a, b), 150.0)
        self.assertEqual(Xtime.seconds_between(b, a), -150.0)
        self.assertEqual(Xtime.seconds_between(a, D(2030, 5, 11, 14, 30, 0)), 86400.0)

    def test_05_the_reminders_do_not_use_datetime_directly_anymore(self):
        for path in ["pitxu/lib/utils/reminders.py", "pitxu/lib/command/stateful/reminders.py"]:
            source = read_file(os.path.join(REPO, path))
            for call in ["datetime.now(", "datetime.strptime(", ".strftime(", "timedelta("]:
                self.assertNotIn(call, source, f"{path} {call}")

    def test_06_weekday_name_is_english_and_independent_of_the_locale(self):
        self.assertEqual(Xtime.weekday_name(D(2026, 11, 23)), "Monday")
        self.assertEqual(Xtime.weekday_name(D(2026, 11, 22)), "Sunday")
        self.assertEqual([Xtime.weekday_name(D(2026, 11, 23 + i)) for i in range(7)], list(Xtime.WEEKDAYS))
        self.assertIn(Xtime.weekday_name(), Xtime.WEEKDAYS)


class SystemDateTests(unittest.TestCase):

    def _tool(self):
        return methods_of("pitxu/lib/command/system/date.py", ["get_local_system_date", "callback_show_date"], {
            "Xtime": Xtime, "full_stack": lambda: "", "logging": logging, "Interaction": object})

    def _instance(self):
        holder = self._tool()
        instance = holder()
        instance.format, instance.displayed_format = "%Y-%m-%d", "%d.%m.%Y"
        instance.status_shortcuts = None
        instance._xlog = logging.getLogger("test")
        return instance

    def test_01_the_date_comes_with_the_day_of_the_week(self):
        value = self._instance().get_local_system_date()
        self.assertRegex(value, r"^\d{4}-\d{2}-\d{2} \((Monday|Tuesday|Wednesday|Thursday|Friday|Saturday|Sunday)\)$")
        self.assertEqual(value, f"{Xtime.current_time_str('%Y-%m-%d')} ({Xtime.weekday_name()})")

    def test_02_the_callback_shows_only_the_date(self):
        shown = []

        class FakeInteraction:
            def show_arbitrary_text_on_foreground_while_speaking(self, icon, text, font_size):
                shown.append(text)

            def get_canvas_from_foreground_display(self):
                return types.SimpleNamespace(FONT_SIZE_BIG=1)

        instance = self._instance()
        instance.callback_show_date(logging.getLogger("test"), FakeInteraction(), "2026-11-23 (Monday)")
        instance.callback_show_date(logging.getLogger("test"), FakeInteraction(), "2026-11-23")
        self.assertEqual(shown, ["23.11.2026", "23.11.2026"])

    def test_03_the_prompts_tell_to_use_the_given_weekday(self):
        for path in ["config/chatbot.yaml.dist"]:
            source = read_file(os.path.join(REPO, path))
            self.assertEqual(source.count("(Monday)"), 4, path)


class TranscriberProcessParamsTests(unittest.TestCase):

    def test_01_the_audio_parameters_are_sent_to_the_transcriber_process(self):
        """ The Preprocessor inside the process reads the filters and samplerates from them: they logged None. """
        source = read_file(os.path.join(REPO, "pitxu/lib/speech_to_text/faster_whisper_stream.py"))
        start = source.index("new_and_start(QUEUE_TRANSCRIBER, FasterWhisperStreamProcess")
        block = source[start:source.index("}))", start)]
        self.assertIn('"audio_parameters": self._xparams.get("audio_parameters")', block)
        # ...and the process hands them to the Preprocessor under the same key.
        process = read_file(os.path.join(REPO, "pitxu/lib/speech_to_text/faster_whisper_stream_process.py"))
        self.assertIn('"audio_parameters": self._xparams.get("audio_parameters")', process)


if __name__ == "__main__":
    unittest.main()
