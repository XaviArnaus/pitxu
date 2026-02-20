import base64
from pyxavi import Config, Dictionary, full_stack, dd

from pitxu.lib.abstract.pyxavi import PyXavi
from pitxu.lib.microservice.microservice_base import MicroserviceBase
from pitxu.lib.microservice.flask_wrapper import FlaskWrapper
from pitxu.lib.speech_to_text.vosk import Vosk, VoskException

from flask import Flask, json, request, current_app
from threading import Thread
import sys, logging, asyncio

class Server(PyXavi, MicroserviceBase):

    server: Flask = Flask(__name__)
    server_thread: FlaskWrapper = None

    # Dependencies to be injected into the server context
    # Actively avoiding here to add typing, to avoid circular imports.
    stt: Vosk = None
    chatbot = None
    chatbot_client_callbacks = None
    output_interaction = None

    VERBOSE_DEBUG: bool = True
    FLASK_LIB_LOG_LEVEL: int = logging.INFO

    def __init__(self, config: Config, params: Dictionary):
        super(Server, self).init_pyxavi(config=config, params=params)

        self._xlog.info("Initializing Server")
        
        if params.key_exists("chatbot"):
            self.chatbot = params.get("chatbot")
        else:
            raise ValueError("Chatbot instance must be provided in params with key 'chatbot'")
        
        if params.key_exists("chatbot_client_callbacks"):
            self.chatbot_client_callbacks = params.get("chatbot_client_callbacks")
        else:
            raise ValueError("Chatbot client callbacks must be provided in params with key 'chatbot_client_callbacks'")
        
        if params.key_exists("output_interaction"):
            self.output_interaction = params.get("output_interaction")
        else:
            raise ValueError("Output interaction must be provided in params with key 'output_interaction'")
        
        # Set the log levels for the Piper libraries based on the configuration
        self.FLASK_LIB_LOG_LEVEL = self._xconfig.get("libs_logger.flask.loglevel", self.FLASK_LIB_LOG_LEVEL)
        self._log_debug("Setting Server log level to: " + str(self.FLASK_LIB_LOG_LEVEL))
        logging.getLogger("flask").setLevel(self.FLASK_LIB_LOG_LEVEL)
        
        self._log_debug("End of Server initialization")
    
    def initialize(self):
        self._xlog.info("Starting Server")

        with self.server.app_context():
            # Add the current context into the server config, so we can access it from the endpoints.
            self.server.config['config'] = self._xconfig
            self.server.config['logger'] = self._xlog
            self.server.config['params'] = self._xparams

            # Add the feature instances into the server config, so we can access them from the endpoints.
            # Vosk needs its own instance, otherwise in "public" execution mode it mixes its michrophone callback
            #   with the server endpoint calls and it produces a segmentation fault.
            self._xlog.debug("Initialising the Speech-to-Text with language [" + self._xparams.get("language") + "]")
            self.server.config['stt'] = Vosk(config=self._xconfig, params=self._xparams)
            self.server.config['chatbot'] = self.chatbot
            self.server.config['chatbot_client_callbacks'] = self.chatbot_client_callbacks
            self.server.config['output_interaction'] = self.output_interaction

        # Start the server
        self.start_server()

        self._log_debug("Server accepts connections now.")
    
    def close(self):
        self._xlog.info("Closing Server")

        self._log_debug("Closing Vosk instance in the server context")
        if 'stt' in self.server.config and self.server.config['stt'] is not None:
            self.server.config['stt'].close()

        self._log_debug("Shutting down Server")
        if self.server_thread.is_alive():
            self._log_debug("Waiting for server thread to finish, with timeout of 0 seconds.")
            self.server_thread.shutdown()
            self.server_thread.join(timeout=0)

        self._xlog.debug("Server shutdown complete")

    def start_server(self):
        self._xlog.info("Starting Server Thread")
        self.server_thread = FlaskWrapper(
            app=self.server,
            host=self._xconfig.get("server.host"),
            port=self._xconfig.get("server.port"),
            # debug=self._xconfig.get("server.debug", False)
        )
        self.server_thread.start()

    # Status endpoint to check if the service is alive and get some info about it.
    @server.route('/status')
    def status():
        # Framework initialization.
        config = current_app.config['config']
        logger = current_app.config['logger']
        params = current_app.config['params']

        logger.info("📥 Received /status request")

        foreground_display_id = config.get("displays.foreground_display", None)
        background_display_id = config.get("displays.background_display", None)
        language = config.get("app.default_language", "?")
        language = params.get("language", language)

        # TODO: we should check first the state AND THEN the config values.
        return {
            "status": "ok",
            "modules_enabled": {
                "foreground_display": config.get(f"{foreground_display_id}.mock", False),
                "background_display": config.get(f"{background_display_id}.mock", False),
                "stt": config.get("speech_to_text.mock", True),
                "tts": config.get("text_to_speech.mock", True),
                "chatbot": not config.get("chatbot.mock", True),
                "ups": config.get("ups.mock", True),
                "gpio": config.get("gpio.mock", True)
            },
            "parameters": {
                "language": language,
                "foreground_display": foreground_display_id,
                "background_display": background_display_id
            },
            "host": {
                "platform": sys.platform,
            }
        }
    
    # Endpoint to receive an audio byte array to make it through the pipeline
    @server.route('/transcribe', methods=['POST'])
    def transcribe():
        # Framework initialization.
        config = current_app.config['config']
        logger = current_app.config['logger']
        params = current_app.config['params']

        # Endpoint initialisation
        bytes_per_chunk = request.json.get("speech-to-text.bytes_per_chunk", 4000)

        audio_data = request.json.get("data_bytes", None)
        if audio_data is not None:
            audio_data = base64.b64decode(audio_data)
        logger.info(f"📥 Received /transcribe request with an audio of length: {len(audio_data) if audio_data is not None else 0}")

        counter = 0
        error = None
        try:
            # Feature initialization.
            stt: Vosk = current_app.config['stt']

            # Process the audio data and get the transcription.
            # This is a loop where we pop chunks of the audio data and send them to the STT engine.
            logger.debug(f"Processing audio data of {len(audio_data)} bytes in frames of {bytes_per_chunk} bytes")
            transcribed = None
            counter = 0
            while len(audio_data) > 0:
                chunk = audio_data[:bytes_per_chunk]
                audio_data = audio_data[bytes_per_chunk:]

                logger.debug(f"Processing chunk of {len(chunk)} bytes, remaining audio data length: {len(audio_data)} bytes")
                transcribed = stt.process_audio_chunk(chunk)

                counter += 1
            
            # It's not normal to not receive anything.
            if transcribed is None:
                logger.warning("🟠 No transcription result returned.")
                return {
                    "status": "ko",
                    "received_bytes_length": len(audio_data),
                    "frames": counter,
                    "error": error,
                    "transcription": None
                }
            
            # Build the transcription to be returned.
            transcription = transcribed["result"]
            if transcribed["final"] is not None and len(transcribed["final"]) > 0:
                if transcription is None:
                    transcription = transcribed["final"]
                else:
                    transcription = transcription + " " + transcribed["final"]

            # We may not have a result, but we may have a partial. Just use it.
            if transcription is None and transcribed["partial"] is not None:
                logger.warning("🟠 No final transcription result returned, but we have a partial result. Returning the partial as the result.")
                transcription = transcribed["partial"]

            # Log me baby
            logger.debug(f"✏️ Transcription result: {transcribed.get('result', None)}")
            logger.debug(f"✏️ Partial transcription: {transcribed.get('partial', None)}")

            # Vosk holds whatever is in the current Result object. We need to clean it at the end of the transcription
            #   to avoid having old transcriptions in the next calls.
            stt.reset_result()

            # Return the final response.
            return {
                "status": "ok", 
                "received_bytes_length": len(audio_data),
                "frames": counter,
                "error": error,
                "transcription": transcription
            }

        except VoskException as ve:
            error = str(ve)
            logger.error(f"🛑 VoskException during STT recognition in the server [transcriber] endpoint: {error}")
            logger.error(full_stack())

        except Exception as e:
            error = str(e)
            logger.error(f"🛑 Error during STT recognition in the server [transcriber] endpoint: {error}")
            logger.error(full_stack())

        return {
            "status": "ko", 
            "received_bytes_length": len(audio_data),
            "error": error,
            "transcription": None
        }
    
    @server.route('/ask_chatbot', methods=['POST'])
    async def ask_chatbot() -> str:
        """
        Method to send a query to the chatbot and get a response.
        """
        from pitxu.lib.chatbot.gemini_chatbot import GeminiChatbot
        from pitxu.lib.objects import ChatbotResponse

        # Framework initialization.
        logger = current_app.config['logger']

        question = request.json.get("question", None)
        logger.info(f"📥 Received /ask_chatbot request with question: {question}")

        error = None
        try:
            # Feature initialization.
            chatbot: GeminiChatbot = current_app.config['chatbot']

            # Set up of all the session context we need for the Chatbot and the MCP tools
            async with chatbot.get_session_manager() as chatbot_session_manager:

                chat_response: ChatbotResponse = await chatbot.ask_async(question)
                answer = chat_response.text
                logger.debug(f"Returning response from chatbot: {answer}")
                return {
                    "status": "ok",
                    "question": question,
                    "answer": answer,
                    "function_call_history": chat_response.function_call_history.to_dict() if chat_response.function_call_history else None,
                    "error": error
                }
        except Exception as e:
            error = str(e)
            logger.error(f"🛑 Error during chatbot response in the server [ask_chatbot] endpoint: {error}")
            logger.error(full_stack())
            return {
                "status": "ko",
                "question": question,
                "answer": None,
                "function_call_history": None,
                "error": error
            }
        
    @server.route('/synthesize', methods=['POST'])
    def synthesize():
        """
        Method to send a text to be synthesized into an audio array of bytes,
        ready to be piped to the sound output
        """
        from pitxu.lib.interaction.interaction import Interaction

        # Framework initialization.
        logger = current_app.config['logger']

        text = request.json.get("text", None)
        logger.info(f"📥 Received /synthesize request with text: {text}")

        error = None
        try:
            # Feature initialization.
            output_interaction: Interaction = current_app.config['output_interaction']

            audio_data = output_interaction.generate_speech_audio_bytes(text)
            return {
                "status": "ok",
                "text": text,
                "audio_bytes_length": len(audio_data.get("audio_bytes", b"")),
                "audio_bytes": base64.b64encode(audio_data.get("audio_bytes", b"")).decode('utf-8'),
                "sample_rate": audio_data.get("sample_rate", None),
                "error": error
            }
        except Exception as e:
            error = str(e)
            logger.error(f"🛑 Error during speech synthesis in the server [synthesize] endpoint: {error}")
            logger.error(full_stack())
            return {
                "status": "ko",
                "text": text,
                "error": error,
                "audio_bytes_length": 0,
                "audio_bytes": None
            }