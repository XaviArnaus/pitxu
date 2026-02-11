from pyxavi import Config, Dictionary, full_stack

from pitxu.lib.abstract.pyxavi import PyXavi

from flask import Flask, request, current_app
from threading import Thread
import sys

class Server(PyXavi):

    server: Flask = Flask(__name__)
    server_thread: Thread = None

    def __init__(self, config: Config, params: Dictionary):
        super(Server, self).init_pyxavi(config=config, params=params)

        self._xlog.info("Initializing Server")

        if params.key_exists("stt"):
            self.stt = params.get("stt")
        else:
            raise ValueError("STT instance must be provided in params with key 'stt'")
        
        if params.key_exists("chatbot"):
            self.chatbot = params.get("chatbot")
        else:
            raise ValueError("Chatbot instance must be provided in params with key 'chatbot'")
        
        if params.key_exists("chatbot_client_callbacks"):
            self.chatbot_client_callbacks = params.get("chatbot_client_callbacks")
        else:
            raise ValueError("Chatbot client callbacks must be provided in params with key 'chatbot_client_callbacks'")
        
        self._log_debug("End of Server initialization")
    
    def initialize(self):
        self._xlog.info("Starting Server")

        # Add the current context into the server config, so we can access it from the endpoints.
        self.server.config['config'] = self._xconfig
        self.server.config['logger'] = self._xlog
        self.server.config['params'] = self._xparams

        # Add the feature instances into the server config, so we can access them from the endpoints.
        self.server.config['stt'] = self.stt
        self.server.config['chatbot'] = self.chatbot
        self.server.config['chatbot_client_callbacks'] = self.chatbot_client_callbacks

        # Start the server
        self.start_server()

        self._log_debug("Server accepts connections now.")
    
    def start_server(self):
        self._xlog.info("Starting Server Thread")
        # Start the server in a separate thread to avoid blocking the main loop
        self.server_thread = Thread(
            target=self.server.run, 
            kwargs={
                "host": self._xconfig.get("server.host", "127.0.0.1"),
                "port": self._xconfig.get("server.port", 5000),
                "debug": self._xconfig.get("server.debug", False),
                "use_reloader": False
            })
        self.server_thread.start()

    # Status endpoint to check if the service is alive and get some info about it.
    @server.route('/status')
    def status():
        # Framework initialization.
        config = current_app.config['config']
        logger = current_app.config['logger']
        params = current_app.config['params']

        logger.debug("Received /status request")

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
        from pitxu.lib.speech_to_text.vosk import Vosk, VoskException

        # Framework initialization.
        logger = current_app.config['logger']

        audio_data = request.data
        logger.debug(f"Received /transcribe request with content type: {request.content_type} and content length: {request.content_length}")

        error = None
        try:
            # Feature initialization.
            stt: Vosk = current_app.config['stt']
            # Should be already initialised.
            # stt.initialize()

            # Process the audio data and get the transcription.
            transcribed = stt.process_audio_data(audio_data)
            return {
                "status": "ok", 
                "message": f"Received audio data of length {len(audio_data)} bytes",
                "error": error,
                "transcription": transcribed
            }

        except VoskException as ve:
            logger.error("🛑 VoskException during STT recognition in the server [transcriber] endpoint: " + str(ve))
            logger.error(full_stack())
            error = str(ve)

        except Exception as e:
            logger.error("🛑 Error during STT recognition in the server [transcriber] endpoint: " + str(e))
            logger.error(full_stack())
            error = str(e)

        return {
            "status": "ko", 
            "message": f"Received audio data of length {len(audio_data)} bytes",
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
        logger.debug(f"Received /ask_chatbot request with question: {question}")

        try:
            # Feature initialization.
            chatbot: GeminiChatbot = current_app.config['chatbot']

            # Set up of all the session context we need for the Chatbot and the MCP tools
            async with chatbot.get_session_manager() as chatbot_session_manager:

                chat_response: ChatbotResponse = await chatbot.ask_async(question)
                answer = chat_response.text
                logger.debug(f"Returning response from chatbot: {answer}")
                return answer
        except Exception as e:
            logger.error("🛑 Error during chatbot response in the server [ask_chatbot] endpoint: " + str(e))
            logger.error(full_stack())
            return "Sorry, an error occurred while processing your request."