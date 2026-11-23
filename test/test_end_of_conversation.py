"""The end of the conversation: an empty answer after the tool is not an error, and the app goes idle after its own goodbye."""
import datetime as datetime_module
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from support import *  # noqa: F401,F403

TOOL = "user_intends_to_end_conversation"


class Obj:
    def __init__(self, **kw): self.__dict__.update(kw)


def pair(name=TOOL, result=True, valid=True):
    """ Only what FunctionCallPair.matches() uses, with the real method taken from the source. """
    Holder = methods_of("pitxu/lib/objects/function_call.py", ["matches"])
    class Pair(Holder):
        @property
        def function_name(self): return name if valid else None
    p = Pair()
    p.function_response = Obj(response={"result": result})
    return p


class History:
    def __init__(self, last): self.last = last
    def get_last(self): return self.last


def parse_error(text, history, allowed):
    Holder = methods_of("pitxu/lib/objects/chatbot_response.py", ["parse_error"],
                        {"GenerateContentResponse": object, "FinishReason": object, "FunctionCallHistory": object})
    response = Obj(text=text, candidates=[Obj(finish_reason="STOP")])
    return Holder.parse_error(response, history, allowed)


ALLOWED = {TOOL: True}


class ParseErrorTests(unittest.TestCase):

    def test_01_empty_text_after_the_end_tool_is_not_an_error(self):
        self.assertIsNone(parse_error("", History(pair()), ALLOWED))
        self.assertIsNone(parse_error(None, History(pair()), ALLOWED))

    def test_02_empty_text_after_another_tool_is_still_an_error(self):
        self.assertEqual(parse_error("", History(pair(name="other")), ALLOWED), "STOP")

    def test_03_empty_text_after_the_tool_with_another_result_is_still_an_error(self):
        self.assertEqual(parse_error("", History(pair(result=False)), ALLOWED), "STOP")
        self.assertEqual(parse_error("", History(pair(result=1)), ALLOWED), "STOP")

    def test_04_empty_text_without_the_rule_or_without_tools_is_still_an_error(self):
        self.assertEqual(parse_error("", History(pair()), None), "STOP")
        self.assertEqual(parse_error("", History(None), ALLOWED), "STOP")
        self.assertEqual(parse_error("", None, ALLOWED), "STOP")

    def test_05_text_is_never_an_error(self):
        self.assertIsNone(parse_error("Bye", History(pair(name="other")), ALLOWED))

    def test_06_a_new_tool_can_be_added_to_the_rule(self):
        self.assertIsNone(parse_error("", History(pair(name="x", result="done")), {**ALLOWED, "x": "done"}))


class CentralizedDefinitionTests(unittest.TestCase):

    def test_01_one_definition_used_by_reactions_and_chatbot(self):
        flow = read_file(os.path.join(REPO, "pitxu/lib/command/system/conversation_flow.py"))
        self.assertIn(f'END_OF_CONVERSATION_TOOL_NAME = "{TOOL}"', flow)
        self.assertIn(f"def {TOOL}(", flow)
        for path in ["pitxu/lib/interaction/reactions.py", "pitxu/lib/chatbot/gemini_chatbot.py"]:
            source = read_file(os.path.join(REPO, path))
            self.assertIn("SystemConversationFlow.END_OF_CONVERSATION_TOOL_NAME", source)
            self.assertNotIn(f'"{TOOL}"', source)

    def test_02_every_language_has_ending_sentences(self):
        for file in ["config/language.yaml.dist", "config/language.yaml"]:
            data = read_yaml(os.path.join(REPO, file))["language"]["end_of_conversation_answers"]
            for lang in ["ca", "es", "en", "de"]:
                self.assertTrue(len(data[lang]) >= 2, f"{file} {lang}")

    def test_03_every_prompt_tells_to_answer_minimal(self):
        for file in ["config/chatbot.yaml.dist", "config/chatbot.yaml"]:
            source = read_file(os.path.join(REPO, file))
            self.assertEqual(source.count("to save tokens") + source.count("per estalviar tokens")
                             + source.count("para ahorrar tokens") + source.count("um Tokens zu sparen"), 4, file)


class GoIdleTests(unittest.TestCase):

    def _app(self, wake_up_only=False):
        Holder = methods_of("pitxu/main.py", ["_go_idle_now", "_text_continues_ongoing_interaction",
                                              "get_seconds_since_last_interaction"],
                            {"datetime": datetime_module.datetime, "timedelta": datetime_module.timedelta})
        calls = []
        class Interaction:
            def is_wake_up_button_wanted_exclusively(self): return wake_up_only
            def unmute_microphone(self, input_stream=None): calls.append("unmute")
            def set_idle_mode_on(self): calls.append("idle")
        app = Holder()
        app._xlog = Log()
        app._log_debug = lambda *a, **k: None
        app._interaction = Interaction()
        app._input_stream = None
        app._seconds_to_hold_interaction_answer = 15
        app._last_stt_processing_time = 12  # even a long transcription of the next text must not revive the conversation
        app._last_interaction_datetime = datetime_module.datetime.now()
        app._last_interaction_paused_seconds = 3
        app._end_listening_phase = lambda reason, mute=True, clear_bar=False: calls.append(("end", reason, mute, clear_bar))
        return app, calls

    def test_01_goes_idle_without_hold_time_and_keeps_listening(self):
        app, calls = self._app()
        self.assertTrue(app._text_continues_ongoing_interaction("x"))
        app._go_idle_now("Conversation ended")
        self.assertFalse(app._text_continues_ongoing_interaction("x"))
        self.assertEqual(calls, ["unmute", "idle", ("end", "conversation ended", False, True)])
        self.assertEqual(app._last_interaction_paused_seconds, 0)

    def test_02_with_the_wake_up_button_only_the_microphone_is_muted(self):
        app, calls = self._app(wake_up_only=True)
        app._go_idle_now("Conversation ended")
        self.assertEqual(calls, ["idle", ("end", "conversation ended", True, True)])


class StatusLinesTests(unittest.TestCase):

    def _run(self, summarize=True):
        Holder = methods_of("pitxu/main.py", ["on_end_of_conversation_requested"],
                            {"asyncio": Obj(run_coroutine_threadsafe=lambda *a, **k: None, get_event_loop=lambda: None)})
        lines, order = [], []
        class Interaction:
            def add_new_status_line(self, text):
                lines.append(text); order.append("line")
        class Chatbot:
            def reset_session(self): order.append("reset")
        app = Holder()
        app._xlog = Log()
        app._xconfig = Obj(get=lambda key, default=None: summarize if key == "memory.summarize_at_end_conversation" else default)
        app._interaction = Interaction()
        app._chatbot = Chatbot()
        app._log_debug = lambda *a, **k: None
        app._summarize_current_conversation = lambda reason: order.append("summary")
        app._warmup_chatbot = lambda: None
        app.on_end_of_conversation_requested()
        return app, lines, order

    def test_01_both_lines_come_before_the_summary(self):
        app, lines, order = self._run()
        self.assertEqual(lines, ["🏁 Conversation ended", "🧠 Summarizing conversation"])
        self.assertEqual(order, ["line", "line", "summary", "reset"])
        self.assertTrue(app._end_of_conversation_requested)

    def test_02_without_summary_only_the_first_line(self):
        _, lines, order = self._run(summarize=False)
        self.assertEqual(lines, ["🏁 Conversation ended"])
        self.assertNotIn("summary", order)

    def test_03_a_broken_display_never_raises_from_the_shortcut(self):
        Holder = methods_of("pitxu/lib/interaction/shortcuts/status.py", ["add_new_status_line"], {"XprocAction": Obj(STATUS_LINE=1)})
        class Pool:
            def send(self, *args, **kwargs): raise RuntimeError("queue down")
        shortcut = Holder()
        shortcut._xlog = Log()
        shortcut.status_lines = []
        shortcut.how_many_status_lines_to_keep = 2
        shortcut.startup_screen_pending = True
        shortcut.process_pool = Pool()
        shortcut.get_queue = lambda: "q"
        shortcut.add_new_status_line("🏁 one", "red")  # does not raise
        self.assertEqual(shortcut.status_lines, [("🏁 one", "red")])
        self.assertFalse(shortcut.startup_screen_pending)
        self.assertTrue(any("Could not add the status line" in line for line in shortcut._xlog.lines))


class FlowWiringTests(unittest.TestCase):
    """ The pieces of main.py in place (the whole class needs the stack to import). """

    def test_01_callback_sets_the_flag_and_the_answer_is_replaced_and_idle_follows(self):
        source = read_file(os.path.join(REPO, "pitxu/main.py"))
        self.assertIn("self._end_of_conversation_requested = True", source)
        self.assertIn("answer = random.choice(self._end_of_conversation_answers)", source)
        self.assertIn('self._go_idle_now("Conversation ended")', source)
        # The exit words path is untouched.
        self.assertIn("answer = self._goodbye_sentence", source)

    def test_02_the_flag_is_cleared_before_each_chatbot_question(self):
        source = read_file(os.path.join(REPO, "pitxu/main.py"))
        self.assertLess(source.index("self._end_of_conversation_requested = False\n        LatencyTimeline.mark(\"llm_sent\")"),
                        source.index("self._reactions.react_on_answer(chat_response=chat_response)"))


if __name__ == "__main__":
    unittest.main()
