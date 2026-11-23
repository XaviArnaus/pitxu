"""The reminder tools: the date and time are checked and normalized, the past is refused, and what is shown is localized."""
import datetime as datetime_module
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from support import *  # noqa: F401,F403

PATH = "pitxu/lib/command/stateful/reminders.py"
METHODS = ["_message", "_validate_date_and_time", "_is_in_the_past", "create_reminder", "get_reminders_for_date",
           "delete_reminder", "get_reminder", "update_reminder", "move_reminder",
           "show_create_reminder", "show_get_reminders_for_date", "show_affected_reminder", "_show_changed_reminder",
           "show_deleted_reminder", "show_updated_reminder", "show_moved_reminder", "get_callback_by_given_function_name"]


class Obj:
    def __init__(self, **kw): self.__dict__.update(kw)


class FakeReminders:
    """ The store: what the tools ask for, kept in a dict. """
    FORMAT_DATE = "%Y-%m-%d"
    FORMAT_TIME = "%H:%M"

    def __init__(self): self.items = {}; self.asked = []

    def create_reminder(self, date, time, text):
        self.asked.append(("create", date, time))
        if (date, time) in self.items: return False
        self.items[(date, time)] = text
        return True

    def get_reminder(self, date, time):
        self.asked.append(("get", date, time))
        return {"date": date, "time": time, "text": self.items[(date, time)]} if (date, time) in self.items else False

    def get_reminders_for_date(self, date):
        self.asked.append(("list", date))
        return [{"time": t, "text": x} for (d, t), x in self.items.items() if d == date]

    def delete_reminder(self, date, time):
        self.asked.append(("delete", date, time))
        return self.items.pop((date, time), None) is not None

    def update_reminder(self, date, time, text):
        self.asked.append(("update", date, time))
        if (date, time) not in self.items: return False
        self.items[(date, time)] = text
        return {"date": date, "time": time, "text": text}

    def move_reminder(self, old_date, old_time, new_date, new_time):
        self.asked.append(("move", old_date, old_time, new_date, new_time))
        if (old_date, old_time) not in self.items: return False
        text = self.items.pop((old_date, old_time))
        self.items[(new_date, new_time)] = text
        return {"date": new_date, "time": new_time, "text": text}


class Canvas:
    FONT_SIZE_BIG, FONT_SIZE_HUGE = 30, 60


class Interaction:
    def __init__(self): self.shown = []
    def get_canvas_from_foreground_display(self): return Canvas()
    def show_arbitrary_text_on_foreground_while_speaking(self, icon, text, font_size): self.shown.append((text, font_size))


def tool(language="en", **overrides):
    Holder = methods_of(PATH, METHODS, {
        "datetime": datetime_module.datetime, "Reminders": FakeReminders, "logging": None, "Interaction": object,
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

    def test_01_date_and_time_are_normalized_before_storing(self):
        t = tool()
        result = t.create_reminder(tomorrow()[:5] + str(int(tomorrow()[5:7])) + "-" + str(int(tomorrow()[8:])), "9:05", "milk")
        self.assertEqual(t._reminders.asked[0], ("create", tomorrow(), "09:05"))
        self.assertIn("09:05", result)
        self.assertEqual(t._reminders.items, {(tomorrow(), "09:05"): "milk"})

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
        class Fixed(datetime_module.datetime):
            @classmethod
            def now(cls, tz=None): return cls(2030, 5, 10, 14, 30, 45)
        Holder = methods_of(PATH, ["_is_in_the_past"], {"datetime": Fixed, "Reminders": FakeReminders})
        t = Holder()
        self.assertFalse(t._is_in_the_past("2030-05-10", "14:30"))
        self.assertFalse(t._is_in_the_past("2030-05-10", "14:31"))
        self.assertTrue(t._is_in_the_past("2030-05-10", "14:29"))
        self.assertTrue(t._is_in_the_past("2030-05-09", "23:59"))

    def test_05_every_other_tool_normalizes_too_and_reports_invalid_input(self):
        t = tool()
        t._reminders.items[(tomorrow(), "09:05")] = "milk"
        short = f"{tomorrow()[:4]}-{int(tomorrow()[5:7])}-{int(tomorrow()[8:])}"
        self.assertEqual(t.get_reminder(short, "9:05")["text"], "milk")
        self.assertEqual(t.get_reminders_for_date(short), [{"time": "09:05", "text": "milk"}])
        self.assertEqual(t.update_reminder(short, "9:05", "bread")["text"], "bread")
        self.assertEqual(t.delete_reminder(short, "9:05")["text"], "bread")
        self.assertEqual(t.get_reminder("nope", "09:00"), message(t, "reminder_invalid_date"))
        self.assertEqual(t.get_reminders_for_date("nope"), message(t, "reminder_invalid_date"))
        self.assertEqual(t.delete_reminder(tomorrow(), "99:00"), message(t, "reminder_invalid_time"))

    def test_06_move_normalizes_both_ends_and_refuses_the_past(self):
        t = tool()
        t._reminders.items[(tomorrow(), "09:05")] = "milk"
        self.assertEqual(t.move_reminder(tomorrow(), "9:05", "2020-01-01", "10:00"), message(t, "reminder_past_datetime"))
        self.assertIn((tomorrow(), "09:05"), t._reminders.items)
        moved = t.move_reminder(tomorrow(), "9:05", tomorrow(), "10:30")
        self.assertEqual(moved, {"date": tomorrow(), "time": "10:30", "text": "milk"})
        self.assertEqual(t.move_reminder(tomorrow(), "x", tomorrow(), "10:30"), message(t, "reminder_invalid_time"))


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

    def test_03_deleted_updated_and_moved_use_their_message(self):
        t, interaction = tool("es"), Interaction()
        t.show_deleted_reminder(Log(), interaction, {"date": "2030-01-02", "time": "10:00", "text": "x"}, {})
        t.show_updated_reminder(Log(), interaction, {"date": "2030-01-02", "time": "10:00", "text": "nuevo"}, {})
        t.show_moved_reminder(Log(), interaction, {"date": "2030-01-03", "time": "11:00", "text": "x"},
                              {"old_date": "2030-01-02", "old_time": "10:00"})
        self.assertEqual([text for text, _ in interaction.shown], [
            message(t, "reminder_deleted", "es") % ("2030-01-02", "10:00"),
            message(t, "reminder_updated", "es") % ("2030-01-02", "10:00", "nuevo"),
            message(t, "reminder_moved", "es") % ("2030-01-02", "10:00", "2030-01-03", "11:00")])

    def test_04_a_message_instead_of_a_reminder_is_shown_as_it_is(self):
        t, interaction = tool(), Interaction()
        t.show_deleted_reminder(Log(), interaction, "No reminder found.", {})
        t.show_moved_reminder(Log(), interaction, "No reminder found.", None)
        self.assertEqual([text for text, _ in interaction.shown], ["No reminder found."] * 2)

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
            for key in ["reminder_count_one", "reminder_count_many", "reminder_list_empty", "reminder_past_datetime"]:
                for lang in ["ca", "es", "en", "de"]:
                    self.assertTrue(block[key][lang], f"{file} {key} {lang}")


if __name__ == "__main__":
    unittest.main()
