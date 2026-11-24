from pyxavi import Config, Dictionary, full_stack
from pitxu.lib.abstract.pyxavi import PyXavi
from pitxu.lib.utils.memory import Memory
from pitxu.lib.utils.xtime import Xtime

from google.genai import types

import json
import logging
import re
import unicodedata


class MemoryConsolidator(PyXavi):
    """
    The nightly consolidation of the memory: the short term entries are summarized into the long term memory,
    with one version of every topic per language.

    A run, in phases:
      1. Raw conversations that could not be summarized (the LLM was down) are summarized now.
      2. The pending short term entries are consolidated: merged with the existing long term topics, or new topics.
      3. The versions in the languages that a topic misses (or that are stale after an update) are generated.
      4. The short term entries that were consolidated long enough ago are deleted.

    Everything that changes the database is atomic, and an interrupted run is safe to run again.
    It is the only writer of the long term memory (with the preload): it owns a Memory created as `long_term_writer`.
    """

    # Defaults of `memory.consolidation.*`
    BATCH_SIZE = 10
    MAX_CANDIDATES = 60
    MAX_ATTEMPTS = 5
    LOCK_TTL_SECONDS = 7200
    BACKUPS_KEEP = 3
    RETENTION_DAYS = 14
    SUMMARY_MAX_LENGTH = 255

    VERBOSE_DEBUG: bool = False

    memory: Memory = None

    def __init__(self, config: Config, params: Dictionary, memory: Memory = None, should_abort: callable = None):
        """
        Args:
            config (Config): The config.
            params (Dictionary): The params, with the `api_key`.
            memory (Memory): A Memory that is a long term writer. If none, it creates its own.
            should_abort (callable): Asked between steps. If it returns True the run stops there, cleanly.
                The Support worker uses it to give way to whatever waits in its queue (like the summary at closing).
        """
        super().init_pyxavi(config=config, params=params)

        self._should_abort = should_abort
        self._aborted = False
        self._own_memory = memory is None
        self.memory = memory if memory is not None else Memory(config=self._xconfig, params=Dictionary({
            "api_key": self._xparams.get("api_key"),
            "base_path": self._xparams.get("base_path"),
            "long_term_writer": True,
        }))

    def close(self):
        if self._own_memory and self.memory is not None:
            self.memory.close()

    # ------------------------------------------------------------ the run

    def run(self, reason: str = "scheduled") -> dict | None:
        """
        Runs the consolidation.

        Args:
            reason (str): What triggered it, for the logs.

        Returns:
            dict | None: What it did (counters), or None if it did not run (no key, or another one is running).
        """
        if not self._xparams.get("api_key"):
            self._xlog.error("🛑 The memory consolidation needs an API key. Skipping.")
            return None

        self._aborted = False
        dry_run = bool(self._setting("dry_run", False))
        stats = {
            "raw_summarized": 0, "raw_discarded": 0, "raw_failed": 0,
            "batches": 0, "created": 0, "updated": 0, "ignored": 0, "failed_entries": 0,
            "translated": 0, "translation_failures": 0, "pruned": 0,
        }

        if not self.memory.acquire_consolidation_lock(float(self._setting("lock_ttl_seconds", self.LOCK_TTL_SECONDS))):
            self._xlog.warning("🟠 Another memory consolidation is running. Skipping this one.")
            return None

        try:
            self._xlog.info(f"🌙 Memory consolidation starts [{reason}]{' (DRY RUN: nothing is written)' if dry_run else ''}.")

            has_work = bool(self.memory.get_pending_conversations()) or self.memory.count_pending_short_entries() > 0 \
                or bool(self._topics_to_complete())
            if has_work and self._setting("backup_before", True) and not dry_run:
                self.memory.db.backup_db("before-consolidation", group="consolidation",
                                         keep=int(self._setting("backups_keep", self.BACKUPS_KEEP)))

            self._phase_raw_conversations(stats, dry_run)
            self._phase_consolidate(stats, dry_run)
            self._phase_complete_languages(stats, dry_run)
            self._phase_prune(stats, dry_run)

            # Only a complete run counts as the last one: an aborted one is to be repeated.
            if not self._aborted and not dry_run:
                self.memory.set_meta(Memory.META_LAST_CONSOLIDATION_AT, Xtime.now().isoformat())

            self.log_summary(
                "Memory consolidation" + (" (aborted)" if self._aborted else ""),
                [(key.replace("_", " "), value) for key, value in stats.items()],
                log_level=logging.INFO)
            return stats

        except Exception as e:
            self._xlog.error(f"🛑 The memory consolidation failed: {e}")
            self._xlog.debug(full_stack())
            return None
        finally:
            self.memory.release_consolidation_lock()

    def _setting(self, name: str, default):
        value = self._xconfig.get(f"memory.consolidation.{name}")
        return value if value is not None else default

    def _abort_requested(self) -> bool:
        if self._aborted:
            return True
        try:
            if self._should_abort is not None and self._should_abort():
                self._xlog.warning("🟠 Something is waiting: the memory consolidation stops here and will be completed later.")
                self._aborted = True
        except Exception:
            pass
        return self._aborted

    # ------------------------------------------------------------ phase 1: raw conversations

    def _phase_raw_conversations(self, stats: dict, dry_run: bool):
        max_attempts = int(self._setting("max_attempts", self.MAX_ATTEMPTS))

        for pending in self.memory.get_pending_conversations():
            if self._abort_requested():
                return
            if pending["attempts"] >= max_attempts:
                self._xlog.warning(f"🟠 The pending conversation #{pending['id']} failed {pending['attempts']} times, not trying again.")
                continue

            result = self.memory.summarize_chatbot_history_as_memory_entry(pending["history"], language=pending["language"])
            if result is None:
                stats["raw_failed"] += 1
                if not dry_run:
                    self.memory.increment_pending_conversation_attempts(pending["id"])
                continue

            if result.get("significant") is False:
                stats["raw_discarded"] += 1
            else:
                stats["raw_summarized"] += 1
                self._xlog.info(f"🌙 Pending conversation #{pending['id']} summarized: {result['summary']}")
                if not dry_run:
                    self.memory.create_short_memory_entry(
                        summary=result["summary"], content=result["content"],
                        created_at=pending["created_at"], language=pending["language"])
            if not dry_run:
                self.memory.delete_pending_conversation(pending["id"])

    # ------------------------------------------------------------ phase 2: consolidate pending short entries

    def _phase_consolidate(self, stats: dict, dry_run: bool):
        supported = self._supported_languages()
        batch_size = max(1, int(self._setting("batch_size", self.BATCH_SIZE)))
        max_attempts = int(self._setting("max_attempts", self.MAX_ATTEMPTS))

        # Per language, because the topics that an entry is merged with are the ones in its language.
        pending_by_language: dict[str, list[dict]] = {}
        for entry in self.memory.get_pending_short_entries():
            language = entry.get("language")
            if language not in supported:
                # Should not happen (the startup labels them all), but one without language must not block the rest.
                self._xlog.warning(f"🟠 Short term entry #{entry['id']} has the language [{language}], that is not supported. Using the legacy one.")
                language = self._xconfig.get("memory.legacy_entries_language", supported[0])
                entry = {**entry, "language": language}
            pending_by_language.setdefault(language, []).append(entry)

        for language, entries in pending_by_language.items():
            for start in range(0, len(entries), batch_size):
                if self._abort_requested():
                    return
                batch = entries[start:start + batch_size]
                stats["batches"] += 1
                self._consolidate_batch(language, batch, stats, dry_run, max_attempts)

    def _consolidate_batch(self, language: str, batch: list[dict], stats: dict, dry_run: bool, max_attempts: int):
        batch_ids = [entry["id"] for entry in batch]
        topics = self._candidate_topics(language, batch)

        # A topic that an earlier update (in another language) left stale in this language must be refreshed
        #   before merging into it: otherwise the merge would start from the old text, and the next translation
        #   would overwrite the earlier update.
        stale_ids = {topic["topic_id"] for topic in topics if topic["stale"]}
        if stale_ids and not dry_run:
            for item in self._topics_to_complete():
                if item["topic_id"] in stale_ids and language in item["targets"]:
                    self._translate_topic({**item, "targets": [language]}, stats)
            topics = self._candidate_topics(language, batch)
        # What could not be refreshed is not offered: a duplicate can be merged later, a lost update can't.
        still_stale = [topic["topic_id"] for topic in topics if topic["stale"]]
        if still_stale:
            self._xlog.warning(f"🟠 The topics {still_stale} are stale in [{language}] and could not be refreshed. They are not offered for merging.")
        topics = [{key: value for key, value in topic.items() if key != "stale"} for topic in topics if not topic["stale"]]

        response_text = self.memory.request_llm_json(
            prompt=self._build_consolidation_prompt(language, batch, topics),
            schema=self._consolidation_schema(),
            model=self._xconfig.get("memory.consolidation_model"),
            settings="consolidation",
            purpose="memory consolidation")

        operations = self._parse_operations(response_text, batch_ids, {topic["topic_id"] for topic in topics}, language) \
            if response_text is not None else []

        covered: set[int] = set()
        for operation in operations:
            self._xlog.info(f"🌙 [{language}] {operation['action']}"
                            + (f" topic #{operation['topic_id']}" if operation["action"] == "update" else "")
                            + f" <- entries {operation['source_ids']}"
                            + (f": {operation['summary']}" if operation["action"] != "ignore" else ""))
            if dry_run:
                covered.update(operation["source_ids"])
                continue
            try:
                self.memory.apply_consolidation(
                    action=operation["action"], short_ids=operation["source_ids"], language=operation["language"],
                    summary=operation.get("summary"), content=operation.get("content"), topic_id=operation.get("topic_id"))
            except Exception as e:
                self._xlog.error(f"🛑 Could not apply the operation {operation['action']} for the entries {operation['source_ids']}: {e}")
                continue
            covered.update(operation["source_ids"])
            stats[{"create": "created", "update": "updated", "ignore": "ignored"}[operation["action"]]] += 1

        # What was not resolved stays pending and is tried again, a limited number of times.
        unresolved = [entry_id for entry_id in batch_ids if entry_id not in covered]
        if unresolved:
            self._xlog.warning(f"🟠 {len(unresolved)} short term entries were not consolidated: {unresolved}")
            if not dry_run:
                failed = self.memory.increment_short_attempts(unresolved, max_attempts)
                stats["failed_entries"] += failed
                if failed:
                    self._xlog.error(f"🛑 {failed} short term entries failed {max_attempts} times and are marked as failed.")

    def _candidate_topics(self, language: str, batch: list[dict]) -> list[dict]:
        """
        The existing topics (in this language) that the batch may be merged with.
        All of them if they are few. Otherwise the ones that share words with the batch.
        """
        topics = [
            {
                "topic_id": row["topic_id"], "summary": row["summary"], "content": row["content"],
                "updated_at": row["updated_at"], "curated": bool(row.get("preload_key")), "stale": bool(row["stale"]),
            }
            for row in self.memory.get_long_memory_rows(language)
        ]
        max_candidates = int(self._setting("max_candidates", self.MAX_CANDIDATES))
        if len(topics) <= max_candidates:
            return topics

        # The topics that an entry of the batch says to correct are always candidates.
        linked_ids = {entry["topic_id"] for entry in batch if entry.get("topic_id")}
        linked = [topic for topic in topics if topic["topic_id"] in linked_ids]
        topics = [topic for topic in topics if topic["topic_id"] not in linked_ids]

        batch_words = self._words(" ".join(f"{entry['summary']} {entry['content']}" for entry in batch))
        scored = [(len(batch_words & self._words(f"{topic['summary']} {topic['content']}")), topic) for topic in topics]
        scored = [item for item in scored if item[0] > 0]
        scored.sort(key=lambda item: item[0], reverse=True)
        return linked + [topic for _, topic in scored[:max(0, max_candidates - len(linked))]]

    @staticmethod
    def _words(text: str) -> set[str]:
        normalized = unicodedata.normalize("NFKD", text.lower())
        normalized = "".join(char for char in normalized if not unicodedata.combining(char))
        return set(re.findall(r"\w{4,}", normalized))

    def _build_consolidation_prompt(self, language: str, batch: list[dict], topics: list[dict]) -> str:
        template = self._xconfig.get("memory.consolidation.prompt")
        if not template:
            raise ValueError("There is no memory.consolidation.prompt in the config")
        now = Xtime.now()
        topic_ids = {topic["topic_id"] for topic in topics}
        data = {
            "today": f"{Xtime.weekday_name(now)} {now.strftime('%Y-%m-%d %H:%M')} ({now.astimezone().tzname()})",
            "language": language,
            "existing_topics": topics,
            "pending_entries": [
                {"id": entry["id"], "summary": entry["summary"], "content": entry["content"], "created_at": entry["created_at"],
                 **({"correction_of_topic": entry["topic_id"]} if entry.get("topic_id") in topic_ids else {})}
                for entry in batch
            ],
        }
        return template.replace("%s", json.dumps(data, ensure_ascii=False, default=str), 1)

    @staticmethod
    def _consolidation_schema() -> types.Schema:
        return types.Schema(
            type=types.Type.OBJECT,
            properties={
                "operations": types.Schema(
                    type=types.Type.ARRAY,
                    items=types.Schema(
                        type=types.Type.OBJECT,
                        properties={
                            "action": types.Schema(type=types.Type.STRING, enum=["create", "update", "ignore"]),
                            "source_ids": types.Schema(type=types.Type.ARRAY, items=types.Schema(type=types.Type.INTEGER)),
                            "topic_id": types.Schema(type=types.Type.INTEGER),
                            "language": types.Schema(type=types.Type.STRING),
                            "summary": types.Schema(type=types.Type.STRING),
                            "content": types.Schema(type=types.Type.STRING),
                        })),
            })

    def _parse_operations(self, response_text: str, batch_ids: list[int], candidate_topic_ids: set[int], language: str) -> list[dict]:
        """
        The valid operations of the answer. What is not valid is dropped with a log, and the entries it covered
        are not marked as consolidated by anyone, so they stay pending.
        An entry can be in only one operation, the first one that claims it.
        """
        data = Memory.parse_llm_json(response_text)
        if data is None or not isinstance(data.get("operations"), list):
            self._xlog.error(f"🛑 The consolidation answer has no operations: {response_text[:500]!r}")
            return []

        supported = self._supported_languages()
        claimed: set[int] = set()
        valid = []
        for raw in data["operations"]:
            if not isinstance(raw, dict):
                continue
            action = raw.get("action")
            source_ids = [entry_id for entry_id in raw.get("source_ids", []) if isinstance(entry_id, int)] \
                if isinstance(raw.get("source_ids"), list) else []
            if action not in ("create", "update", "ignore"):
                self._xlog.warning(f"🟠 Operation dropped, unknown action: {raw}")
                continue
            if not source_ids or any(entry_id not in batch_ids for entry_id in source_ids):
                self._xlog.warning(f"🟠 Operation dropped, its source ids are not of this batch: {raw}")
                continue
            source_ids = [entry_id for entry_id in dict.fromkeys(source_ids) if entry_id not in claimed]
            if not source_ids:
                continue

            operation = {"action": action, "source_ids": source_ids, "language": language}
            if action != "ignore":
                summary = raw.get("summary") if isinstance(raw.get("summary"), str) else ""
                content = raw.get("content") if isinstance(raw.get("content"), str) else ""
                if not summary.strip() or not content.strip():
                    self._xlog.warning(f"🟠 Operation dropped, it has no summary or content: {raw}")
                    continue
                operation["summary"] = summary.strip()[:self.SUMMARY_MAX_LENGTH]
                operation["content"] = content.strip()
                if action == "create" and raw.get("language") in supported:
                    # The language that the entry is really in, if it was labelled with another one.
                    operation["language"] = raw["language"]
            if action == "update":
                if raw.get("topic_id") not in candidate_topic_ids:
                    self._xlog.warning(f"🟠 Operation dropped, it updates a topic that is not a candidate: {raw}")
                    continue
                operation["topic_id"] = raw["topic_id"]

            claimed.update(source_ids)
            valid.append(operation)
        return valid

    # ------------------------------------------------------------ phase 3: complete the languages

    def _topics_to_complete(self) -> list[dict]:
        """
        The topics that miss a supported language, or have a stale version.
        For each one: the topic, the newest fresh version (the source to translate from) and the languages to generate.
        """
        supported = self._supported_languages()
        by_topic: dict[int, list[dict]] = {}
        for row in self.memory.get_long_memory_rows():
            by_topic.setdefault(row["topic_id"], []).append(row)

        topics = []
        for topic_id, rows in by_topic.items():
            present = {row["language"] for row in rows}
            targets = [language for language in supported if language not in present]
            targets += [row["language"] for row in rows if row["stale"] and row["language"] in supported]
            fresh = [row for row in rows if not row["stale"]]
            if not targets:
                continue
            if not fresh:
                self._xlog.warning(f"🟠 Topic #{topic_id} has no fresh version to translate from. Skipping.")
                continue
            source = max(fresh, key=lambda row: row["updated_at"] or "")
            targets = [language for language in dict.fromkeys(targets) if language != source["language"]]
            if targets:
                topics.append({"topic_id": topic_id, "source": source, "targets": targets})
        return topics

    def _phase_complete_languages(self, stats: dict, dry_run: bool):
        for topic in self._topics_to_complete():
            if self._abort_requested():
                return
            source, targets = topic["source"], topic["targets"]
            self._xlog.info(f"🌙 Topic #{topic['topic_id']}: {source['language']} -> {', '.join(targets)}"
                            f"{' (dry run)' if dry_run else ''}")
            if dry_run:
                continue
            if not self._translate_topic(topic, stats):
                return

    def _translate_topic(self, topic: dict, stats: dict) -> bool:
        """
        Generates the versions of a topic in its target languages from its source version.
        What fails stays missing (or stale) and is tried again the next time.
        Returns False only if the translations can't be done at all (no prompt in the config).
        """
        template = self._xconfig.get("memory.consolidation.translation_prompt")
        if not template:
            self._xlog.error("🛑 There is no memory.consolidation.translation_prompt in the config. Cannot complete the languages.")
            return False

        source, targets = topic["source"], topic["targets"]
        prompt = template.replace("%s", json.dumps({
            "source_language": source["language"],
            "target_languages": targets,
            "summary": source["summary"],
            "content": source["content"],
        }, ensure_ascii=False), 1)
        response_text = self.memory.request_llm_json(
            prompt=prompt,
            schema=self._translation_schema(),
            model=self._xconfig.get("memory.consolidation_model"),
            settings="consolidation",
            purpose="memory translation")
        data = Memory.parse_llm_json(response_text) if response_text is not None else None
        translations = data.get("translations") if data else None
        if not isinstance(translations, list):
            stats["translation_failures"] += len(targets)
            return True

        done = set()
        for translation in translations:
            if not isinstance(translation, dict):
                continue
            language = translation.get("language")
            summary = translation.get("summary")
            content = translation.get("content")
            if language not in targets or language in done or not isinstance(summary, str) or not isinstance(content, str) \
                    or not summary.strip() or not content.strip():
                continue
            try:
                self.memory.upsert_long_memory_translation(
                    topic["topic_id"], language, summary.strip()[:self.SUMMARY_MAX_LENGTH], content.strip())
                done.add(language)
                stats["translated"] += 1
            except Exception as e:
                self._xlog.error(f"🛑 Could not store the [{language}] version of the topic #{topic['topic_id']}: {e}")
        stats["translation_failures"] += len([language for language in targets if language not in done])
        return True

    @staticmethod
    def _translation_schema() -> types.Schema:
        return types.Schema(
            type=types.Type.OBJECT,
            properties={
                "translations": types.Schema(
                    type=types.Type.ARRAY,
                    items=types.Schema(
                        type=types.Type.OBJECT,
                        properties={
                            "language": types.Schema(type=types.Type.STRING),
                            "summary": types.Schema(type=types.Type.STRING),
                            "content": types.Schema(type=types.Type.STRING),
                        })),
            })

    # ------------------------------------------------------------ phase 4: prune

    def _phase_prune(self, stats: dict, dry_run: bool):
        retention_days = float(self._xconfig.get("memory.short_term.retention_days", self.RETENTION_DAYS))
        if dry_run:
            return
        stats["pruned"] = self.memory.prune_short_memory(retention_days)
        if stats["pruned"]:
            self._xlog.info(f"🌙 {stats['pruned']} short term entries older than {retention_days} days were deleted.")

    # ------------------------------------------------------------

    def _supported_languages(self) -> list[str]:
        supported = self._xconfig.get("app.supported_languages", [])
        if not supported:
            raise ValueError("app.supported_languages is not defined in the config")
        return list(supported)
