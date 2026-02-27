from pyxavi import Config, Dictionary, full_stack, dd

from pitxu.lib.abstract.pyxavi import PyXavi
from pitxu.lib.microservice.microservice_base import MicroserviceBase
from pitxu.lib.microservice.flask_wrapper import FlaskWrapper
from pitxu.lib.speech_to_text.vosk import Vosk, VoskException

from flask import Flask, request, current_app
import base64
import sys, logging

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
        from pitxu.lib.utils.system import System

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

        self._xlog.info(
            f"Server accepts connections now: " +
            f"{self.PROTOCOL}://{System.get_default_network_interface().get('ip')}:{self._xconfig.get('server.port')}")
    
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
        self._log_debug("Starting Server Thread")
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
        from pitxu.lib.command import SystemPowerManagement
        from pitxu.lib.utils.system import System

        # Framework initialization.
        config = current_app.config['config']
        logger = current_app.config['logger']
        params = current_app.config['params']

        logger.info("📥 Received /status request")

        foreground_display_id = config.get("displays.foreground_display", None)
        background_display_id = config.get("displays.background_display", None)
        language = config.get("app.default_language", "?")
        language = params.get("language", language)

        # Feature initialization.
        chatbot = current_app.config['chatbot']
        tools = chatbot.get_session_manager().get_clients() if chatbot is not None else {}
        power_management: SystemPowerManagement = tools.get("power_management", None) if tools is not None else None
       
        if power_management is not None:
            battery_percentage =  power_management.get_battery_level()
            power_cable_connected =  power_management.is_power_cable_connected()
            consumption_watts = power_management.get_power_consumption()
            charging_eta = power_management.get_total_charging_estimation_time()
            cpu_temperature = power_management.get_system_temperature_and_fan_speed()
        else:
            battery_percentage = "N/A"
            power_cable_connected = "N/A"
            consumption_watts = "N/A"
            charging_eta = "N/A"
            cpu_temperature = "N/A"

        # TODO: we should check first the state AND THEN the config values.
        return {
            "status": "ok",
            "app": {
                "version": params.get("app_version", "?"),
                "execution_mode": config.get("app.execution_mode", "?"),
                "chatbot_name": config.get("chatbot.name", "?"),
            },
            "modules_enabled": {
                "foreground_display": not config.get(f"{foreground_display_id}.mock", False),
                "background_display": not config.get(f"{background_display_id}.mock", False),
                "stt": not config.get("speech-to-text.mock", True),
                "tts": not config.get("text-to-speech.mock", True),
                "chatbot": not config.get("chatbot.mock", True),
                "ups": not config.get("ups.mock", True),
                "gpio": not config.get("gpio.mock", True)
            },
            "parameters": {
                "language": language,
                "foreground_display": foreground_display_id,
                "background_display": background_display_id
            },
            "host": {
                "platform": sys.platform,
            },
            "system": {
                "battery_percentage": battery_percentage,
                "power_cable_connected": power_cable_connected,
                "consumption_watts": consumption_watts,
                "charging_eta": charging_eta,
                "cpu_temperature": cpu_temperature["temperature"] if isinstance(cpu_temperature, dict) else "N/A",
                "cpu_fan_speed": cpu_temperature["fan_speed"] if isinstance(cpu_temperature, dict) else "N/A"
            },
            "reports": {
                "power_throttle": System.get_power_throttle() if power_management is not None else "N/A"
            }
        }
    
    # Endpoint to receive an audio byte array to make it through the pipeline
    @server.route('/transcribe', methods=['POST'])
    def transcribe():
        # Framework initialization.
        # config = current_app.config['config']
        logger = current_app.config['logger']
        # params = current_app.config['params']

        # Endpoint initialisation
        bytes_per_chunk = request.json.get("speech-to-text.bytes_per_chunk", 4000)

        audio_data = request.json.get("data_bytes", None)
        audio_data_length = 0
        dd(audio_data)
        if audio_data is not None:
            audio_data = base64.b64decode(audio_data)
            # audio_data = np.frombuffer(audio_data, dtype=np.int16)
            audio_data_length = len(audio_data)
        logger.info(f"📥 Received /transcribe request with an audio of length: {audio_data_length}")

        # It's not normal to not receive anything.
        if len(audio_data) == 0:
            logger.warning("🟠 No audio data received.")
            return {
                "status": "ko",
                "received_bytes_length": audio_data_length,
                "frames": 0,
                "error": "Empty audio data received",
                "transcription": None
            }

        counter = 0
        error = None
        try:
            # Feature initialization.
            stt: Vosk = current_app.config['stt']

            # Process the audio data and get the transcription.
            # This is a loop where we pop chunks of the audio data and send them to the STT engine.
            logger.debug(f"Processing audio data of {audio_data_length} bytes in frames of {bytes_per_chunk} bytes")
            transcribed = []
            transcribed = {
                "result": [],
                "partial": "",
                "final": []
            }
            counter = 0
            while len(audio_data) > 0:
                chunk = audio_data[:bytes_per_chunk]
                audio_data = audio_data[bytes_per_chunk:]

                logger.debug(f"Processing chunk of {len(chunk)} bytes, remaining audio data length: {len(audio_data)} bytes")
                chunk_transcribed = stt.process_audio_chunk(chunk)

                if chunk_transcribed is not None:
                    if chunk_transcribed.get("result", None) is not None:
                        transcribed["result"].append(chunk_transcribed["result"])
                        # We only get a result after several partials, and then the partial accummulator gets cleared.
                        # So take the chance to clear the stored partials until now, to avoid merging them again any time later.
                        transcribed["partial"] = ""
                    if chunk_transcribed.get("partial", None) is not None:
                        # Partials are accummulative. Do not pile them up.
                        transcribed["partial"] = chunk_transcribed["partial"]
                    if chunk_transcribed.get("final", None) is not None:
                        transcribed["final"].append(chunk_transcribed["final"])

                counter += 1
            
            # Process any remaining audio in Vosk
            remaining_transcribed = stt.process_remaining_vosk()
            if remaining_transcribed is not None and "final" in remaining_transcribed and remaining_transcribed["final"] is not None:
                transcribed["final"].append(remaining_transcribed["final"])
            
            dd(transcribed)
            
            # Now merge all the transcribed chunks into a single transcription result.
            transcribed_completed = {
                "result": " ".join(transcribed["result"]) if len(transcribed["result"]) > 0 else None,
                "partial": transcribed["partial"] if len(transcribed["partial"]) > 0 else None,
                "final": " ".join(transcribed["final"]) if len(transcribed["final"]) > 0 else None
            }
            dd(transcribed_completed)

            # It's not normal to not receive anything.
            if transcribed_completed is None:
                logger.warning("🟠 No transcription result returned.")
                return {
                    "status": "ko",
                    "received_bytes_length": audio_data_length,
                    "frames": counter,
                    "error": error,
                    "transcription": None
                }
            
            # Build the transcription to be returned.
            transcription = transcribed_completed["result"].strip() if transcribed_completed.get("result", None) is not None else None
            if transcribed_completed["final"] is not None and len(transcribed_completed["final"]) > 0:
                if transcription is None:
                    transcription = transcribed_completed["final"]
                else:
                    transcription = transcription + " " + transcribed_completed["final"]

            # We may not have a result, but we may have a partial. Just use it.
            if transcription is None and transcribed_completed["partial"] is not None and len(transcribed_completed["partial"]) > 0:
                logger.warning("🟠 No final transcription result returned, but we have a partial result. Returning the partial as the result.")
                transcription = transcribed_completed["partial"]

            # Log me baby
            logger.debug(f"✏️ Transcription: {transcription}")
            logger.debug(f"✏️   Transcribed Result: {transcribed_completed.get('result', None)}")
            logger.debug(f"✏️   Transcribed Partial: {transcribed_completed.get('partial', None)}")
            logger.debug(f"✏️   Transcribed Final: {transcribed_completed.get('final', None)}")

            # Vosk holds whatever is in the current Result object. We need to clean it at the end of the transcription
            #   to avoid having old transcriptions in the next calls.
            stt.reset_result()

            # Return the final response.
            return {
                "status": "ok", 
                "received_bytes_length": audio_data_length,
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
            "received_bytes_length": audio_data_length,
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
        # asyncio_runner: asyncio.Runner = current_app.config["asyncio_runner"]

        question = request.json.get("question", None)
        logger.info(f"📥 Received /ask_chatbot request with question: {question}")

        error = None
        try:
            # Feature initialization.
            chatbot: GeminiChatbot = current_app.config['chatbot']

            chat_response: ChatbotResponse = await chatbot.ask_async(question)
            answer = chat_response.text if chat_response else None

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