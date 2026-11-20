import logging
import os
import re
import threading
import time

from pyxavi import Storage


class EmojiStats:
    """
    Counts how many times every emoji (animation) is shown, per day, and keeps the counters in a YAML file (a pyxavi Storage).

    The counts live in memory, keyed by the date of the use (not the date of the saving), and are merged into the file by flush():
    every night, every hour, and when the application closes, so a Pi that is switched off or crashes loses at most an hour.
    A flush adds to what the file already has, so a restart in the middle of the day keeps accumulating into the same day.

    File (storage.path / storage.emojis_stats_file, "emojis_stats.yaml" by default):

        '2026-11-20':
          emojis: {smile-small: 12, sorry: 2}
          chosen_by: {chosen: 9, none: 4, no_tag: 1, invalid: 1, default: 1}
          invalid_labels: {made-up-label: 1}

    "chosen_by" tells how the emoji was decided:
        chosen      The chatbot gave a label that is configured.
        none        The chatbot said the answer is neutral.
        no_tag      The answer came without an emotion tag.
        invalid     The chatbot gave a label that is not configured (it is also counted in invalid_labels).
        default     Shown without the chatbot (like the greeting).
        requested   Asked directly by code (like a tool).

    Everything lives in the main process and is a class-level store, like LatencyTimeline, so any class there can count without wiring.
    It is called from several threads, hence the lock. It must never interfere with the interaction: nothing here raises.

    ⚠️ The keys go through the path syntax of the Storage: a "." splits them, a "#" is a wildcard and a number is a list index.
    The names of the animations are safe, but the label of an invalid emotion is whatever the chatbot wrote, so it is cleaned first.
    """

    DEFAULT_STORAGE_PATH: str = "storage/"
    DEFAULT_FILE: str = "emojis_stats.yaml"
    MAX_LABEL_LENGTH: int = 40

    _lock = threading.Lock()
    # date -> {"emojis": {name: n}, "chosen_by": {how: n}, "invalid_labels": {label: n}}
    _pending: dict = {}
    _file: str | None = None
    _logger = logging.getLogger(__name__)

    @staticmethod
    def configure(config) -> None:
        """ Takes the path of the file from the config (storage.path and storage.emojis_stats_file). """
        try:
            EmojiStats._file = os.path.join(
                config.get("storage.path", EmojiStats.DEFAULT_STORAGE_PATH),
                config.get("storage.emojis_stats_file", EmojiStats.DEFAULT_FILE))
        except Exception as e:
            EmojiStats._logger.warning(f"📊 Could not configure the emoji stats, they will not be saved: {e}")

    @staticmethod
    def count(emoji: str, how: str = "requested", invalid_label: str | None = None) -> None:
        """
        Counts one use of the emoji today.

        Args:
            emoji: The name of the animation that is shown.
            how: How it was decided, see the class docs.
            invalid_label: When how is "invalid", the label the chatbot made up.
        """
        try:
            day = time.strftime("%Y-%m-%d")
            with EmojiStats._lock:
                bucket = EmojiStats._pending.setdefault(day, {})
                EmojiStats._add(bucket, "emojis", EmojiStats._safe_key(emoji))
                EmojiStats._add(bucket, "chosen_by", EmojiStats._safe_key(how))
                if invalid_label:
                    EmojiStats._add(bucket, "invalid_labels", EmojiStats._safe_key(invalid_label))
        except Exception:
            pass

    @staticmethod
    def flush() -> bool:
        """
        Adds the counts in memory to the file and forgets them. If the file can not be written, the counts stay in memory
        for the next flush.

        Returns:
            bool: True if there was something and it was saved (or there was nothing to save), False if saving failed.
        """
        with EmojiStats._lock:
            if not EmojiStats._pending:
                return True
            if EmojiStats._file is None:
                return False
            taken, EmojiStats._pending = EmojiStats._pending, {}
            path = EmojiStats._file

        try:
            os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
            # A fresh read, so what is in the file now is what the counts are added to.
            storage = Storage(filename=path)
            for day, bucket in taken.items():
                stored = storage.get(day, None)
                if not isinstance(stored, dict):
                    stored = {}
                EmojiStats._merge_day(stored, bucket)
                storage.set(day, stored)
            storage.write_file()
            total = sum(sum(bucket.get("emojis", {}).values()) for bucket in taken.values())
            EmojiStats._logger.info(f"📊 Saved {total} emoji uses of {len(taken)} day(s) into {path}")
            return True
        except Exception as e:
            EmojiStats._logger.error(f"📊 Could not save the emoji stats into {path}, they stay in memory for the next time: {e}")
            with EmojiStats._lock:
                for day, bucket in taken.items():
                    EmojiStats._merge_day(EmojiStats._pending.setdefault(day, {}), bucket)
            return False

    # --------- Internals ---------

    @staticmethod
    def _safe_key(value: str) -> str:
        """
        A key that the Storage takes as a plain name: lower case letters, digits, "-" and "_" only (no ".", no "#"),
        starting with a letter (a number would be taken as a list index), and not too long.
        """
        key = re.sub(r"[^a-z0-9_-]", "_", str(value).strip().lower())[:EmojiStats.MAX_LABEL_LENGTH]
        if key == "" or not key[0].isalpha():
            key = "x_" + key
        return key

    @staticmethod
    def _add(bucket: dict, section: str, key: str, amount: int = 1) -> None:
        counters = bucket.setdefault(section, {})
        counters[key] = counters.get(key, 0) + amount

    @staticmethod
    def _merge_day(target: dict, source: dict) -> None:
        for section, counters in source.items():
            for key, amount in counters.items():
                EmojiStats._add(target, section, key, amount)
