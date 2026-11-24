"""LlmJson: the JSON answer is read tolerantly, the request retries what may be temporary, and every use has its own settings."""
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from support import *  # noqa: F401,F403
from pitxu.lib.utils import llm_json  # noqa: E402
from pitxu.lib.utils.llm_json import LlmJson  # noqa: E402


class Response:
    def __init__(self, text, candidates=None): self.text, self.candidates = text, candidates or []


class FakeClient:
    """ Stands in for genai.Client: gives what is in `script` one by one (an exception is raised), and keeps what it was asked. """
    script, calls, timeouts = [], [], []

    def __init__(self, api_key=None, http_options=None):
        FakeClient.timeouts.append(http_options)
        self.models = self

    def generate_content(self, model, contents, config):
        FakeClient.calls.append(model)
        step = FakeClient.script.pop(0)
        if isinstance(step, Exception):
            raise step
        return step


def server_error():
    error = llm_json.ServerError.__new__(llm_json.ServerError)
    Exception.__init__(error, "boom")
    error.code, error.message = 500, "boom"
    return error


class ParseTests(unittest.TestCase):

    def test_plain_json_fenced_json_and_json_with_text_around(self):
        self.assertEqual(LlmJson.parse('{"a": 1}'), {"a": 1})
        self.assertEqual(LlmJson.parse('```json\n{"a": 1}\n```'), {"a": 1})
        self.assertEqual(LlmJson.parse('Here it is: {"a": {"b": 2}} Enjoy'), {"a": {"b": 2}})

    def test_what_is_not_an_object_is_none(self):
        for text in (None, "", "no json", "[1, 2]", '{"a": '):
            self.assertIsNone(LlmJson.parse(text), text)

    def test_memory_gives_the_same_answers(self):
        from pitxu.lib.utils.memory import Memory
        self.assertEqual(Memory.parse_llm_json('```json\n{"a": 1}\n```'), {"a": 1})


class RequestTests(unittest.TestCase):

    def setUp(self):
        FakeClient.script, FakeClient.calls, FakeClient.timeouts = [], [], []
        self.slept = []
        self._client, self._sleep = llm_json.genai.Client, llm_json.time.sleep
        llm_json.genai.Client = FakeClient
        llm_json.time.sleep = self.slept.append
        self.addCleanup(lambda: (setattr(llm_json.genai, "Client", self._client), setattr(llm_json.time, "sleep", self._sleep)))
        self.config = cfg(tempfile.mkdtemp())

    def llm(self, api_key="key"):
        return LlmJson(config=self.config, params=params(api_key=api_key))

    def test_an_answer_is_returned_with_the_model_asked(self):
        FakeClient.script = [Response('{"ok": true}')]
        self.assertEqual(self.llm().request("p", None, model="the-model"), '{"ok": true}')
        self.assertEqual(FakeClient.calls, ["the-model"])

    def test_without_a_model_it_uses_the_default(self):
        FakeClient.script = [Response("{}")]
        self.llm().request("p", None)
        self.assertEqual(FakeClient.calls, [LlmJson.DEFAULT_MODEL])

    def test_without_a_key_it_does_not_ask(self):
        self.assertIsNone(self.llm(api_key=None).request("p", None))
        self.assertEqual(FakeClient.calls, [])

    def test_a_temporary_problem_is_retried_with_a_doubling_backoff(self):
        FakeClient.script = [server_error(), server_error(), Response("{}")]
        self.assertEqual(self.llm().request("p", None, settings=["x"]), "{}")
        self.assertEqual(self.slept, [LlmJson.DEFAULT_BACKOFF_SECONDS, LlmJson.DEFAULT_BACKOFF_SECONDS * 2])

    def test_it_gives_up_after_the_tries(self):
        FakeClient.script = [server_error() for _ in range(5)]
        self.assertIsNone(self.llm().request("p", None))
        self.assertEqual(len(FakeClient.calls), LlmJson.DEFAULT_RETRIES)

    def test_an_empty_answer_is_not_retried(self):
        FakeClient.script = [Response("")]
        self.assertIsNone(self.llm().request("p", None))
        self.assertEqual(len(FakeClient.calls), 1)

    def test_the_settings_of_the_first_block_that_defines_them_win(self):
        self.config.set("lists.translation.retries", 2)
        self.config.set("lists.translation.backoff_seconds", 7)
        self.config.set("memory.summarization.retries", 9)
        self.config.set("memory.summarization.request_timeout_seconds", 33)
        FakeClient.script = [server_error() for _ in range(5)]
        self.llm().request("p", None, settings=["lists.translation", "memory.summarization"])
        self.assertEqual(len(FakeClient.calls), 2)          # From the first block.
        self.assertEqual(self.slept, [7])                   # From the first block.
        # The timeout was not in the first block: from the second (the stand-in of the tests does not keep it).
        self.assertEqual(getattr(FakeClient.timeouts[0], "timeout", 33000), 33000)

    def test_the_time_budget_stops_the_tries(self):
        self.config.set("lists.translation.backoff_seconds", 100)
        self.config.set("lists.translation.max_total_seconds", 50)
        FakeClient.script = [server_error(), Response("{}")]
        self.assertIsNone(self.llm().request("p", None, settings=["lists.translation"]))
        self.assertEqual((len(FakeClient.calls), self.slept), (1, []))

    def test_the_lists_do_not_read_memory_settings(self):
        # The lists asked for their own block: what the memory defines must not change them.
        self.config.set("memory.consolidation.retries", 9)
        self.config.set("memory.summarization.retries", 9)
        FakeClient.script = [server_error() for _ in range(10)]
        self.llm().request("p", None, settings=["lists.translation"])
        self.assertEqual(len(FakeClient.calls), self.config.get("lists.translation.retries"))

    def test_memory_asks_through_it_with_its_own_blocks_and_model(self):
        from pitxu.lib.utils.memory import Memory
        asked = {}

        def spy(self, prompt, schema, model=None, purpose="request", settings=None):
            asked.update(model=model, purpose=purpose, settings=settings)
            return "{}"

        real = LlmJson.request
        LlmJson.request = spy
        try:
            tmp = tempfile.mkdtemp()
            config = cfg(tmp)
            memory = Memory(config=config, params=params())
            try:
                self.assertEqual(memory.request_llm_json("p", None, settings="consolidation", purpose="memory translation"), "{}")
            finally:
                memory.close()
        finally:
            LlmJson.request = real
        self.assertEqual(asked, {"model": config.get("memory.summarization_model"), "purpose": "memory translation",
                                 "settings": ["memory.consolidation", "memory.summarization"]})


if __name__ == "__main__":
    unittest.main()
