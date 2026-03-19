from pitxu.lib.abstract.pyxavi import PyXavi
from pitxu.lib.utils.system import System
from pitxu.lib.utils.xtime import Xtime
from pitxu.lib.utils.json_logger import JsonLogger
from pitxu.lib.microservice.client import Client

from pyxavi import Config, Dictionary, full_stack

import platform
import os
import glob

class Maintenance(PyXavi):
    '''
    Utility class to perform maintenance tasks.
    '''

    _mocked_files_folders: list[str] = None
    _generated_audios_folders: list[str] = None
    _generated_audio_signal_plots_folders: list[str] = None
    _excluded_filenames: list[str] = None
    _excluded_audio_filenames: list[str] = None
    _excluded_audio_signal_plot_filenames: list[str] = None

    # Parallel logger
    _maintenance_logger: JsonLogger = None

    # It's stupid to collect all the data and not have it available to be used by the whole application.
    _last_gathered_metrics: Dictionary = None

    # Client support for connecting to Pitxu
    _client: Client = None

    # TODO: This has to be pre-loaded by param after collecting all running displays from Main.
    DEFAULT_STORAGE_PATH = "storage/"
    DEFAULT_MOCKED_EINK_PATH = "mocked/eink/"
    DEFAULT_MOCKED_MATRIX_PATH = "mocked/matrix/"
    DEFAULT_MOCKED_LCD_PATH = "mocked/lcd/"
    DEFAULT_MOCKED_DSI_LCD_PATH = "mocked/dsi_lcd/"
    DEFAULT_EXCLUDED_FILENAMES = [".keep"]
    DEFAULT_AUDIO_PATH = "audio/"
    DEFAULT_AUDIO_PREPROCESSED_INPUT_PATH = "preprocessed_input/"
    DEFAULT_AUDIO_INPUT_PATH = "input/"
    DEFAULT_AUDIO_OUTPUT_PATH = "output/"
    DEFAULT_AUDIO_SIGNAL_PLOTS_PATH = "signals/"
    DEFAULT_AUDIO_SPECTROGRAM_PLOTS_PATH = "spectrograms/"
    DEFAULT_AUDIO_FOURIER_TRANSFORM_PLOTS_PATH = "fourier_transforms/"

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
            self._xconfig.get("storage.audio.path", self.DEFAULT_AUDIO_PATH) + self._xconfig.get("storage.audio.output", self.DEFAULT_AUDIO_OUTPUT_PATH),
            self._xconfig.get("storage.audio.path", self.DEFAULT_AUDIO_PATH) + self._xconfig.get("storage.audio.preprocessed_input", self.DEFAULT_AUDIO_PREPROCESSED_INPUT_PATH)
        ]
        self._excluded_audio_filenames = self._xconfig.get("storage.audio.exclude_from_cleaning", self.DEFAULT_EXCLUDED_FILENAMES)

        # Audio signals paths and exclusions definition.
        # TODO: This should be automatic.
        self._generated_audio_signal_plots_folders = [
            self._xconfig.get("storage.signal_plots.path", self.DEFAULT_AUDIO_PATH + self.DEFAULT_AUDIO_SIGNAL_PLOTS_PATH)
        ]
        self._excluded_audio_signal_plot_filenames = self._xconfig.get("storage.signal_plots.exclude_from_cleaning", self.DEFAULT_EXCLUDED_FILENAMES)

        # Audio spectrogram paths and exclusions definition.
        # TODO: This should be automatic.
        self._generated_audio_spectrogram_plots_folders = [
            self._xconfig.get("storage.spectrogram_plots.path", self.DEFAULT_AUDIO_PATH + self.DEFAULT_AUDIO_SPECTROGRAM_PLOTS_PATH)
        ]
        self._excluded_audio_spectrogram_plot_filenames = self._xconfig.get("storage.spectrogram_plots.exclude_from_cleaning", self.DEFAULT_EXCLUDED_FILENAMES)

        # Audio fourier_transform paths and exclusions definition.
        # TODO: This should be automatic.
        self._generated_audio_fourier_transform_plots_folders = [
            self._xconfig.get("storage.fourier_transform_plots.path", self.DEFAULT_AUDIO_PATH + self.DEFAULT_AUDIO_FOURIER_TRANSFORM_PLOTS_PATH)
        ]
        self._excluded_audio_fourier_transform_plot_filenames = self._xconfig.get("storage.fourier_transform_plots.exclude_from_cleaning", self.DEFAULT_EXCLUDED_FILENAMES)

        self._client = Client(config=config, params=params)

        # Initialize the maintenance logger.
        self._init_maintenance_logger()
    
    def _init_maintenance_logger(self):
        
        self._maintenance_logger = JsonLogger(self._xconfig, self._xparams)
    
    def get_last_gathered_metrics(self) -> Dictionary:
        return self._last_gathered_metrics
    
    def is_pitxu_server_alive(self) -> bool:
        try:
            status = self._client.status()
            if status and status.get("status") == "ok":
                return True
            else:
                return False
        except Exception as e:
            self._xlog.error(f"Error checking Pitxu server status: {e}")
            return False
    
    def log_metrics(self, metrics: dict = {}):

        # Initialize the metrics entry.
        local_metrics = {
            "timestamp": Xtime.current_time_str(),
        }

        try:

            # This data is only available under linux.
            if self._is_linux():

                local_metrics["cpu"] = {
                    "temperature": System.get_cpu_temperature(),
                    "temp": System.get_cpu_temp(),
                    
                    "power_throttle": System.get_power_throttle()
                }
                try:
                    local_metrics["cpu"]["fan_speed"] = System.get_cpu_fan_speed()
                except Exception as e:
                    self._log_debug(f"Could not get the Fan Speed. Most likely this device does not have it.")
                
                try:
                    local_metrics["cpu"]["volts"] = System.get_cpu_volts()
                    local_metrics["cpu"]["amps"] = System.get_cpu_amps()
                    local_metrics["cpu"]["input_voltage"] = System.get_input_voltage()
                except Exception as e:
                    self._log_debug(f"Could not get some CPU metrics. Most likely this device does not have them.")
                
                local_metrics["memory"] = System.get_memory_usage()
                local_metrics["pitxu_process_memory"] = System.get_pitxu_memory_use()
                local_metrics["load"] = System.get_system_load()
                local_metrics["uptime"] = System.get_system_uptime()

                wifis = System.get_connected_wifi()
                if wifis and len(wifis) > 0:
                    wifi_ssid = wifis[0].get("ssid", "N/A")
                else:
                    wifi_ssid = "N/A"
                local_metrics["network"] = {
                    "wifi_ssid": wifi_ssid
                }
            
            # This data is only available under linux and macos.
            if self._is_linux() or self._is_macos():

                local_metrics["disk"] = System.get_disk_usage()
                
                network = System.get_default_network_interface()
                ip = network.get("ip", "N/A") if network else "N/A"

                if "network" not in local_metrics:
                    local_metrics["network"] = {}
                local_metrics["network"]["ip"] = ip
            
            if self._xconfig.get("app.execution_mode", "local") == "client":
                local_metrics["pitxu_server_alive"] = "alive" if self.is_pitxu_server_alive() else "unreachable"
        
        except Exception as e:
            self._xlog.error(f"Error collecting maintenance metrics: {e}")
            self._xlog.debug(full_stack())
            local_metrics["error"] = str(e)

        # Now merge and log.
        metrics = {
            **local_metrics,
            **metrics
        }

        # Create a Dictionary out of it and keep it available for the whole application to use it.
        self._last_gathered_metrics = Dictionary(metrics)

        # Now log it.
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
    
    def clean_previous_generated_audio_signal_plots(self) -> None:
        '''
        Cleans the previous generated audio signal plots from the storage folder.
        '''
        self.clean_previous_generated_files(
            directories_after_storage=self._generated_audio_signal_plots_folders,
            excluded_filenames=self._excluded_audio_signal_plot_filenames,
            file_extension="*.png")
    
    def clean_previous_generated_audio_spectrogram_plots(self) -> None:
        '''
        Cleans the previous generated audio spectrogram plots from the storage folder.
        '''
        self.clean_previous_generated_files(
            directories_after_storage=self._generated_audio_spectrogram_plots_folders,
            excluded_filenames=self._excluded_audio_spectrogram_plot_filenames,
            file_extension="*.png")
    
    def clean_previous_generated_audio_fourier_transform_plots(self) -> None:
        '''
        Cleans the previous generated audio fourier transform plots from the storage folder.
        '''
        self.clean_previous_generated_files(
            directories_after_storage=self._generated_audio_fourier_transform_plots_folders,
            excluded_filenames=self._excluded_audio_fourier_transform_plot_filenames,
            file_extension="*.png")

    def _is_linux(self) -> bool:
        return platform.system() == "Linux"
    
    def _is_macos(self) -> bool:
        return platform.system() == "Darwin"
    
    def _is_windows(self) -> bool:
        return platform.system() == "Windows"
