from pitxu.lib.abstract.pyxavi import PyXavi
from pitxu.lib.hardware import NetworkReader, PowerReader, SystemReader, ThermalReader
from pitxu.lib.utils.xtime import Xtime
from pitxu.lib.utils.json_logger import JsonLogger
from pitxu.lib.microservice.client import Client

from pyxavi import Config, Dictionary, full_stack

from pitxu.lib.utils.animation_cache import get_cache_root, compute_fingerprint, compute_composite_fingerprint, build_cache_dir_name
from pitxu.lib.objects.composite_animation import normalize_composite_spec

import os
import glob
import shutil

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

    # Gives the pids of the processes to report in the metrics, by name (the Process Pool, once it exists).
    _process_pids_provider: callable = None

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
    DEFAULT_NEW_START_TIMESTAMP_FILE = "new_start_timestamp.yaml"

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

        self._new_start_timestamp_file = os.path.join(
            self._xconfig.get("storage.path", self.DEFAULT_STORAGE_PATH),
            self._xconfig.get("storage.new_start_timestamp_file", self.DEFAULT_NEW_START_TIMESTAMP_FILE))

        self._client = Client(config=config, params=params)

        # Initialize the maintenance logger.
        self._init_maintenance_logger()
    
    def _init_maintenance_logger(self):
        
        self._maintenance_logger = JsonLogger(self._xconfig, self._xparams)
    
    def get_last_gathered_metrics(self) -> Dictionary:
        return self._last_gathered_metrics

    def set_process_pids_provider(self, provider: callable) -> None:
        """
        Sets a callable that returns {process name: pid} for the processes to report in the metrics.
        Called on every metrics log, so it always reflects the processes running at that moment.
        """
        self._process_pids_provider = provider
    
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
            if SystemReader.is_linux():

                local_metrics["cpu"] = {
                    "temperature": ThermalReader.cpu_temperature(),
                    "power_throttle": PowerReader.throttle_report()
                }

                # These are not on every device (no fan, no PMIC): leave them out when they can't be read.
                pmic = PowerReader.pmic_readings() or {}
                optional_cpu_metrics = {
                    "fan_speed": ThermalReader.cpu_fan_rpm(),
                    "volts": pmic.get("VDD_CORE_V"),
                    "amps": pmic.get("VDD_CORE_A"),
                    "input_voltage": pmic.get("EXT5V_V"),
                }
                for key, value in optional_cpu_metrics.items():
                    if value is not None:
                        local_metrics["cpu"][key] = value
                    else:
                        self._log_debug(f"Could not get the CPU {key}. Most likely this device does not have it.")

                local_metrics["memory"] = SystemReader.memory_info()
                local_metrics["pitxu_process_memory"] = SystemReader.process_memory()
                local_metrics["load"] = SystemReader.load_average()
                local_metrics["uptime"] = SystemReader.uptime_seconds()

                # The network that we are connected to, not the strongest one around.
                wifi = NetworkReader.connected_wifi()
                wifi_ssid = wifi.get("ssid", "N/A") if wifi else "N/A"
                local_metrics["network"] = {
                    "wifi_ssid": wifi_ssid
                }
            
            # This data is only available under linux and macos.
            if SystemReader.is_linux() or SystemReader.is_macos():

                local_metrics["disk"] = SystemReader.disk_usage("/")
                
                network = NetworkReader.default_interface()
                ip = network.get("ip", "N/A") if network else "N/A"

                if "network" not in local_metrics:
                    local_metrics["network"] = {}
                local_metrics["network"]["ip"] = ip
            
            # CPU and memory per process, to know which one consumes what.
            if SystemReader.is_linux() or SystemReader.is_macos():
                pids_by_name = {"main": os.getpid()}
                if self._process_pids_provider is not None:
                    pids_by_name.update(self._process_pids_provider())
                local_metrics["processes"] = SystemReader.processes_usage(pids_by_name)
                self._log_debug("📊 Processes (cpu% / rss MB / pss MB): " + ", ".join(
                    f"{name}: {entry.get('cpu_percent')} / {round(entry.get('rss', 0) / SystemReader.MEGABYTES)} / "
                    f"{round(entry.get('pss', entry.get('uss', 0)) / SystemReader.MEGABYTES)}"
                    for name, entry in local_metrics["processes"].items()))

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
            storage_path = self._xconfig.get("storage.path", self.DEFAULT_STORAGE_PATH)
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
    
    def clean_stale_animation_cache(self) -> None:
        '''
        Removes from the animations cache the folders of animations that no longer exist or whose GIF has changed.
        The cache itself is generated by the animations when they are loaded, because only then the sizes are known.
        '''
        try:
            cache_root = get_cache_root(self._xconfig)
            if cache_root is None or not os.path.isdir(cache_root):
                return

            base_path = self._xconfig.get("animations.path", "pitxu/animations")
            expected_folders = set()
            for animation_name, animation_file in (self._xconfig.get("animations.map", {}) or {}).items():
                if animation_file is None:
                    continue
                animation_full_path = os.path.join(base_path, animation_file)
                if os.path.exists(animation_full_path):
                    expected_folders.add(build_cache_dir_name(animation_name, compute_fingerprint(animation_full_path)))

            # The composite animations (two animations merged) have their own folders, named after the composite.
            for composite_name, composite_spec in (self._xconfig.get("animations.composites", {}) or {}).items():
                try:
                    spec = normalize_composite_spec(composite_spec)
                    files = [os.path.join(base_path, (self._xconfig.get("animations.map", {}) or {}).get(part, "") or "") for part in (spec["base"], spec["badge"])]
                    if all(os.path.isfile(file) for file in files):
                        expected_folders.add(build_cache_dir_name(composite_name, compute_composite_fingerprint(files, spec)))
                except ValueError:
                    continue

            removed = 0
            for entry in os.listdir(cache_root):
                entry_path = os.path.join(cache_root, entry)
                if os.path.isdir(entry_path) and entry not in expected_folders:
                    shutil.rmtree(entry_path, ignore_errors=True)
                    removed += 1
            self._xlog.info(f"⚙️  Animations cache checked in: {cache_root}. Stale entries removed: {removed}")

        except Exception as e:
            self._xlog.error(f"⚙️  Error cleaning the animations cache: {e}")

    def write_new_start_timestamp_to_file(self) -> str | None:
        try:
            timestamp = Xtime.current_time_str()
            with open(self._new_start_timestamp_file, "w") as f:
                f.write(timestamp)
            self._xlog.info(f"⚙️  Written new start timestamp [{timestamp}] to file: {self._new_start_timestamp_file}")
            return timestamp
        except Exception as e:
            self._xlog.error(f"⚙️  Error writing new start timestamp to file: {e}")
            return None
    
    def load_current_start_timestamp_from_file(self) -> str | None:
        try:
            if not os.path.exists(self._new_start_timestamp_file):
                self._xlog.warning(f"⚙️  New start timestamp file does not exist: {self._new_start_timestamp_file}")
                return None
            with open(self._new_start_timestamp_file, "r") as f:
                timestamp = f.read().strip()
            self._xlog.debug(f"⚙️  Loaded current start timestamp from file: {timestamp}")
            return timestamp
        except Exception as e:
            self._xlog.error(f"⚙️  Error loading current start timestamp from file: {e}")
            return None

    def _long_term_writer_params(self) -> Dictionary:
        """ Params for a Memory that is allowed to write in the long term memory. Only maintenance tasks use it. """
        return Dictionary({
            "api_key": self._xparams.get("api_key"),
            "base_path": self._xparams.get("base_path"),
            "long_term_writer": True,
        })

    def execute_db_migrations(self):
        '''
        Brings the database to the last version (with a backup first, if there is anything to migrate),
        and sets the language of the memory entries that come from before the languages existed.

        It must run once, in the Main process, before anything else opens the database.
        '''
        if not self._xconfig.get("database.sqlite.auto_migrate", True):
            self._xlog.info("⚙️  Automatic database migration is disabled. Skipping.")
            return

        try:
            from pitxu.lib.database.db_sqlite import DbSqlite
            database = DbSqlite(config=self._xconfig, params=self._xparams)
            try:
                applied = database.migrate_db()
                self._xlog.info(f"⚙️  Database migrations done: {applied} applied.")
            finally:
                database.close()

            from pitxu.lib.utils.memory import Memory
            memory = Memory(config=self._xconfig, params=self._long_term_writer_params())
            try:
                memory.backfill_legacy_language()
            finally:
                memory.close()
        except Exception as e:
            self._xlog.error(f"⚙️  Error migrating the database: {e}")

    def release_in_flight_conversations(self):
        '''
        The closing of the application keeps a copy of the conversation while it is being summarized. If the application
        was killed before it finished, the copy is still there: at startup nothing is summarizing it anymore,
        so it becomes a normal pending conversation for the nightly consolidation.
        '''
        try:
            from pitxu.lib.utils.memory import Memory
            memory = Memory(config=self._xconfig, params=self._xparams)
            try:
                released = memory.release_in_flight_conversations()
            finally:
                memory.close()
            if released:
                self._xlog.info(f"⚙️  {released} conversation(s) of the previous closing will be summarized by the nightly consolidation.")
        except Exception as e:
            self._xlog.error(f"⚙️  Error releasing the in-flight conversations: {e}")

    def execute_memory_preload(self):
        '''
        Executes a preload of the Memory to have it ready and avoid potential delays when it's used for the first time.
        '''
        try:
            from pitxu.lib.utils.memory import Memory
            memory = Memory(config=self._xconfig, params=self._long_term_writer_params())
            memory.preload_memory()
            self._xlog.info("⚙️  Memory preloaded successfully.")
            memory.close()
        except Exception as e:
            self._xlog.error(f"⚙️  Error preloading Memory: {e}")