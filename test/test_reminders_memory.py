"""An announced reminder is remembered: in the chatbot history, in the short term memory, and the summary knows."""
import datetime as datetime_module
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from support import *  # noqa: F401,F403
from pitxu.lib.utils.reminders import Reminders  # noqa: E402

MARKER = "[SYSTEM NOTICE]"


class Obj:
    def __init__(self, **kw): self.__dict__.update(kw)


def reminders(language="en"):
    tmp = tempfile.mkdtemp()
    config = cfg(tmp)
    database = DbSqlite(config=config, params=params())
    database.migrate_db()
    database.close()
    return tmp, config, Reminders(config=config, params=params(language=language))


def announcement(count=1, language="en"):
    _, _, r = reminders(language)
    due = [{"id": 10 + i, "date": "2030-05-10", "time": "14:30", "text": f"check the oven {i}" if count > 1 else "check the oven",
            "announced": False} for i in range(count)]
    a = r.build_announcement(due, now=datetime_module.datetime(2030, 5, 10, 14, 30, 45))
    r.close()
    return a



class WordsTests(unittest.TestCase):

    def setUp(self):
        _, _, self.r = reminders()
        self.addCleanup(self.r.close)

    def test_01_the_notice_starts_with_the_marker_and_tells_the_ids(self):
        notice = self.r.build_history_notice(announcement(2))
        self.assertTrue(notice.startswith(MARKER + " "))
        self.assertIn("10, 11", notice)
        self.assertEqual(self.r.HISTORY_NOTICE_MARKER, MARKER)

    def test_02_the_memory_entry_of_one_reminder_names_it(self):
        a = announcement(1)
        summary, content = self.r.build_memory_entry(a, announced_at=datetime_module.datetime(2030, 5, 10, 14, 31, 5))
        self.assertEqual(summary, "Reminder announced: check the oven")
        self.assertEqual(content, "At 2030-05-10 14:31 Pitxu announced out loud: Reminder: check the oven. (reminder ids: 10)")

    def test_03_the_memory_entry_of_several_counts_them_and_keeps_them_all_in_the_content(self):
        a = announcement(3)
        summary, content = self.r.build_memory_entry(a, announced_at=datetime_module.datetime(2030, 5, 10, 14, 31, 5))
        self.assertEqual(summary, "3 reminders announced")
        for text in ["check the oven 0", "check the oven 1", "check the oven 2", "ids: 10, 11, 12"]:
            self.assertIn(text, content)

    def test_04_every_language_has_every_message(self):
        for language in ["en", "ca", "es", "de"]:
            _, _, r = reminders(language)
            try:
                for count in (1, 3):
                    a = announcement(count, language)
                    notice = r.build_history_notice(a)
                    summary, content = r.build_memory_entry(a)
                    self.assertTrue(notice.startswith(MARKER) and summary and content, language)
                    self.assertNotIn("%", notice + summary + content, language)
            finally:
                r.close()

    def test_05_the_summary_prompt_of_every_language_knows_the_notices(self):
        for file in ["config/memory.yaml.dist", "config/memory.yaml"]:
            prompts = read_yaml(os.path.join(REPO, file))["memory"]["summary_prompt"]
            for language in ["ca", "es", "en", "de"]:
                self.assertIn(MARKER, prompts[language], f"{file} {language}")
                self.assertEqual(prompts[language].count("%s"), 1, f"{file} {language}")  # still the one place for the history

    def test_06_the_messages_exist_in_both_language_files(self):
        for file in ["config/language.yaml.dist", "config/language.yaml"]:
            block = read_yaml(os.path.join(REPO, file))["language"]["reminders"]
            for key in ["reminder_history_notice", "reminder_memory_summary_one", "reminder_memory_summary_many", "reminder_memory_content"]:
                for lang in ["ca", "es", "en", "de"]:
                    self.assertTrue(block[key][lang], f"{file} {key} {lang}")


class HistoryTests(unittest.TestCase):

    def _chatbot(self, mock=False, chat="fake"):
        class Content:
            def __init__(self, role, parts): self.role, self.parts = role, parts
        class Part:
            def __init__(self, text): self.text = text
        recorded = []
        class Chat:
            def record_history(self, **kwargs): recorded.append(kwargs)
        Holder = methods_of("pitxu/lib/chatbot/gemini_chatbot.py", ["add_notice_to_history"],
                            {"types": Obj(Content=Content, Part=Part)})
        bot = Holder()
        bot._xlog = Log()
        bot._xconfig = Obj(get=lambda key, default=None: mock if key == "chatbot.mock" else default)
        bot._chat = Chat() if chat == "fake" else chat
        return bot, recorded

    def test_01_the_pair_is_valid_history_with_a_list_as_model_output(self):
        bot, recorded = self._chatbot()
        self.assertTrue(bot.add_notice_to_history(MARKER + " notice", "Reminder: milk."))
        call = recorded[0]
        self.assertTrue(call["is_valid"])
        self.assertEqual(call["automatic_function_calling_history"], [])
        self.assertEqual((call["user_input"].role, call["user_input"].parts[0].text), ("user", MARKER + " notice"))
        # The library extends the history with whatever it gets: a single Content would break it. It is a list.
        self.assertIsInstance(call["model_output"], list)
        self.assertEqual((call["model_output"][0].role, call["model_output"][0].parts[0].text), ("model", "Reminder: milk."))

    def test_02_a_mocked_chatbot_or_without_session_adds_nothing(self):
        bot, recorded = self._chatbot(mock=True)
        self.assertFalse(bot.add_notice_to_history("n", "s"))
        bot, recorded = self._chatbot(chat=None)
        self.assertFalse(bot.add_notice_to_history("n", "s"))

    def test_03_a_failing_library_is_logged_and_not_raised(self):
        bot, _ = self._chatbot()
        class Broken:
            def record_history(self, **kwargs): raise RuntimeError("boom")
        bot._chat = Broken()
        self.assertFalse(bot.add_notice_to_history("n", "s"))
        self.assertTrue(any("Could not add the notice" in line for line in bot._xlog.lines))

    def test_05_every_record_history_call_gives_the_model_output_as_a_list(self):
        import ast
        source = read_file(os.path.join(REPO, "pitxu/lib/chatbot/gemini_chatbot.py"))
        calls = [node for node in ast.walk(ast.parse(source))
                 if isinstance(node, ast.Call) and getattr(node.func, "attr", None) == "record_history"]
        self.assertEqual(len(calls), 6)
        for call in calls:
            model_output = next(keyword.value for keyword in call.keywords if keyword.arg == "model_output")
            self.assertIsInstance(model_output, ast.List, f"line {call.lineno}")
            self.assertEqual(len(model_output.elts), 1, f"line {call.lineno}")

    def test_04_the_notice_is_not_the_user_speaking_for_the_summary(self):
        Holder = methods_of("pitxu/main.py", ["_user_turns_in"], {"Reminders": Reminders})
        history = [{"role": "user", "text": "hello"},
                   {"role": "model", "text": "hi"},
                   {"role": "user", "text": MARKER + " The application just announced..."},
                   {"role": "model", "text": "Reminder: milk."},
                   {"role": "user", "text": ""},
                   {"role": "user", "text": "thanks"}]
        self.assertEqual(Holder._user_turns_in(history), 2)
        self.assertEqual(Holder._user_turns_in(history[2:4]), 0)


class RecordTests(unittest.TestCase):
    """ Main._record_announcement with a real database and a fake chatbot. """

    def _app(self, language="ca", chatbot="fake"):
        tmp = tempfile.mkdtemp()
        config = cfg(tmp)
        database = DbSqlite(config=config, params=params())
        database.migrate_db()
        database.close()
        calls = []
        class Bot:
            def add_notice_to_history(self, notice, spoken): calls.append((notice, spoken))
        Holder = methods_of("pitxu/main.py", ["_record_announcement"], {"Dictionary": Dictionary})
        app = Holder()
        app._xlog = Log()
        app._xconfig = config
        app._xparams = Dictionary({"api_key": "k", "base_path": REPO, "language": language})
        app._chatbot = Bot() if chatbot == "fake" else chatbot
        app._reminders = Reminders(config=config, params=params(language=language))
        self.addCleanup(app._reminders.close)
        return app, config, calls

    def _short_entries(self, config):
        database = DbSqlite(config=config, params=params())
        try:
            return [dict(row) for row in database.connection.execute("SELECT summary, content, language FROM short_time_memory")]
        finally:
            database.close()

    def test_01_it_goes_to_the_history_and_to_the_short_term_memory_in_the_session_language(self):
        app, config, calls = self._app("ca")
        a = announcement(1, "ca")
        app._record_announcement(a)
        self.assertEqual(len(calls), 1)
        self.assertTrue(calls[0][0].startswith(MARKER))
        self.assertEqual(calls[0][1], a["spoken"])
        entries = self._short_entries(config)
        self.assertEqual(len(entries), 1)
        self.assertEqual(entries[0]["summary"], "Recordatori anunciat: check the oven")
        self.assertEqual(entries[0]["language"], "ca")
        self.assertIn(a["spoken"], entries[0]["content"])

    def test_02_a_chatbot_that_fails_does_not_stop_the_memory(self):
        app, config, calls = self._app()
        class Broken:
            def add_notice_to_history(self, notice, spoken): raise RuntimeError("boom")
        app._chatbot = Broken()
        app._record_announcement(announcement(1))
        self.assertEqual(len(self._short_entries(config)), 1)
        self.assertTrue(any("chatbot history" in line for line in app._xlog.lines))

    def test_03_without_chatbot_only_the_memory_is_written(self):
        app, config, _ = self._app(chatbot=None)
        app._record_announcement(announcement(2))
        entries = self._short_entries(config)
        self.assertEqual([e["summary"] for e in entries], ["2 recordatoris anunciats"])

    def test_04_a_memory_that_fails_does_not_stop_the_history_nor_raise(self):
        app, config, calls = self._app()
        app._xconfig = Obj(get=lambda key, default=None: (_ for _ in ()).throw(RuntimeError("config broke")))
        app._record_announcement(announcement(1))
        self.assertEqual(len(calls), 1)
        self.assertTrue(any("into the memory" in line for line in app._xlog.lines))


if __name__ == "__main__":
    unittest.main()
