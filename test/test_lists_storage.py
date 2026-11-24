"""The lists in the database: names and how they are found, items by id, duplicates, done, soft deletes, copies, translations."""
import os
import sys
import tempfile
import time
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from support import *  # noqa: F401,F403
from pitxu.lib.utils.lists import Lists  # noqa: E402


def store(language="en"):
    """ A migrated database in a temporary directory, and the Lists on it. Returns (tmp, config, lists). """
    tmp = tempfile.mkdtemp()
    config = cfg(tmp)
    database = DbSqlite(config=config, params=params())
    database.migrate_db()
    database.close()
    return tmp, config, Lists(config=config, params=params(language=language))


class ListsTests(unittest.TestCase):

    def setUp(self):
        self.tmp, self.config, self.lists = store()
        self.addCleanup(self.lists.close)

    def make(self, name="Shopping list", items=("milk", "bread")):
        return self.lists.create_list(name, items=list(items))["list"]

    def texts(self, list_id, language=None):
        return [(i["text"], i["done"]) for i in self.lists.get_list(list_id, language)["items"]]

    # ----- lists -----

    def test_01_the_name_is_kept_as_it_is_given(self):
        created = self.lists.create_list("To Do Client")
        self.assertTrue(created["created"])
        self.assertEqual(created["list"]["name"], "To Do Client")  # The old one lowercased it: "To do client".
        self.assertEqual(created["list"]["language"], "en")

    def test_02_creating_one_that_exists_gives_it_back_and_keeps_its_items(self):
        first = self.make()
        again = self.lists.create_list("  SHOPPING   list ")
        self.assertFalse(again["created"])
        self.assertEqual(again["list"]["id"], first["id"])
        self.assertEqual(self.texts(first["id"]), [("milk", False), ("bread", False)])  # The old one replaced it by an empty one.

    def test_03_accents_and_capitals_do_not_make_another_name(self):
        a = self.lists.create_list("Lista de la compra")["list"]
        b = self.lists.create_list("lista de la cómpra")
        self.assertFalse(b["created"])
        self.assertEqual(b["list"]["id"], a["id"])

    def test_04_an_empty_name_is_refused(self):
        with self.assertRaises(ValueError):
            self.lists.create_list("   ")

    def test_05_updating_a_list_does_not_touch_its_items(self):
        shopping = self.make()
        result = self.lists.update_list(shopping["id"], new_name="Groceries", new_description="weekly")
        self.assertTrue(result["updated"])
        self.assertEqual(result["changed"], ["name", "description"])
        self.assertEqual(self.texts(shopping["id"]), [("milk", False), ("bread", False)])  # The old one left it with 0.
        self.assertEqual(self.lists.get_list(shopping["id"])["name"], "Groceries")

    def test_06_a_name_taken_by_another_list_is_a_conflict(self):
        a = self.make("A")
        b = self.make("B", items=())
        result = self.lists.update_list(b["id"], new_name="a")
        self.assertFalse(result["updated"])
        self.assertEqual(result["conflict"]["id"], a["id"])
        self.assertEqual(self.lists.get_list(b["id"])["name"], "B")

    def test_07_renaming_to_the_same_name_changes_nothing_and_is_not_a_conflict(self):
        a = self.make("A")
        result = self.lists.update_list(a["id"], new_name="A")
        self.assertEqual((result["updated"], result["changed"], result["conflict"]), (False, [], None))

    def test_08_favourite_and_unknown_list(self):
        a = self.make("A")
        self.assertTrue(self.lists.update_list(a["id"], favourite=True)["list"]["favourite"])
        self.assertFalse(self.lists.update_list(a["id"], favourite=False)["list"]["favourite"])
        self.assertIs(self.lists.update_list(999, favourite=True), False)

    def test_09_the_lists_come_favourites_first_and_with_their_counts(self):
        a = self.make("Alpha", items=("x", "y"))
        self.make("Beta", items=())
        z = self.make("Zeta", items=("z",))
        self.lists.update_list(z["id"], favourite=True)
        self.lists.check_items(True, item_ids=[self.lists.get_list(a["id"])["items"][0]["id"]])
        listed = self.lists.get_lists()
        self.assertEqual([entry["name"] for entry in listed], ["Zeta", "Alpha", "Beta"])
        self.assertEqual([(e["open"], e["done"]) for e in listed], [(1, 0), (1, 1), (0, 0)])

    # ----- finding a list -----

    def test_10_resolving_exact_partial_and_similar(self):
        shopping = self.make("Shopping list")
        self.make("Books to read")
        resolve = self.lists.resolve_list
        self.assertEqual(resolve("shopping LIST")["list"]["id"], shopping["id"])
        self.assertEqual(resolve("shopping")["list"]["id"], shopping["id"])            # Partial.
        self.assertEqual(resolve("my shopping list please")["list"]["id"], shopping["id"])
        self.assertEqual(resolve("shoping list")["list"]["id"], shopping["id"])        # Misheard: similar.
        missing = resolve("holidays")
        self.assertIsNone(missing["list"])
        self.assertEqual(sorted(missing["candidates"]), ["Books to read", "Shopping list"])  # Tells what exists.

    def test_11_several_partial_matches_are_an_ambiguity(self):
        self.make("Shopping list")
        self.make("Shopping ideas")
        result = self.lists.resolve_list("shopping")
        self.assertIsNone(result["list"])
        self.assertTrue(result["ambiguous"])
        self.assertEqual(sorted(result["candidates"]), ["Shopping ideas", "Shopping list"])

    def test_12_strict_does_not_accept_a_partial_name(self):
        self.make("Shopping list")
        self.assertIsNone(self.lists.resolve_list("shopping", strict=True)["list"])
        self.assertIsNotNone(self.lists.resolve_list("Shopping list", strict=True)["list"])

    def test_13_a_name_in_another_language_finds_the_list(self):
        shopping = self.make("Shopping list")
        self.lists.db.connection.execute(
            "INSERT INTO list_translation (list_id, language, name, name_key) VALUES (?, 'de', 'Einkaufsliste', 'einkaufsliste')",
            (shopping["id"],))
        self.lists.db.connection.commit()
        self.assertEqual(self.lists.resolve_list("einkaufsliste")["list"]["id"], shopping["id"])
        self.assertFalse(self.lists.create_list("Einkaufsliste")["created"])

    # ----- items -----

    def test_20_items_have_ids_and_keep_their_text(self):
        shopping = self.make(items=())
        result = self.lists.add_items(shopping["id"], ["  Milk ", "bread"])
        self.assertEqual([i["text"] for i in result["added"]], ["Milk", "bread"])
        self.assertEqual(result["count"], 2)
        self.assertEqual(self.lists.get_item(result["added"][0]["id"])["text"], "Milk")

    def test_21_adding_to_a_missing_list_is_false(self):
        self.assertIs(self.lists.add_items(999, ["x"]), False)

    def test_22_a_duplicate_is_refused_whatever_its_status_and_tells_it(self):
        shopping = self.make(items=("milk",))
        milk = self.lists.get_list(shopping["id"])["items"][0]["id"]
        self.lists.check_items(True, item_ids=[milk])
        result = self.lists.add_items(shopping["id"], ["Milk", "eggs", "EGGS"])
        self.assertEqual([i["text"] for i in result["added"]], ["eggs"])  # The repeated one in the same batch is not twice.
        self.assertEqual(result["duplicates"], [{"id": milk, "text": "milk", "done": True}])
        self.assertTrue(self.lists.get_item(milk)["done"])  # Nothing was reopened.

    def test_23_the_same_text_can_be_in_two_lists(self):
        a, b = self.make("A", items=("milk",)), self.make("B", items=("milk",))
        self.assertEqual(len(self.lists.get_list(a["id"])["items"]), 1)
        self.assertEqual(len(self.lists.get_list(b["id"])["items"]), 1)

    def test_24_a_duplicate_is_found_in_a_translation_too(self):
        shopping = self.make(items=("milk",))
        item = self.lists.get_list(shopping["id"])["items"][0]["id"]
        self.lists.db.connection.execute(
            "INSERT INTO list_item_translation (item_id, language, text, text_key) VALUES (?, 'de', 'Milch', 'milch')", (item,))
        self.lists.db.connection.commit()
        self.assertEqual(self.lists.add_items(shopping["id"], ["milch"])["duplicates"][0]["id"], item)

    def test_25_items_come_open_first_then_done_each_by_creation(self):
        shopping = self.make(items=())
        ids = [self.lists.add_items(shopping["id"], [text])["added"][0]["id"] for text in ("a", "b", "c", "d")]
        self.lists.check_items(True, item_ids=[ids[0], ids[2]])
        self.assertEqual(self.texts(shopping["id"]), [("b", False), ("d", False), ("a", True), ("c", True)])

    def test_26_updating_an_item(self):
        shopping = self.make(items=("milk", "bread"))
        milk, bread = [i["id"] for i in self.lists.get_list(shopping["id"])["items"]]
        result = self.lists.update_item(milk, "oat milk")
        self.assertTrue(result["updated"])
        self.assertEqual(result["item"]["text"], "oat milk")
        # Another item has that text: nothing changes and it says which.
        clash = self.lists.update_item(milk, "BREAD")
        self.assertFalse(clash["updated"])
        self.assertEqual(clash["duplicate"]["id"], bread)
        self.assertEqual(self.lists.get_item(milk)["text"], "oat milk")
        # Only the case changes: it is the same item, not a duplicate.
        self.assertTrue(self.lists.update_item(milk, "Oat Milk")["updated"])
        self.assertIs(self.lists.update_item(999, "x"), False)

    def test_27_updating_an_item_drops_its_translations(self):
        shopping = self.make(items=("milk",))
        item = self.lists.get_list(shopping["id"])["items"][0]["id"]
        self.lists.db.connection.execute(
            "INSERT INTO list_item_translation (item_id, language, text, text_key) VALUES (?, 'de', 'Milch', 'milch')", (item,))
        self.lists.db.connection.commit()
        self.lists.update_item(item, "oat milk")
        self.assertEqual(self.lists.db.connection.execute("SELECT COUNT(*) FROM list_item_translation").fetchone()[0], 0)

    # ----- done -----

    def test_30_check_and_uncheck_by_id_tell_what_changed(self):
        shopping = self.make(items=("a", "b"))
        a, b = [i["id"] for i in self.lists.get_list(shopping["id"])["items"]]
        result = self.lists.check_items(True, item_ids=[a, a, 999])
        self.assertEqual((result["changed"], result["unchanged"], result["missing"], result["list_ids"]), ([a], [a], [999], [shopping["id"]]))
        self.assertIsNotNone(self.lists.db.connection.execute("SELECT done_at FROM list_item WHERE id = ?", (a,)).fetchone()[0])
        self.assertEqual(self.lists.check_items(False, item_ids=[a, b])["changed"], [a])
        self.assertIsNone(self.lists.db.connection.execute("SELECT done_at FROM list_item WHERE id = ?", (a,)).fetchone()[0])

    def test_31_a_whole_list_can_be_reset(self):
        shopping = self.make(items=("a", "b", "c"))
        everything = [i["id"] for i in self.lists.get_list(shopping["id"])["items"]]
        self.lists.check_items(True, item_ids=everything)
        result = self.lists.check_items(False, list_id=shopping["id"])
        self.assertEqual(result["changed"], everything)
        self.assertEqual({done for _, done in self.texts(shopping["id"])}, {False})

    def test_32_check_needs_the_items_or_the_list_but_not_both(self):
        shopping = self.make()
        with self.assertRaises(ValueError):
            self.lists.check_items(True)
        with self.assertRaises(ValueError):
            self.lists.check_items(True, item_ids=[1], list_id=shopping["id"])
        self.assertIs(self.lists.check_items(True, list_id=999), False)

    # ----- soft deletes -----

    def test_40_removed_items_are_hidden_and_can_be_restored(self):
        shopping = self.make(items=("a", "b"))
        a, b = [i["id"] for i in self.lists.get_list(shopping["id"])["items"]]
        result = self.lists.remove_items([a, 999])
        self.assertEqual([i["id"] for i in result["removed"]], [a])
        self.assertEqual(result["missing"], [999])
        self.assertEqual(self.texts(shopping["id"]), [("b", False)])
        self.assertIs(self.lists.get_item(a), False)
        self.assertEqual([i["text"] for i in self.lists.get_removed_items(shopping["id"])], ["a"])
        restored = self.lists.restore_items([a, b])  # b was never removed.
        self.assertEqual([i["id"] for i in restored["restored"]], [a])
        self.assertEqual(restored["missing"], [b])
        self.assertEqual(self.texts(shopping["id"]), [("a", False), ("b", False)])  # Back in its place: creation order.

    def test_41_a_removed_text_can_be_added_again_and_then_the_old_one_does_not_come_back(self):
        shopping = self.make(items=("milk",))
        old = self.lists.get_list(shopping["id"])["items"][0]["id"]
        self.lists.remove_items([old])
        self.assertEqual(len(self.lists.add_items(shopping["id"], ["milk"])["added"]), 1)
        restored = self.lists.restore_items([old])
        self.assertEqual(restored["restored"], [])
        self.assertEqual(len(restored["duplicates"]), 1)

    def test_42_a_deleted_list_is_hidden_with_its_items_and_comes_back_with_them(self):
        shopping = self.make()
        deleted = self.lists.delete_list(shopping["id"])
        self.assertEqual((deleted["name"], deleted["items"]), ("Shopping list", 2))
        self.assertIs(self.lists.get_list(shopping["id"]), False)
        self.assertEqual(self.lists.get_lists(), [])
        self.assertIs(self.lists.add_items(shopping["id"], ["x"]), False)
        self.assertIsNone(self.lists.resolve_list("shopping list")["list"])
        found = self.lists.resolve_list("shopping list", deleted=True)["list"]
        self.assertEqual(found["id"], shopping["id"])
        self.assertTrue(self.lists.restore_list(shopping["id"])["restored"])
        self.assertEqual(self.texts(shopping["id"]), [("milk", False), ("bread", False)])

    def test_43_the_name_of_a_deleted_list_can_be_used_again_and_then_it_is_not_restored(self):
        old = self.make("Shopping list")
        self.lists.delete_list(old["id"])
        new = self.lists.create_list("Shopping list")
        self.assertTrue(new["created"])
        self.assertNotEqual(new["list"]["id"], old["id"])
        result = self.lists.restore_list(old["id"])
        self.assertFalse(result["restored"])
        self.assertEqual(result["conflict"]["id"], new["list"]["id"])

    def test_44_restoring_what_is_not_deleted_is_false(self):
        shopping = self.make()
        self.assertIs(self.lists.restore_list(shopping["id"]), False)
        self.assertIs(self.lists.restore_list(999), False)

    def test_45_items_of_a_deleted_list_are_not_restored_alone(self):
        shopping = self.make(items=("a",))
        a = self.lists.get_list(shopping["id"])["items"][0]["id"]
        self.lists.remove_items([a])
        self.lists.delete_list(shopping["id"])
        self.assertEqual(self.lists.restore_items([a])["missing"], [a])

    # ----- copies -----

    def test_50_copy_takes_the_items_open_with_their_translations_and_leaves_the_rest(self):
        source = self.make("Weekly", items=("milk", "bread", "eggs"))
        self.lists.update_list(source["id"], new_description="every week", favourite=True)
        milk, bread, eggs = [i["id"] for i in self.lists.get_list(source["id"])["items"]]
        self.lists.check_items(True, item_ids=[milk])
        self.lists.remove_items([eggs])
        self.lists.db.connection.execute(
            "INSERT INTO list_item_translation (item_id, language, text, text_key) VALUES (?, 'de', 'Milch', 'milch')", (milk,))
        self.lists.db.connection.commit()

        copy = self.lists.create_list("Next week", copy_from_id=source["id"])
        self.assertEqual(copy["copied"], 2)
        self.assertEqual(copy["list"]["description"], "every week")
        self.assertFalse(copy["list"]["favourite"])
        self.assertEqual(self.texts(copy["list"]["id"]), [("milk", False), ("bread", False)])  # Reset, without the removed one.
        self.assertEqual(self.texts(source["id"]), [("bread", False), ("milk", True)])           # The source is as it was.
        self.assertEqual(self.texts(copy["list"]["id"], "de")[0], ("Milch", False))

    def test_51_copying_from_a_missing_list_is_an_error_and_creates_nothing(self):
        with self.assertRaises(ValueError):
            self.lists.create_list("Next week", copy_from_id=999)
        self.assertEqual(self.lists.get_lists(), [])

    def test_52_copy_and_new_items_together(self):
        source = self.make("Weekly", items=("milk",))
        copy = self.lists.create_list("Next", copy_from_id=source["id"], items=["Milk", "tea"])
        self.assertEqual([i["text"] for i in copy["added"]], ["tea"])
        self.assertEqual(len(copy["duplicates"]), 1)

    # ----- translations on reading -----

    def test_60_reading_in_a_language_uses_the_translations_and_says_what_is_missing(self):
        shopping = self.make(items=("milk", "bread"))
        milk = self.lists.get_list(shopping["id"])["items"][0]["id"]
        connection = self.lists.db.connection
        connection.execute("INSERT INTO list_item_translation (item_id, language, text, text_key) VALUES (?, 'de', 'Milch', 'milch')", (milk,))
        connection.execute("INSERT INTO list_translation (list_id, language, name, name_key) VALUES (?, 'de', 'Einkaufsliste', 'einkaufsliste')", (shopping["id"],))
        connection.commit()
        german = self.lists.get_list(shopping["id"], "de")
        self.assertEqual(german["name"], "Einkaufsliste")
        self.assertEqual([i["text"] for i in german["items"]], ["Milch", "bread"])  # What is not translated yet, in its language.
        self.assertEqual(german["untranslated"], 1)
        english = self.lists.get_list(shopping["id"], "en")  # The language it was written in: nothing to translate.
        self.assertEqual((english["name"], english["untranslated"]), ("Shopping list", 0))
        self.assertEqual(self.lists.get_lists("de")[0]["name"], "Einkaufsliste")

    # ----- the database -----

    def test_70_deleting_a_row_for_good_cascades_to_items_and_translations(self):
        shopping = self.make(items=("milk",))
        item = self.lists.get_list(shopping["id"])["items"][0]["id"]
        connection = self.lists.db.connection
        connection.execute("INSERT INTO list_item_translation (item_id, language, text, text_key) VALUES (?, 'de', 'Milch', 'milch')", (item,))
        connection.execute("INSERT INTO list_translation (list_id, language, name, name_key) VALUES (?, 'de', 'E', 'e')", (shopping["id"],))
        connection.commit()
        connection.execute("DELETE FROM list WHERE id = ?", (shopping["id"],))
        connection.commit()
        for table in ("list_item", "list_item_translation", "list_translation"):
            self.assertEqual(connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0], 0, table)

    def test_71_a_failure_in_the_middle_saves_nothing(self):
        shopping = self.make(items=("a",))
        original = self.lists._item_dict
        self.lists._item_dict = lambda row: 1 / 0
        try:
            with self.assertRaises(ZeroDivisionError):
                self.lists.remove_items([self.lists.get_list(shopping["id"])["items"][0]["id"]])
        finally:
            self.lists._item_dict = original
        self.assertEqual(self.texts(shopping["id"]), [("a", False)])

    def test_72_the_migration_is_the_version_5(self):
        self.assertEqual(self.lists.db.connection.execute("PRAGMA user_version").fetchone()[0], 5)


if __name__ == "__main__":
    unittest.main()
