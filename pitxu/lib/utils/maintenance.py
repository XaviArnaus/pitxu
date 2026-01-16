from pitxu.lib.abstract.pyxavi import PyXavi

from pyxavi import Config, Dictionary, dd

class Maintenance(PyXavi):
    '''
    Utility class to perform maintenance tasks.
    '''

    _mocked_files_folders: list[str] = None
    _excluded_filenames: list[str] = None

    DEFAULT_STORAGE_PATH = "storage/"
    DEFAULT_MOCKED_EINK_PATH = "mocked/eink/"
    DEFAULT_MOCKED_MATRIX_PATH = "mocked/matrix/"
    DEFAULT_MOCKED_LCD_PATH = "mocked/lcd/"
    DEFAULT_EXCLUDED_FILENAMES = [".keep"]

    def __init__(self, config: Config = None, params: Dictionary = None):
        super(Maintenance, self).init_pyxavi(config=config, params=params)

        self._mocked_files_folders = [
            self._xconfig.get("storage.mocked_files.eink", self.DEFAULT_MOCKED_EINK_PATH),
            self._xconfig.get("storage.mocked_files.led_matrix", self.DEFAULT_MOCKED_MATRIX_PATH),
            self._xconfig.get("storage.mocked_files.lcd", self.DEFAULT_MOCKED_LCD_PATH)
        ]
        self._excluded_filenames = self._xconfig.get("storage.mocked_files.exclude_from_cleaning", self.DEFAULT_EXCLUDED_FILENAMES)

    def clean_previous_mocked_images(self) -> None:
        '''
        Cleans the previous mocked images from the storage folder.
        '''
        try:
            import os
            import glob

            storage_path = self._xparams.get("storage_path", self.DEFAULT_STORAGE_PATH)
            paths_to_cleanup = []

            # Ensure that the mocked paths exist
            for mocked_path in self._mocked_files_folders:
                full_path = os.path.join(storage_path, mocked_path)
                if not os.path.exists(full_path):
                    self._xlog.warning(f"⚙️  Mocked path does not exist: {full_path}")
                    continue
                paths_to_cleanup.append(full_path)
            
            if len(paths_to_cleanup) == 0:
                self._xlog.info("⚙️ No mocked paths to clean.")
                return
            for path in paths_to_cleanup:
                files = glob.glob(os.path.join(path, "*.png"))
                for f in files:
                    if os.path.basename(f) in self._excluded_filenames:
                        self._xlog.debug(f"⚙️  Skipping excluded mocked image: {f}")
                        continue
                    os.remove(f)

                self._xlog.info(f"⚙️  Cleaned previous mocked images from: {path}")

        except Exception as e:
            self._xlog.error(f"⚙️  Error cleaning previous mocked images: {e}")

