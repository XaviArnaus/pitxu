"""What the lists show on the foreground screen: read from the database, the items touched marked, a window for long lists."""
import logging
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from support import *  # noqa: F401,F403
from test_lists_storage import store  # noqa: E402
from pitxu.lib.command.stateful.lists import StatefulLists  # noqa: E402


class Canvas:
    FONT_SIZE_MEDIUM, FONT_SIZE_BIG, FONT_SIZE_HUGE = 24, 32, 48


class Screen:
    """ The interaction: what was asked to show, as the keyword arguments of the call. """
    def __init__(self): self.shown = []
    def get_canvas_from_foreground_display(self): return Canvas()
    def show_arbitrary_text_on_foreground_while_speaking(self, **kwargs): self.shown.append(kwargs)


class ScreenTests(unittest.TestCase):

    def setUp(self):
        self.tmp, self.config, self.lists = store()
        self.addCleanup(self.lists.close)
        self.tools = StatefulLists(config=self.config, params=params(language="en", lists=self.lists))
        self.screen = Screen()
        self.log = logging.getLogger("pitxu_test")

    def run_tool(self, name, *args, **kwargs):
        """ Calls the tool and then its callback with the answer, like the chatbot does. Returns the answer. """
        value = getattr(self.tools, name)(*args, **kwargs)
        self.tools.get_callback_by_given_function_name(name)(self.log, self.screen, value, {})
        return value

    @property
    def last(self):
        return self.screen.shown[-1]

    def test_01_every_tool_has_a_callback_except_none(self):
        for tool in self.tools.get_tool_definition():
            self.assertNotEqual(self.tools.get_callback_by_given_function_name(tool.__name__), self.tools.default_empty_callback, tool.__name__)

    def test_01b_the_title_is_not_bigger_than_big(self):
        self.run_tool("create_list", "Shopping list", items=["milk"])
        self.assertEqual(self.last["font_header_size"], Canvas.FONT_SIZE_BIG)

    def test_02_creating_a_list_with_items_shows_it_with_the_new_ones_marked(self):
        self.run_tool("create_list", "Shopping list", items=["milk", "bread"])
        self.assertEqual(self.last["header"], "Shopping list")
        self.assertEqual(self.last["text"], "⬜ milk 👈\n⬜ bread 👈")
        self.assertEqual((self.last["icon"], self.last["align"], self.last["font_size"]), ("📝", "left", 24))

    def test_03_adding_marks_only_the_new_and_the_duplicates_that_were_there(self):
        self.run_tool("create_list", "Shopping list", items=["milk", "bread"])
        self.run_tool("add_items", "shopping", ["eggs", "Milk"])
        self.assertEqual(self.last["text"], "⬜ milk 👈\n⬜ bread\n⬜ eggs 👈")

    def test_04_checking_shows_the_status_and_marks_the_changed(self):
        self.run_tool("create_list", "Shopping list", items=["milk", "bread", "eggs"])
        milk = self.tools.get_lists("shopping")["items"][0][0]
        self.run_tool("check_items", True, item_ids=[milk])
        self.assertEqual(self.last["text"], "⬜ bread\n⬜ eggs\n✅ milk 👈")  # Open first, done at the end.
        self.run_tool("check_items", False, list_name="shopping")
        self.assertEqual(self.last["text"], "⬜ milk 👈\n⬜ bread\n⬜ eggs")

    def test_05_updating_an_item_marks_it_and_a_refused_one_marks_the_duplicate(self):
        self.run_tool("create_list", "Shopping list", items=["milk", "bread"])
        milk, bread = [i[0] for i in self.tools.get_lists("shopping")["items"]]
        self.run_tool("update_item", milk, "oat milk")
        self.assertEqual(self.last["text"], "⬜ oat milk 👈\n⬜ bread")
        self.run_tool("update_item", milk, "BREAD")
        self.assertEqual(self.last["text"], "⬜ oat milk\n⬜ bread 👈")

    def test_06_removing_shows_the_list_and_what_was_removed(self):
        self.run_tool("create_list", "Shopping list", items=["milk", "bread"])
        milk = self.tools.get_lists("shopping")["items"][0][0]
        self.run_tool("remove_items", [milk])
        self.assertEqual(self.last["text"], "⬜ bread\n🗑 Removed: milk")

    def test_07_removing_the_last_item_still_shows_what_happened(self):
        self.run_tool("create_list", "Shopping list", items=["milk"])
        self.run_tool("remove_items", [self.tools.get_lists("shopping")["items"][0][0]])
        self.assertEqual(self.last["text"], "🗑 Removed: milk")

    def test_08_an_empty_list_says_so(self):
        self.run_tool("create_list", "Shopping list")
        self.assertEqual(self.last["text"], "No items yet")
        self.assertEqual(self.last["align"], "center")

    def test_09_a_favourite_list_has_a_star_for_icon(self):
        self.run_tool("create_list", "Shopping list", items=["milk"])
        self.run_tool("update_list", "shopping", favourite=True)
        self.assertEqual((self.last["icon"], self.last["header"]), ("⭐", "Shopping list"))

    def test_10_the_lists_with_stars_and_open_counts(self):
        self.run_tool("create_list", "Shopping list", items=["milk", "bread"])
        self.run_tool("create_list", "Books")
        self.run_tool("update_list", "books", favourite=True)
        self.run_tool("get_lists")
        self.assertEqual(self.last["text"], "⭐ Books (0)\nShopping list (2)")
        self.assertEqual(self.last["header"], "Lists")

    def test_11_no_lists_says_so(self):
        self.run_tool("get_lists")
        self.assertEqual(self.last["text"], "No lists yet")

    def test_12_reading_one_list_shows_it_without_marks(self):
        self.run_tool("create_list", "Shopping list", items=["milk"])
        self.run_tool("get_lists", "shopping")
        self.assertEqual(self.last["text"], "⬜ milk")

    def test_13_a_deleted_list_says_so_and_the_trash_shows_what_can_come_back(self):
        self.run_tool("create_list", "Shopping list", items=["milk", "bread"])
        self.run_tool("delete_list", "Shopping list")
        self.assertEqual((self.last["text"], self.last["icon"]), ("List deleted: Shopping list", "🗑"))
        self.run_tool("restore", list_name="shopping list")
        self.assertEqual(self.last["text"], "⬜ milk\n⬜ bread")
        milk = self.tools.get_lists("shopping")["items"][0][0]
        self.run_tool("remove_items", [milk])
        self.run_tool("restore", list_name="shopping")  # Only to see the trash.
        self.assertEqual((self.last["header"], self.last["text"]), ("Shopping list", "🗑 milk"))
        self.run_tool("restore", item_ids=[milk])
        self.assertEqual(self.last["text"], "⬜ milk 👈\n⬜ bread")

    def test_14_an_error_is_shown_as_it_is(self):
        self.run_tool("add_items", "holidays", ["x"])
        self.assertIn("holidays", self.last["text"])
        self.assertEqual(self.last["align"], "center")

    def test_15_a_long_list_is_a_window_around_the_change_with_what_is_hidden(self):
        texts = [f"item {n:02d}" for n in range(1, 21)]
        self.run_tool("create_list", "Long", items=texts)
        self.assertEqual(self.last["text"].splitlines()[0], "⬜ item 01 👈")  # All new: the window starts at the top.
        self.assertEqual(self.last["text"].splitlines()[-1], "… +12")
        self.assertEqual(len(self.last["text"].splitlines()), 9)
        item = self.tools.get_lists("long")["items"][9][0]
        self.run_tool("check_items", True, item_ids=[item])  # Moves to the end: the window follows it.
        lines = self.last["text"].splitlines()
        self.assertEqual(lines[0], "… +12")
        self.assertEqual(lines[-1], "✅ item 10 👈")
        self.assertEqual(len(lines), 9)

    def test_16_a_window_in_the_middle_has_both_hidden_counts(self):
        self.run_tool("create_list", "Long", items=[f"item {n:02d}" for n in range(1, 21)])
        item = self.tools.get_lists("long")["items"][9][0]
        self.run_tool("update_item", item, "changed")
        lines = self.last["text"].splitlines()
        self.assertEqual((lines[0], lines[-1]), ("… +5", "… +7"))
        self.assertIn("⬜ changed 👈", lines)

    def test_17_the_texts_come_in_the_language_of_the_session(self):
        self.run_tool("create_list", "Shopping list", items=["milk"])
        item = self.tools.get_lists("shopping")["items"][0][0]
        self.lists.db.connection.execute(
            "INSERT INTO list_item_translation (item_id, language, text, text_key) VALUES (?, 'de', 'Milch', 'milch')", (item,))
        self.lists.db.connection.execute(
            "INSERT INTO list_translation (list_id, language, name, name_key) VALUES (1, 'de', 'Einkaufsliste', 'einkaufsliste')")
        self.lists.db.connection.commit()
        german = StatefulLists(config=self.config, params=params(language="de", lists=self.lists))
        german.show_list(self.log, self.screen, german.get_lists("einkaufsliste"), {})
        self.assertEqual((self.last["header"], self.last["text"]), ("Einkaufsliste", "⬜ Milch"))

    def test_18_a_failure_in_the_screen_does_not_raise(self):
        self.run_tool("create_list", "Shopping list", items=["milk"])
        self.lists.db.connection.close()
        self.tools.show_list(self.log, self.screen, {"list_id": 1}, {})  # It is only logged.


if __name__ == "__main__":
    unittest.main()
