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
    def get_busy_interaction_flags(self): return [name for name, up in self.busy.items() if up]
    def is_wake_up_button_wanted_exclusively(self): return self.wake_up_only
    def set_idle_mode_off(self): self.calls.append("idle off")
    def set_idle_mode_on(self): self.calls.append("idle on")
    def unmute_microphone(self, input_stream=None): self.calls.append("unmute")
    def wait_for_foreground_display_queue_to_empty(self): pass
    def wait_for_busy_foreground_display_to_idle(self): pass
    def get_canvas_from_foreground_display(self): return Obj(FONT_SIZE_BIG=30)

    def show_arbitrary_text_on_foreground_while_announcing(self, **kwargs): self.calls.append(("show", kwargs))
    def show_animation_while_announcing(self, animation): self.calls.append(("animation", animation))
    def wait_for_animation_display_queue_to_empty(self): pass
    def set_announcement_busy(self): self.calls.append("flag up")
    def unset_announcement_busy(self): self.calls.append("flag down")

    def say(self, text):
        self.calls.append(("say", text))
        if self.say_fails: raise RuntimeError("speaker broke")


class Obj:
    def __init__(self, **kw): self.__dict__.update(kw)


class FakeClock:
    """ A clock that only moves when somebody sleeps. """
    now = 0.0
    on_sleep = None
    @classmethod
    def monotonic(cls): return cls.now
    @classmethod
    def sleep(cls, seconds):
        cls.now += seconds
        if cls.on_sleep: cls.on_sleep(cls.now)


class FakeStore:
    def __init__(self, calls, due_list):
        self.calls, self.due_list = calls, due_list

    def get_due(self): return list(self.due_list)

    def build_announcement(self, due_list):
        return {"spoken": "SPOKEN", "screen": "SCREEN", "title": "TITLE", "count": len(due_list), "ids": [d["id"] for d in due_list]}

    def mark_announced(self, ids): self.calls.append(("mark", ids))


class FakeScheduler:
    def __init__(self): self.jobs = []
    def add_job(self, function): self.jobs.append(function)


def app(due_list, active=True, hold=0):
    Holder = methods_of("pitxu/main.py", ["announce_due_reminders", "_announce_reminders",
                                          "_check_waiting_reminders", "_safe_step", "_go_idle_now", "_announcement_layout",
                                          "_hold_announcement_on_screen"],
                        {"full_stack": lambda: "", "time": FakeClock, "datetime": datetime_module.datetime, "timedelta": datetime_module.timedelta})
    a = Holder()
    a.calls = []
    a._xlog = Log()
    a._log_debug = lambda *x, **k: None
    a._is_pitxu_active = active
    a._xconfig = Obj(get=lambda key, default=None: hold if key == "reminders.screen_hold_seconds" else default)
    a.animation_setting = "reminder"
    a._xconfig = Obj(get=lambda key, default=None: hold if key == "reminders.screen_hold_seconds"
                     else (a.animation_setting if key == "animations.reminder" else default))
    FakeClock.now, FakeClock.on_sleep = 0.0, None
    a._reminders_waiting = False
    a._reminders_announcing = threading.Lock()
    a._interaction = FakeInteraction(a.calls)
    a._reminders = FakeStore(a.calls, due_list)
    a._scheduler = FakeScheduler()
    a._end_listening_phase = lambda reason, **k: a.calls.append(("end listening", reason) if not (k.get("clear_bar") and reason == "reminder announcement") else ("end listening", reason, "clear bar"))
    a._start_listening_phase = lambda reason, **k: a.calls.append(("start listening", reason))
    a._wake_up = lambda reason, **k: a.calls.append(("wake up", reason))
    a._seconds_to_hold_interaction_answer = 15
    a._last_interaction_datetime = datetime_module.datetime.now()
    a._last_interaction_paused_seconds = 0
    a._input_stream = None
    a._record_announcement = lambda announcement: a.calls.append(("record", announcement["spoken"]))
    return a


ONE = [{"id": 1, "date": "2030-05-10", "time": "14:30", "text": "milk"}]
TWO = ONE + [{"id": 2, "date": "2030-05-10", "time": "14:30", "text": "bread"}]


def names(a): return [c if isinstance(c, str) else c[0] for c in a.calls]


class InteractionBusyTests(unittest.TestCase):

    def _interaction(self, **busy):
        Holder = methods_of("pitxu/lib/interaction/interaction.py", ["is_interaction_busy", "get_busy_interaction_flags"])
        muted = busy.pop("muted", False)
        flags = {"chatbot": False, "speaker": False, "transcriber": False, "vad": False, **busy}
        class Interaction(Holder):
            def is_microphone_muted(self): return muted
            def is_chatbot_busy(self): return flags["chatbot"]
            def is_speaker_busy(self): return flags["speaker"]
            def is_transcriber_busy(self): return flags["transcriber"]
            def is_vad_detected(self): return flags["vad"]
        return Interaction()

    def test_01_it_is_busy_when_any_of_the_four_is(self):
        self.assertFalse(self._interaction().is_interaction_busy())
        for who in ["chatbot", "speaker", "transcriber", "vad"]:
            self.assertTrue(self._interaction(**{who: True}).is_interaction_busy(), who)

    def test_01b_a_vad_left_up_with_the_microphone_muted_is_not_busy(self):
        self.assertTrue(self._interaction(vad=True, muted=False).is_interaction_busy())
        self.assertFalse(self._interaction(vad=True, muted=True).is_interaction_busy())
        self.assertEqual(self._interaction(vad=True, muted=True).get_busy_interaction_flags(), [])
        # The other flags count whatever the microphone does.
        self.assertTrue(self._interaction(chatbot=True, muted=True).is_interaction_busy())
        self.assertEqual(self._interaction(chatbot=True, speaker=True, vad=True).get_busy_interaction_flags(),
                         ["chatbot", "speaker", "vad"])

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
        self.assertEqual(names(a), ["idle off", "show", "animation", "flag up", "end listening", "say", "record", "mark", "flag down", "unmute", "idle on", "end listening"])
        self.assertEqual(a.calls[5], ("say", "SPOKEN"))
        self.assertEqual(a.calls[6], ("record", "SPOKEN"))
        self.assertEqual(a.calls[7], ("mark", [1]))
        self.assertFalse(a._reminders_waiting)

    def test_02_one_is_shown_big_and_several_as_a_list_from_the_top_left(self):
        single = app(ONE); single.announce_due_reminders()
        several = app(TWO); several.announce_due_reminders()
        self.assertEqual(single.calls[1][1], {"icon": "📝", "text": "SCREEN", "font_size": 30, })
        self.assertEqual(several.calls[1][1], {"icon": "📝", "header": "TITLE", "font_header_size": 30, "text": "SCREEN", "align": "left", "valign": "top", })
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
        self.assertEqual(names(a), ["idle off", "show", "animation", "flag up", "end listening", "say", "record", "mark", "flag down", "unmute", "idle on", "end listening"])
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
        self.assertNotIn("record", names(a))  # it was not said: it is not remembered as said
        self.assertEqual(names(a)[-2:], ["idle on", "end listening"])
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

    def test_10_after_the_announcement_it_goes_idle_whatever_the_wake_up_method(self):
        for button_only in [False, True]:
            a = app(ONE)
            a._interaction.wake_up_only = button_only
            a.announce_due_reminders()
            self.assertEqual(names(a)[-2:], ["idle on", "end listening"])
            self.assertEqual(a.calls[-1], ("end listening", "reminders announced"))
            self.assertNotIn("start listening", names(a))
            self.assertNotIn("wake up", names(a))
            self.assertEqual("unmute" in names(a), not button_only)  # the trigger words are heard, unless only the button is wanted
            expired = (datetime_module.datetime.now() - a._last_interaction_datetime).total_seconds()
            self.assertGreater(expired, 15)  # the hold time is over: the next text needs the trigger words

    def test_10a_the_reminders_stay_on_screen_until_the_hold_is_over_and_then_the_flag_goes_down(self):
        a = app(TWO, hold=5)
        a.announce_due_reminders()
        self.assertEqual(names(a), ["idle off", "show", "animation", "flag up", "end listening", "say", "record", "mark",
                                    "flag down", "unmute", "idle on", "end listening"])
        self.assertGreaterEqual(FakeClock.now, 5)  # it waited, with the flag up

    def test_10a2_the_flag_is_up_while_it_waits(self):
        a = app(ONE, hold=5)
        seen = []
        FakeClock.on_sleep = lambda now: seen.append(names(a)[-1])
        a.announce_due_reminders()
        self.assertTrue(seen and all(last == "mark" for last in seen), seen)  # nothing came after the mark: the flag was still up

    def test_10d_the_layout_of_a_single_reminder_is_big(self):
        a = app(ONE)
        a.announce_due_reminders()
        shown = [c[1] for c in a.calls if isinstance(c, tuple) and c[0] == "show"][0]
        self.assertEqual(shown["font_size"], 30)
        self.assertNotIn("header", shown)

    def test_10e_whoever_wakes_pitxu_up_meanwhile_keeps_the_screen(self):
        a = app(ONE, hold=5)
        FakeClock.on_sleep = lambda now: setattr(a, "_last_interaction_datetime", datetime_module.datetime.now() + datetime_module.timedelta(seconds=1)) if now >= 1 else None
        a.announce_due_reminders()
        self.assertNotIn("idle on", names(a))
        self.assertIn(("mark", [1]), a.calls)
        self.assertLess(FakeClock.now, 5)  # it did not wait for the rest
        self.assertEqual(names(a).count("flag down"), 1)  # the screen is released at once, the new interaction draws its own

    def test_10f_a_busy_pitxu_or_a_closing_one_does_not_go_idle(self):
        a = app(ONE, hold=5)
        FakeClock.on_sleep = lambda now: a._interaction.busy.update(chatbot=True)
        a.announce_due_reminders()
        self.assertNotIn("idle on", names(a))
        self.assertIn("flag down", names(a))
        a = app(ONE, hold=5)
        FakeClock.on_sleep = lambda now: setattr(a, "_is_pitxu_active", False)
        a.announce_due_reminders()
        self.assertNotIn("idle on", names(a))
        self.assertIn("flag down", names(a))

    def test_10g_a_failed_speech_is_not_held_but_the_flag_goes_down(self):
        a = app(ONE, hold=5)
        a._interaction.say_fails = True
        a.announce_due_reminders()
        self.assertEqual(FakeClock.now, 0.0)  # no waiting
        self.assertEqual(names(a).count("flag down"), 1)
        self.assertLess(names(a).index("flag up"), names(a).index("flag down"))
        self.assertEqual(names(a)[-2:], ["idle on", "end listening"])

    def test_10g2_a_failure_before_the_flag_goes_up_does_not_lower_it(self):
        a = app(ONE)
        a._interaction.show_arbitrary_text_on_foreground_while_announcing = lambda **k: (_ for _ in ()).throw(RuntimeError("display broke"))
        a.announce_due_reminders()
        self.assertNotIn("flag up", names(a))
        self.assertNotIn("flag down", names(a))
        self.assertIn(("mark", [1]), a.calls)
        self.assertTrue(any("Error announcing the reminders" in line for line in a._xlog.lines))

    def test_10g3_the_paints_are_registered_before_the_flag_goes_up_with_the_animation(self):
        a = app(ONE)
        a.announce_due_reminders()
        self.assertLess(names(a).index("show"), names(a).index("flag up"))
        self.assertIn(("animation", "reminder"), a.calls)
        self.assertLess(names(a).index("animation"), names(a).index("flag up"))
        a = app(ONE)
        a.animation_setting = ""
        a.announce_due_reminders()
        self.assertNotIn("animation", names(a))  # none configured: only the text
        self.assertIn("flag up", names(a))

    def test_10h_the_setting_is_in_both_config_files_and_validated(self):
        for file in ["config/main.yaml.dist", "config/main.yaml"]:
            self.assertEqual(read_yaml(os.path.join(REPO, file))["reminders"]["screen_hold_seconds"], 5, file)
        source = read_file(os.path.join(REPO, "pitxu/lib/utils/memory_config_validator.py"))
        self.assertIn('"reminders.screen_hold_seconds"', source)

    def test_10i_the_countdown_is_cleared_before_the_announcement(self):
        a = app(ONE)
        a.announce_due_reminders()
        self.assertIn(("end listening", "reminder announcement", "clear bar"), a.calls)

    def test_10j_the_waiting_log_tells_the_busy_flags(self):
        a = app(ONE)
        a._interaction.busy["vad"] = True
        a.announce_due_reminders()
        self.assertTrue(any("busy: vad" in line for line in a._xlog.lines))

    def test_10b_a_list_has_a_title_and_a_single_reminder_does_not(self):
        a = app(TWO)
        a.announce_due_reminders()
        shown = [c[1] for c in a.calls if isinstance(c, tuple) and c[0] == "show"][0]
        self.assertEqual((shown["header"], shown["text"], shown["icon"]), ("TITLE", "SCREEN", "📝"))
        a = app(ONE)
        a.announce_due_reminders()
        shown = [c[1] for c in a.calls if isinstance(c, tuple) and c[0] == "show"][0]
        self.assertNotIn("header", shown)

    def test_10c_the_title_is_in_every_language(self):
        for language in ["en", "ca", "es", "de"]:
            r = reminders(language)
            self.addCleanup(r.close)
            for items in ([due("2030-05-10", "14:30", "x")], [due("2030-05-10", "14:30", "x", 1), due("2030-05-10", "14:30", "y", 2)]):
                self.assertTrue(r.build_announcement(items, now=NOW)["title"], language)

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
