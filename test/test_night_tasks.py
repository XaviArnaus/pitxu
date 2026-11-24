"""The night: one job for everything, at the configured time, with the memory consolidation inside."""
import datetime as datetime_module
import tempfile
import logging
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from support import *  # noqa: F401,F403


class FakeScheduler:
    def __init__(self, *args, **kwargs): self.jobs = []; self.started = False
    def add_listener(self, *args, **kwargs): pass
    def add_job(self, function, trigger, **kwargs): self.jobs.append({"name": function.__name__, "trigger": trigger, **kwargs})
    def start(self): self.started = True


class FakeEmojiStats:
    flushed = 0
    @classmethod
    def flush(cls): cls.flushed += 1


def _named(name):
    def job(*args, **kwargs): pass
    job.__name__ = name
    return job


class SchedulerTests(unittest.TestCase):

    def _jobs(self, **overrides):
        Holder = methods_of("pitxu/main.py", ["_initialize_schedulers"], {
            "BackgroundScheduler": FakeScheduler, "EVENT_JOB_EXECUTED": 1, "EVENT_JOB_ERROR": 2, "logging": logging,
            "datetime": datetime_module.datetime, "timedelta": datetime_module.timedelta, "EmojiStats": FakeEmojiStats})
        holder = Holder()
        holder._xconfig = cfg(tempfile.mkdtemp(), **overrides)
        holder._xparams = Dictionary({"execution_mode": "local_status"})
        holder._xlog = Log()
        holder._log_debug = lambda message: None
        holder.SCHEDULER_LIB_LOGLEVEL = holder.TZLOCAL_LIB_LOGLEVEL = logging.WARNING
        holder._input_stream = None
        for name in ("do_every_minute_tasks", "do_every_second_tasks", "do_at_night_tasks", "request_memory_consolidation",
                     "request_memory_consolidation_if_overdue"):
            setattr(holder, name, _named(name))
        holder._initialize_schedulers()
        return holder._scheduler.jobs

    def test_there_is_a_single_night_job_at_the_default_time(self):
        jobs = self._jobs()
        crons = [job for job in jobs if job["trigger"] == "cron"]
        self.assertEqual([(job["name"], job["hour"], job["minute"]) for job in crons], [("do_at_night_tasks", 3, 0)])
        self.assertFalse(any(job["name"] == "request_memory_consolidation" for job in jobs), "the consolidation has no job of its own")

    def test_the_time_of_the_night_job_is_configurable(self):
        crons = [job for job in self._jobs(**{"night_tasks.hour": 4, "night_tasks.minute": 45}) if job["trigger"] == "cron"]
        self.assertEqual([(job["hour"], job["minute"]) for job in crons], [(4, 45)])

    def test_the_catch_up_after_the_start_depends_on_the_config(self):
        names = lambda jobs: [job["name"] for job in jobs]
        self.assertIn("request_memory_consolidation_if_overdue", names(self._jobs()))
        self.assertNotIn("request_memory_consolidation_if_overdue", names(self._jobs(**{"memory.consolidation.startup_catchup": False})))
        self.assertNotIn("request_memory_consolidation_if_overdue", names(self._jobs(**{"memory.consolidation.enabled": False})))


class NightTasksTests(unittest.TestCase):

    def _run(self, rotate_fails=False, **overrides):
        Holder = methods_of("pitxu/main.py", ["do_at_night_tasks", "_safe_step"], {
            "EmojiStats": FakeEmojiStats, "full_stack": lambda: ""})
        holder = Holder()
        holder._xconfig = cfg(tempfile.mkdtemp(), **overrides)
        holder._xlog = Log()
        holder._log_debug = lambda message: None
        calls = []

        class Maintenance:
            @staticmethod
            def rotate_metrics_logs():
                calls.append("rotate")
                if rotate_fails:
                    raise RuntimeError("disk full")

        holder._maintenance = Maintenance()
        holder.request_memory_consolidation = lambda reason: calls.append(("consolidate", reason))

        class Support:
            @staticmethod
            def translate_lists(reason):
                calls.append(("translate lists", reason))

        holder._support = Support()

        class Lists:
            @staticmethod
            def cleanup(done_after_days, trash_after_days):
                calls.append(("lists cleanup", done_after_days, trash_after_days))

        holder._lists = Lists()
        FakeEmojiStats.flushed = 0
        holder.do_at_night_tasks()
        return holder, calls

    def test_it_does_everything(self):
        _, calls = self._run()
        self.assertEqual(calls, ["rotate", ("lists cleanup", 14, 30), ("translate lists", "night"), ("consolidate", "night")])
        self.assertEqual(FakeEmojiStats.flushed, 1)

    def test_the_consolidation_can_be_turned_off(self):
        _, calls = self._run(**{"memory.consolidation.enabled": False})
        self.assertEqual(calls, ["rotate", ("lists cleanup", 14, 30), ("translate lists", "night")])
        self.assertEqual(FakeEmojiStats.flushed, 1)

    def test_the_translation_of_the_lists_can_be_turned_off(self):
        _, calls = self._run(**{"lists.translation.enabled": False})
        self.assertEqual(calls, ["rotate", ("lists cleanup", 14, 30), ("consolidate", "night")])

    def test_the_cleanup_of_the_lists_can_be_turned_off_and_has_its_periods(self):
        _, calls = self._run(**{"lists.cleanup.enabled": False})
        self.assertNotIn(("lists cleanup", 14, 30), calls)
        _, calls = self._run(**{"lists.cleanup.done_after_days": 7, "lists.cleanup.trash_after_days": 60})
        self.assertIn(("lists cleanup", 7, 60), calls)

    def test_a_failing_task_does_not_skip_the_others(self):
        holder, calls = self._run(rotate_fails=True)
        self.assertEqual(calls, ["rotate", ("lists cleanup", 14, 30), ("translate lists", "night"), ("consolidate", "night")])
        self.assertEqual(FakeEmojiStats.flushed, 1)
        self.assertTrue(any("rotate metrics logs" in line and "disk full" in line for line in holder._xlog.lines))


if __name__ == "__main__":
    unittest.main()
