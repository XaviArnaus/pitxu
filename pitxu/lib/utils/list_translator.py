from pyxavi import Config, Dictionary, full_stack
from pitxu.lib.abstract.pyxavi import PyXavi
from pitxu.lib.utils.lists import Lists
from pitxu.lib.utils.llm_json import LlmJson

from google.genai import types

import json
import logging


class ListTranslator(PyXavi):
    """
    The night translation of the lists: the names, the descriptions and the items get a version in every supported language,
    so a list is read in the language that the user speaks, whatever the language it was written in.

    What it translates is what `Lists.get_untranslated()` says is missing, so an interrupted run is safe to run again, and
    what is edited (its translations are deleted) is done again. It asks the LLM like the memory consolidation does
    (`LlmJson.request()`, with the retries and settings of `lists.translation`), in batches. What fails stays missing for the next time.

    The language of a text is only a hint: the user may dictate a German shopping list while talking English. The LLM is told
    to leave a text as it is for the target languages that it already is in.
    """

    # Defaults of `lists.translation.*`
    BATCH_SIZE = 30

    VERBOSE_DEBUG: bool = False

    lists: Lists = None
    llm: LlmJson = None

    def __init__(self, config: Config, params: Dictionary, lists: Lists = None, llm: LlmJson = None, should_abort: callable = None):
        """
        Args:
            config (Config): The config.
            params (Dictionary): The params, with the `api_key`.
            lists (Lists): The lists. If none, it creates its own (its own connection to the database).
            llm (LlmJson): What asks the LLM. If none, it creates its own.
            should_abort (callable): Asked between batches. If it returns True the run stops there, cleanly.
                The Support worker uses it to give way to whatever waits in its queue.
        """
        super().init_pyxavi(config=config, params=params)

        self._should_abort = should_abort
        self._own_lists = lists is None
        self.lists = lists if lists is not None else Lists(config=self._xconfig, params=self._xparams)
        self.llm = llm if llm is not None else LlmJson(config=self._xconfig, params=self._xparams)

    def close(self):
        if self._own_lists and self.lists is not None:
            self.lists.close()

    def run(self, reason: str = "scheduled") -> dict | None:
        """
        Translates everything that is missing.

        Returns:
            dict | None: What it did (counters), or None if it did not run (disabled, no key, or no prompt).
        """
        if not self._xconfig.get("lists.translation.enabled", True):
            self._xlog.info("🌙 The translation of the lists is disabled. Skipping.")
            return None
        if not self._xparams.get("api_key"):
            self._xlog.error("🛑 The translation of the lists needs an API key. Skipping.")
            return None
        template = self._xconfig.get("lists.translation.prompt")
        if not template:
            self._xlog.error("🛑 There is no lists.translation.prompt in the config. Cannot translate the lists.")
            return None

        stats = {"lists_translated": 0, "items_translated": 0, "failed": 0, "stale": 0, "collisions": 0, "batches": 0, "aborted": False}
        try:
            supported = list(self._xconfig.get("app.supported_languages", []))
            if not supported:
                raise ValueError("app.supported_languages is not defined in the config")

            pending = self.lists.get_untranslated(supported)
            self._xlog.info(f"🌙 Translation of the lists starts [{reason}]: {len(pending)} texts to translate.")
            batch_size = max(1, int(self._xconfig.get("lists.translation.batch_size", self.BATCH_SIZE)))
            for start in range(0, len(pending), batch_size):
                if self._abort_requested(stats):
                    break
                self._translate_batch(template, pending[start:start + batch_size], stats)

            self.log_summary("Lists translation" + (" (aborted)" if stats["aborted"] else ""),
                             [(key.replace("_", " "), value) for key, value in stats.items()], log_level=logging.INFO)
            return stats
        except Exception as e:
            self._xlog.error(f"🛑 The translation of the lists failed: {e}")
            self._xlog.debug(full_stack())
            return None

    def _abort_requested(self, stats: dict) -> bool:
        try:
            if self._should_abort is not None and self._should_abort():
                self._xlog.warning("🟠 Something is waiting: the translation of the lists stops here and will be completed later.")
                stats["aborted"] = True
        except Exception:
            pass
        return stats["aborted"]

    def _translate_batch(self, template: str, batch: list[dict], stats: dict) -> None:
        stats["batches"] += 1
        elements = {(e["kind"], e["id"]): e for e in batch}
        prompt = template.replace("%s", json.dumps([
            {"kind": e["kind"], "id": e["id"], "source_language": e["source_language"] or "unknown",
             "text": e["text"], "description": e["description"] or "", "targets": e["targets"]} for e in batch],
            ensure_ascii=False), 1)
        response_text = self.llm.request(
            prompt=prompt,
            schema=self._schema(),
            model=self._xconfig.get("lists.translation.model") or None,
            purpose="lists translation",
            settings=["lists.translation"])
        data = LlmJson.parse(response_text)
        translations = data.get("translations") if data else None
        if not isinstance(translations, list):
            stats["failed"] += sum(len(e["targets"]) for e in batch)
            return

        done = set()
        for translation in translations:
            if not isinstance(translation, dict):
                continue
            element = elements.get((translation.get("kind"), translation.get("id")))
            language, text = translation.get("language"), translation.get("text")
            if element is None or language not in element["targets"] or (element["kind"], element["id"], language) in done \
                    or not isinstance(text, str) or not text.strip():
                continue
            try:
                if element["kind"] == "list":
                    description = translation.get("description") if isinstance(translation.get("description"), str) else None
                    status = self.lists.set_list_translation(element["id"], language, text, description, element["key"])
                else:
                    status = self.lists.set_item_translation(element["id"], language, text, element["key"])
            except Exception as e:
                self._xlog.error(f"🛑 Could not store the [{language}] version of the {element['kind']} #{element['id']}: {e}")
                continue
            done.add((element["kind"], element["id"], language))
            if status == "stored":
                stats["lists_translated" if element["kind"] == "list" else "items_translated"] += 1
            elif status == "stale":
                stats["stale"] += 1  # It changed meanwhile: its new text is translated the next time.
            else:
                stats["collisions"] += 1
                self._xlog.warning(f"🟠 The [{language}] name of the list #{element['id']} is the name of another list: not stored.")
        stats["failed"] += sum(1 for e in batch for language in e["targets"] if (e["kind"], e["id"], language) not in done)

    @staticmethod
    def _schema() -> types.Schema:
        return types.Schema(
            type=types.Type.OBJECT,
            properties={
                "translations": types.Schema(
                    type=types.Type.ARRAY,
                    items=types.Schema(
                        type=types.Type.OBJECT,
                        properties={
                            "kind": types.Schema(type=types.Type.STRING),
                            "id": types.Schema(type=types.Type.INTEGER),
                            "language": types.Schema(type=types.Type.STRING),
                            "text": types.Schema(type=types.Type.STRING),
                            "description": types.Schema(type=types.Type.STRING),
                        })),
            })
