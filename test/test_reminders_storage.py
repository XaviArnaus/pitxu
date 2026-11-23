"""The reminders in the database: ids, due and late, announced, snooze, prune, and the move from the old YAML file."""
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


def store(language="en"):
    """ A migrated database in a temporary directory, and the Reminders on it. Returns (tmp, config, reminders). """
    tmp = tempfile.mkdtemp()
    config = cfg(tmp)
    database = DbSqlite(config=config, params=params())
    database.migrate_db()
    database.close()
    return tmp, config, Reminders(config=config, params=params(language=language))


class StorageTests(unittest.TestCase):

    def setUp(self):
        self.tmp, self.config, self.reminders = store()
        self.addCleanup(self.reminders.close)

    def test_01_ids_and_several_in_the_same_minute(self):
        a = self.reminders.create_reminder("2030-05-10", "14:30", "milk")
        b = self.reminders.create_reminder("2030-05-10", "14:30", "bread")
        self.assertEqual((a["id"], b["id"]), (1, 2))
        self.assertEqual((a["date"], a["time"], a["text"], a["announced"]), ("2030-05-10", "14:30", "milk", False))
        self.assertEqual(self.reminders.get_reminder(2)["text"], "bread")

    def test_02_the_language_of_the_session_is_kept(self):
        self.reminders.create_reminder("2030-05-10", "14:30", "x")
        self.reminders.create_reminder("2030-05-10", "14:31", "y", language="ca")
        languages = [row[0] for row in self.reminders.db.connection.execute("SELECT language FROM reminders ORDER BY id")]
        self.assertEqual(languages, ["en", "ca"])

    def test_03_the_list_of_a_date_is_pending_only_in_time_order(self):
        self.reminders.create_reminder("2030-05-10", "18:00", "evening")
        self.reminders.create_reminder("2030-05-10", "08:00", "morning")
        self.reminders.create_reminder("2030-05-09", "23:59", "day before")
        self.reminders.create_reminder("2030-05-11", "00:00", "day after")
        done = self.reminders.create_reminder("2030-05-10", "12:00", "done")
        self.reminders.mark_announced([done["id"]])
        listed = self.reminders.get_reminders_for_date("2030-05-10")
        self.assertEqual([r["text"] for r in listed], ["morning", "evening"])

    def test_04_due_is_everything_pending_up_to_now_oldest_first(self):
        self.reminders.create_reminder("2030-05-10", "14:30", "now")
        self.reminders.create_reminder("2030-05-10", "14:31", "future")
        self.reminders.create_reminder("2030-05-09", "09:00", "late from yesterday")
        self.reminders.create_reminder("2030-05-10", "14:30", "now too")
        announced = self.reminders.create_reminder("2030-05-10", "10:00", "announced")
        self.reminders.mark_announced([announced["id"]])
        due = self.reminders.get_due(now=D(2030, 5, 10, 14, 30, 45))
        self.assertEqual([r["text"] for r in due], ["late from yesterday", "now", "now too"])

    def test_05_announcing_takes_it_out_of_what_is_due_and_is_idempotent(self):
        a = self.reminders.create_reminder("2030-05-10", "14:30", "milk")
        self.assertEqual(self.reminders.mark_announced([a["id"]]), 1)
        self.assertEqual(self.reminders.mark_announced([a["id"]]), 0)
        self.assertEqual(self.reminders.mark_announced([]), 0)
        self.assertEqual(self.reminders.get_due(now=D(2030, 5, 11)), [])
        self.assertTrue(self.reminders.get_reminder(a["id"])["announced"])

    def test_06_update_delete_and_get_of_an_unknown_id_say_false(self):
        self.assertIs(self.reminders.get_reminder(99), False)
        self.assertIs(self.reminders.update_reminder(99, "x"), False)
        self.assertIs(self.reminders.delete_reminder(99), False)
        self.assertIs(self.reminders.move_reminder(99, "2030-05-10", "10:00"), False)

    def test_07_update_and_delete_give_the_reminder(self):
        a = self.reminders.create_reminder("2030-05-10", "14:30", "milk")
        self.assertEqual(self.reminders.update_reminder(a["id"], "bread")["text"], "bread")
        deleted = self.reminders.delete_reminder(a["id"])
        self.assertEqual((deleted["id"], deleted["text"]), (a["id"], "bread"))
        self.assertIs(self.reminders.get_reminder(a["id"]), False)

    def test_08_moving_an_announced_reminder_makes_it_pending_again(self):
        a = self.reminders.create_reminder("2030-05-10", "14:30", "oven")
        self.reminders.mark_announced([a["id"]])
        moved = self.reminders.move_reminder(a["id"], "2030-05-10", "14:40")
        self.assertEqual((moved["time"], moved["previous_time"], moved["previous_date"], moved["announced"]),
                         ("14:40", "14:30", "2030-05-10", False))
        self.assertEqual([r["id"] for r in self.reminders.get_due(now=D(2030, 5, 10, 14, 45))], [a["id"]])

    def test_09_prune_deletes_only_what_was_announced_long_ago(self):
        old = self.reminders.create_reminder("2030-05-01", "10:00", "old")
        recent = self.reminders.create_reminder("2030-05-01", "11:00", "recent")
        pending = self.reminders.create_reminder("2030-05-01", "12:00", "pending")
        self.reminders.mark_announced([old["id"]], announced_at=D(2030, 5, 1, 10, 0))
        self.reminders.mark_announced([recent["id"]], announced_at=D(2030, 5, 9, 10, 0))
        self.assertEqual(self.reminders.prune_announced(7, now=D(2030, 5, 10, 3, 0)), 1)
        self.assertIs(self.reminders.get_reminder(old["id"]), False)
        self.assertTrue(self.reminders.get_reminder(recent["id"]))
        self.assertTrue(self.reminders.get_reminder(pending["id"]))

    def test_10_threads_can_write_at_the_same_time(self):
        errors = []
        def work(n):
            try:
                for i in range(10): self.reminders.create_reminder("2030-05-10", "14:30", f"{n}-{i}")
            except Exception as e: errors.append(e)
        threads = [threading.Thread(target=work, args=(n,)) for n in range(8)]
        [t.start() for t in threads]; [t.join() for t in threads]
        self.assertEqual(errors, [])
        self.assertEqual(len(self.reminders.get_due(now=D(2030, 5, 11))), 80)

    def test_10b_get_due_never_raises_and_logs_the_problem(self):
        self.reminders.create_reminder("2030-05-10", "14:30", "milk")
        self.reminders.db.connection.close()
        log = Log()
        self.reminders._xlog = log
        self.assertEqual(self.reminders.get_due(now=D(2030, 5, 11)), [])
        self.assertTrue(any("Could not get the due reminders" in line for line in log.lines))
        # The others do raise: their callers (the tools) answer with an error message.
        with self.assertRaises(Exception):
            self.reminders.get_reminder(1)
        self.reminders.close = lambda: None  # (the connection is already closed)

    def test_11_the_table_comes_with_the_migrations(self):
        tables = [row[0] for row in self.reminders.db.connection.execute("SELECT name FROM sqlite_master WHERE type = 'table'")]
        self.assertIn("reminders", tables)
        version = self.reminders.db.connection.execute("PRAGMA user_version").fetchone()[0]
        self.assertGreaterEqual(version, 4)


class LegacyImportTests(unittest.TestCase):

    def setUp(self):
        self.tmp, self.config, self.reminders = store()
        self.addCleanup(self.reminders.close)
        self.path = os.path.join(self.tmp, "reminders.yaml")

    def _write(self, content):
        write_file(self.path, content)

    def test_01_everything_is_imported_and_the_file_is_deleted(self):
        self._write("'2026-02-21': {}\n'2030-01-02':\n  13-00: 'Buy milk'\n  13-15: 'Call mum'\n'2020-01-01':\n  09-00: 'Very old'\n")
        stats = self.reminders.import_legacy_yaml()
        self.assertEqual((stats["entries"], stats["imported"], stats["already_there"], stats["invalid"], stats["file_deleted"]),
                         (3, 3, 0, [], True))
        self.assertFalse(os.path.exists(self.path))
        due = self.reminders.get_due(now=D(2030, 1, 3))
        self.assertEqual([(r["date"], r["time"], r["text"]) for r in due],
                         [("2020-01-01", "09:00", "Very old"), ("2030-01-02", "13:00", "Buy milk"), ("2030-01-02", "13:15", "Call mum")])

    def test_02_without_the_file_nothing_happens(self):
        self.assertEqual(self.reminders.import_legacy_yaml()["found"], False)

    def test_03_a_second_run_does_not_duplicate(self):
        self._write("'2030-01-02':\n  13-00: 'Buy milk'\n")
        self.reminders.create_reminder("2030-01-02", "13:00", "Buy milk")
        stats = self.reminders.import_legacy_yaml()
        self.assertEqual((stats["imported"], stats["already_there"], stats["file_deleted"]), (0, 1, True))
        self.assertEqual(len(self.reminders.get_due(now=D(2030, 1, 3))), 1)

    def test_04_an_entry_that_cannot_be_read_keeps_the_file_and_imports_the_rest_once(self):
        self._write("'2030-01-02':\n  13-00: 'Buy milk'\n  99-99: 'Broken time'\n")
        stats = self.reminders.import_legacy_yaml()
        self.assertEqual((stats["imported"], len(stats["invalid"]), stats["file_deleted"]), (1, 1, False))
        self.assertTrue(os.path.exists(self.path))
        stats = self.reminders.import_legacy_yaml()
        self.assertEqual((stats["imported"], stats["already_there"], stats["file_deleted"]), (0, 1, False))
        self.assertEqual(len(self.reminders.get_due(now=D(2030, 1, 3))), 1)

    def test_05_yaml_that_reads_dates_and_times_as_other_types_is_understood(self):
        # Without quotes YAML reads 2030-01-02 as a date, and 13:00 as 780 (minutes).
        self._write("2030-01-02:\n  13:00: 'Unquoted'\n")
        stats = self.reminders.import_legacy_yaml()
        self.assertEqual((stats["imported"], stats["file_deleted"]), (1, True))
        due = self.reminders.get_due(now=D(2030, 1, 3))
        self.assertEqual((due[0]["date"], due[0]["time"]), ("2030-01-02", "13:00"))

    def test_06_a_file_that_is_not_what_it_should_keeps_itself(self):
        self._write("- just\n- a list\n")
        stats = self.reminders.import_legacy_yaml()
        self.assertEqual((stats["file_deleted"], len(stats["invalid"])), (False, 1))
        self.assertTrue(os.path.exists(self.path))

    def test_07_an_empty_file_is_just_deleted(self):
        self._write("")
        stats = self.reminders.import_legacy_yaml()
        self.assertEqual((stats["entries"], stats["file_deleted"]), (0, True))


class WiringTests(unittest.TestCase):

    def test_01_main_moves_the_old_file_right_after_the_migrations(self):
        source = read_file(os.path.join(REPO, "pitxu/main.py"))
        self.assertLess(source.index("self._maintenance.execute_db_migrations()"),
                        source.index("self._maintenance.import_legacy_reminders()"))
        self.assertLess(source.index("self._maintenance.import_legacy_reminders()"),
                        source.index("self._maintenance.execute_memory_preload()"))

    def test_02_the_chatbot_tools_share_the_instance_of_main(self):
        self.assertIn('"reminders": self._reminders', read_file(os.path.join(REPO, "pitxu/main.py")))
        self.assertIn('self._xparams.key_exists("reminders")', read_file(os.path.join(REPO, "pitxu/lib/command/stateful/reminders.py")))

    def test_03_main_and_ptt_use_get_due_directly(self):
        main = read_file(os.path.join(REPO, "pitxu/main.py"))
        self.assertIn("due = self._reminders.get_due()", main)
        self.assertIn("for reminder in self._reminders.get_due():", read_file(os.path.join(REPO, "pitxu/main_client_ptt.py")))
        for source in [main, read_file(os.path.join(REPO, "pitxu/main_client_ptt.py"))]:
            self.assertNotIn("_safe_due_reminders", source)

    def test_04_the_night_tasks_prune_with_the_configured_days(self):
        source = read_file(os.path.join(REPO, "pitxu/main.py"))
        self.assertIn('self._reminders.prune_announced(', source)
        for file in ["config/main.yaml.dist", "config/main.yaml"]:
            self.assertEqual(read_yaml(os.path.join(REPO, file))["reminders"]["keep_announced_days"], 7)


if __name__ == "__main__":
    unittest.main()
