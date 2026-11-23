"""The announcement of the reminders: the words (one, late, very old, several) and when it happens (not while busy)."""
import datetime as datetime_module
import os
import sys
import tempfile
import threading
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from support import *  # noqa: F401,F403
from pitxu.lib.utils.reminders import Reminders  # noqa: E402

D = datetime_module.datetime
NOW = D(2030, 5, 10, 14, 30, 45)


def reminders(language="en", **overrides) -> Reminders:
    tmp = tempfile.mkdtemp()
    config = cfg(tmp, **overrides)
    database = DbSqlite(config=config, params=params())
    database.migrate_db()
    database.close()
    return Reminders(config=config, params=params(language=language))


def due(date, time, text, i=1):
    return {"id": i, "date": date, "time": time, "text": text, "announced": False}


class WordsTests(unittest.TestCase):

    def setUp(self):
        self.r = reminders()
        self.addCleanup(self.r.close)

    def test_01_one_on_time_is_the_text_as_it_is(self):
        a = self.r.build_announcement([due("2030-05-10", "14:30", "milk")], now=NOW)
        self.assertEqual((a["spoken"], a["screen"], a["count"], a["ids"]), ("Reminder: milk.", "milk", 1, [1]))

    def test_02_a_late_one_says_when_it_was_for(self):
        a = self.r.build_announcement([due("2030-05-10", "14:20", "milk")], now=NOW)
        self.assertEqual((a["spoken"], a["screen"]), ("Reminder: At 14:20, milk.", "At 14:20, milk"))

    def test_03_late_is_more_than_the_configured_minutes(self):
        on_time = self.r.build_announcement([due("2030-05-10", "14:29", "milk")], now=NOW)
        late = self.r.build_announcement([due("2030-05-10", "14:28", "milk")], now=NOW)
        self.assertEqual(on_time["screen"], "milk")
        self.assertEqual(late["screen"], "At 14:28, milk")
        patient = reminders(**{"reminders.late_after_minutes": 60})
        self.addCleanup(patient.close)
        self.assertEqual(patient.build_announcement([due("2030-05-10", "14:20", "milk")], now=NOW)["screen"], "milk")

    def test_04_from_another_day_it_says_the_date_too(self):
        a = self.r.build_announcement([due("2030-05-09", "23:00", "milk")], now=NOW)
        self.assertEqual(a["screen"], "On 2030-05-09 at 23:00, milk")
        self.assertNotIn("very old", a["spoken"])

    def test_05_a_very_old_one_warns_that_it_could_not_be_announced_back_then(self):
        a = self.r.build_announcement([due("2030-05-01", "10:00", "milk")], now=NOW)
        self.assertEqual(a["spoken"], "Reminder: On 2030-05-01 at 10:00, milk. This reminder is very old and could not be announced back then.")
        self.assertEqual(a["screen"], "On 2030-05-01 at 10:00, milk")

    def test_06_very_old_is_after_the_configured_hours(self):
        strict = reminders(**{"reminders.very_old_after_hours": 1})
        self.addCleanup(strict.close)
        self.assertIn("very old", strict.build_announcement([due("2030-05-10", "12:00", "milk")], now=NOW)["spoken"])

    def test_07_several_are_one_list(self):
        a = self.r.build_announcement([due("2030-05-10", "14:30", "milk", 1), due("2030-05-10", "14:30", "bread", 2),
                                       due("2030-05-10", "14:00", "oven", 3)], now=NOW)
        self.assertEqual(a["count"], 3)
        self.assertEqual(a["ids"], [1, 2, 3])
        self.assertEqual(a["spoken"], "You have 3 reminders: milk. bread. At 14:00, oven.")
        self.assertEqual(a["screen"], "• milk\n• bread\n• At 14:00, oven")

    def test_08_a_very_old_one_in_a_list_has_its_own_warning(self):
        a = self.r.build_announcement([due("2030-05-10", "14:30", "milk", 1), due("2030-05-01", "10:00", "old", 2)], now=NOW)
        self.assertEqual(a["spoken"].count("very old"), 1)
        self.assertTrue(a["spoken"].startswith("You have 2 reminders: milk. On 2030-05-01 at 10:00, old."))

    def test_09_a_text_that_is_a_sentence_already_is_not_doubled(self):
        self.assertEqual(self.r.build_announcement([due("2030-05-10", "14:30", "Did you lock the door?")], now=NOW)["spoken"],
                         "Reminder: Did you lock the door?")

    def test_10_every_language_has_every_form(self):
        for language in ["en", "ca", "es", "de"]:
            r = reminders(language)
            self.addCleanup(r.close)
            for items in ([due("2030-05-10", "14:30", "x")], [due("2030-05-10", "14:20", "x")], [due("2030-05-09", "23:00", "x")],
                          [due("2030-05-01", "10:00", "x")], [due("2030-05-10", "14:30", "x", 1), due("2030-05-10", "14:30", "y", 2)]):
                a = r.build_announcement(items, now=NOW)
                self.assertTrue(a["spoken"] and a["screen"], language)
                self.assertNotIn("%", a["spoken"] + a["screen"], language)
        self.assertIn("molt antic", reminders("ca").build_announcement([due("2030-05-01", "10:00", "x")], now=NOW)["spoken"])


class FakeInteraction:
    def __init__(self, calls):
        self.calls = calls
        self.busy = {"chatbot": False, "speaker": False, "transcriber": False, "vad": False}
        self.wake_up_only = False
        self.say_fails = False

    def is_interaction_busy(self): return any(self.busy.values())
    def is_wake_up_button_wanted_exclusively(self): return self.wake_up_only
    def set_idle_mode_off(self): self.calls.append("idle off")
    def wait_for_foreground_display_queue_to_empty(self): pass
    def wait_for_busy_foreground_display_to_idle(self): pass
    def get_canvas_from_foreground_display(self): return Obj(FONT_SIZE_BIG=30)

    def show_arbitrary_text_on_foreground_while_speaking(self, **kwargs): self.calls.append(("show", kwargs))

    def say(self, text):
        self.calls.append(("say", text))
        if self.say_fails: raise RuntimeError("speaker broke")


class Obj:
    def __init__(self, **kw): self.__dict__.update(kw)


class FakeStore:
    def __init__(self, calls, due_list):
        self.calls, self.due_list = calls, due_list

    def get_due(self): return list(self.due_list)

    def build_announcement(self, due_list):
        return {"spoken": "SPOKEN", "screen": "SCREEN", "count": len(due_list), "ids": [d["id"] for d in due_list]}

    def mark_announced(self, ids): self.calls.append(("mark", ids))


class FakeScheduler:
    def __init__(self): self.jobs = []
    def add_job(self, function): self.jobs.append(function)


def app(due_list, active=True):
    Holder = methods_of("pitxu/main.py", ["announce_due_reminders", "_announce_reminders",
                                          "_check_waiting_reminders", "_safe_step"],
                        {"full_stack": lambda: ""})
    a = Holder()
    a.calls = []
    a._xlog = Log()
    a._log_debug = lambda *x, **k: None
    a._is_pitxu_active = active
    a._reminders_waiting = False
    a._reminders_announcing = threading.Lock()
    a._interaction = FakeInteraction(a.calls)
    a._reminders = FakeStore(a.calls, due_list)
    a._scheduler = FakeScheduler()
    a._end_listening_phase = lambda reason, **k: a.calls.append(("end listening", reason))
    a._start_listening_phase = lambda reason, **k: a.calls.append(("start listening", reason))
    a._wake_up = lambda reason, **k: a.calls.append(("wake up", reason))
    return a


ONE = [{"id": 1, "date": "2030-05-10", "time": "14:30", "text": "milk"}]
TWO = ONE + [{"id": 2, "date": "2030-05-10", "time": "14:30", "text": "bread"}]


def names(a): return [c if isinstance(c, str) else c[0] for c in a.calls]


class InteractionBusyTests(unittest.TestCase):

    def _interaction(self, **busy):
        Holder = methods_of("pitxu/lib/interaction/interaction.py", ["is_interaction_busy"])
        flags = {"chatbot": False, "speaker": False, "transcriber": False, "vad": False, **busy}
        class Interaction(Holder):
            def is_chatbot_busy(self): return flags["chatbot"]
            def is_speaker_busy(self): return flags["speaker"]
            def is_transcriber_busy(self): return flags["transcriber"]
            def is_vad_detected(self): return flags["vad"]
        return Interaction()

    def test_01_it_is_busy_when_any_of_the_four_is(self):
        self.assertFalse(self._interaction().is_interaction_busy())
        for who in ["chatbot", "speaker", "transcriber", "vad"]:
            self.assertTrue(self._interaction(**{who: True}).is_interaction_busy(), who)

    def test_02_the_memory_consolidation_waits_for_it_and_for_the_hold_time(self):
        Holder = methods_of("pitxu/main.py", ["_is_idle_for_memory_consolidation", "get_seconds_since_last_interaction"],
                            {"datetime": datetime_module.datetime})
        app_ = Holder()
        app_._seconds_to_hold_interaction_answer = 15
        app_._last_interaction_paused_seconds = 0
        app_._last_interaction_datetime = None
        app_._interaction = Obj(is_interaction_busy=lambda: False)
        self.assertTrue(app_._is_idle_for_memory_consolidation())
        app_._interaction = Obj(is_interaction_busy=lambda: True)
        self.assertFalse(app_._is_idle_for_memory_consolidation())
        app_._interaction = Obj(is_interaction_busy=lambda: False)
        app_._last_interaction_datetime = datetime_module.datetime.now()  # inside the hold time
        self.assertFalse(app_._is_idle_for_memory_consolidation())
        app_._last_interaction_datetime = datetime_module.datetime.now() - datetime_module.timedelta(seconds=60)
        self.assertTrue(app_._is_idle_for_memory_consolidation())


class WhenTests(unittest.TestCase):

    def test_01_when_idle_it_shows_says_marks_after_saying_and_hands_the_turn_back(self):
        a = app(ONE)
        a.announce_due_reminders()
        self.assertEqual(names(a), ["idle off", "show", "end listening", "say", "mark", "start listening"])
        self.assertEqual(a.calls[3], ("say", "SPOKEN"))
        self.assertEqual(a.calls[4], ("mark", [1]))
        self.assertFalse(a._reminders_waiting)

    def test_02_one_is_shown_big_and_several_as_a_list_from_the_top_left(self):
        single = app(ONE); single.announce_due_reminders()
        several = app(TWO); several.announce_due_reminders()
        self.assertEqual(single.calls[1][1], {"icon": "📝", "text": "SCREEN", "font_size": 30})
        self.assertEqual(several.calls[1][1], {"icon": "📝", "text": "SCREEN", "align": "left", "valign": "top"})
        self.assertEqual([c for c in several.calls if c[0] == "mark"], [("mark", [1, 2])])
        self.assertEqual(len([c for c in several.calls if c[0] == "say"]), 1)

    def test_03_when_busy_it_waits_and_announces_nothing(self):
        for who in ["chatbot", "speaker", "transcriber", "vad"]:
            a = app(ONE)
            a._interaction.busy[who] = True
            a.announce_due_reminders()
            self.assertEqual(a.calls, [], who)
            self.assertTrue(a._reminders_waiting, who)

    def test_04_the_tick_announces_what_waited_as_soon_as_it_is_idle(self):
        a = app(ONE)
        a._interaction.busy["speaker"] = True
        a.announce_due_reminders()
        a._check_waiting_reminders()
        self.assertEqual(a._scheduler.jobs, [])  # still busy
        a._interaction.busy["speaker"] = False
        a._check_waiting_reminders()
        self.assertEqual(len(a._scheduler.jobs), 1)
        a._scheduler.jobs[0]()  # what the scheduler would run
        self.assertEqual(names(a), ["idle off", "show", "end listening", "say", "mark", "start listening"])
        a._check_waiting_reminders()
        self.assertEqual(len(a._scheduler.jobs), 1)  # nothing waits anymore

    def test_05_the_tick_does_nothing_if_nothing_waits_or_there_is_no_scheduler(self):
        a = app(ONE)
        a._check_waiting_reminders()
        self.assertEqual(a._scheduler.jobs, [])
        a._reminders_waiting = True
        a._scheduler = None
        a._check_waiting_reminders()  # does not raise

    def test_06_nothing_due_resets_the_waiting_and_does_nothing(self):
        a = app([])
        a._reminders_waiting = True
        a.announce_due_reminders()
        self.assertEqual(a.calls, [])
        self.assertFalse(a._reminders_waiting)

    def test_07_a_failing_speech_is_logged_and_the_reminders_are_still_marked(self):
        a = app(ONE)
        a._interaction.say_fails = True
        a.announce_due_reminders()
        self.assertIn(("mark", [1]), a.calls)
        self.assertEqual(names(a)[-1], "start listening")
        self.assertTrue(any("Error announcing the reminders" in line for line in a._xlog.lines))
        self.assertTrue(a._reminders_announcing.acquire(blocking=False))  # the lock was released

    def test_08_only_one_announcement_at_a_time(self):
        a = app(ONE)
        a._reminders_announcing.acquire()
        a.announce_due_reminders()
        self.assertEqual(a.calls, [])

    def test_09_a_closing_application_announces_nothing(self):
        a = app(ONE, active=False)
        a.announce_due_reminders()
        self.assertEqual(a.calls, [])

    def test_10_with_only_the_wake_up_button_the_microphone_stays_muted(self):
        a = app(ONE)
        a._interaction.wake_up_only = True
        a.announce_due_reminders()
        self.assertEqual(names(a)[-1], "wake up")
        self.assertNotIn("start listening", names(a))

    def test_11_the_ticks_call_it(self):
        source = read_file(os.path.join(REPO, "pitxu/main.py"))
        self.assertIn("            self.announce_due_reminders()", source)
        self.assertIn("            self._check_waiting_reminders()", source)

    def test_12_the_new_settings_and_messages_are_in_both_config_files(self):
        for file in ["config/main.yaml.dist", "config/main.yaml"]:
            block = read_yaml(os.path.join(REPO, file))["reminders"]
            self.assertEqual((block["late_after_minutes"], block["very_old_after_hours"]), (2, 24))
        for file in ["config/language.yaml.dist", "config/language.yaml"]:
            block = read_yaml(os.path.join(REPO, file))["language"]["reminders"]
            for key in ["reminder_announcement_multiple", "reminder_item_late_today", "reminder_item_late_other_day", "reminder_very_old_warning"]:
                for lang in ["ca", "es", "en", "de"]:
                    self.assertTrue(block[key][lang], f"{file} {key} {lang}")


if __name__ == "__main__":
    unittest.main()
