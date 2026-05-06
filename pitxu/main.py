from subprocess import call

from pyxavi import Config, Dictionary, Storage, full_stack, dd

import signal

from pitxu.lib.abstract.pyxavi import PyXavi
from pitxu.lib.utils.text import Text
from pitxu.lib.utils.stopwatch import Stopwatch
from pitxu.lib.utils.system import System
from pitxu.lib.utils.maintenance import Maintenance
from pitxu.lib.utils.reminders import Reminders
from pitxu.lib.utils.fan_control import FanControl
from pitxu.lib.chatbot import GeminiChatbot
from pitxu.lib.chatbot.chatbot_session_manager import ChatbotSessionManager
from pitxu.lib.interaction.interaction import Interaction
from pitxu.lib.interaction.reactions import Reactions
from pitxu.lib.canvas.canvas import Canvas
from pitxu.lib.support_process.support import Support
from pitxu.lib.speech_to_text.vosk import Vosk, VoskException
from pitxu.lib.speech_to_text.capture_handler import CaptureHandler
from pitxu.lib.objects import ChatbotResponse, FunctionCallPair
from pitxu.lib.microservice.server import Server
from pitxu.lib.utils.xtime import Xtime
from pitxu.lib.utils.audio_parameters_loader import AudioParametersLoader

import sys
import sounddevice
import time
import logging
import asyncio
from copy import deepcopy
from datetime import datetime
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.events import EVENT_JOB_ERROR, EVENT_JOB_EXECUTED

class Main(PyXavi):

    _state: Storage = None
    
    _last_processed_minute: int = -1
    _last_processed_second: int = -1
    _last_processed_interaction_percentage: int = -1
    _last_interaction_datetime: datetime = None
    _last_interaction_paused_seconds: int = 0
    _seconds_to_hold_interaction_answer: int = 15
    _idle_minutes_to_show_status: int = 2

    _server: Server = None
    _fan_control_iterated_seconds: int = -1
    _fan_control_trigger_every_seconds: int = 5

    _audio_parameters: dict = None

    _chatbot: GeminiChatbot = None
    _chatbot_session_manager: ChatbotSessionManager = None
    _dictate: Vosk = None
    _raw_input_stream: sounddevice.RawInputStream = None
    _capture_handler: CaptureHandler = None

    _is_pitxu_active: bool = True
    _current_start_timestamp: str = None

    _chatbot_client_callbacks: dict[str, callable] = None

    _input_stream: sounddevice.RawInputStream = None
    _interaction: Interaction = None
    _reactions: Reactions = None

    _support: Support = None

    _maintenance: Maintenance = None
    _reminders: Reminders = None
    _fan_control: FanControl = None

    _stopwatch: Stopwatch = None
    _supported_languages: list = []
    _greeting_sentence: str = None
    _goodbye_sentence: str = None
    _trigger_answers: list[str] = []
    _exit_words: list = []
    _trigger_words: list = []
    _tokens_counter: int = 0

    _dictate_count: int = 0
    _answer_count: int = 0

    ENGLISH: str = "en-us"
    CATALAN: str = "ca"
    GERMAN: str = "de"
    SPANISH: str = "es"

    SCHEDULER_LIB_LOGLEVEL = logging.WARNING
    TZLOCAL_LIB_LOGLEVEL = logging.INFO

    VERBOSE_DEBUG: bool = True

    def __init__(self, config: Config = None, params: Dictionary = None):

        super(Main, self).init_pyxavi(config=config, params=params)

        # Handle SIGTERM for graceful shutdown
        signal.signal(signal.SIGTERM, self._handle_signal)
        signal.signal(signal.SIGINT, self._handle_signal)

        self._instantiate()
    
    async def run(self):

        sw_init = self._stopwatch.start(name="init")

        try:

            # Execute the initial maintenance tasks
            self._maintenance.clean_previous_mocked_images()
            self._maintenance.clean_previous_generated_audios()
            self._maintenance.clean_previous_generated_audio_signal_plots()
            self._maintenance.clean_previous_generated_audio_spectrogram_plots()
            self._maintenance.clean_previous_generated_audio_fourier_transform_plots()

            # Register that we just did a new start
            self._current_start_timestamp = self._maintenance.write_new_start_timestamp_to_file()

            # Initialise the Interaction manager, with Process pool, shared memory, displays, painter and TTS.
            self._initialize_interactions()
            # This is the only one that initializes BEFORE showing the phase. We need interaction() to be ready!
            self._interaction.show_init_phases(1, text="💬 Interactions")

            # Startup splash. It should be understood as a "Loading..." screen.
            # We set it for 4s, but it may be overridden by the display config block for the related display.
            self._interaction.startup_splash(for_seconds=4.0)

            # Load all language statics, like the exit words and the greeting / goodbye sentences
            self._interaction.show_init_phases(2, text="⚙️  Statics, Params and Support")
            self._load_statics_params_and_support()

            # Initialise all classes that require a model. They go per language.
            self._interaction.show_init_phases(3, text="🧠 Models")
            self._load_models()

            # Initialize the microphone and defines the callback for the audio capture.
            self._interaction.show_init_phases(4, text="🎙️  Microphone")
            self._instantiate_input_stream()
                
            # Set up of all the session context we need for the Chatbot and the MCP tools
            self._interaction.show_init_phases(5, text="🤖 Chatbot Session Manager")
            await self._initialize_chatbot_session_manager()

            # Initialise the Chatbot async context with all the tools from the session manager
            self._interaction.show_init_phases(6, text="🤖 Chatbot")
            await self._chatbot.initialize_async(tools=self._chatbot_session_manager.tools)
            self._chatbot_client_callbacks = self._chatbot.get_session_manager().get_client_callbacks_by_function_name()

            # Initialise the Server that accepts requests to the defined endpoints.
            self._interaction.show_init_phases(7, text="🖥️  Server")
            self._initialize_server()

            # Initialize the Reactions class
            self._interaction.show_init_phases(8, text="⚡️ Reactions")
            self._initialize_reactions(input_stream=self._input_stream)

            # TODO: We need to have a way to set callbacks by time, for the reminders and the maintenance tasks. 
            #   That would be the equivalent of the do_every_minute_tasks() and do_every_second_tasks() that we had in the loop.
            self._interaction.show_init_phases(9, text="⏱️  Schedulers")
            self._initialize_schedulers()

            # Welcome greeting
            sw_greeting = self._stopwatch.start(name="greeting")
            self._interaction.show_init_phases(10, text="👋 Greeting")
            self._interaction.say(self._greeting_sentence)
            self._xlog.debug("⏱️  Greeting: " + str(self._stopwatch.stop(sw_greeting)))

            # Clean the display after initialisation.
            self._log_debug("Clearing display after initialisation.")
            self._interaction.clear_combined_display()
            self._interaction.wait_for_all_queues_to_empty()
            self._xlog.debug("⏱️  Initialisations: " + str(self._stopwatch.stop(sw_init)))

            # Before we start with the loop, let's set the last interaction time to now
            # It just started, there was a greeting after all.
            # Maybe the user wants to talk straight away without the trigger words.
            self.reset_last_interaction_event_mark()
            self._interaction.unmute_microphone(input_stream=self._input_stream)

            # At this point, all initialisations are done.
            # Because we work this callbacks, this is the last point before the signal.pause() stops and waits
            self._interaction.show_init_phases(11, text="✅ Ready")
            self._xlog.info("✅ All initialisations done, entering idle state, waiting for interactions...")

            # HERE WAS THE MAIN LOOP.
            #   It has been moved to main_execution_on_vad_detected_finished() method,
            #   that is called by the VAD callback when the user finishes speaking.

            # Wait indefinitely until a signal is received (like SIGTERM for graceful shutdown)
            # Here it was a signal.pause() before, but it fails to hold the application when the APscheduler triggers and
            #   executes any System.* function that uses a subprocess.run(). Feels like the subprocess.run() sends any SIGINT or SIGTERM or any other
            #   and the signal.pause() gets it and releases the pause, and the app finishes.
            # I've tried to catch all possible signals and no avail. I surrended to end up using a while-loop, but I really don't like it.
            try:
                while True:
                    await asyncio.sleep(1)
            except (KeyboardInterrupt, SystemExit) as e:
                self._xlog.info("Pressed Control + C from Main.run() or received termination signal, exiting MainClientPTT run loop.")
            
            # Now that the pause has resumed, means that we are meant to close.
            # Make sure we leave the state properly
            self._xlog.debug("🏁 Exit signal detected.")
            self._interaction.set_idle_mode_off()
            self._interaction.wait_for_foreground_display_queue_to_empty()
            self._interaction.wait_for_busy_foreground_display_to_idle()

        except KeyboardInterrupt:
            self._xlog.info("Pressed Control + C from main")
        except VoskException as ve:
            if not self._is_pitxu_active:
                self._xlog.warning("🛑 Exception detected in Main run loop, but Pitxu is already in the process of closing, so ignoring it: " + str(ve))
                return
            self._xlog.error("🛑 VoskException detected in Main run loop: " + str(ve))
        except Exception as e:
            if not self._is_pitxu_active:
                self._xlog.warning("🛑 Exception detected in Main run loop, but Pitxu is already in the process of closing, so ignoring it: " + str(e))
                return
            self._xlog.error("🛑 Error in Main run loop: " + str(e))
            self._xlog.error(full_stack())  
        
        # However it happened, just close nicely.
        self.close_nicely()
    
    async def main_execution_on_vad_detected_started(self):
        """
        This method is called when the user starts speaking, detected by the VAD in CaptureHandler.
        It is meant to be passed as a callback to the CaptureHandler, to be called in vad_on_speech_start() method there.

        THE WHOLE CHAIN IS WRONG. USER DIDN'T START SPEAKING, INSTEAD, VAD DETECTED SOMETHING.
        WE NEED TO CHANGE THE SHARED MEMORY FLAG THAT IT USES, AND ALL THE METHOD NAMES FROM user_speaking TO vad_detected_speech.
        THE ACTION ON THE user_speaking MUST BE ONCE THE TRANSCRIPTION IS POSITIVE, BUT THE DISPLAY FLOW CAN STAY.
        """

        self._xlog.info("User started speaking, via VAD callback.")

        try:

            # self._interaction.show_arbitrary_icon_on_foreground_while_user_speaking(
            #     icon="🎙️", 
            #     text="SPEAKING", 
            #     color=self._interaction.get_canvas_from_foreground_display().COLOR_GREEN)
            # self._interaction.wait_for_foreground_display_queue_to_empty()
            pass
        
        except Exception as e:
            self._xlog.error("🛑 Error in main_execution_on_vad_detected_started(): " + str(e))
            self._xlog.error(full_stack())

    
    async def main_execution_on_vad_detected_finished(self):
        """
        This method is called when the user finishes speaking, detected by the VAD in CaptureHandler.
        It is used to trigger the processing of the captured audio immediately, abandoning the main loop iteration approach.
        It is meant to be passed as a callback to the CaptureHandler, to be called in vad_on_speech_end() method there.
        """

        self._xlog.info("Main execution triggered by user finishing speaking, via VAD callback.")

        try:
        
            # Pitxu may be already closing, so we better check the state before doing anything.
            if not self._is_pitxu_active:
                self._xlog.warning("🛑 Main execution triggered by user finishing speaking, but Pitxu is already in the process of closing, so ignoring it.")
                return
            
            # Initialize the question variable, that will be filled with the recognized text from the microphone.
            question = ""
            
            # Recognize what comes from the microphone
            sw_dictate = self._stopwatch.continue_or_start(name="dictate" + str(self._dictate_count))
            # question = self._dictate.recognize()
            question = self._dictate.recognize_all_queue_at_once()
            if (question == None or question.strip() == ""):
                # Nothing recognized, nothing to process.
                return

            # Still here? Then something got recognised.
            self._log_debug("💬 Recognised dictate: " + question)
            self._xlog.debug("⏱️  Dictate " + str(self._dictate_count) + ": " + str(self._stopwatch.stop(sw_dictate)))
            self._dictate_count += 1

            # Mute microphone to avoid self-looping
            # ❗️ THE FLOW STOPS HERE, JUST AFTER MUTING THE MIC, THE LOGGING THA COMES NEXT DOES NOT SHOW UP.
            self._interaction.mute_microphone(input_stream=self._input_stream)
            self._log_debug("REMOVEME Microphone muted to avoid self-looping while processing the interaction.")

            # Initialize the answer that collects until interaction.
            answer = None

            # Analyze the question to see what to do.
            text_has_exit_intention = self._text_has_exit_intention(question)
            text_is_only_trigger_words = self._text_is_only_trigger_words(question)
            text_initial_words_intend_to_trigger_interaction = self._text_initial_words_intend_to_trigger_interaction(question)
            text_continues_ongoing_interaction = self._text_continues_ongoing_interaction(question)

            # Avoid calling the Chatbot when we can exit directly.
            if text_has_exit_intention and text_continues_ongoing_interaction:

                self._log_debug("Detection: We're inside hold interaction time and the user wants to exit.")

                # An interaction comes, stop the idle mode.
                self._interaction.set_idle_mode_off()

                # Just assume a goodbye
                answer = self._goodbye_sentence
            # Avoid calling the Chatbot when the text is only meant for waking up the system.
            elif text_is_only_trigger_words:

                self._log_debug("Detection: Text only has trigger words.")
                                
                # An interaction comes, stop the idle mode.
                self._interaction.set_idle_mode_off()

                # Randomly choose one of the trigger answers
                import random
                answer = random.choice(self._trigger_answers)
            # Check if the text is meant to trigger or continue an interaction
            # Same as before, but the question is passed to the chatbot.
            elif text_initial_words_intend_to_trigger_interaction or text_continues_ongoing_interaction:

                self._log_debug("Detection: Text intends to trigger or continue an interaction.")

                # Here we start with the Chatbot.
                # -------------------------------

                # An interaction comes, stop the idle mode.
                self._interaction.set_idle_mode_off()

                # We set it as busy in shared memory, so the Background Display can show the thinking effect
                # Apparently, in the Raspberry Pi, the TTS starts too fast and the display does not get time
                #   to react on the busy flag changes and be displayed on time.
                self._interaction.show_thinking()
                # I am going to try to show the question while thinking.
                # It may give some time to the LCD to show the previous called thinking effect.
                self._interaction.show_arbitrary_text_on_foreground_while_thinking(
                    icon="👤",
                    text=question,
                    font_size=24,
                )
                self._interaction.wait_for_background_display_queue_to_empty()
                self._interaction.set_chatbot_busy()
                chat_response: ChatbotResponse = await self._chatbot.ask_async(question)
                self._tokens_counter += chat_response.metadata.total_token_count if chat_response.metadata and chat_response.metadata.total_token_count is not None else 0
                self._interaction.unset_chatbot_busy()

                try:
                    # We react on the answer received from the Chatbot, that may include function call responses and code blocks,
                    # or instructions for us to react, beyond the text to speak.
                    # For example, we may have to execute a Shutdown.
                    #
                    # Keep in mind that:
                    #   - repeating a question that involves a tool does not mean that in the second time the tool gets called.
                    #       It may just take the previous question and answer again.
                    #       There may not be a second function call response.
                    #   - by taking get_last(), we may be showing a previous response that does not fit to the question.
                    #       So the second time we may not be able to show the time on the screen, for example.
                    self._xlog.info(f"Reacting to a Chatbot answer: \n\t- Text: {chat_response.text}\n\t- Function Calls: {chat_response.function_call_history.get_names()}\n\t- Code blocks: {len(chat_response.code) if chat_response.code else 0}")
                    self._reactions.react_on_answer(chat_response=chat_response)
                except Exception as e:
                    self._xlog.error("🛑 Error reacting to function call: " + str(e))
                
                # Finally, this is the answer string that moves on.
                answer = chat_response.text

                # This waiting happens BEFORE we reached the answering phase with the interaction.say().
                # If the react_on_last_function_call() involved a show_arbitrary_text_on_foreground_while_speaking(),
                # It will be waiting forever because the TTS has not started yet.
                # - Commenting it out to see how it goes.
                # - Uncommenting again because seems like the block happens in interaction.say() instead.
                self._interaction.wait_for_foreground_display_queue_to_empty()

            # Anything else is ignored.
            else:
                self._xlog.debug("💤 Ignoring dictate as no interaction was intended.")
                # Removing the question, as it could be an unwanted trigger for exit.
                question = ""
            
            # We have an answer, whatever it is. Interact back.

            # Do we actually have any answer?
            if answer is not None and answer.strip() != "":
            
                # Clean the answer first, just in case
                answer = Text.remove_emojis(answer)
                answer = Text.remove_markdown(answer)
                answer = Text.replace_known_text(answer, self._xconfig.get("language.text_replacements." + self._xparams.get("language"), {}))

                # Answer
                sw_answer = self._stopwatch.start(name="answer" + str(self._answer_count))
                self._interaction.say(answer)
                self._xlog.debug("⏱️  Answer " + str(self._answer_count) + ": " + str(self._stopwatch.stop(sw_answer)))
                self._answer_count += 1

                # If we were communicating an error, it's over and start new
                if self._interaction.is_chatbot_error():
                    self._interaction.unset_chatbot_error()
                
                if text_has_exit_intention:
                    self._xlog.info("Exit intention detected in the recognized text, and an answer was given, so proceeding to close Pitxu nicely.")
                    # The goodbye sentence is said, we can proceed to close.
                    self.close_nicely()
                    return
                
                # Last thing to do is to remember this as the last interaction.
                # Has to happen at the very last otherwise the time is consumed by the possible answering process.
                self.reset_last_interaction_event_mark()

            # Unmute microphone to continue listening, but we'll wait an extra second to avoid immediate re-triggering.
            # This second here makes the human-computer interaction worse.
            # We need to find a way to stop the TTS audio from being input into the SST without intorducing such a delay.
            # COMMENTED: Trying to activelly stop and start the input stream at the same mutin/unmuting the mic,
            #   instead of waiting. 
            # Hypothesis: When we activate the mic again, the buffer may contain data (the last spoken text) and it gets processed.
            # time.sleep(1)
            self._interaction.unmute_microphone(input_stream=self._input_stream)
        
        except KeyboardInterrupt:
            self._xlog.info("Pressed Control + C from main")
        except VoskException as ve:
            if not self._is_pitxu_active:
                self._xlog.warning("🛑 Exception detected in Main run callback, but Pitxu is already in the process of closing, so ignoring it: " + str(ve))
                return
            self._xlog.error("🛑 VoskException detected in Main run callback: " + str(ve))
        except Exception as e:
            if not self._is_pitxu_active:
                self._xlog.warning("🛑 Exception detected in Main run callback, but Pitxu is already in the process of closing, so ignoring it: " + str(e))
                return
            self._xlog.error("🛑 Error in Main run callback: " + str(e))
            self._xlog.error(full_stack())  


    # ------------- End of the main method run() -------------

    def get_seconds_since_last_interaction(self) -> int:
        if self._last_interaction_datetime is None:
            return None
        
        # This is:
        #   Current time
        #       minus last interaction time
        #       minus the amount of seconds that VAD detection paused the counter.
        #
        # The self._last_interaction_paused_seconds is maintained in the on_every_second_tasks(), 
        #   in the block of the holding interaction time.
        return (datetime.now() \
                - self._last_interaction_datetime).total_seconds() \
                - self._last_interaction_paused_seconds
    
    def reset_last_interaction_event_mark(self):
        self._last_interaction_datetime = datetime.now()
        self._last_interaction_paused_seconds = 0

    def _text_has_exit_intention(self, text):
        return text in self._exit_words
    
    def _text_continues_ongoing_interaction(self, question: str) -> bool:
        # We may be in an ongoing interaction, so let's check the last interaction time
        # We must take in account the time spent talking
        if self._last_interaction_datetime is not None and \
                self.get_seconds_since_last_interaction() <= self._seconds_to_hold_interaction_answer:
                return True
        
        # No ongoing interaction
        return False
    
    def _text_initial_words_intend_to_trigger_interaction(self, question: str) -> bool:
        # Let's consider that from what the user said, the first 5 words need to be one of the trigger words
        first_words = Text.remove_accents(" ".join(question.lower().strip().split(" ")[0:5]))
        for trigger_word in self._trigger_words:
            if trigger_word in first_words:
                return True
        
        # No trigger word found
        return False
    
    def _text_is_only_trigger_words(self, question: str) -> bool:
        # Let's consider that from what the user said, all words need to be one of the trigger words
        all_user_input = Text.remove_accents(question.lower().strip())
        for trigger_word in self._trigger_words:
            if trigger_word in all_user_input:
                return True
        
        # No trigger word found
        return False
    
    # ------------ Initializations and closings -------------
    
    def close_nicely(self, avoid_final_exit=False):
        """
        Close the application nicely, cleaning up resources and saving state.

        Args:
            avoid_final_exit (bool): If True, avoids calling sys.exit() at the end. Useful when we want to shutdown or reboot after this method.
        """

        if not self._is_pitxu_active:
            self._log_debug("Already closed nicely, skipping.")
            return
        
        # Mark as not active anymore, so the rest of the app can see the state
        self._is_pitxu_active = False

        sw_closing = self._stopwatch.continue_or_start(name="closing")
        self._log_debug("Closing nicely...")

        # The chatbot may be in "Thinking" mode, unset it anyways.
        self._interaction.unset_chatbot_busy()

        # Reactivate the microphone because it keeps the state on shutdowns / reboots.
        # We never want it to be muted when starting.
        self._interaction.unmute_microphone()

        # In case that the user was speaking, clear the flag to avoid waiting forever.
        self._interaction.unset_vad_detected()

        # The scheduler contains a thread, so close it properly.
        self._scheduler.shutdown()

        # Persist state
        self.persist_state()

        # Stop Idle Mode if active
        if self._interaction.is_idle_mode_on():
            self._interaction.set_idle_mode_off()

        # Clear the displays
        self.clear_displays()

        # Close the Support class, which empties the queue discarding all actions there
        if self._support is not None:
            self._support.close()

        # Wait for all the queues and processes to get empty
        self._interaction.get_process_pool().get_memory_manager().force_all_flags_to_idle()
        self._interaction.wait_for_all_queues_to_empty()
        self._interaction.wait_for_all_busy_processes_to_idle()

        # Stop the Chatbot Session Manager.
        # ❗️ THE CLOSING STOPS HERE. RESULT() TIMESOUT AND THE EXCEPTION GETS CAUGHT, BUT THE APP KEEPS RUNNING AND DOES NOT CLOSE. IT SEEMS LIKE THE EXCEPTION IS NOT THE PROBLEM, BUT THE FACT OF WAITING FOR THE COROUTINE TO FINISH WITH RESULT() IS WHAT MAKES IT HANG. MAYBE WE CAN JUST CALL THE COROUTINE WITHOUT WAITING FOR IT TO FINISH? OR WAIT FOR IT WITH A TIMEOUT AND IGNORE IF IT TIMES OUT?
        if self._chatbot_session_manager is not None:
            future = asyncio.run_coroutine_threadsafe(self._close_chatbot_session_manager(), asyncio.get_event_loop())
            try:
                if future.result(timeout=1) == True:  # Wait for the coroutine to finish, with a timeout to avoid hanging indefinitely
                    self._xlog.info("Chatbot Session Manager closed successfully.")
                else:
                    self._xlog.warning("Chatbot Session Manager did not close successfully.")
            except Exception as e:
                self._xlog.error("🛑 Error while closing Chatbot Session Manager: " + str(e))
                self._xlog.error("🛑 " + full_stack())

        # Close the server
        if self._server is not None:
            self._server.close()

        # Close Vosk
        if self._dictate is not None:
            self._dictate.close()

        # Finish all related multiprocess stuff
        self._interaction.get_process_pool().finish_leftover_processes()

        # Finish interactions and related processes
        self._interaction.close()

        # ------ Final logs ------

        self._xlog.debug("⏱️  Closed: " + str(self._stopwatch.stop(sw_closing)))

        # Here comes anything that we want to do before leaving
        try:
            self._xlog.info("⏱️  Final Stopwatch report:\n" + self._stopwatch.stop_and_report())
            self._xlog.info("💡  Memory used: " + str(System.memory_use(System.MEGABYTES)) + " MB")
            self._xlog.info("💰  Tokens used: " + str(self._tokens_counter))
        except (Exception, RuntimeError) as e:
            self._xlog.error("🛑 Error while logging final stats: " + str(e))

        # If requested, avoid the final sys.exit()
        if avoid_final_exit:
            self._xlog.info("Exiting nicely avoided final sys.exit() as requested.")
            return

        # And now, simply exit
        self._xlog.info("Exiting now. Goodbye!")
        sys.exit(0)
    
    def persist_state(self):

        self._state.set("tokens_counter", int(self._state.get("tokens_counter", 0)) + self._tokens_counter)
        self._state.write_file()
        self._xlog.debug("Persisted state to " + self._xconfig.get("storage.state_file"))

    def clear_displays(self):
        if self._interaction.displays_are_combined():
            self._log_debug("Clearing the Combined Display.")
            self._interaction.clear_combined_display()
            return
        self._log_debug("Clearing the Foreground Display.")
        self._interaction.clear_foreground_display()
        self._log_debug("Clearing the Background Display.")
        self._interaction.clear_background_display()

    def _instantiate(self):
        """
        The initialization of the Main itself, what you would include in __init__()
        """
        # Initialize State
        self._state = Storage(filename=self._xconfig.get("storage.path") + self._xconfig.get("storage.state_file"))

        # Initial Language. 1st from the state, then from the config, and last default to Catalan.
        language = self._state.get("language", self._xconfig.get("app.default_language", self.CATALAN))
        self._xparams.set("language", language)

        # Initialize Maintenance utility
        self._maintenance = Maintenance(config=self._xconfig, params=self._xparams)

        # Supported Languages
        self._supported_languages = self._xconfig.get("app.supported_languages")

        # Check and complain if the initial language is not supported
        if self._xparams.get("language") not in self._supported_languages:
            self._xlog.error(f"🛑 Initial language [{self._xparams.get('language')}] is not in the supported languages list: {self._supported_languages}")
            self._xlog.error("🛑 Please change the initial language in the state file or the default language in the config file to one of the supported languages.")
            self._xlog.error("🛑 Supported languages are: " + ", ".join(self._supported_languages))
            self._xlog.error("🛑 Exiting now.")
            sys.exit(1)

        # The Reminders functionality
        self._reminders = Reminders(config=self._xconfig, params=self._xparams)

        # Stopwatch to measure times
        self._stopwatch = Stopwatch()
    
    def _handle_signal(self, sig, frame):
        """
        Handle signals for graceful shutdown.
        This is set to handle SIGTERM, that is the signal sent by systemctl stop and reboot commands.

        This allows the service to stop gracefully when receiving a termination signal,
        that happens with systemctl stop or reboot commands.
        """

        signal_name = signal.Signals(sig).name if sig in signal.Signals.__members__.values() else str(sig)

        self._xlog.warning(f"🔪 Signal [{signal_name}] received in Main, closing nicely now...")
        self.close_nicely()
    
    def _load_statics_params_and_support(self):
        """
        Load all the static values and params that we are going to use in the app, that may depend on the language.
        This includes the greeting and goodbye sentences, the trigger words and answers, and the exit words.
        """

        # Initialize the case fan control and apply it.
        self._fan_control = FanControl(config=self._xconfig, params=self._xparams)
        self._fan_control_trigger_every_seconds = self._xconfig.get("gpio.cpu_temperature.control_interval_seconds", self._fan_control_trigger_every_seconds)
        self._fan_control.toggle_all_fans_by_temperature()

        # Get all audio parameters in one place, to be used by the different components that need it
        #   (SST, TTS, preprocessing, dumper, ...).
        self._audio_parameters = AudioParametersLoader(config=self._xconfig, params=self._xparams).get_audio_parameters()
        self._xparams.set("audio_parameters", self._audio_parameters)

        # Load all language statics, like the exit words and the greeting / goodbye sentences
        self._load_language_statics()

        # Initialise the Support worker.
        support_params = Dictionary({
            "audio_parameters": self._audio_parameters,
            "process_pool": self._interaction.get_process_pool(),
        })
        self._support = Support(config=self._xconfig, params=support_params)
        self._support.initialize()
    
    def _load_models(self):
        
        # Initialise Speech-to-Text. This runs in the main process
        self._xlog.debug("Initialising the Speech-to-Text with language [" + self._xparams.get("language") + "]")
        # COMMENTED: This way Vosk chooses between config or device.
        # self._xparams.set("samplerate", self._xconfig.get("speech-to-text.input_samplerate"))

        if self._xconfig.get("speech-to-text.engine", "vosk") == "vosk":
            self._xparams.set("samplerate", self._audio_parameters.get("stt_samplerate"))
            self._xparams.set("support", self._support)
            self._dictate = Vosk(config=self._xconfig, params=self._xparams)
        else:
            self._xlog.error("🛑 Unsupported Speech-to-Text engine specified in config: " + self._xconfig.get("speech-to-text.engine"))
            self._xlog.error("🛑 Supported engines are: vosk")
            self._xlog.error("🛑 Exiting now.")
            sys.exit(1)

        input_audio_chunk_queue = self._dictate.get_queue()

        # Initialise the Capture Handler, that captures the audio from the microphone.
        # It needs the original samplerate so that it can resample the chunk from it to 16 kHz.
        self._capture_handler = CaptureHandler(config=self._xconfig, params=Dictionary({
            "capture_queue": input_audio_chunk_queue,
            "microphone_samplerate": self._audio_parameters.get("input_samplerate"),
            "target_samplerate": self._audio_parameters.get("resample_target_samplerate"),
            # The callback that triggers when the user starts speaking, detected by the VAD.
            "on_vad_detected_started_callback": self.main_execution_on_vad_detected_started,
            # The callback that triggers the main execution when the user finishes speaking, detected by the VAD.
            "on_vad_detected_finished_callback": self.main_execution_on_vad_detected_finished,
            # The callback needs the main event loop from asyncio to trigger the main execution, so we pass it here.
            "main_event_loop": asyncio.get_event_loop()
        }))

        # # Initialise the Raw Input Stream for microphone
        # self._xlog.debug("Initialising the Raw Input Stream for microphone")
        # if self._xconfig.get("speech_to_text.mock", True) is False:
        #     self._xlog.info("Loading Real Raw Input Stream (mic) for Speech-to-Text by Config")
        #     from pitxu.lib.speech_to_text.wrapper_raw_input_stream import WrapperRawInputStream
        #     # Correct format for Vosk is PCM 16khz 16bit mono
        #     self._raw_input_stream = WrapperRawInputStream(samplerate=self._dictate.samplerate,
        #                     blocksize = 0, 
        #                     device=self._dictate.device,
        #                     dtype="int16", 
        #                     channels=1,
        #                     callback=self._dictate.callback)
        # else:
        #     self._xlog.info("Loading Mocked Raw Input Stream (mic) for Speech-to-Text by Config")
        #     from pitxu.lib.speech_to_text.mocked_raw_input_stream import MockedRawInputStream
        #     self._raw_input_stream = MockedRawInputStream(config=self._xconfig, dictionary=self._xparams)

        # Initialise Chatbot
        self._xlog.debug("Initialising the Chatbot Client with language [" + self._xparams.get("language") + "]")
        self._chatbot = GeminiChatbot(config=self._xconfig, params=self._xparams)

    def _load_language_statics(self):

        # Load the greeting sentence
        self._xlog.debug("Load Greeting with language [" + self._xparams.get("language") + "]")
        self._greeting_sentence = self._xconfig.get("language.greeting." + self._xparams.get("language"))

        # Load the goodbye sentence
        self._xlog.debug("Load Goodbye with language [" + self._xparams.get("language") + "]")
        self._goodbye_sentence = self._xconfig.get("language.goodbye." + self._xparams.get("language"))

        # Load trigger words
        self._xlog.debug("Load Trigger words with language [" + self._xparams.get("language") + "]")
        self._trigger_words = self._xconfig.get("language.trigger_words." + self._xparams.get("language"))

        # Load trigger answers
        self._xlog.debug("Load Trigger answers with language [" + self._xparams.get("language") + "]")
        self._trigger_answers = self._xconfig.get("language.trigger_answers." + self._xparams.get("language"))

        # Compile exit words
        all_possible_exit_words = []
        for language, exit_words in dict(self._xconfig.get("language.exit_words")).items():
            for word in exit_words:
                if word not in all_possible_exit_words:
                    all_possible_exit_words.append(word)
        self._xlog.debug("Load ALL possible exit words " + str(all_possible_exit_words) + "")
        self._exit_words = all_possible_exit_words

        # Idle mode after some minutes of inactivity
        self._idle_minutes_to_show_status = self._xconfig.get("maintenance.idle_minutes", self._idle_minutes_to_show_status)
    
    def _instantiate_input_stream(self):
        """
        Initialization of the Raw Input Stream for the microphone, that feeds the Speech-to-Text engine with audio chunks.
        """

        # This is the samplerate that generates the chunks received in CaptureHandler.callback().
        #   In MacOS the microphone can't be set to an arbitrary samplerate that fits on us, so
        #   the config value for it must be -1 so that it gets inferred by de library.
        # Then the CaptureHeader will resample it to 16 kHz, and that's why the rest of components work
        #   under 16 kHz.
        # Set the samplerate that we're going to settle for the STT (ensure that the STT model has the EXACT SAME VALUE)
        # Fall back to what the Vosk's Kaldi Recognizer is using if the config value is not set.
        samplerate = self._audio_parameters.get("input_samplerate")
        blocksize = self._xconfig.get("speech-to-text.blocksize", 1024)

        self._xlog.debug("Initialising the Raw Input Stream for microphone")
        self._input_stream = sounddevice.RawInputStream(
                            #samplerate=self._dictate.samplerate,
                            # samplerate=16000, # Vosk works better with 16kHz, even if the mic supports higher rates.
                            samplerate=samplerate,
                            # blocksize=0, 
                            blocksize=blocksize,
                            device=self._dictate.device,
                            dtype="int16", 
                            channels=1,
                            # callback=self._dictate.callback) as input_stream:
                            callback=self._capture_handler.callback)
        
        self.log_summary("Raw Input Stream (Mic) initialized", [
                    ("Device", self._dictate.device),
                    ("Sample Rate", samplerate),
                    ("Block Size", blocksize if blocksize > 0 else "0 (automatic by pyAudio)"),
                    ("Channels", 1),
                    ("Data Type", "int16"),
                    ("Callback", "CaptureHandler.callback")
                ])
    
    async def _initialize_chatbot_session_manager(self):
        """
        Initialization of the Chatbot Session Manager, that manages the session with the Chatbot and its history.
        """

        self._xlog.info("Initialising Chatbot Session Manager")
        
        self._chatbot_session_manager = self._chatbot.get_session_manager()
        await self._chatbot_session_manager.start_session()
    
    async def _close_chatbot_session_manager(self) -> bool:
        """
        Closing of the Chatbot Session Manager, that manages the session with the Chatbot and its history.
        """

        self._xlog.info("Closing Chatbot Session Manager")
        
        if self._chatbot_session_manager is not None:
            await self._chatbot_session_manager.stop_session()
            self._chatbot_session_manager = None
        
        return True
    
    def _initialize_schedulers(self):
        """
        Initialisation of the schedulers for the tasks that need to be executed by time, like the reminders.
        """

        def job_listener(event):
            if event.exception:
                self._xlog.error("🛑 Error in scheduled job: " + str(event.exception))
            # We already show some minimal logging for each job executed. This is not really needed beyond debug.
            # else:
            #     self._log_debug("✅ Scheduled job executed successfully: " + str(event.job_id))

        self._xlog.info("Initialising Schedulers")
        self._scheduler = BackgroundScheduler(
            job_defaults={
                "coalesce": True
            }
        )
        self._scheduler.add_listener(job_listener, EVENT_JOB_EXECUTED | EVENT_JOB_ERROR)

        self._log_debug(f"Setting 'apscheduler' library log level to {self.SCHEDULER_LIB_LOGLEVEL}")
        logging.getLogger("apscheduler").setLevel(self.SCHEDULER_LIB_LOGLEVEL)
        self._log_debug(f"Setting 'tzlocal' library log level to {self.TZLOCAL_LIB_LOGLEVEL}")
        logging.getLogger("tzlocal").setLevel(self.TZLOCAL_LIB_LOGLEVEL)

        # EVERY MINUTE
        self._scheduler.add_job(self.do_every_minute_tasks, 'interval', seconds=60, args=[None])

        # EVERY SECOND
        self._scheduler.add_job(self.do_every_second_tasks, 'interval', seconds=1)

        # EVERY NIGHT AT 3 AM
        self._scheduler.add_job(self.do_at_night_tasks, 'cron', hour=3, minute=0)
        self._scheduler.start()
    
    def _initialize_interactions(self):
        """
        Initialisation of the Interaction class, that manages output (TTS and displays)
        """

        self._xlog.info("Initialising Interaction class")
        self._interaction = Interaction(config=self._xconfig, params=self._xparams)

        # We start with the microphone muted.
        # At this point we don't have the Input Stream yet, just making sure that we start muted.
        self._interaction.mute_microphone()
    
    def _initialize_reactions(self, input_stream: sounddevice.RawInputStream = None):
        """
        Initialisation of the Reactions class, that manages the reactions to the Chatbot answers and tool calls.
        """

        self._xlog.info("Initialising Reactions class")

        params: Dictionary = Dictionary({
            "interaction": self._interaction,
            "client_callbacks": self._chatbot_client_callbacks,
            "close_nicely_callback": self.close_nicely,
            "input_stream": input_stream
        })
        self._reactions = Reactions(config=self._xconfig, params=params)
    
    def _initialize_server(self):
        """
        Initializes the Server that accepts requests to the defined endpoints
        """

        if self._xconfig.get("server.enabled", False) and self._xconfig.get("app.execution_mode", "") in ["public", "server"]:
            self._xlog.info("Initializing Server as it is enabled by configuration.")
            # params = deepcopy(self._xparams)
            params = Dictionary()
            # Needed for the Server.
            params.set("app_version", self._xparams.get("app_version"))
            params.set("samplerate", self._audio_parameters.get("server_samplerate")) # Also needed in Vosk.
            params.set("output_interaction", self._interaction)
            params.set("chatbot", self._chatbot)
            params.set("chatbot_client_callbacks", self._chatbot_client_callbacks)
            params.set("support", self._support) # Also needed in Vosk & Preprocessor
            params.set("current_start_timestamp", self._current_start_timestamp)
            # Needed for the Vosk class initialised inside the Server.
            params.set("language", self._xparams.get("language"))
            params.set("audio_parameters", self._audio_parameters) # Also needed by the Preprocessor

            self._server = Server(config=self._xconfig, params=params)
            self._server.initialize()
        else:
            self._xlog.info(f"Server is disabled by configuration (" +
                            f"enabled: {"TRUE" if self._xconfig.get('server.enabled', False) else "FALSE"}, " +
                            f"execution mode [{self._xconfig.get('app.execution_mode', '_NOT_SET_')}]"+
                            ") > not initializing it.")

    # ------- Stuff to do every minute -------

    def do_every_minute_tasks(self, input_stream: sounddevice.RawInputStream = None):
        current_minute = time.localtime().tm_min
        if current_minute != self._last_processed_minute:
            self._last_processed_minute = current_minute
            self._log_debug("🕐 New minute detected: " + str(current_minute) + ".")
            # Get the possible reminder for the current date and time
            date_str = datetime.now().strftime(Reminders.FORMAT_DATE)
            time_str = datetime.now().strftime(Reminders.FORMAT_TIME)
            reminder: dict = self._reminders.get_reminder(date_str, time_str)
            if reminder is not False:
                self._log_debug("📝 Reminder found for now: " + str(reminder))
                # Show reminder in eInk and say it
                reminder_text_for_speaking = self._xconfig.get("language.reminders.reminder_announcement." + self._xparams.get("language")) % reminder.get("text", "")
                self._interaction.set_idle_mode_off()
                self._interaction.wait_for_foreground_display_queue_to_empty()
                self._interaction.wait_for_busy_foreground_display_to_idle()
                self._interaction.show_arbitrary_text_on_foreground_while_speaking(
                    icon="📝",
                    text=reminder.get("text", ""),
                    font_size=Canvas.FONT_SIZE_BIG)
                self._interaction.mute_microphone(input_stream=input_stream)
                self._interaction.say(reminder_text_for_speaking)
                # TODO: Would be wonderful to integrate this spoken reminder to the history of the chatbot
                self._interaction.unmute_microphone(input_stream=input_stream)
                # Remove the reminder now that it's been announced
                self._reminders.delete_reminder(date_str, time_str)
                # Reset the last interaction time, as we just spoke
                self._last_interaction_datetime = datetime.now()
            
            # Every minute, log a bunch of metrics defined internally.
            # It also accepts a dict, that will be merged with the internal metrics.
            self._maintenance.log_metrics()

            # If we've been inactive for more than 2 minutes, start the idle mode.
            if self._last_interaction_datetime == None or \
                Xtime.now_minus_seconds_as_milliseconds(seconds=self._idle_minutes_to_show_status * 60) > self._last_interaction_datetime.timestamp() * 1000:

                if not self._interaction.is_idle_mode_on():
                    self._log_debug(f"User has been inactive for more than {self._idle_minutes_to_show_status} minutes (or was never active), starting idle mode.")
                    self._interaction.set_idle_mode_on()

            # If we've been inactive for more than 2 minutes, show some basic status information in the screen.
            # Also, if we never interacted, asume we're idle.
            if self._interaction.is_idle_mode_on():
                
                self._log_debug(f"User is in idle mode, showing status information.")

                try:
                    wifi = self._maintenance.get_last_gathered_metrics().get("network", {}).get("wifi_ssid", "SSID: Not connected")
                    network = self._maintenance.get_last_gathered_metrics().get("network", {}).get("ip", "IP: Not connected")
                    text = wifi.replace("N/A", "SSID: Not connected") + "\n" + \
                        network.replace("N/A", "IP: Not connected")
                    if self._xconfig.get("app.execution_mode", "") in ["client"]:
                        server_status = self._maintenance.get_last_gathered_metrics().get("pitxu_server_alive", "unreachable")
                        text = text + "\n" + ("✅ Connected" if server_status == "alive" else f"❌ Not Connected:\n{server_status}")
                    
                    self._interaction.show_arbitrary_text_on_foreground_while_idle(
                        icon="💤",
                        text=text,
                        font_size=self._interaction.get_canvas_from_foreground_display().FONT_SIZE_SMALL,
                        header="Idle",
                        font_header_size=self._interaction.get_canvas_from_foreground_display().FONT_SIZE_BIG,
                        show_for_seconds=15)

                except (Exception, RuntimeError) as e:
                    self._xlog.error("🛑 Error while showing idle status information: " + str(e))
            
            # Pollute the logs with VAD stats every minute, as they are interesting to check from time to time.
            if self._xconfig.get("speech-to-text.vad.enabled", False):
                vad_stats = self._capture_handler.get_vad_handler().get_stats()
                self.log_summary("VAD stats", [(key.replace("_", " ").title(), value) for key, value in vad_stats.items()])
    
    # ------- Stuff to do every second -------

    def do_every_second_tasks(self):

        current_second = int(time.time())
        if current_second > self._last_processed_second:
            self._last_processed_second = current_second
            # COMMENTING: This log is too much verbose, as it happens every second.
            # self._log_debug("🕐 New second detected: " + str(time.localtime(current_second).tm_sec) + f".")

            # Control the fans according to the temperature, every some seconds is good enough for that.
            if self._fan_control_iterated_seconds < 0:
                self._fan_control.toggle_all_fans_by_temperature()
                self._fan_control_iterated_seconds += 1
            elif self._fan_control_iterated_seconds >= self._fan_control_trigger_every_seconds - 1:
                self._fan_control_iterated_seconds = -1
            else:
                self._fan_control_iterated_seconds += 1
            
            self._state.set("fan_case_status", self._fan_control.get_fan_status())
            self._state.write_file()

            
            # Show the interaction holding percentage if we're expecting an interaction
            if self._last_interaction_datetime is not None and not self._interaction.is_microphone_muted():
                
                # Calculate how much left in percentages the time to hold the interaction
                seconds_since_last_interaction = self.get_seconds_since_last_interaction()
            
                if seconds_since_last_interaction <= self._seconds_to_hold_interaction_answer:
                    # We are meant to show the holding percentage.

                    if not self._interaction.is_vad_detected():
                        # Vad did not detect anything, and we're in the time window to show the holding percentage
                        # Calculate it.
                        self._last_processed_interaction_percentage = int(100 - (seconds_since_last_interaction / self._seconds_to_hold_interaction_answer * 100))
                    else:
                        self._xlog.debug("🎤 User may be speaking, pausing interaction holding time counter.")
                        self._last_interaction_paused_seconds += 1
                    
                    # Display it.
                    if not self._interaction.is_background_display_busy() and self._last_processed_interaction_percentage >= 0:
                        self._xlog.debug(f"⏳ Waiting for an user interaction. {self._last_processed_interaction_percentage}% (paused {self._last_interaction_paused_seconds}s) time left.")
                        self._interaction.show_interaction_holding_percentage(self._last_processed_interaction_percentage)
                    else:
                        self._xlog.debug("🤖 Background display is busy, not showing interaction holding percentage.")

                elif self._last_processed_interaction_percentage >= 0:
                    # We are meant to clean the display.

                    # if not self._interaction.is_vad_detected():
                        # Vad did not detect anything, and the time to hold the interaction is over.
                        # We clear the background display and reset the percentage.
                        self._last_processed_interaction_percentage = -1
                        self._last_interaction_paused_seconds = 0
                        # Clean the display.
                        if not self._interaction.is_background_display_busy():
                            self._xlog.debug("⏳ Waiting for an user interaction is over. Clearing remainings.")
                            self._interaction.clear_background_display()
                        else:
                            self._xlog.debug("🤖 Background display is busy, not cleaning the background display.")
                    # else:
                    #     self._xlog.debug("🎤 User may be speaking, pausing cleaning holding time counter.")
    
    # ------------- Stuff to do daily -------------

    def do_at_night_tasks(self):

        # At night, we want to clear the logs that are older than the retention period.
        self._maintenance.rotate_metrics_logs()
                    
