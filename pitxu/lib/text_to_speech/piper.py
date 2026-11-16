import logging, time
import numpy as np
import sounddevice
from piper.voice import PiperVoice

from pyxavi import Config

from pitxu.lib.abstract.xprocess import Xprocess
from pitxu.lib.objects import XprocAction
from pitxu.lib.text_to_speech.speaker_level_meter import SpeakerLevelMeter
from definitions import ROOT_DIR, SHARED_SPEAKER_LEVEL, SHARED_FIRST_AUDIO_TIMESTAMP, SHARED_SPEECH_INTERRUPT_REQUESTED

class Piper(Xprocess):

    MODELS_PATH = "tts_models/"

    _model = None
    _voice: PiperVoice = None
    _output_stream: sounddevice.OutputStream = None
    _level_meter: SpeakerLevelMeter = None

    PIPER_LIB_LOG_LEVEL: int = logging.INFO

    def get_process_name(self) -> str:
        return "Piper"

    def initialize(self):
        self._xlog.info("Initializing Piper Worker")
        language = self._xparams.get("language")
        gender = self._xconfig.get("chatbot.gender", "female")
        self._log_debug("Language is: " + str(language) + ", Gender is: " + str(gender))
        model_name = self._xconfig.get("text-to-speech.per_language." + language + "." + gender)
        self._model = ROOT_DIR + "/" + str(self._xconfig.get("storage.path")) + str(self.MODELS_PATH) + str(model_name) + ".onnx"
        self._xlog.info("Loading TTS model from: " + self._model)
        self._voice = PiperVoice.load(self._model)

        # Set the log levels for the Piper libraries based on the configuration
        self.PIPER_LIB_LOG_LEVEL = self._xconfig.get("libs_logger.piper.loglevel", self.PIPER_LIB_LOG_LEVEL)
        self._log_debug("Setting Piper client log level to: " + str(self.PIPER_LIB_LOG_LEVEL))
        logging.getLogger("piper.voice").setLevel(self.PIPER_LIB_LOG_LEVEL)

        self._log_debug("Creating Piper Output Stream with samplerate: " + str(self._voice.config.sample_rate))
        self._output_stream = sounddevice.OutputStream(
            samplerate=self._voice.config.sample_rate,
            blocksize=0,
            channels=1,
            dtype='int16'
        )
        # Optional VU meter: publishes the level of the audio being played to drive the speaking animation.
        # Only with real audio: the mocked TTS has nothing to measure.
        # The shared values are needed for the first audio timestamp (latency log) and the VU meter.
        self._shared_memory.initialize_existing_shared_memory_values()

        if self._xconfig.get("text-to-speech.speaking_animation", "loop") == "vu" \
                and not self._xconfig.get("text-to-speech.mock", True):
            vu_config = "text-to-speech.vu."
            self._level_meter = SpeakerLevelMeter(
                publish=lambda level: self._shared_memory.write_shared_memory_value(SHARED_SPEAKER_LEVEL, level),
                slice_seconds=self._xconfig.get(vu_config + "slice_seconds", 0.03),
                floor_db=self._xconfig.get(vu_config + "floor_db", -45.0),
                ceil_db=self._xconfig.get(vu_config + "ceil_db", -8.0),
                attack=self._xconfig.get(vu_config + "attack", 0.7),
                release=self._xconfig.get(vu_config + "release", 0.4),
                latency_offset=float(self._output_stream.latency) + self._xconfig.get(vu_config + "latency_offset", 0.0),
                log=self._xlog.info if self._xconfig.get(vu_config + "log_levels", True) else None
            )
            self._xlog.info("Speaker level meter enabled for the speaking animation")

        self.log_summary("Piper Worker", [
            ("Language", language),
            ("Gender", gender),
            ("Model", model_name),
            ("Sample Rate", self._voice.config.sample_rate)
        ])

    def finish(self):
        if self._level_meter is not None:
            self._level_meter.close()
        self._xlog.debug("Closing output stream")
        if self._output_stream is not None:
            self._output_stream.close()
        self._xlog.debug("Done finishing Piper Worker")
    
    def run_with_context(self, config: Config, logger: logging, action: XprocAction, param: any):
        
        if action == XprocAction.SAY and param != "":
            self.say(param)
        
        if action == XprocAction.SAY_OUTPUT_QUEUE and param != "":
            self.synthesize_and_return_through_output_queue(param)

    def say(self, text: str):

        # While talking we set the speaker busy flag and mute the microphone, keeping track of its previous state
        # So that we can restore it to what it was before
        # REMOVEME: This is now handled in the parent Xprocess
        # self.write_shared_memory_flag(SHARED_SPEAKER_BUSY, True)

        # An old request (a press that came too late for the previous speech) must never cut this one.
        self.write_shared_memory_flag(SHARED_SPEECH_INTERRUPT_REQUESTED, False)

        if self._xconfig.get("text-to-speech.mock", True):
            self._xlog.warning("Mocking TTS by Config. Should have said [" + text + "]")
            # Emulate that we're doing something by waiting a second per 10 words
            words = text.split(" ")
            wait_time = max(1, len(words) / 10)
            self._xlog.debug(f"Mocking TTS wait time for {wait_time} seconds")
            # In slices, so that it can be interrupted like the real one.
            waited = 0.0
            while waited < wait_time:
                if self._is_speech_interrupt_requested():
                    self._xlog.info("🤐 Speech interrupted (mocked).")
                    break
                time.sleep(min(0.1, wait_time - waited))
                waited += 0.1

        else:
            self._xlog.debug("Saying [" + text.replace("\n", "\\n") + "]")

            self._output_stream.start()
            # with self._output_stream:
            self._log_debug("Output stream started")
            first_chunk = True
            interrupted = False
            sample_rate = self._voice.config.sample_rate
            # 0 writes the whole sentence at once, so the interruption waits for the end of the sentence.
            slice_size = int(sample_rate * float(self._xconfig.get("text-to-speech.interrupt_slice_seconds", 0.1)))

            # According to the docs, PiperVoice.synthesize returns an iterator of AudioChunks
            # which represent sentences.
            for int_data in self.generate_audio_chunks(text):
                # The synthesis of this sentence may have taken a while.
                if self._is_speech_interrupt_requested():
                    interrupted = True
                    break

                # Schedule the level of this chunk for the speaking animation (non blocking)
                if self._level_meter is not None:
                    self._level_meter.feed(int_data, sample_rate)

                # The very first write of this speech is when the user starts to hear it (give or take the stream latency).
                # Published for the latency log in Main. It must never get in the way of the speech.
                if first_chunk:
                    first_chunk = False
                    try:
                        self._shared_memory.write_shared_memory_value(SHARED_FIRST_AUDIO_TIMESTAMP, time.time())
                    except Exception as e:
                        self._log_debug(f"Could not publish the first audio timestamp: {e}")

                # Make it to speak. The same samples, in order, in slices: the blocking write keeps pacing
                # the playback like before, but we get the chance to look at the interruption between slices.
                self._log_debug("Writing audio bytes to output stream")
                step = slice_size if slice_size > 0 else len(int_data)
                for start in range(0, len(int_data), step):
                    if self._is_speech_interrupt_requested():
                        interrupted = True
                        break
                    self._output_stream.write(int_data[start:start + step])
                if interrupted:
                    break

            if interrupted:
                self._xlog.info("🤐 Speech interrupted by the user.")
                # abort() drops what is already in the sound card buffer, stop() would play it out.
                self._output_stream.abort()
                # The microphone stays closed (the speaker is still busy) for a moment: the button press, the hand
                # and the sound that is still in the air must not be heard as if the user had started to speak.
                time.sleep(float(self._xconfig.get("text-to-speech.interrupt_settle_seconds", 0.4)))
            else:
                self._log_debug("All audio chunks processed, stopping output stream")
                # Comment the following and tab properly for the with statement if used
                self._output_stream.stop()

            # The stream has drained (or was cut): bars back to zero, and the schedule of the levels not played is dropped.
            if self._level_meter is not None:
                self._level_meter.stop()

        # Done, interrupted or not: the request is consumed.
        self.write_shared_memory_flag(SHARED_SPEECH_INTERRUPT_REQUESTED, False)
        self._log_debug("Finished saying communication")

    def _is_speech_interrupt_requested(self) -> bool:
        try:
            return bool(self.read_shared_memory_flag(SHARED_SPEECH_INTERRUPT_REQUESTED))
        except Exception as e:
            self._log_debug(f"Could not read the speech interrupt flag: {e}")
            return False
    
    def synthesize_and_return_through_output_queue(self, text: str):
        if self._output_queue is not None:
            self._log_debug("Generating audio bytes for text and sending through output queue")
            # Generate the audio bytes for the given text and send them through the output queue
            for audio_bytes in self.generate_audio_chunks(text):
                self._output_queue.put({
                    "audio_bytes": audio_bytes,
                    "sample_rate": self._voice.config.sample_rate
                })
            # We need to tell the consumer that we're done sending audio bytes,
            # so we send a None value (which is not a valid audio chunk)
            self._output_queue.put(self._sentinel_output_queue)
        else:
            self._log_debug("No output queue defined, cannot send audio bytes")
    
    def generate_audio_chunks(self, text: str):
        # This is a generator that yields audio chunks for the given text, to be used in streaming scenarios
        for chunk in self._voice.synthesize(text):
            int_data = np.frombuffer(chunk.audio_int16_bytes, dtype=np.int16)
            yield int_data
    
    # REMOVEME: This is now handled in the parent Xprocess
    # def pause_mic(self):
    #     self.write_shared_memory_flag(SHARED_MICROPHONE_MUTED, True)
    # REMOVEME: This is now handled in the parent Xprocess
    # def resume_mic(self):
    #     self.write_shared_memory_flag(SHARED_MICROPHONE_MUTED, False)
