from pyxavi import Config, Dictionary
from pitxu.lib.abstract.pyxavi import PyXavi

from google import genai
from google.genai import types
from google.genai.errors import ClientError, ServerError

import json
import re
import time


class LlmJson(PyXavi):
    """
    Asks the LLM for a JSON answer that follows a schema, and reads it.

    It does not know who asks: the memory (summaries, consolidation, translations) and the lists (translations) use it.
    The retries, the backoff, the timeouts and the time budget are read from the config blocks that the caller names
    (`settings`), so every use has its own: `request(..., settings=["lists.translation"])` reads `lists.translation.retries`,
    `lists.translation.backoff_seconds`, `lists.translation.request_timeout_seconds` and `lists.translation.max_total_seconds`.
    """

    # What is used when no block of the settings defines it.
    DEFAULT_MODEL = "gemini-2.5-flash"
    DEFAULT_RETRIES = 3
    DEFAULT_BACKOFF_SECONDS = 2
    DEFAULT_REQUEST_TIMEOUT_SECONDS = 20
    DEFAULT_MAX_TOTAL_SECONDS = 40

    VERBOSE_DEBUG: bool = False

    def __init__(self, config: Config = None, params: Dictionary = None):
        """
        Args:
            config (Config): The config.
            params (Dictionary): The params, with the `api_key`.
        """
        super().init_pyxavi(config=config, params=params)

    def request(self, prompt: str, schema: types.Schema, model: str = None, purpose: str = "request",
                settings: list[str] = None) -> str | None:
        """
        Asks the LLM for a JSON answer that follows the schema. Retries (with exponential backoff, within an overall
        time budget) when the problem may be temporary: server errors, quota (429) and network errors.

        Args:
            prompt (str): What to ask.
            schema (types.Schema): The shape of the answer.
            model (str): The model. Default: `DEFAULT_MODEL`.
            purpose (str): What it is for, to tell it in the logs.
            settings (list[str]): The config blocks with `retries`, `backoff_seconds`, `request_timeout_seconds` and
                `max_total_seconds`. For every one, the first block that defines it wins. What none defines is taken from the defaults.

        Returns:
            str | None: The text of the answer, or None if it failed.
        """
        api_key = self._xparams.get("api_key")
        if not api_key:
            self._xlog.error(f"🛑 Cannot ask the LLM for the {purpose}: there is no API key.")
            return None

        def setting(name: str, default):
            for block in settings or []:
                value = self._xconfig.get(f"{block}.{name}")
                if value is not None:
                    return value
            return default

        retries = int(setting("retries", self.DEFAULT_RETRIES))
        backoff_seconds = float(setting("backoff_seconds", self.DEFAULT_BACKOFF_SECONDS))
        request_timeout = float(setting("request_timeout_seconds", self.DEFAULT_REQUEST_TIMEOUT_SECONDS))
        max_total_seconds = float(setting("max_total_seconds", self.DEFAULT_MAX_TOTAL_SECONDS))
        model = model or self.DEFAULT_MODEL

        client = genai.Client(api_key=api_key, http_options=types.HttpOptions(timeout=int(request_timeout * 1000)))
        generation_config = types.GenerateContentConfig(
            response_mime_type="application/json",
            response_schema=schema)

        started_at = time.monotonic()
        for attempt in range(1, retries + 1):
            self._xlog.debug(f"Asking for the {purpose}. Try #{attempt} / {retries}")

            # Only the request is inside the try: a bug in our own code must not look like a network problem to retry.
            try:
                response = client.models.generate_content(model=model, contents=prompt, config=generation_config)
            except ServerError as e:
                problem = f"Server error [{e.code}] {e.message}"
            except ClientError as e:
                if e.code != 429:
                    # Bad key, bad request...: it will not get better by trying again.
                    self._xlog.error(f"🛑 Client error using [{model}] for the {purpose}, not retrying: [{e.code}] {e.message}")
                    return None
                problem = f"Quota exceeded [{e.code}] {e.message}"
            except Exception as e:
                # Network errors and timeouts.
                problem = f"{type(e).__name__}: {e}"
            else:
                if response.text:
                    self._log_debug(f"The {purpose} request was successful.")
                    return response.text
                # Nothing to read: blocked or empty. Asking again would give the same.
                finish_reason = response.candidates[0].finish_reason if response.candidates else "no candidates"
                self._xlog.error(f"🛑 The {purpose} of [{model}] has no text. Finish reason: {finish_reason}")
                return None

            self._xlog.warning(f"🟠 Try #{attempt} / {retries} of the {purpose} failed using [{model}]: {problem}")

            if attempt >= retries:
                break
            wait_seconds = backoff_seconds * (2 ** (attempt - 1))
            if time.monotonic() - started_at + wait_seconds >= max_total_seconds:
                self._xlog.warning(f"🟠 Not retrying the {purpose}: the {max_total_seconds}s budget would be exceeded.")
                break
            time.sleep(wait_seconds)

        self._xlog.error(f"🛑 The {purpose} failed after {attempt} tries.")
        return None

    @staticmethod
    def parse(response_text: str) -> dict | None:
        """
        The JSON object of the answer of the LLM. The JSON mode should give plain JSON, but it is tolerant:
        if there are fences or text around it, the object is extracted. None if there is no valid object.
        """
        if response_text is None:
            return None
        cleaned = re.sub(r"^```(?:json)?\s*|\s*```$", "", response_text.strip())

        data = None
        try:
            data = json.loads(cleaned)
        except json.JSONDecodeError:
            found = re.search(r"\{.*\}", cleaned, re.DOTALL)
            if found:
                try:
                    data = json.loads(found.group(0))
                except json.JSONDecodeError:
                    pass

        return data if isinstance(data, dict) else None
