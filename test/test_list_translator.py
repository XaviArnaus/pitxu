"""The night translation of the lists: what is missing, the batches, what the LLM gives back is checked, edits are translated again."""
import json
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from support import *  # noqa: F401,F403
from test_lists_storage import store  # noqa: E402
from pitxu.lib.utils.list_translator import ListTranslator  # noqa: E402

LANGUAGES = ["en", "ca", "de", "es"]


class FakeLlm:
    """ The LLM: `answer(elements)` gives the translations for the elements that were asked. The prompts are kept. """

    def __init__(self, answer=None):
        self.prompts, self.models, self.answer = [], [], answer or self.translate_everything

    @staticmethod
    def translate_everything(elements):
        return [{"kind": e["kind"], "id": e["id"], "language": language,
                 "text": f"{e['text']}[{language}]", "description": f"{e['description']}[{language}]" if e["description"] else ""}
                for e in elements for language in e["targets"]]

    def request(self, prompt, schema, model=None, purpose="request", settings=None):
        self.prompts.append(prompt)
        self.models.append((model, settings, purpose))
        elements = json.loads(prompt.split("# Input\n", 1)[1])
        reply = self.answer(elements)
        return None if reply is None else json.dumps({"translations": reply})


class TranslatorTests(unittest.TestCase):

    def setUp(self):
        self.tmp, self.config, self.lists = store()
        self.addCleanup(self.lists.close)
        self.llm = FakeLlm()
        self.aborted = False

    def translator(self, **overrides):
        for key, value in overrides.items():
            self.config.set(key, value)
        return ListTranslator(config=self.config, params=params(), lists=self.lists, llm=self.llm,
                              should_abort=lambda: self.aborted)

    def shopping(self, items=("milk", "bread"), language="en"):
        created = self.lists.create_list("Shopping list", language=language, items=list(items))
        return created["list"]

    def rows(self, sql):
        return [tuple(r) for r in self.lists.db.connection.execute(sql).fetchall()]

    # ----- what is missing -----

    def test_01_every_text_misses_the_languages_but_its_own(self):
        shopping = self.shopping(items=("milk",))
        pending = self.lists.get_untranslated(LANGUAGES)
        self.assertEqual([(e["kind"], e["targets"]) for e in pending], [("list", ["ca", "de", "es"]), ("item", ["ca", "de", "es"])])
        self.assertEqual(pending[0]["id"], shopping["id"])

    def test_02_what_is_already_translated_is_not_asked_again(self):
        self.shopping(items=("milk",))
        self.translator().run()
        self.assertEqual(self.lists.get_untranslated(LANGUAGES), [])

    def test_03_removed_items_and_deleted_lists_are_not_translated(self):
        shopping = self.shopping(items=("milk", "bread"))
        milk = self.lists.get_list(shopping["id"])["items"][0]["id"]
        self.lists.remove_items([milk])
        other = self.lists.create_list("Books", items=["novel"])["list"]
        self.lists.delete_list(other["id"])
        pending = self.lists.get_untranslated(LANGUAGES)
        self.assertEqual([(e["kind"], e["text"]) for e in pending], [("list", "Shopping list"), ("item", "bread")])

    def test_04_an_unknown_language_is_translated_into_all_of_them(self):
        shopping = self.shopping(items=("milk",), language=None)
        self.lists.db.connection.execute("UPDATE list_item SET language = NULL")
        self.lists.db.connection.commit()
        item = [e for e in self.lists.get_untranslated(LANGUAGES) if e["kind"] == "item"][0]
        self.assertEqual((item["source_language"], item["targets"]), (None, LANGUAGES))

    # ----- the run -----

    def test_10_names_descriptions_and_items_are_translated_and_read_back(self):
        shopping = self.shopping()
        self.lists.update_list(shopping["id"], new_description="weekly")
        stats = self.translator().run()
        self.assertEqual((stats["lists_translated"], stats["items_translated"], stats["failed"]), (3, 6, 0))
        german = self.lists.get_list(shopping["id"], "de")
        self.assertEqual((german["name"], german["description"], german["untranslated"]), ("Shopping list[de]", "weekly[de]", 0))
        self.assertEqual([i["text"] for i in german["items"]], ["milk[de]", "bread[de]"])

    def test_11_the_prompt_carries_the_elements_and_the_model_and_settings_of_the_lists(self):
        self.shopping(items=("milk",))
        self.translator().run()
        elements = json.loads(self.llm.prompts[0].split("# Input\n", 1)[1])
        self.assertEqual(elements[0], {"kind": "list", "id": 1, "source_language": "en", "text": "Shopping list",
                                       "description": "", "targets": ["ca", "de", "es"]})
        self.assertEqual(self.llm.models[0], ("gemini-3.1-flash-lite", ["lists.translation"], "lists translation"))

    def test_12_another_model_can_be_configured_and_empty_is_the_default_of_llm_json(self):
        self.shopping(items=())
        self.translator(**{"lists.translation.model": "list-model"}).run()
        self.assertEqual(self.llm.models[0][0], "list-model")
        self.translator(**{"lists.translation.model": ""}).run()  # Nothing missing now: add something to ask again.
        self.lists.create_list("Books")
        self.translator(**{"lists.translation.model": ""}).run()
        self.assertIsNone(self.llm.models[-1][0])

    def test_13_batches(self):
        self.shopping(items=[f"item {n}" for n in range(5)])  # The list and 5 items.
        stats = self.translator(**{"lists.translation.batch_size": 2}).run()
        self.assertEqual((stats["batches"], len(self.llm.prompts)), (3, 3))
        self.assertEqual(stats["items_translated"], 15)

    def test_14_a_second_run_asks_for_nothing(self):
        self.shopping()
        translator = self.translator()
        translator.run()
        asked = len(self.llm.prompts)
        stats = translator.run()
        self.assertEqual((len(self.llm.prompts), stats["batches"]), (asked, 0))

    def test_15_edited_texts_are_translated_again_and_only_those(self):
        shopping = self.shopping()
        milk, bread = [i["id"] for i in self.lists.get_list(shopping["id"])["items"]]
        translator = self.translator()
        translator.run()
        self.lists.update_item(milk, "oat milk")
        self.lists.update_list(shopping["id"], new_name="Groceries")
        translator.run()
        german = self.lists.get_list(shopping["id"], "de")
        self.assertEqual((german["name"], [i["text"] for i in german["items"]]), ("Groceries[de]", ["oat milk[de]", "bread[de]"]))
        asked = json.loads(self.llm.prompts[-1].split("# Input\n", 1)[1])
        self.assertEqual(sorted((e["kind"], e["id"]) for e in asked), [("item", milk), ("list", shopping["id"])])

    def test_16_a_text_that_is_already_in_the_target_language_comes_back_the_same(self):
        shopping = self.shopping(items=("Milch",))  # German, written in an English session.
        self.llm.answer = lambda elements: [
            {"kind": e["kind"], "id": e["id"], "language": language, "text": "Milch" if e["text"] == "Milch" else e["text"],
             "description": ""} for e in elements for language in e["targets"]]
        self.translator().run()
        self.assertEqual(self.lists.get_list(shopping["id"], "de")["items"][0]["text"], "Milch")
        self.assertEqual(self.lists.add_items(shopping["id"], ["milch"])["duplicates"][0]["text"], "Milch")

    # ----- what the LLM gives back is checked -----

    def test_20_what_is_not_valid_is_ignored_and_counted_as_failed(self):
        shopping = self.shopping(items=("milk",))
        item = self.lists.get_list(shopping["id"])["items"][0]["id"]
        self.llm.answer = lambda elements: [
            {"kind": "item", "id": item, "language": "de", "text": "Milch", "description": ""},   # Good.
            {"kind": "item", "id": item, "language": "de", "text": "Milch again", "description": ""},  # Twice.
            {"kind": "item", "id": item, "language": "fr", "text": "lait", "description": ""},   # Not a target.
            {"kind": "item", "id": item, "language": "es", "text": "  ", "description": ""},     # Empty.
            {"kind": "item", "id": 999, "language": "ca", "text": "x", "description": ""},       # Not asked.
            "garbage"]
        stats = self.translator().run()
        self.assertEqual(stats["items_translated"], 1)
        self.assertEqual(stats["failed"], 5)  # Of the 6 asked (3 for the list, 3 for the item) only one was given.
        self.assertEqual(self.rows("SELECT language, text FROM list_item_translation"), [("de", "Milch")])
        self.assertEqual(len(self.lists.get_untranslated(LANGUAGES)), 2)  # They are asked again the next night.

    def test_21_an_answer_that_is_not_json_or_no_answer_fails_the_batch_and_keeps_everything_missing(self):
        self.shopping(items=("milk",))
        self.llm.answer = lambda elements: None
        stats = self.translator().run()
        self.assertEqual((stats["failed"], stats["items_translated"]), (6, 0))
        self.llm.request = lambda *a, **k: "not json"
        stats = self.translator().run()
        self.assertEqual(stats["failed"], 6)
        self.assertEqual(self.rows("SELECT COUNT(*) FROM list_item_translation"), [(0,)])

    def test_22_a_text_edited_while_translating_is_not_given_the_old_translation(self):
        shopping = self.shopping(items=("milk",))
        item = self.lists.get_list(shopping["id"])["items"][0]["id"]

        def answer(elements):
            self.lists.update_item(item, "oat milk")  # The user edits it while the LLM works.
            return self.llm.translate_everything(elements)

        self.llm.answer = answer
        stats = self.translator().run()
        self.assertEqual(stats["stale"], 3)
        self.assertEqual(self.rows("SELECT COUNT(*) FROM list_item_translation"), [(0,)])
        self.assertEqual(self.rows("SELECT COUNT(*) FROM list_translation"), [(3,)])  # The list was not edited.

    def test_23_a_translated_name_that_is_the_name_of_another_list_is_not_stored(self):
        self.lists.create_list("Compra")
        shopping = self.shopping(items=())
        self.llm.answer = lambda elements: [
            {"kind": "list", "id": e["id"], "language": "ca", "text": "Compra", "description": ""}
            for e in elements if e["kind"] == "list" and e["text"] == "Shopping list"]
        stats = self.translator().run()
        self.assertEqual(stats["collisions"], 1)
        self.assertEqual(self.rows("SELECT COUNT(*) FROM list_translation WHERE list_id = %d" % shopping["id"]), [(0,)])
        self.assertEqual(self.lists.resolve_list("compra")["list"]["name"], "Compra")  # Still found as what it is.

    # ----- running it -----

    def test_30_disabled_without_key_or_prompt_it_does_not_run(self):
        self.shopping()
        self.assertIsNone(self.translator(**{"lists.translation.enabled": False}).run())
        self.config.set("lists.translation.enabled", True)
        no_key = ListTranslator(config=self.config, params=Dictionary({"base_path": REPO}), lists=self.lists, llm=self.llm)
        self.assertIsNone(no_key.run())
        self.config.set("lists.translation.prompt", "")
        self.assertIsNone(self.translator().run())
        self.assertEqual(self.llm.prompts, [])

    def test_31_it_gives_way_when_something_is_waiting_and_continues_later(self):
        self.shopping(items=[f"item {n}" for n in range(4)])
        self.aborted = True
        stats = self.translator(**{"lists.translation.batch_size": 2}).run()
        self.assertEqual((stats["aborted"], stats["batches"], self.llm.prompts), (True, 0, []))
        self.aborted = False
        self.translator().run()
        self.assertEqual(self.lists.get_untranslated(LANGUAGES), [])

    def test_32_the_night_config_defaults_of_the_dist(self):
        block = read_yaml(os.path.join(REPO, "config", "main.yaml.dist"))["lists"]["translation"]
        self.assertEqual((block["enabled"], block["batch_size"]), (True, ListTranslator.BATCH_SIZE))
        self.assertEqual((block["retries"], block["backoff_seconds"]), (3, 5))
        self.assertIn("%s", block["prompt"])


if __name__ == "__main__":
    unittest.main()
