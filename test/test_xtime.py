"""Xtime: the conversions that the app shares."""
import datetime as datetime_module
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


if __name__ == "__main__":
    unittest.main()
