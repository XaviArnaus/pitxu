"""The night cleanup of the lists: done items to the trash (not in favourites), the old trash deleted for good."""
import datetime as datetime_module
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from support import *  # noqa: F401,F403
from test_lists_storage import store  # noqa: E402

NOW = datetime_module.datetime(2030, 6, 30, 3, 0, 0)


def ago(days):
    return (NOW - datetime_module.timedelta(days=days)).strftime("%Y-%m-%d %H:%M:%S")


class CleanupTests(unittest.TestCase):

    def setUp(self):
        self.tmp, self.config, self.lists = store()
        self.addCleanup(self.lists.close)

    def make(self, name, items):
        created = self.lists.create_list(name, items=list(items))["list"]
        return created, [i["id"] for i in self.lists.get_list(created["id"])["items"]]

    def sql(self, statement, *args):
        self.lists.db.connection.execute(statement, args)
        self.lists.db.connection.commit()

    def done(self, item_id, days):
        self.lists.check_items(True, item_ids=[item_id])
        self.sql("UPDATE list_item SET done_at = ? WHERE id = ?", ago(days), item_id)

    def count(self, table):
        return self.lists.db.connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]

    def test_01_old_done_items_go_to_the_trash_and_can_be_restored(self):
        shopping, (old, recent, open_item) = self.make("Shopping", ["old", "recent", "open"])
        self.done(old, 15)
        self.done(recent, 13)
        result = self.lists.cleanup(14, 30, now=NOW)
        self.assertEqual(result, {"trashed": 1, "purged_items": 0, "purged_lists": 0})
        self.assertEqual([i["text"] for i in self.lists.get_list(shopping["id"])["items"]], ["open", "recent"])
        self.assertEqual([i["text"] for i in self.lists.get_removed_items(shopping["id"])], ["old"])
        self.assertEqual(len(self.lists.restore_items([old])["restored"]), 1)

    def test_02_a_favourite_list_keeps_its_done_items(self):
        shopping, (old,) = self.make("Shopping", ["old"])
        self.lists.update_list(shopping["id"], favourite=True)
        self.done(old, 100)
        self.assertEqual(self.lists.cleanup(14, 30, now=NOW)["trashed"], 0)
        self.assertEqual(len(self.lists.get_list(shopping["id"])["items"]), 1)

    def test_03_the_items_that_go_to_the_trash_have_the_whole_period_there(self):
        shopping, (old,) = self.make("Shopping", ["old"])
        self.done(old, 100)
        self.lists.cleanup(14, 30, now=NOW)
        self.assertEqual(self.lists.cleanup(14, 30, now=NOW + datetime_module.timedelta(days=29))["purged_items"], 0)
        self.assertEqual(self.lists.cleanup(14, 30, now=NOW + datetime_module.timedelta(days=31))["purged_items"], 1)
        self.assertEqual(self.count("list_item"), 0)

    def test_04_old_trash_is_deleted_for_good_with_its_translations_and_recent_trash_stays(self):
        shopping, (old, recent) = self.make("Shopping", ["old", "recent"])
        self.lists.remove_items([old, recent])
        self.sql("UPDATE list_item SET deleted_at = ? WHERE id = ?", ago(31), old)
        self.sql("UPDATE list_item SET deleted_at = ? WHERE id = ?", ago(29), recent)
        self.sql("INSERT INTO list_item_translation (item_id, language, text, text_key) VALUES (?, 'de', 'alt', 'alt')", old)
        result = self.lists.cleanup(14, 30, now=NOW)
        self.assertEqual((result["trashed"], result["purged_items"]), (0, 1))
        self.assertEqual([i["text"] for i in self.lists.get_removed_items(shopping["id"])], ["recent"])
        self.assertEqual(self.count("list_item_translation"), 0)

    def test_05_a_list_deleted_long_ago_goes_with_its_items_and_translations(self):
        gone, (a, b) = self.make("Gone", ["a", "b"])
        kept, (c,) = self.make("Kept", ["c"])
        self.sql("INSERT INTO list_translation (list_id, language, name, name_key) VALUES (?, 'de', 'Weg', 'weg')", gone["id"])
        self.lists.delete_list(gone["id"])
        self.sql("UPDATE list SET deleted_at = ? WHERE id = ?", ago(31), gone["id"])
        result = self.lists.cleanup(14, 30, now=NOW)
        self.assertEqual((result["purged_lists"], result["purged_items"]), (1, 2))
        self.assertEqual((self.count("list"), self.count("list_item"), self.count("list_translation")), (1, 1, 0))
        self.assertEqual(self.lists.get_list(kept["id"])["items"][0]["text"], "c")

    def test_06_a_list_deleted_recently_can_still_be_restored_whatever_its_items_were(self):
        shopping, (old,) = self.make("Shopping", ["old"])
        self.done(old, 100)
        self.lists.delete_list(shopping["id"])
        self.sql("UPDATE list SET deleted_at = ? WHERE id = ?", ago(5), shopping["id"])
        result = self.lists.cleanup(14, 30, now=NOW)
        self.assertEqual((result["trashed"], result["purged_lists"]), (0, 0))  # The items of a deleted list are not touched.
        self.assertTrue(self.lists.restore_list(shopping["id"])["restored"])
        self.assertEqual(len(self.lists.get_list(shopping["id"])["items"]), 1)

    def test_07_an_open_item_is_never_trashed_and_done_without_date_is_left(self):
        shopping, (a, b) = self.make("Shopping", ["a", "b"])
        self.sql("UPDATE list_item SET created_at = ? WHERE id = ?", ago(100), a)  # Old, but open.
        self.sql("UPDATE list_item SET done = 1, done_at = NULL WHERE id = ?", b)
        self.assertEqual(self.lists.cleanup(14, 30, now=NOW)["trashed"], 0)

    def test_08_nothing_to_do_does_nothing(self):
        self.assertEqual(self.lists.cleanup(14, 30, now=NOW), {"trashed": 0, "purged_items": 0, "purged_lists": 0})

    def test_09_the_defaults_of_the_dist(self):
        block = read_yaml(os.path.join(REPO, "config", "main.yaml.dist"))["lists"]["cleanup"]
        self.assertEqual((block["enabled"], block["done_after_days"], block["trash_after_days"]), (True, 14, 30))


if __name__ == "__main__":
    unittest.main()
