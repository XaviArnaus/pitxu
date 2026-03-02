from pitxu.lib.abstract.pyxavi import PyXavi
from pitxu.lib.utils.system import System
from pitxu.lib.utils.xtime import Xtime
from pitxu.lib.utils.json_logger import JsonLogger

from pyxavi import Config, Dictionary, dd

import platform
import os
import glob

class Maintenance(PyXavi):
    '''
    Utility class to perform maintenance tasks.
    '''

    _mocked_files_folders: list[str] = None
    _excluded_filenames: list[str] = None

    # Parallel logger
    _maintenance_logger: JsonLogger = None

    # TODO: This has to be pre-loaded by param after collecting all running displays from Main.
    DEFAULT_STORAGE_PATH = "storage/"
    DEFAULT_MOCKED_EINK_PATH = "mocked/eink/"
    DEFAULT_MOCKED_MATRIX_PATH = "mocked/matrix/"
    DEFAULT_MOCKED_LCD_PATH = "mocked/lcd/"
    DEFAULT_MOCKED_DSI_LCD_PATH = "mocked/dsi_lcd/"
    DEFAULT_EXCLUDED_FILENAMES = [".keep"]
    DEFAULT_AUDIO_PATH = "audio/"
    DEFAULT_AUDIO_INPUT_PATH = "input/"
    DEFAULT_AUDIO_OUTPUT_PATH = "output/"

    def __init__(self, config: Config = None, params: Dictionary = None):
        super(Maintenance, self).init_pyxavi(config=config, params=params)

        # Images paths and exclusions definition.
        # TODO: This should be automatic.
        self._mocked_images_folders = [
            self._xconfig.get("storage.mocked_files.eink", self.DEFAULT_MOCKED_EINK_PATH),
            self._xconfig.get("storage.mocked_files.led_matrix", self.DEFAULT_MOCKED_MATRIX_PATH),
            self._xconfig.get("storage.mocked_files.lcd", self.DEFAULT_MOCKED_LCD_PATH),
            self._xconfig.get("storage.mocked_files.dsi_lcd", self.DEFAULT_MOCKED_DSI_LCD_PATH)
        ]
        self._excluded_image_filenames = self._xconfig.get("storage.mocked_files.exclude_from_cleaning", self.DEFAULT_EXCLUDED_FILENAMES)

        # Audio paths and exclusions definition.
        # TODO: This should be automatic.
        self._generated_audios_folders = [
            self._xconfig.get("storage.audio.path", self.DEFAULT_AUDIO_PATH) + self._xconfig.get("storage.audio.input", self.DEFAULT_AUDIO_INPUT_PATH),
            self._xconfig.get("storage.audio.path", self.DEFAULT_AUDIO_PATH) + self._xconfig.get("storage.audio.output", self.DEFAULT_AUDIO_OUTPUT_PATH)
        ]
        self._excluded_audio_filenames = self._xconfig.get("storage.audio.exclude_from_cleaning", self.DEFAULT_EXCLUDED_FILENAMES)

        # Initialize the maintenance logger.
        self._init_maintenance_logger()
    
    def _init_maintenance_logger(self):
        
        self._maintenance_logger = JsonLogger(self._xconfig, self._xparams)
    
    def get_logger(self) -> JsonLogger:
        return self._maintenance_logger
    
    def log_metrics(self, metrics: dict = {}):

        # Initialize the metrics entry.
        local_metrics = {
            "timestamp": Xtime.current_time_str(),
        }

        # CPU data is only available under linux.
        if self._is_linux():
            local_metrics["cpu"] = {
                "temperature": System.get_cpu_temperature(),
                "fan_speed": System.get_cpu_fan_speed(),
                "volts": System.get_cpu_volts(),
                "amps": System.get_cpu_amps(),
                "temp": System.get_cpu_temp(),
                "input_voltage": System.get_input_voltage(),
                "power_throttle": System.get_power_throttle()
            }
        
        # Network data is available under linux and macos.
        wifis = System.get_connected_wifi()
        if wifis and len(wifis) > 0:
            wifi_ssid = wifis[0].get("ssid", "N/A")
        else:
            wifi_ssid = "N/A"
        network = System.get_default_network_interface()
        ip = network.get("ip", "N/A") if network else "N/A"

        local_metrics["network"] = {
            "wifi_ssid": wifi_ssid,
            "ip": ip
        }

        # Now merge and log.
        metrics = {
            **local_metrics,
            **metrics
        }
        self._maintenance_logger.log(metrics)
        self._xlog.debug(f"🗒️ Logged maintenance metrics.")
    
    def rotate_metrics_logs(self):
        self._maintenance_logger.rotate()
    
    def clean_previous_generated_files(self, 
                                       directories_after_storage: list[str] = [], 
                                       excluded_filenames: list[str] = [],
                                       file_extension: str = "*") -> None:
        '''
        Cleans the previous mocked images from the storage folder.
        '''
        try:
            storage_path = self._xparams.get("storage_path", self.DEFAULT_STORAGE_PATH)
            paths_to_cleanup = []

            # Ensure that the mocked paths exist
            for mocked_path in directories_after_storage:
                full_path = os.path.join(storage_path, mocked_path)
                if not os.path.exists(full_path):
                    self._xlog.warning(f"⚙️  Generated files path does not exist: {full_path}")
                    continue
                paths_to_cleanup.append(full_path)
            
            if len(paths_to_cleanup) == 0:
                self._xlog.info("⚙️  No generated files paths to clean.")
                return
            for path in paths_to_cleanup:
                files = glob.glob(os.path.join(path, file_extension))
                for f in files:
                    if os.path.basename(f) in excluded_filenames:
                        self._xlog.debug(f"⚙️  Skipping excluded generated file: {f}")
                        continue
                    os.remove(f)

                self._xlog.info(f"⚙️  Cleaned previous generated files from: {path}")

        except Exception as e:
            self._xlog.error(f"⚙️  Error cleaning previous generated files: {e}")

    def clean_previous_mocked_images(self) -> None:
        '''
        Cleans the previous mocked images from the storage folder.
        '''
        self.clean_previous_generated_files(
            directories_after_storage=self._mocked_images_folders,
            excluded_filenames=self._excluded_image_filenames,
            file_extension="*.png")
    
    def clean_previous_generated_audios(self) -> None:
        '''
        Cleans the previous generated audio files from the storage folder.
        '''
        self.clean_previous_generated_files(
            directories_after_storage=self._generated_audios_folders,
            excluded_filenames=self._excluded_audio_filenames,
            file_extension="*.wav")

    def _is_linux(self) -> bool:
        return platform.system() == "Linux"
    
    def _is_macos(self) -> bool:
        return platform.system() == "Darwin"
    
    def _is_windows(self) -> bool:
        return platform.system() == "Windows"
