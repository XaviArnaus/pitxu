from pitxu.lib.abstract.pyxavi import PyXavi

from pyxavi import Config, Dictionary, dd

class Maintenance(PyXavi):
    '''
    Utility class to perform maintenance tasks.
    '''

    _mocked_files_folders: list[str] = None
    _excluded_filenames: list[str] = None

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
    
    def clean_previous_generated_files(self, 
                                       directories_after_storage: list[str] = [], 
                                       excluded_filenames: list[str] = [],
                                       file_extension: str = "*") -> None:
        '''
        Cleans the previous mocked images from the storage folder.
        '''
        try:
            import os
            import glob

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

