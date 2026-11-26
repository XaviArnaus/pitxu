"""What surrounds the lists: the prompt for the chatbot, the language keys that the code uses, and the doc."""
import os
import re
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from support import *  # noqa: F401,F403

LANGUAGES = ["ca", "es", "en", "de"]
TOOLS = ["get_lists", "create_list", "update_list", "delete_list", "add_items", "update_item", "check_items", "remove_items", "restore"]


class PromptTests(unittest.TestCase):

    def instruction(self, **overrides):
        Holder = methods_of("pitxu/lib/chatbot/gemini_chatbot.py", ["_lists_instruction"])
        holder = Holder()
        holder._xconfig = cfg(tempfile.mkdtemp(), **overrides)
        return holder._lists_instruction()

    def test_the_instruction_is_in_the_config_and_has_no_placeholder(self):
        text = self.instruction()
        self.assertIn("# Lists", text)
        self.assertNotIn("%", text)

    def test_every_tool_the_instruction_names_exists(self):
        names = set(re.findall(r"`(\w+)", self.instruction())) & set(re.findall(r"\b[a-z]+_[a-z_]+\b", self.instruction()))
        self.assertTrue({"add_items", "create_list", "check_items", "get_lists"} <= names)
        self.assertTrue(names <= set(TOOLS) | {"done"}, names - set(TOOLS))

    def test_it_can_be_emptied(self):
        self.assertEqual(self.instruction(**{"chatbot.lists_instruction": ""}), "")

    def test_it_is_the_last_thing_added_to_the_system_instruction(self):
        source = read_file(os.path.join(REPO, "pitxu/lib/chatbot/gemini_chatbot.py"))
        self.assertIn("+ emotion_instruction + memory_autonomy_instruction + lists_instruction,", source)


class LanguageKeysTests(unittest.TestCase):

    def test_every_message_the_code_uses_is_in_the_four_languages(self):
        source = read_file(os.path.join(REPO, "pitxu/lib/command/stateful/lists.py"))
        used = set(re.findall(r'_message\("(\w+)"\)', source))
        block = read_yaml(os.path.join(REPO, "config", "language.yaml.dist"))["language"]["lists"]
        self.assertTrue(used)
        for key in used:
            self.assertIn(key, block, key)
            self.assertEqual(sorted(block[key]), sorted(LANGUAGES), key)

    def test_the_messages_with_a_placeholder_have_the_same_ones_in_every_language(self):
        block = read_yaml(os.path.join(REPO, "config", "language.yaml.dist"))["language"]["lists"]
        for key, texts in block.items():
            counts = {language: text.count("%s") for language, text in texts.items()}
            self.assertEqual(len(set(counts.values())), 1, (key, counts))


class DocTests(unittest.TestCase):

    def test_the_doc_names_every_setting_and_tool(self):
        doc = read_file(os.path.join(REPO, "docs", "lists.md"))
        for block, settings in read_yaml(os.path.join(REPO, "config", "main.yaml.dist"))["lists"].items():
            for key in settings:
                self.assertIn(f"lists.{block}.{key}", doc)
        for tool in TOOLS:
            self.assertIn(f"`{tool}", doc)

    def test_the_changelog_and_the_doc_know_the_translation_command(self):
        self.assertIn("translate_lists", read_file(os.path.join(REPO, "docs", "lists.md")))
        self.assertIn("translate_lists", read_file(os.path.join(REPO, "CHANGELOG.md")))


if __name__ == "__main__":
    unittest.main()
