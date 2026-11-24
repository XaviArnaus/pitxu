"""The move of the old lists.yaml into the database: dates, language, repeated items, and the file only deleted when all is in."""
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from support import *  # noqa: F401,F403
from test_lists_storage import store  # noqa: E402

# As it is in the Pi: the junk keys of the old entries, an empty list, a date that YAML reads as a datetime.
LEGACY = """\
low-confidence-transcription-logs:
  created_at: 2026-06-01 19:22
  description: null
  entries: []
  name: Low confidence transcription logs
shopping-list:
  created_at: 2026-05-11 07:06
  description: weekly
  entries:
  - created at: ''
    created_at: 2026-05-11 07:07
    list_name: Shopping list
    text: toilet paper
  - created at: ''
    created_at: '2026-05-11 07:08'
    list_name: Shopping list
    text: pasta
  name: Shopping list
"""


class LegacyListsTests(unittest.TestCase):

    def setUp(self):
        self.tmp, self.config, self.lists = store(language="ca")
        self.addCleanup(self.lists.close)
        self.path = os.path.join(self.tmp, "lists.yaml")

    def write(self, content=LEGACY):
        with open(self.path, "w", encoding="utf-8") as handle:
            handle.write(content)

    def by_name(self, name):
        found = self.lists.resolve_list(name, strict=True)["list"]
        return self.lists.get_list(found["id"])

    def test_01_no_file_does_nothing(self):
        stats = self.lists.import_legacy_yaml()
        self.assertEqual((stats["found"], stats["file_deleted"]), (False, False))

    def test_02_lists_and_items_move_with_their_dates_and_the_language_of_the_app(self):
        self.write()
        stats = self.lists.import_legacy_yaml()
        self.assertEqual((stats["lists"], stats["items"], stats["imported_lists"], stats["imported_items"]), (2, 2, 2, 2))
        self.assertTrue(stats["file_deleted"])
        self.assertFalse(os.path.exists(self.path))

        shopping = self.by_name("Shopping list")
        self.assertEqual([(i["text"], i["done"]) for i in shopping["items"]], [("toilet paper", False), ("pasta", False)])
        self.assertEqual(shopping["description"], "weekly")
        self.assertEqual(self.by_name("Low confidence transcription logs")["items"], [])
        rows = self.lists.db.connection.execute(
            "SELECT l.created_at AS l, l.language AS lang, i.created_at AS i FROM list l JOIN list_item i ON i.list_id = l.id "
            "WHERE l.name = 'Shopping list' ORDER BY i.id").fetchall()
        self.assertEqual([(r["l"], r["lang"], r["i"]) for r in rows],
                         [("2026-05-11 07:06", "ca", "2026-05-11 07:07"), ("2026-05-11 07:06", "ca", "2026-05-11 07:08")])

    def test_03_the_language_can_be_given(self):
        self.write()
        self.lists.import_legacy_yaml(language="en")
        self.assertEqual(self.lists.db.connection.execute("SELECT DISTINCT language FROM list_item").fetchall()[0][0], "en")

    def test_04_a_repeated_item_is_imported_once_and_logged_and_the_file_goes(self):
        self.write("a:\n  name: A\n  entries:\n  - text: Milk\n  - text: milk\n  - text: bread\n")
        stats = self.lists.import_legacy_yaml()
        self.assertEqual(stats["imported_items"], 2)
        self.assertEqual(stats["duplicates"], ["A: milk"])
        self.assertTrue(stats["file_deleted"])

    def test_05_an_unreadable_entry_keeps_the_file_and_imports_the_rest_only_once(self):
        self.write("a:\n  name: A\n  entries:\n  - text: milk\n  - text: ''\nb: nonsense\n")
        first = self.lists.import_legacy_yaml()
        self.assertEqual(len(first["invalid"]), 2)
        self.assertFalse(first["file_deleted"])
        self.assertTrue(os.path.exists(self.path))
        second = self.lists.import_legacy_yaml()
        self.assertEqual((second["imported_lists"], second["imported_items"], second["already_there"]), (0, 0, 1))
        self.assertEqual(len(self.by_name("A")["items"]), 1)

    def test_06_what_was_imported_before_is_not_imported_twice(self):
        self.write()
        self.lists.import_legacy_yaml()
        self.write()  # The file comes back (a restored copy).
        stats = self.lists.import_legacy_yaml()
        self.assertEqual((stats["imported_lists"], stats["imported_items"], stats["already_there"]), (0, 0, 2))
        self.assertEqual(self.lists.db.connection.execute("SELECT COUNT(*) FROM list").fetchone()[0], 2)
        self.assertFalse(os.path.exists(self.path))

    def test_07_a_failure_imports_nothing_and_keeps_the_file(self):
        self.write()
        original = self.lists._find_item_by_key
        self.lists._find_item_by_key = lambda *a: 1 / 0
        try:
            with self.assertRaises(ZeroDivisionError):
                self.lists.import_legacy_yaml()
        finally:
            self.lists._find_item_by_key = original
        self.assertTrue(os.path.exists(self.path))
        self.assertEqual(self.lists.db.connection.execute("SELECT COUNT(*) FROM list").fetchone()[0], 0)

    def test_08_an_empty_file_is_deleted_and_a_file_that_is_not_a_dict_is_kept(self):
        self.write("")
        self.assertTrue(self.lists.import_legacy_yaml()["file_deleted"])
        self.write("- a\n- b\n")
        stats = self.lists.import_legacy_yaml()
        self.assertFalse(stats["file_deleted"])
        self.assertEqual(len(stats["invalid"]), 1)

    def test_09_two_slugs_with_the_same_name_are_one_list(self):
        self.write("a:\n  name: Shopping\n  entries:\n  - text: milk\nb:\n  name: shopping\n  entries:\n  - text: milk\n  - text: tea\n")
        stats = self.lists.import_legacy_yaml()
        self.assertEqual((stats["imported_lists"], stats["imported_items"]), (1, 2))
        self.assertEqual([i["text"] for i in self.by_name("Shopping")["items"]], ["milk", "tea"])


if __name__ == "__main__":
    unittest.main()
