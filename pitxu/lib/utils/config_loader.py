from pyxavi import Config

class ConfigLoader:

    @staticmethod
    def load_config_files() -> Config:
        """
        Loads all configs existing in CONFIG_DIR.

        This is a merge-all-to-one approach, so may be the case that later objects
            overwrite older ones
        """

        import glob
        import os
        from definitions import CONFIG_DIR

        config_files = glob.glob(os.path.join(CONFIG_DIR, "*.yaml"))

        # Yes, technically we're loading main.yaml twice
        config = Config(filename=os.path.join(CONFIG_DIR, "main.yaml"))
        for file in config_files:
            config.merge_from_file(filename=os.path.join(CONFIG_DIR, file))

        return config