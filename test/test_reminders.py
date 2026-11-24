"""The reminder tools: the date and time are checked and normalized, the past is refused, and what is shown is localized."""
import datetime as datetime_module
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from support import *  # noqa: F401,F403
from pitxu.lib.utils.xtime import Xtime  # noqa: E402

PATH = "pitxu/lib/command/stateful/reminders.py"
METHODS = ["_message", "_validate_date_and_time", "_as_id", "_not_found", "_is_in_the_past", "create_reminder",
           "get_reminders_for_date", "delete_reminder", "get_reminder", "update_reminder", "move_reminder",
           "show_create_reminder", "show_get_reminders_for_date", "show_affected_reminder", "_show_changed_reminder",
           "show_deleted_reminder", "show_updated_reminder", "show_moved_reminder", "get_callback_by_given_function_name"]


class Obj:
    def __init__(self, **kw): self.__dict__.update(kw)


class FakeReminders:
    """ The store: what the tools ask for, kept in a dict by id. """
    FORMAT_DATE = "%Y-%m-%d"
    FORMAT_TIME = "%H:%M"

    def __init__(self): self.items = {}; self.asked = []; self.next_id = 1

    def _dict(self, i): return {"id": i, **self.items[i], "announced": False}

    def create_reminder(self, date, time, text):
        self.asked.append(("create", date, time))
        i, self.next_id = self.next_id, self.next_id + 1
        self.items[i] = {"date": date, "time": time, "text": text}
        return self._dict(i)

    def get_reminder(self, reminder_id):
        self.asked.append(("get", reminder_id))
        return self._dict(reminder_id) if reminder_id in self.items else False

    def get_reminders_for_date(self, date):
        self.asked.append(("list", date))
        return [self._dict(i) for i, r in self.items.items() if r["date"] == date]

    def delete_reminder(self, reminder_id):
        self.asked.append(("delete", reminder_id))
        reminder = self.get_reminder(reminder_id)
        self.items.pop(reminder_id, None)
        return reminder

    def update_reminder(self, reminder_id, text):
        self.asked.append(("update", reminder_id))
        if reminder_id not in self.items: return False
        self.items[reminder_id]["text"] = text
        return self._dict(reminder_id)

    def move_reminder(self, reminder_id, new_date, new_time):
        self.asked.append(("move", reminder_id, new_date, new_time))
        if reminder_id not in self.items: return False
        before = self.items[reminder_id]
        previous = {"previous_date": before["date"], "previous_time": before["time"]}
        before.update(date=new_date, time=new_time)
        return {**self._dict(reminder_id), **previous}


class Canvas:
    FONT_SIZE_BIG, FONT_SIZE_HUGE = 30, 60


class Interaction:
    def __init__(self): self.shown = []
    def get_canvas_from_foreground_display(self): return Canvas()
    def show_arbitrary_text_on_foreground_while_speaking(self, icon, text, font_size): self.shown.append((text, font_size))


def tool(language="en", **overrides):
    Holder = methods_of(PATH, METHODS, {
        "Xtime": Xtime, "Reminders": FakeReminders, "logging": None, "Interaction": object,
        "full_stack": lambda: ""})
    t = Holder()
    t._xlog = Log()
    t._xconfig = cfg(tempfile.mkdtemp(), **overrides)
    t._xparams = Dictionary({"language": language})
    t._reminders = FakeReminders()
    t.default_empty_callback = lambda *args, **kwargs: None
    return t


def tomorrow() -> str:
    return (datetime_module.datetime.now() + datetime_module.timedelta(days=1)).strftime("%Y-%m-%d")


def message(t, key, language="en"):
    return t._xconfig.get(f"language.reminders.{key}.{language}")


class ValidationTests(unittest.TestCase):

    def test_01_date_and_time_are_normalized_before_storing_and_the_id_is_given(self):
        t = tool()
        short = f"{tomorrow()[:4]}-{int(tomorrow()[5:7])}-{int(tomorrow()[8:])}"
        result = t.create_reminder(short, "9:05", "milk")
        self.assertEqual(t._reminders.asked[0], ("create", tomorrow(), "09:05"))
        self.assertEqual((result["id"], result["date"], result["time"], result["text"]), (1, tomorrow(), "09:05", "milk"))

    def test_02_invalid_date_or_time_gets_the_message_in_every_language(self):
        for language in ["en", "ca", "es", "de"]:
            t = tool(language)
            self.assertEqual(t.create_reminder("tomorrow", "09:00", "x"), message(t, "reminder_invalid_date", language))
            self.assertEqual(t.create_reminder(tomorrow(), "25:00", "x"), message(t, "reminder_invalid_time", language))
            self.assertEqual(t._reminders.asked, [])

    def test_03_the_past_is_refused(self):
        t = tool("ca")
        self.assertEqual(t.create_reminder("2020-01-01", "10:00", "old"), message(t, "reminder_past_datetime", "ca"))
        self.assertEqual(t._reminders.items, {})

    def test_04_the_current_minute_is_not_the_past(self):
        class FixedClock(Xtime):
            @staticmethod
            def now(): return datetime_module.datetime(2030, 5, 10, 14, 30, 45)
        Holder = methods_of(PATH, ["_is_in_the_past"], {"Xtime": FixedClock, "Reminders": FakeReminders})
        t = Holder()
        self.assertFalse(t._is_in_the_past("2030-05-10", "14:30"))
        self.assertFalse(t._is_in_the_past("2030-05-10", "14:31"))
        self.assertTrue(t._is_in_the_past("2030-05-10", "14:29"))
        self.assertTrue(t._is_in_the_past("2030-05-09", "23:59"))

    def test_05_several_reminders_can_share_the_minute_and_are_addressed_by_id(self):
        t = tool()
        first = t.create_reminder(tomorrow(), "09:05", "milk")
        second = t.create_reminder(tomorrow(), "09:05", "bread")
        self.assertNotEqual(first["id"], second["id"])
        self.assertEqual(t.get_reminders_for_date(tomorrow()),
                         [{"id": 1, "time": "09:05", "text": "milk"}, {"id": 2, "time": "09:05", "text": "bread"}])
        self.assertEqual(t.get_reminder(2)["text"], "bread")
        self.assertEqual(t.update_reminder(2, "rolls")["text"], "rolls")
        self.assertEqual(t.delete_reminder(1)["text"], "milk")
        self.assertEqual([r["id"] for r in t.get_reminders_for_date(tomorrow())], [2])

    def test_06_the_date_of_the_list_is_normalized_and_checked(self):
        t = tool()
        t.create_reminder(tomorrow(), "09:05", "milk")
        short = f"{tomorrow()[:4]}-{int(tomorrow()[5:7])}-{int(tomorrow()[8:])}"
        self.assertEqual(len(t.get_reminders_for_date(short)), 1)
        self.assertEqual(t.get_reminders_for_date("nope"), message(t, "reminder_invalid_date"))

    def test_07_an_unknown_or_invalid_id_says_so_with_the_id_in_every_language(self):
        for language in ["en", "ca", "es", "de"]:
            t = tool(language)
            for call in [t.get_reminder, t.delete_reminder]:
                self.assertEqual(call(99), message(t, "reminder_not_found", language) % 99)
                self.assertEqual(call("abc"), message(t, "reminder_not_found", language) % "abc")
            self.assertEqual(t.update_reminder(99, "x"), message(t, "reminder_not_found", language) % 99)
            self.assertEqual(t.move_reminder(99, tomorrow(), "10:00"), message(t, "reminder_not_found", language) % 99)

    def test_08_an_id_that_arrives_as_text_still_works(self):
        t = tool()
        t.create_reminder(tomorrow(), "09:05", "milk")
        self.assertEqual(t.get_reminder("1")["text"], "milk")
        self.assertEqual(t.get_reminder(1.0)["text"], "milk")

    def test_09_move_normalizes_refuses_the_past_and_tells_where_it_was(self):
        t = tool()
        t.create_reminder(tomorrow(), "09:05", "milk")
        self.assertEqual(t.move_reminder(1, "2020-01-01", "10:00"), message(t, "reminder_past_datetime"))
        self.assertEqual(t._reminders.items[1]["time"], "09:05")
        self.assertEqual(t.move_reminder(1, tomorrow(), "x"), message(t, "reminder_invalid_time"))
        moved = t.move_reminder(1, tomorrow(), "9:30")
        self.assertEqual((moved["time"], moved["previous_time"], moved["previous_date"]), ("09:30", "09:05", tomorrow()))

    def test_10_a_store_that_fails_gives_the_error_message(self):
        t = tool("de")
        class Broken:
            def __getattr__(self, name): raise RuntimeError("database is locked")
        t._reminders = Broken()
        self.assertEqual(t.create_reminder(tomorrow(), "09:00", "x"), message(t, "reminder_creation_error", "de"))
        self.assertEqual(t.get_reminders_for_date(tomorrow()), message(t, "reminder_retrieval_error", "de"))
        self.assertEqual(t.delete_reminder(1), message(t, "reminder_deletion_error", "de"))
        self.assertEqual(t.update_reminder(1, "x"), message(t, "reminder_update_error", "de"))
        self.assertEqual(t.move_reminder(1, tomorrow(), "10:00"), message(t, "reminder_move_error", "de"))


class DisplayTests(unittest.TestCase):

    def test_01_the_count_is_localized_and_handles_empty_one_many(self):
        for language, one, many in [("en", "1 reminder.", "3 reminders."), ("ca", "1 recordatori.", "3 recordatoris."),
                                    ("es", "1 recordatorio.", "3 recordatorios."), ("de", "1 Erinnerung.", "3 Erinnerungen.")]:
            t, interaction = tool(language), Interaction()
            t.show_get_reminders_for_date(Log(), interaction, [], {})
            t.show_get_reminders_for_date(Log(), interaction, [1], {})
            t.show_get_reminders_for_date(Log(), interaction, [1, 2, 3], {})
            self.assertEqual([text for text, _ in interaction.shown],
                             [message(t, "reminder_list_empty", language), one, many])

    def test_02_an_error_message_is_not_counted_as_reminders(self):
        t, interaction = tool(), Interaction()
        t.show_get_reminders_for_date(Log(), interaction, "Invalid date.", {})
        self.assertEqual(interaction.shown, [("Invalid date.", Canvas.FONT_SIZE_BIG)])

    def test_03_deleted_updated_moved_and_created_use_their_message(self):
        t, interaction = tool("es"), Interaction()
        reminder = {"id": 1, "date": "2030-01-02", "time": "10:00", "text": "nuevo"}
        t.show_create_reminder(Log(), interaction, reminder, {})
        t.show_deleted_reminder(Log(), interaction, reminder, {})
        t.show_updated_reminder(Log(), interaction, reminder, {})
        t.show_moved_reminder(Log(), interaction, {**reminder, "date": "2030-01-03", "time": "11:00",
                                                  "previous_date": "2030-01-02", "previous_time": "10:00"}, {})
        self.assertEqual([text for text, _ in interaction.shown], [
            message(t, "reminder_set", "es") % ("2030-01-02", "10:00", "nuevo"),
            message(t, "reminder_deleted", "es") % ("2030-01-02", "10:00"),
            message(t, "reminder_updated", "es") % ("2030-01-02", "10:00", "nuevo"),
            message(t, "reminder_moved", "es") % ("2030-01-02", "10:00", "2030-01-03", "11:00")])

    def test_04_a_message_instead_of_a_reminder_is_shown_as_it_is(self):
        t, interaction = tool(), Interaction()
        t.show_create_reminder(Log(), interaction, "Past.", {})
        t.show_deleted_reminder(Log(), interaction, "No reminder found.", {})
        t.show_moved_reminder(Log(), interaction, "No reminder found.", None)
        self.assertEqual([text for text, _ in interaction.shown], ["Past.", "No reminder found.", "No reminder found."])

    def test_05_every_tool_has_its_callback(self):
        t = tool()
        names = {n: t.get_callback_by_given_function_name(n).__name__ for n in
                 ["create_reminder", "get_reminders_for_date", "delete_reminder", "update_reminder", "move_reminder", "get_reminder"]}
        self.assertEqual(names["delete_reminder"], "show_deleted_reminder")
        self.assertEqual(names["update_reminder"], "show_updated_reminder")
        self.assertEqual(names["move_reminder"], "show_moved_reminder")
        self.assertEqual(names["get_reminder"], "show_affected_reminder")

    def test_06_the_new_keys_exist_in_every_language_in_both_config_files(self):
        for file in ["config/language.yaml.dist", "config/language.yaml"]:
            block = read_yaml(os.path.join(REPO, file))["language"]["reminders"]
            for key in ["reminder_count_one", "reminder_count_many", "reminder_list_empty", "reminder_past_datetime", "reminder_not_found"]:
                for lang in ["ca", "es", "en", "de"]:
                    self.assertTrue(block[key][lang], f"{file} {key} {lang}")
            self.assertNotIn("reminder_already_exists", block)


if __name__ == "__main__":
    unittest.main()
