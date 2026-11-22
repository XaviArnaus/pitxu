"""The config of the memory: validation with fallback to defaults, and the comparison of the live files with the .dist."""
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from support import *  # noqa: F401,F403
from pitxu.lib.utils.config_checker import ConfigChecker
from pitxu.lib.utils.memory_config_validator import MemoryConfigValidator


class ValidationTests(unittest.TestCase):

    def test_the_default_config_is_valid(self):
        config = cfg(tempfile.mkdtemp())
        self.assertEqual(MemoryConfigValidator.validate(config), [])

    def test_a_missing_setting_is_not_an_error(self):
        config = cfg(tempfile.mkdtemp())
        config.set("memory.consolidation", {"enabled": True})   # all the other consolidation settings are gone
        self.assertEqual(MemoryConfigValidator.validate(config), [])

    def test_invalid_values_are_replaced_by_the_default_and_reported(self):
        config = cfg(tempfile.mkdtemp(), **{
            "night_tasks.hour": 25,
            "night_tasks.minute": "zero",
            "memory.consolidation.batch_size": 0,
            "memory.consolidation.dry_run": "no",
            "memory.summarization.close_timeout_seconds": -5,
            "memory.short_term.retention_days": None,        # None is "not set", not an error
            "memory.consolidation_model": "  ",
            "database.sqlite.backups_keep": 0,
        })
        messages = MemoryConfigValidator.validate(config)
        self.assertEqual(len(messages), 7)
        self.assertEqual(config.get("night_tasks.hour"), 3)
        self.assertEqual(config.get("memory.consolidation.batch_size"), 10)
        self.assertEqual(config.get("memory.consolidation.batch_size"), 10)
        self.assertIs(config.get("memory.consolidation.dry_run"), False)
        self.assertEqual(config.get("memory.summarization.close_timeout_seconds"), 45)
        self.assertEqual(config.get("memory.consolidation_model"), "gemini-3.1-flash-lite")
        self.assertEqual(config.get("database.sqlite.backups_keep"), 5)
        self.assertTrue(any("night_tasks.hour" in m and "25" in m for m in messages))
        # And once fixed there is nothing else to say.
        self.assertEqual(MemoryConfigValidator.validate(config), [])

    def test_the_night_time_moved_from_the_memory_to_the_night_tasks(self):
        config = cfg(tempfile.mkdtemp(), **{"memory.consolidation.hour": 4, "memory.consolidation.minute": 30})
        messages = MemoryConfigValidator.validate(config)
        self.assertEqual(len(messages), 2)
        self.assertTrue(all("night_tasks" in m and "not used any more" in m for m in messages))
        self.assertEqual(config.get("night_tasks.hour"), 3, "the old value is not taken")

    def test_the_dist_has_the_night_tasks_and_no_old_time_in_the_memory(self):
        config = cfg(tempfile.mkdtemp())
        self.assertEqual((config.get("night_tasks.hour"), config.get("night_tasks.minute")), (3, 0))
        self.assertIsNone(config.get("memory.consolidation.hour"))
        self.assertIsNone(config.get("memory.consolidation.minute"))

    def test_a_boolean_is_not_a_number(self):
        config = cfg(tempfile.mkdtemp(), **{"night_tasks.hour": True, "memory.consolidation.batch_size": True})
        self.assertEqual(len(MemoryConfigValidator.validate(config)), 2)

    def test_the_legacy_language_must_be_a_supported_one(self):
        config = cfg(tempfile.mkdtemp(), **{"memory.legacy_entries_language": "fr"})
        messages = MemoryConfigValidator.validate(config)
        self.assertEqual(config.get("memory.legacy_entries_language"), "en")
        self.assertTrue(any("legacy_entries_language" in m for m in messages))

    def test_a_prompt_without_the_data_placeholder_is_only_reported(self):
        config = cfg(tempfile.mkdtemp(), **{"memory.consolidation.prompt": "no placeholder here"})
        messages = MemoryConfigValidator.validate(config)
        self.assertEqual(config.get("memory.consolidation.prompt"), "no placeholder here")
        self.assertTrue(any("memory.consolidation.prompt" in m for m in messages))

    def test_a_close_timeout_too_close_to_the_systemd_one_is_reported(self):
        config = cfg(tempfile.mkdtemp(), **{"memory.summarization.close_timeout_seconds": 110})
        messages = MemoryConfigValidator.validate(config)
        self.assertEqual(config.get("memory.summarization.close_timeout_seconds"), 110)   # reported, not changed
        self.assertTrue(any("systemd" in m for m in messages))

    def test_messages_go_to_the_log(self):
        config = cfg(tempfile.mkdtemp(), **{"night_tasks.hour": 99})
        with self.assertLogs("pitxu_test", level="WARNING") as captured:
            MemoryConfigValidator.validate(config, logging.getLogger("pitxu_test"))
        self.assertTrue(any("night_tasks.hour" in line for line in captured.output))

    def test_memory_validates_its_config_once(self):
        config = cfg(tempfile.mkdtemp(), **{"night_tasks.hour": 99})
        with self.assertLogs("pitxu_test", level="WARNING") as captured:
            first = Memory(config=config, params=params())
            second = Memory(config=config, params=params())
        self.assertEqual(config.get("night_tasks.hour"), 3)
        self.assertEqual(sum("night_tasks.hour" in line for line in captured.output), 1)
        first.close()
        second.close()


class CheckerTests(unittest.TestCase):

    def _write(self, directory, name, content):
        with open(os.path.join(directory, name), "w") as handle:
            handle.write(content)

    def test_it_tells_what_differs(self):
        directory = tempfile.mkdtemp()
        self._write(directory, "a.yaml.dist", "a:\n  one: 1\n  two:\n    three: 3\n  list: [1, 2]\n")
        self._write(directory, "a.yaml", "a:\n  one: 10\n  extra: 5\n  list: [9]\n")
        self._write(directory, "b.yaml.dist", "b:\n  x: 1\n")
        self._write(directory, "b.yaml", "b:\n  x: 2\n")
        self._write(directory, "c.yaml.dist", "c:\n  y: 1\n")      # there is no live c.yaml
        self._write(directory, "d.yaml", "d: 1\n")                  # a live file without .dist: not compared
        report = ConfigChecker.compare(directory)
        self.assertEqual(sorted(report), ["a", "b", "c"])
        self.assertEqual(report["a"]["missing_in_live"], ["a.two.three"])
        self.assertEqual(report["a"]["only_in_live"], ["a.extra"])
        self.assertEqual(report["b"], {"live_file_missing": False, "missing_in_live": [], "only_in_live": []})
        self.assertTrue(report["c"]["live_file_missing"])
        self.assertEqual(report["c"]["missing_in_live"], ["c.y"])

    def test_the_dist_files_of_the_repository_can_be_read(self):
        report = ConfigChecker.compare(os.path.join(REPO, "config"))
        self.assertIn("memory", report)
        self.assertIn("database", report)

    def test_the_dist_of_the_memory_has_no_dead_settings(self):
        """ Every key that was removed from the code must not come back to the .dist """
        paths = ConfigChecker.setting_paths(os.path.join(REPO, "config", "memory.yaml.dist"))
        for removed in ("memory.filename", "memory.summary_similarity_threshold"):
            self.assertNotIn(removed, paths)


if __name__ == "__main__":
    unittest.main()
