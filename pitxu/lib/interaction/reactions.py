from pyxavi import Config, Dictionary, Storage, full_stack
from pitxu.lib.abstract.pyxavi import PyXavi

from pitxu.lib.interaction.interaction import Interaction
from pitxu.lib.objects.chatbot_response import ChatbotResponse
from pitxu.lib.objects.function_call import FunctionCallPair
from pitxu.lib.canvas.canvas import Canvas

from functools import partial
from subprocess import call
import sys
import sounddevice

class Reactions(PyXavi):

    # Support to triger interactions with the user
    interaction: Interaction = None

    # Link to the Tool callback functions, so we can trigger them.
    client_callbacks: dict = {}

    # Link to the close nicely function, so we can trigger it from a reaction if needed.
    close_nicely_callback: callable = None

    # Support to trigger a particular callback when the user intends to end the conversation.
    end_of_conversation_callback: callable = None

    # Support to behave with the microphone.
    input_stream: sounddevice.RawInputStream = None

    # Support to store state.
    state: Storage = None
    
    def __init__(self, config: Config, params: Dictionary):
        super(Reactions, self).init_pyxavi(config=config, params=params)

        if not params.key_exists("interaction") or not isinstance(params.get("interaction"), Interaction):
            raise Exception("Reactions class needs an Interaction instance passed in the params with key 'interaction'")
        self.interaction = params.get("interaction")

        if not params.key_exists("client_callbacks") or not isinstance(params.get("client_callbacks"), dict):
            raise Exception("Reactions class needs a dict with the client callbacks passed in the params with key 'client_callbacks'")
        self.client_callbacks = params.get("client_callbacks")

        if not params.key_exists("close_nicely_callback") or not callable(params.get("close_nicely_callback")):
            raise Exception("Reactions class needs a callable with the close nicely function passed in the params with key 'close_nicely_callback'")
        self.close_nicely_callback = params.get("close_nicely_callback")

        if params.key_exists("end_of_conversation_callback") and callable(params.get("end_of_conversation_callback")):
            self.end_of_conversation_callback = params.get("end_of_conversation_callback")

        if params.key_exists("input_stream") and isinstance(params.get("input_stream"), sounddevice.RawInputStream):
            self.input_stream = params.get("input_stream")
        
        self.initialize()
    
    def initialize(self):
        self._xlog.info("Initializing Reactions")

        # Initialize State
        self.state = Storage(filename=self._xconfig.get("storage.path") + self._xconfig.get("storage.state_file"))

        self._log_debug("Done Initializing Reactions")

    def react_on_answer(self, chat_response: ChatbotResponse) -> ChatbotResponse:
        """
        Reacts to the received answer beyond simply answering, like expressions, emotions, or actions.

        Args:
            chat_response (ChatbotResponse): The last response from the chatbot.
        
        Returns:
            ChatbotResponse: The possibly modified chatbot response after reacting to it.
        """

        # We do need a proper Chat Response. Otherwise just return.
        if chat_response is None or not isinstance(chat_response, ChatbotResponse):
            return chat_response
        
        # The whole logic for the code block needs to be reviewed.
        # The code can come in 2 ways:
        #   1. Inside the text, as part of the answer.
        #       - the code is extracted from the text when parsing the answer from the chatbot.
        #       - this should have priority over a function call with code.
        #   2. As a callback from a Tool
        #       - the code should be handled by the callback of the tool.
        # TODO: This is too messy, should be unified.

        # 1st. handle the case of having the code already post-processed as part of the answer.
        if chat_response.has_code() and len(chat_response.code) > 0:

            try:
                self._xlog.debug("⚡️ Reacting to an answer with code block inside the text")
                chat_response = self.handle_answer_with_code_block(chat_response)
            except Exception as e:
                self._xlog.error("🛑 Error reacting to an answer: " + str(e))
                self._xlog.debug(full_stack())

        # 2nd. handle the answer as an usual reaction.
        else:

            function_call_pair = chat_response.function_call_history.get_last()
            callback_was_handled = False
            if function_call_pair.has_response():
                callback_was_handled = self.react_on_function_call(function_call_pair)

            if not callback_was_handled:
                self._xlog.debug("⚡️ Reacting to an answer without code block or function call, just showing the text on the foreground display.")
                self.interaction.show_arbitrary_text_on_foreground_while_speaking(
                    icon="🧠",
                    text=chat_response.text
                )
        
        # We return the possibly modified chat response, so it can be spoken or shown as well.
        return chat_response
        
    
    def react_on_function_call(self, function_call_pair: FunctionCallPair) -> bool:
        """
        Reacts to the received function call response, meaning that a Tool was used,
        and we're supposed to show anything on the screen.

        Args:
            function_call_pair (FunctionCallPair): The last response from the chatbot with a function call.
        
        Returns:
            bool: True if the function call was handled, False otherwise.
        """

        # The idea here is to be able to use the hardware as part of the response, like moving eyes,
        #   or showing the hour in the Display if asked for the time...
        #
        # More importantly, this is the way to perform a proper close_nicely(), besides just
        #   shutting down or rebooting the system without caring.
        # For this last point to happen, we need to control the answer of the tool, give something
        #   specific to search for here.

        # We do need a proper Function Call Pair (actually a response). Otherwise just return.
        if function_call_pair is None or \
            not isinstance(function_call_pair, FunctionCallPair) or \
            not function_call_pair.has_response():
            return False
        
        self._xlog.debug("⚡️ Reacting to function call: " + str(function_call_pair.function_name))

        # Now distribute according to what we received.
        result = True
        try:

            if function_call_pair.function_name == "error":

                # We got an error.
                self.handle_error(function_call_pair)
            
            elif function_call_pair.function_name == "shutdown_local_machine":

                # We got a shutdown request.
                self.handle_shutdown_request()
            
            elif function_call_pair.function_name == "reboot_local_machine":

                # We got a reboot request.
                self.handle_reboot_request()
            
            elif function_call_pair.function_name == "restart_system":

                # We got a restart request.
                self.handle_restart_request()
            
            elif function_call_pair.function_name == "change_language":

                # We got a language change request.
                self.handle_language_change_request(function_call_pair)
            
            elif function_call_pair.function_name == "user_intends_to_end_conversation":

                # We got an end of conversation request.
                self.handle_end_of_conversation_request(function_call_pair)
            
            elif function_call_pair.function_name in self.client_callbacks.keys():

                # We got a client tool callback, treat it generically.
                # Please note that this must go at the end of all possibilities, so we
                #   can allow particular implementations like the shutdown and reboot above.
                self.handle_client_callback(function_call_pair)

            else:

                self._xlog.debug("⚡️ No reaction implemented for this function call, just ignoring it: " + str(function_call_pair.function_name))
                result = False
            
            return result
        
        except Exception as e:
            self._xlog.error("🛑 Error reacting to function call: " + str(e))
            self._xlog.debug(full_stack())
            return False

    def handle_error(self, function_call_pair: FunctionCallPair):
        self._xlog.debug("🚨  Showing an ERROR in the Foreground Display")

        self.interaction.set_idle_mode_off()
        self.interaction.wait_for_foreground_display_queue_to_empty()
        self.interaction.wait_for_busy_foreground_display_to_idle()

        self.interaction.show_arbitrary_text_on_foreground_while_speaking(
            icon="🚨",
            text=function_call_pair.function_response.response.get("result", "unknown"),
            font_size=self._get_canvas().FONT_SIZE_BIG)
    
    def handle_client_callback(self, function_call_pair: FunctionCallPair):
        self._xlog.debug("↩️  Reacting to a function call with a client callback: " + str(function_call_pair.function_name))
        
        value = function_call_pair.function_response.response.get("result", "unknown")
        args = function_call_pair.function_call.arguments
        self._xlog.debug("📺 Executing callback with value: " + str(value))
        self.interaction.set_idle_mode_off()
        self.interaction.wait_for_foreground_display_queue_to_empty()
        self.interaction.wait_for_busy_foreground_display_to_idle()

        # Here we call the callback from within the command, passing the context of `main._interaction` and the value
        # Whatever happens, it's done there inside.
        partial(
            self.client_callbacks[function_call_pair.function_name],
            self._xlog,
            self.interaction,
            value,
            args
        )()
    
    def handle_shutdown_request(self):
        self._xlog.debug("💤 Preparing for shutdown...")

        try:
            self.close_nicely_callback(avoid_final_exit=True)

            self._log_debug("Calling system shutdown now...")
            call("sudo nohup shutdown -h now", shell=True)
        except Exception as e:
            self._xlog.error(f"Error during shutdown: {e}")
    
    def handle_reboot_request(self):
        self._xlog.debug("♻️  Preparing for reboot...")

        try:
            self.close_nicely_callback(avoid_final_exit=True)

            self._log_debug("Calling system reboot now...")
            call("sudo nohup reboot", shell=True)
        except Exception as e:
            self._xlog.error(f"Error during reboot: {e}")
    
    def handle_restart_request(self):
        self._xlog.debug("🔄 Preparing for restart...")

        try:
            self.close_nicely_callback(avoid_final_exit=True)

            self._log_debug("Restarting the application now...")
            call("sudo nohup systemctl restart pitxu", shell=True)
        except Exception as e:
            self._xlog.error(f"Error during restart: {e}")
    
    def handle_language_change_request(self, function_call_pair: FunctionCallPair):
        self._xlog.debug("🌐 Preparing to change system language...")

        result = function_call_pair.function_response.response.get("result", False)
        intended_language = function_call_pair.function_call.arguments.get("new_language", "unknown")
        supported_languages = self._xconfig.get("app.supported_languages", [])

        if isinstance(result, bool) and result is False:
            # This means that the language change failed internally. Most likely because we could not understand
            # the requested language or it is not supported.
            result = self._xconfig.get(f"language.language_not_supported.{self._xparams.get('language')}") % intended_language

        elif isinstance(result, str) and result not in supported_languages:
            # This means that the result of the function returned anything but a supported language.
            # Most likely is an error string. Simply let it say it.
            self._xlog.debug("🚨 Showing the ERROR in the eInk")

            self.interaction.set_idle_mode_off()
            self.interaction.wait_for_foreground_display_queue_to_empty()
            self.interaction.wait_for_busy_foreground_display_to_idle()

            self.interaction.show_arbitrary_text_on_foreground_while_speaking(
                icon="🚨",
                text=result,
                font_size=Canvas.FONT_SIZE_BIG)

        else:
            # We have here the new desired language code.
            try:
                # The very first thing is to set the language in the app's state.
                self.state.set("language", result)
                self.state.write_file()
                self._xlog.debug(f"🌐 System language saved into app's state to [{result}].")

                # If we close the app now, the microphone is still muted, and gets conserved.
                self._unmute_microphone_if_needed()

                # Now we close the app and give an exit code that indicates to the launcher that it just needs to restart the app.
                self.close_nicely_callback(avoid_final_exit=True)
                self._xlog.info("🌐 Exiting with code 42 to indicate language change")
                # Feels like does not really exit, as logs show that afterwards it tries to unmute the microphone.
                # Trying now to change from exit(42) to sys.exit(42)
                sys.exit(42)
            except Exception as e:
                self._xlog.error(f"🛑 Failed to change system language to '{result}': {e}")

        # If we reached this point, means that the language change failed for any reason.
        self._unmute_microphone_if_needed()
    
    def handle_end_of_conversation_request(self, function_call_pair: FunctionCallPair):
        self._xlog.debug("🏁 Handling end of conversation request...")

        result = function_call_pair.function_response.response.get("result", False)

        if isinstance(result, bool) and result is True:
            # This means that the end of conversation request was successful.
            self._xlog.info("🏁 End of conversation request handled successfully.")

            try:
                # Just trigger the end of conversation callback if it exists, 
                #   so the app can decide what to do, like going to idle mode, or shutting down, or whatever.
                if self.end_of_conversation_callback is not None:
                    self.end_of_conversation_callback()
                else:
                    self._xlog.debug("⚠️  No end of conversation callback defined, just unmuting the microphone if needed.")
                    self._unmute_microphone_if_needed()
            except Exception as e:
                self._xlog.error(f"🛑 Failed to handle end of conversation request: {e}")

        # If we reached this point, means that the language change failed for any reason.
        self._unmute_microphone_if_needed()
    
    def handle_answer_with_code_block(self, chat_response: ChatbotResponse) -> ChatbotResponse:
        self._xlog.debug(f"⚡️ Reacting to the first of {len(chat_response.code)} code blocks in the response for language [{self._xparams.get('language')}]")

        self.interaction.show_code_block_on_foreground_while_speaking(
            code=chat_response.code[0],
            for_seconds=10.0)

        # Sometimes it answers with code but no text, so we make it more human:
        if chat_response.text.strip() == "":
            chat_response.text = self._xconfig.get("language.code.empty_answer_with_code." + self._xparams.get("language"))
        
        # In any case, we return the possibly modified chat response, so it can be spoken or shown as well.
        return chat_response
    
    def _get_canvas(self) -> Canvas:
        return self.interaction.get_canvas_from_foreground_display()
    
    def _unmute_microphone_if_needed(self):
        # This highly depends on the execution mode: 
        #   - public and local, Mic should be unmuted when starting, otherwise no trigger words will work.
        #   - client, Mic can be muted, as the PTT activates it anyways.
        if self._xconfig.get("app.execution_mode") in ["public", "local"]:
            self.interaction.unmute_microphone(input_stream=self.input_stream)
