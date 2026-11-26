"""The tools of the chatbot for lists: compact answers, items by id, names resolved, errors as messages in the language of the session."""
import inspect
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from support import *  # noqa: F401,F403
from test_lists_storage import store  # noqa: E402
from pitxu.lib.command.stateful.lists import StatefulLists  # noqa: E402


class ToolsTests(unittest.TestCase):

    def setUp(self):
        self.tmp, self.config, self.lists = store()
        self.addCleanup(self.lists.close)
        self.tools = StatefulLists(config=self.config, params=params(language="en", lists=self.lists))

    def message(self, key, language="en"):
        return self.config.get(f"language.lists.{key}.{language}")

    def shopping(self, items=("milk", "bread")):
        return self.tools.create_list("Shopping list", items=list(items))

    def ids(self, name="Shopping list"):
        return [i[0] for i in self.tools.get_lists(name)["items"]]

    def test_01_the_nine_tools_are_the_ones_of_the_plan(self):
        names = [tool.__name__ for tool in self.tools.get_tool_definition()]
        self.assertEqual(names, ["get_lists", "create_list", "update_list", "delete_list", "add_items", "update_item",
                                 "check_items", "remove_items", "restore"])
        for tool in self.tools.get_tool_definition():
            self.assertTrue(inspect.getdoc(tool), tool.__name__)

    def test_02_creating_a_list_with_items_answers_compactly(self):
        result = self.shopping()
        self.assertEqual(result["created"], True)
        self.assertEqual([text for _, text in result["added"]], ["milk", "bread"])
        self.assertNotIn("duplicates", result)

    def test_03_creating_one_that_exists_says_so_with_its_counts(self):
        self.shopping()
        again = self.tools.create_list("shopping LIST", items=["eggs"])
        self.assertEqual((again["created"], again["open"], again["done"]), (False, 2, 0))
        self.assertEqual(len(self.ids()), 2)  # Nothing was added to it.

    def test_04_copy_from_names_the_source_and_resets(self):
        self.shopping()
        self.tools.check_items(True, list_name="shopping")
        copy = self.tools.create_list("Next week", copy_from="shopping")
        self.assertEqual(copy["copied"], 2)
        self.assertEqual([i[2] for i in self.tools.get_lists("Next week")["items"]], [False, False])
        self.assertIsInstance(self.tools.create_list("Other", copy_from="holidays"), str)  # The source does not exist.

    def test_05_the_overview_and_one_list_with_its_items_as_triples(self):
        self.shopping()
        self.tools.create_list("Books")
        self.tools.update_list("Books", favourite=True)
        overview = self.tools.get_lists()
        self.assertEqual([(l["name"], l["open"], l["done"], l.get("favourite")) for l in overview],
                         [("Books", 0, 0, True), ("Shopping list", 2, 0, None)])
        full = self.tools.get_lists("shopping")
        self.assertEqual([i[1:] for i in full["items"]], [["milk", False], ["bread", False]])

    def test_06_a_list_that_does_not_exist_tells_which_do_and_how_to_create_it(self):
        self.shopping()
        answer = self.tools.add_items("holidays", ["x"])
        self.assertEqual(answer, self.message("list_not_found") % ("holidays", "Shopping list"))
        self.assertIn("create_list", answer)
        other = store()[2]
        self.addCleanup(other.close)
        empty = StatefulLists(config=self.config, params=params(language="en", lists=other))
        self.assertEqual(empty.get_lists("x"), self.message("list_not_found_empty") % "x")

    def test_07_adding_items_answers_with_ids_duplicates_and_the_count(self):
        self.shopping()
        milk = self.ids()[0]
        self.tools.check_items(True, item_ids=[milk])
        result = self.tools.add_items("shopping", ["Milk", "eggs"])
        self.assertEqual((result["list"], result["count"]), ("Shopping list", 3))
        self.assertEqual([text for _, text in result["added"]], ["eggs"])
        self.assertEqual(result["duplicates"], [[milk, "milk", True]])  # The chatbot asks whether to reopen it.

    def test_08_items_sent_as_one_string_or_with_text_ids_are_understood(self):
        self.shopping(items=())
        self.assertEqual(self.tools.add_items("shopping", "tea")["added"][0][1], "tea")
        item = self.ids()[0]
        self.assertEqual(self.tools.check_items(True, item_ids=str(item))["changed"], [item])
        self.assertEqual(self.tools.update_item(str(item), "green tea")["text"], "green tea")

    def test_09_updating_an_item(self):
        self.shopping()
        milk, bread = self.ids()
        self.assertEqual(self.tools.update_item(milk, "oat milk")["text"], "oat milk")
        self.assertEqual(self.tools.update_item(milk, "Bread"), {"updated": False, "duplicate": [bread, "bread", False]})
        self.assertEqual(self.tools.update_item(999, "x"), self.message("item_not_found") % 999)
        self.assertEqual(self.tools.update_item("abc", "x"), self.message("item_not_found") % "abc")

    def test_10_check_by_ids_or_by_list_never_both_never_none(self):
        self.shopping()
        milk, bread = self.ids()
        done = self.tools.check_items(True, item_ids=[milk, 999])
        self.assertEqual((done["changed"], done["missing"]), ([milk], [999]))
        self.assertNotIn("unchanged", done)
        reset = self.tools.check_items(False, list_name="shopping")
        self.assertEqual(reset["changed"], [milk])
        self.assertEqual(reset["unchanged"], [bread])
        needs = self.message("list_check_needs_target")
        self.assertEqual(self.tools.check_items(True), needs)
        self.assertEqual(self.tools.check_items(True, item_ids=[milk], list_name="shopping"), needs)

    def test_11_remove_and_restore_items(self):
        self.shopping()
        milk, bread = self.ids()
        removed = self.tools.remove_items([milk, 999])
        self.assertEqual((removed["removed"], removed["missing"]), ([[milk, "milk"]], [999]))
        self.assertEqual(self.tools.restore(list_name="shopping")["removed"], [[milk, "milk"]])  # To choose from.
        self.assertEqual(self.tools.restore(item_ids=[milk])["restored"], [[milk, "milk"]])
        self.assertEqual(len(self.ids()), 2)

    def test_12_restoring_with_nothing_to_go_by_is_a_message(self):
        self.assertEqual(self.tools.restore(), self.message("list_restore_needs_target"))

    def test_13_delete_needs_the_exact_name_and_restore_brings_it_back(self):
        self.shopping()
        self.tools.create_list("Shopping ideas")
        too_loose = self.tools.delete_list("shop")
        self.assertIsInstance(too_loose, str)
        self.assertIn("Shopping list", too_loose)  # It says which exist.
        deleted = self.tools.delete_list("Shopping list")
        self.assertEqual((deleted["name"], deleted["items"]), ("Shopping list", 2))
        self.assertEqual(self.tools.restore(list_name="shopping list")["restored"], "Shopping list")
        self.assertEqual(len(self.ids()), 2)

    def test_14_an_ambiguous_name_is_not_acted_on(self):
        self.shopping()
        self.tools.create_list("Shopping ideas")
        answer = self.tools.add_items("shopping", ["x"])
        self.assertEqual(answer, self.message("list_ambiguous") % ("shopping", "Shopping list, Shopping ideas"))

    def test_15_update_list_and_a_name_that_is_taken(self):
        self.shopping()
        self.tools.create_list("Books")
        self.assertEqual(self.tools.update_list("books", new_name="Reading")["changed"], ["name"])
        self.assertEqual(self.tools.update_list("Reading", new_name="shopping list"), self.message("list_name_taken") % "Shopping list")

    def test_16_a_name_is_needed_to_create(self):
        self.assertEqual(self.tools.create_list("  "), self.message("list_name_missing"))

    def test_17_errors_are_messages_in_the_language_of_the_session(self):
        self.shopping()
        catalan = StatefulLists(config=self.config, params=params(language="ca", lists=self.lists))
        self.assertEqual(catalan.update_item(999, "x"), self.message("item_not_found", "ca") % 999)

    def test_18_a_failing_database_is_a_message_not_an_exception(self):
        self.shopping()
        self.lists.db.connection.close()
        self.assertEqual(self.tools.get_lists(), self.message("list_retrieval_error"))
        self.assertEqual(self.tools.add_items("shopping", ["x"]), self.message("list_items_error"))

    def test_19_reading_in_a_language_marks_what_is_not_translated(self):
        self.shopping()
        german = self.tools.get_lists("shopping", language="DE")
        self.assertEqual(german["untranslated"], 3)  # The name and the two items.
        self.assertEqual(self.tools.get_lists(language="de")[0]["untranslated"], True)
        self.assertNotIn("untranslated", self.tools.get_lists("shopping", language="en"))

    def test_20_the_tool_descriptions_stay_short(self):
        # They travel with every request: the nine together must stay at or under what the ten old ones cost (about 714 tokens; 450 words are about 600).
        words = sum(len(inspect.getdoc(tool).split()) for tool in self.tools.get_tool_definition())
        self.assertLess(words, 450)


if __name__ == "__main__":
    unittest.main()
