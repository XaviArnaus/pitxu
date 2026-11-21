from pyxavi import Config

import logging
import numbers


class MemoryConfigValidator:
    """
    Checks the values of the memory (and database) settings.

    A value that is not valid is reported in the log and replaced, in the config of this process, by its default:
    a typo in a YAML file must not stop the application nor fail at the worst moment (the nightly consolidation).
    A setting that is not in the config is not an error: the code has its own default for it.

    Every process has its own copy of the config, so every process runs this (`Memory` does it once per config).
    """

    @staticmethod
    def _is_number(value) -> bool:
        return isinstance(value, numbers.Real) and not isinstance(value, bool)

    @staticmethod
    def _is_int(value) -> bool:
        return isinstance(value, int) and not isinstance(value, bool)

    @classmethod
    def _rules(cls) -> list[tuple]:
        """ (key, default, what it must be, predicate). The predicate gets a value that is not None. """
        number = cls._is_number
        integer = cls._is_int
        boolean = lambda v: isinstance(v, bool)
        text = lambda v: isinstance(v, str) and v.strip() != ""
        return [
            ("memory.summarize_at_end_conversation", True, "True or False", boolean),
            ("memory.summarize_on_close", True, "True or False", boolean),
            ("memory.min_user_turns", 1, "an integer, 0 or more", lambda v: integer(v) and v >= 0),
            ("memory.summarization.close_timeout_seconds", 45, "a number of seconds above 0", lambda v: number(v) and v > 0),
            ("memory.summarization.retries", 3, "an integer, 1 or more", lambda v: integer(v) and v >= 1),
            ("memory.summarization.backoff_seconds", 2, "a number of seconds, 0 or more", lambda v: number(v) and v >= 0),
            ("memory.summarization.request_timeout_seconds", 20, "a number of seconds above 0", lambda v: number(v) and v > 0),
            ("memory.summarization.max_total_seconds", 40, "a number of seconds above 0", lambda v: number(v) and v > 0),
            ("memory.summarization.include_current_date", True, "True or False", boolean),
            ("memory.summarization.fallback_save_raw", True, "True or False", boolean),
            ("memory.summarization_model", "gemini-3.1-flash-lite", "a model name", text),
            ("memory.consolidation_model", "gemini-3.1-flash-lite", "a model name", text),
            ("memory.short_term.retention_days", 14, "a number of days, 0 or more", lambda v: number(v) and v >= 0),
            ("memory.consolidation.enabled", True, "True or False", boolean),
            ("memory.consolidation.hour", 3, "an integer between 0 and 23", lambda v: integer(v) and 0 <= v <= 23),
            ("memory.consolidation.minute", 0, "an integer between 0 and 59", lambda v: integer(v) and 0 <= v <= 59),
            ("memory.consolidation.defer_minutes", 10, "a number of minutes above 0", lambda v: number(v) and v > 0),
            ("memory.consolidation.max_defer_hours", 3, "a number of hours, 0 or more", lambda v: number(v) and v >= 0),
            ("memory.consolidation.startup_catchup", True, "True or False", boolean),
            ("memory.consolidation.startup_delay_seconds", 300, "a number of seconds, 0 or more", lambda v: number(v) and v >= 0),
            ("memory.consolidation.overdue_hours", 26, "a number of hours above 0", lambda v: number(v) and v > 0),
            ("memory.consolidation.batch_size", 10, "an integer, 1 or more", lambda v: integer(v) and v >= 1),
            ("memory.consolidation.max_candidates", 60, "an integer, 1 or more", lambda v: integer(v) and v >= 1),
            ("memory.consolidation.max_attempts", 5, "an integer, 1 or more", lambda v: integer(v) and v >= 1),
            ("memory.consolidation.backup_before", True, "True or False", boolean),
            ("memory.consolidation.backups_keep", 3, "an integer, 1 or more", lambda v: integer(v) and v >= 1),
            ("memory.consolidation.lock_ttl_seconds", 7200, "a number of seconds above 0", lambda v: number(v) and v > 0),
            ("memory.consolidation.dry_run", False, "True or False", boolean),
            ("memory.consolidation.retries", 3, "an integer, 1 or more", lambda v: integer(v) and v >= 1),
            ("memory.consolidation.backoff_seconds", 5, "a number of seconds, 0 or more", lambda v: number(v) and v >= 0),
            ("memory.consolidation.request_timeout_seconds", 60, "a number of seconds above 0", lambda v: number(v) and v > 0),
            ("memory.consolidation.max_total_seconds", 180, "a number of seconds above 0", lambda v: number(v) and v > 0),
            ("chatbot.memory_autonomy", True, "True or False", boolean),
            ("database.sqlite.auto_migrate", True, "True or False", boolean),
            ("database.sqlite.backups_keep", 5, "an integer, 1 or more", lambda v: integer(v) and v >= 1),
            ("database.sqlite.wal", True, "True or False", boolean),
            ("database.sqlite.busy_timeout_seconds", 30, "a number of seconds above 0", lambda v: number(v) and v > 0),
        ]

    # The longest the closing may take: the TimeoutStopSec of config/system/pitxu.service.
    SYSTEMD_STOP_TIMEOUT_SECONDS = 120

    @classmethod
    def validate(cls, config: Config, logger: logging.Logger = None) -> list[str]:
        """
        Replaces what is not valid by the default, and returns the messages (also logged as warnings).
        """
        messages = []

        def report(message: str):
            messages.append(message)
            if logger is not None:
                logger.warning("🟠 Config: " + message)

        for key, default, description, is_valid in cls._rules():
            value = config.get(key)
            if value is None or is_valid(value):
                continue
            report(f"[{key}] is {value!r}, it must be {description}. Using the default: {default!r}.")
            config.set(key, default)

        supported = config.get("app.supported_languages") or []
        fallback_language = "en" if "en" in supported or not supported else supported[0]
        legacy = config.get("memory.legacy_entries_language")
        if legacy is not None and supported and legacy not in supported:
            report(f"[memory.legacy_entries_language] is {legacy!r}, it must be one of {supported}. Using {fallback_language!r}.")
            config.set("memory.legacy_entries_language", fallback_language)

        # Without a default that can replace them: only reported.
        for key in ("memory.consolidation.prompt", "memory.consolidation.translation_prompt"):
            value = config.get(key)
            if value is not None and (not isinstance(value, str) or "%s" not in value):
                report(f"[{key}] must be a text with a %s where the data goes. The consolidation will not work until it is fixed.")

        close_timeout = config.get("memory.summarization.close_timeout_seconds")
        if close_timeout is not None and cls._is_number(close_timeout) and close_timeout > cls.SYSTEMD_STOP_TIMEOUT_SECONDS - 20:
            report(f"[memory.summarization.close_timeout_seconds] is {close_timeout}: it leaves less than 20 seconds of the "
                   f"{cls.SYSTEMD_STOP_TIMEOUT_SECONDS} that systemd gives to stop. The summary may be cut, "
                   "and then it is kept for the nightly consolidation.")

        return messages
