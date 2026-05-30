from pyxavi import Config, Dictionary
from pitxu.lib.abstract.pyxavi import PyXavi

import sounddevice as sd

class AudioParametersLoader(PyXavi):

    DEFAULT_INPUT_DEVICE: int = 0
    DEFAULT_STT_ENGINE: str = "vosk"
    DEFAULT_INPUT_SAMPLERATE: int = 16000
    DEFAULT_RESAMPLE_TARGET_SAMPLERATE: int = 16000
    DEFAULT_PREPROCESSING_SAMPLERATE: int = 16000
    DEFAULT_SERVER_SAMPLERATE: int = 16000
    DEFAULT_MEANINGFUL_AUDIO_RMS_THRESHOLD: float = 0.5

    input_device: int = None
    stt_engine: str = None
    input_samplerate: int = None
    resample_target_samplerate: int = None
    preprocessing_samplerate: int = None
    stt_samplerate: int = None
    server_samplerate: int = None
    filter_lowcut_freq: int = 300
    filter_highcut_freq: int = 3400
    filter_order: int = 3
    meaningful_audio_rms_threshold: float = 0.5

    full_audio_parameters: dict = {}

    def __init__(self, config: Config, params: Dictionary):
        super(AudioParametersLoader, self).init_pyxavi(config=config, params=params)

        self._xlog.info("Loading audio parameters for Speech-to-Text")
        self.load_parameters()
    
    def load_parameters(self):
        self.input_device = self.get_input_device()
        self.stt_engine = self.get_stt_engine()
        self.input_samplerate = self.get_input_samplerate()
        self.stt_samplerate = self.get_stt_samplerate()
        self.preprocessing_samplerate = self.get_preprocessing_samplerate()
        self.server_samplerate = self.get_server_instance_input_samplerate()
        self.resample_target_samplerate = self.get_resample_target_samplerate()
        self.meaningful_audio_rms_threshold = self.get_meaningful_audio_rms_threshold()

        self.filter_lowcut_freq = self.get_filter_lowcut_freq()
        self.filter_highcut_freq = self.get_filter_highcut_freq()
        self.filter_order = self.get_filter_order()
        self.full_audio_parameters = {
            "input_device": self.input_device,
            "stt_engine": self.stt_engine,
            "input_samplerate": self.input_samplerate,
            "resample_target_samplerate": self.resample_target_samplerate,
            "preprocessing_samplerate": self.preprocessing_samplerate,
            "stt_samplerate": self.stt_samplerate,
            "server_samplerate": self.server_samplerate,
            "filter_lowcut_freq": self.filter_lowcut_freq,
            "filter_highcut_freq": self.filter_highcut_freq,
            "filter_order": self.filter_order,
            "meaningful_audio_rms_threshold": self.meaningful_audio_rms_threshold
        }
    
    def get_audio_parameters(self) -> dict:
        return self.full_audio_parameters

    def get_input_device(self) -> int:
        if self._xparams.key_exists("input_device"):
            input_device = self._xparams.get("input_device")
            self._log_debug(f"Using input device from params: {input_device}")
            return input_device
        elif self._xconfig.key_exists("speech-to-text.input_device"):
            input_device = self._xconfig.get("speech-to-text.input_device")
            self._log_debug(f"Using input device from config: {input_device}")
            return input_device
        else:
            self._xlog.warning(f"No input device specified in params or config, using default input device ({self.DEFAULT_INPUT_DEVICE})")
            return self.DEFAULT_INPUT_DEVICE
    
    def get_input_samplerate(self) -> int:
        # 1. See if we have it defined in the Config.
        samplerate = self._xconfig.get("speech-to-text.input_samplerate")
        # If we receive a -1, means that we actively set that we use whatever the device samplerate is.
        # This will trigger the resampler in the Capture Handler to resample from the device samplerate to the target samplerate.
        if samplerate == -1 or samplerate is None:
            samplerate = self.get_samplerate_from_device()
        return samplerate

    def get_samplerate_from_device(self) -> int:
        if self.input_device is not None:
            device_info = sd.query_devices(self.input_device, "input")
            # soundfile expects an int, sounddevice provides a float:
            return int(device_info["default_samplerate"])
        return self.DEFAULT_INPUT_SAMPLERATE  # Default samplerate if no device is specified
    
    def get_server_instance_input_samplerate(self) -> int:
        # This is the samplerate that we will receive in the Server instance, which may be different from the one in the Capture Handler if the client is sending it.
        if self._xconfig.key_exists("server.input_samplerate"):
            samplerate = self._xconfig.get("server.input_samplerate", None)
            self._log_debug(f"Server samplerate set from config: {samplerate}")
            return samplerate
        else:
            self._log_debug(f"No Server samplerate provided, using default of {self.DEFAULT_SERVER_SAMPLERATE} Hz.")
            return self.DEFAULT_SERVER_SAMPLERATE
    
    def get_resample_target_samplerate(self) -> int:
        # This is the samplerate that we will resample to in the Capture Handler, before feeding the audio chunks into the VAD and Preprocessor.
        # It should match the one expected by the VAD and Preprocessor, as well as the one set in the Config for the STT engine.
        if self._xconfig.key_exists("speech-to-text.target_samplerate"):
            target_samplerate = self._xconfig.get("speech-to-text.target_samplerate")
            self._log_debug(f"Using resample target samplerate from config: {target_samplerate}")
            return target_samplerate
        else:
            self._log_debug(f"No target samplerate specified in config, using default of {self.DEFAULT_RESAMPLE_TARGET_SAMPLERATE} Hz")
            return self.DEFAULT_RESAMPLE_TARGET_SAMPLERATE
    
    def get_stt_engine(self) -> str:
        if self._xconfig.key_exists("speech-to-text.engine"):
            stt_engine = self._xconfig.get("speech-to-text.engine")
            self._log_debug(f"Using Speech-to-Text engine from config: {stt_engine}")
            return stt_engine
        else:
            self._log_debug(f"No Speech-to-Text engine specified in config, using default of '{self.DEFAULT_STT_ENGINE}'")
            return self.DEFAULT_STT_ENGINE
    
    def get_stt_samplerate(self) -> int:
        # 1. We may have it forced
        if self._xparams.key_exists("force_stt_samplerate"):
            forced_samplerate = self._xparams.get("force_stt_samplerate")
            self._log_debug(f"Using Speech-to-Text forced samplerate from params: {forced_samplerate}")
            return forced_samplerate
        # 2. Mainly we'll have it defined in the Config
        elif self._xconfig.key_exists(f"speech-to-text.{self.stt_engine}.input_samplerate"):
            stt_samplerate = self._xconfig.get(f"speech-to-text.{self.stt_engine}.input_samplerate")
            self._log_debug(f"Using Speech-to-Text samplerate from '{self.stt_engine}' config: {stt_samplerate}")
            return stt_samplerate
        # 3. Otherwise just take the one from the device.
        else:
            device_samplerate = self.get_samplerate_from_device()
            self._log_debug(f"Using Speech-to-Text samplerate from device {self.input_device}: {device_samplerate}")
            return device_samplerate
    
    def get_preprocessing_samplerate(self) -> int:
        # 1. We may have it forced.
        if self._xparams.key_exists("force_preprocessing_samplerate"):
            samplerate = self._xparams.get("force_preprocessing_samplerate")
            self._log_debug(f"Using preprocessing forced samplerate from params: {samplerate}")
            return samplerate
        # Most likely we have it defined in the Config.
        elif self._xconfig.get("speech-to-text.preprocessor.input_samplerate", None) is not None and \
             self._xconfig.get("speech-to-text.preprocessor.input_samplerate", None) > 0:
            samplerate = self._xconfig.get("speech-to-text.preprocessor.input_samplerate")
            self._log_debug(f"Using preprocessing samplerate from config: {samplerate}")
            return samplerate
        else:
            self._xlog.warning(f"No samplerate provided in params to Preprocess, using default of {self.DEFAULT_PREPROCESSING_SAMPLERATE} Hz")
            return self.DEFAULT_PREPROCESSING_SAMPLERATE
    
    def get_filter_lowcut_freq(self) -> int:
        return self._xconfig.get("speech-to-text.preprocessor.lowcut_freq", self.filter_lowcut_freq)
    
    def get_filter_highcut_freq(self) -> int:
        return self._xconfig.get("speech-to-text.preprocessor.highcut_freq", self.filter_highcut_freq)

    def get_filter_order(self) -> int:
        return self._xconfig.get("speech-to-text.preprocessor.filter_order", self.filter_order)

    def get_meaningful_audio_rms_threshold(self) -> float:
        if self._xconfig.key_exists("speech-to-text.preprocessor.meaningful_audio_rms_threshold"):
            threshold = self._xconfig.get("speech-to-text.preprocessor.meaningful_audio_rms_threshold")
            self._log_debug(f"Using meaningful audio RMS threshold from config: {threshold}")
            return threshold
        else:
            self._xlog.debug(f"No meaningful audio RMS threshold provided in config, using default of {self.DEFAULT_MEANINGFUL_AUDIO_RMS_THRESHOLD}")
            return self.DEFAULT_MEANINGFUL_AUDIO_RMS_THRESHOLD