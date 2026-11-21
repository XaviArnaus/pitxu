"""The chatbot using the memory on its own: the notification of what it wrote, and the autonomy instruction."""
import ast
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from support import *  # noqa: F401,F403


class FakeCanvas:
    FONT_SIZE_MEDIUM = 20
    FONT_SIZE_BIG = 30


class FakeInteraction:
    """ Keeps what was asked to be shown, and where. """
    def __init__(self):
        self.calls = []

    def get_canvas_from_foreground_display(self): return FakeCanvas()
    def show_arbitrary_text_on_foreground(self, **kwargs): self.calls.append(("top_right", kwargs))
    def show_text_block_on_foreground_while_speaking(self, text, **kwargs): self.calls.append(("overall", {"text": text}))
    def show_error(self, text, **kwargs): self.calls.append(("error", {"text": text}))


class NotificationTests(unittest.TestCase):

    def setUp(self):
        self.tmp, self.config, self.writer, self.consolidator = env()
        self.tools = tools(self.config)
        self.log = Log()

    def _react(self, function_name, value, tools_instance=None):
        """ What the application does when the chatbot called the tool: runs the callback of that tool. """
        interaction = FakeInteraction()
        callback = (tools_instance or self.tools).get_callback_by_given_function_name(function_name)
        callback(self.log, interaction, value, {})
        return interaction.calls

    def test_a_new_entry_is_notified_in_the_top_right_with_its_summary(self):
        entry = self.tools.create_memory_entry("New dog", "Rex is the dog")
        calls = self._react("create_memory_entry", entry)
        self.assertEqual(len(calls), 1)
        where, shown = calls[0]
        self.assertEqual(where, "top_right")
        self.assertEqual(shown["header"], "Saved to memory")
        self.assertEqual(shown["text"], "New dog")
        self.assertEqual(shown["icon"], "🧠")

    def test_an_update_is_notified_with_its_summary(self):
        entry = self.tools.create_memory_entry("New dog", "Rex is the dog")
        updated = self.tools.update_memory_entry_by_id(entry["id"], summary="New dog: Rex", content="Rex, a labrador")
        for function_name in ("update_memory_entry_by_id", "update_last_memory_entry"):
            where, shown = self._react(function_name, updated)[0]
            self.assertEqual((where, shown["header"], shown["text"]), ("top_right", "Memory updated", "New dog: Rex"))

    def test_the_correction_of_a_long_term_entry_says_it_is_pending(self):
        long_id = [x for x in self.tools.get_memory_entries_by_summary("vehicles") if x["id"].startswith("L:")][0]["id"]
        correction = self.tools.update_memory_entry_by_id(long_id, summary="Vehicles: sold the moto", content="The moto was sold.")
        where, shown = self._react("update_memory_entry_by_id", correction)[0]
        self.assertEqual((where, shown["header"], shown["text"]), ("top_right", "Correction pending", "Vehicles: sold the moto"))

    def test_forgetting(self):
        long_id = [x for x in self.tools.get_memory_entries_by_summary("vehicles") if x["id"].startswith("L:")][0]["id"]
        registered = self.tools.forget_memory_entry(long_id)
        where, shown = self._react("forget_memory_entry", registered)[0]
        self.assertEqual(shown["header"], "Forget request registered")
        self.assertFalse(shown["text"].startswith("FORGET REQUEST"), "the technical prefix is not shown")
        self.assertIn("Vehicles", shown["text"])
        short = self.tools.create_memory_entry("temp", "x")
        deleted = self.tools.forget_memory_entry(short["id"])
        self.assertEqual(self._react("forget_memory_entry", deleted)[0][1]["header"], "Forgotten")

    def test_the_label_follows_the_language_of_the_session(self):
        spanish = tools(self.config, "es")
        entry = spanish.create_memory_entry("Perro nuevo", "Rex")
        self.assertEqual(self._react("create_memory_entry", entry, spanish)[0][1]["header"], "Guardado en la memoria")

    def test_an_error_is_shown_as_an_error(self):
        calls = self._react("create_memory_entry", "I'm sorry, there was an error creating the memory entry.")
        self.assertEqual(calls, [("error", {"text": "I'm sorry, there was an error creating the memory entry."})])

    def test_reading_still_uses_the_overall_screen(self):
        entries = self.tools.get_memory_entries_by_summary("vehicles")
        for function_name in ("get_memory_entries_by_summary", "get_memory_entries_by_date", "get_memory_entry_by_id",
                              "get_last_five_memory_entries"):
            calls = self._react(function_name, entries)
            self.assertEqual([where for where, _ in calls], ["overall"], function_name)

    def test_every_tool_has_a_callback(self):
        for tool in self.tools.get_tool_definition():
            self.assertTrue(callable(self.tools.get_callback_by_given_function_name(tool.__name__)), tool.__name__)


def _load_method(relative_path: str, name: str):
    """ A method of a class of the application, without importing the module (it needs the whole stack). """
    with open(os.path.join(REPO, relative_path)) as handle:
        tree = ast.parse(handle.read())
    function = next(node for node in ast.walk(tree) if isinstance(node, ast.FunctionDef) and node.name == name)
    module = ast.Module(body=[ast.ClassDef(name="Holder", bases=[], keywords=[], body=[function], decorator_list=[], type_params=[])],
                        type_ignores=[])
    ast.fix_missing_locations(module)
    namespace = {}
    exec(compile(module, relative_path, "exec"), namespace)
    return namespace["Holder"]


class AutonomyInstructionTests(unittest.TestCase):

    def _instruction(self, **overrides):
        holder = _load_method("pitxu/lib/chatbot/gemini_chatbot.py", "_memory_autonomy_instruction")()
        holder._xconfig = cfg(tempfile.mkdtemp(), **overrides)
        return holder._memory_autonomy_instruction()

    def test_it_is_added_by_default(self):
        instruction = self._instruction()
        self.assertIn("YOUR memory", instruction)
        self.assertIn("Never save passwords, tokens, API keys", instruction)

    def test_it_can_be_turned_off(self):
        self.assertEqual(self._instruction(**{"chatbot.memory_autonomy": False}), "")

    def test_without_text_nothing_is_added(self):
        self.assertEqual(self._instruction(**{"chatbot.memory_autonomy_instruction": ""}), "")

    def test_no_prompt_asks_for_confirmation_to_use_the_memory_any_more(self):
        config = cfg(tempfile.mkdtemp())
        for language in ("ca", "es", "en", "de"):
            prompt = config.get(f"chatbot.system_instruction.{language}")
            self.assertIn("forget_memory_entry", prompt)
        english = config.get("chatbot.system_instruction.en")
        critical_line = next(line for line in english.splitlines() if "critical system tasks" in line)
        self.assertNotIn("memory", critical_line)
        self.assertNotIn("ask the user for confirmation and use `forget_memory_entry`", english)

    def test_the_instruction_has_no_percent_sign(self):
        """ The system instruction goes through `%`: a stray one would break the chatbot at startup. """
        self.assertNotIn("%", cfg(tempfile.mkdtemp()).get("chatbot.memory_autonomy_instruction"))


if __name__ == "__main__":
    unittest.main()
