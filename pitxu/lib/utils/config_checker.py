import os

import yaml


class ConfigChecker:
    """
    Compares every live config file (`config/x.yaml`, personal, not in git) with its reference (`config/x.yaml.dist`).
    It tells which settings the live file lacks (the application then uses the defaults of the code) and which ones
    only the live file has (typos, or settings that were removed). Read-only.
    """

    @classmethod
    def compare(cls, config_dir: str) -> dict[str, dict]:
        """
        Returns, per `.dist` file, a dict with:
          - `live_file_missing`: True if there is no live file at all
          - `missing_in_live`: settings of the `.dist` that the live file does not have
          - `only_in_live`: settings of the live file that the `.dist` does not have
        """
        report = {}
        for name in sorted(os.listdir(config_dir)):
            if not name.endswith(".yaml.dist"):
                continue
            live_path = os.path.join(config_dir, name[:-len(".dist")])
            reference = cls.setting_paths(os.path.join(config_dir, name))
            if not os.path.exists(live_path):
                report[name[:-len(".yaml.dist")]] = {"live_file_missing": True, "missing_in_live": sorted(reference), "only_in_live": []}
                continue
            live = cls.setting_paths(live_path)
            report[name[:-len(".yaml.dist")]] = {
                "live_file_missing": False,
                "missing_in_live": sorted(reference - live),
                "only_in_live": sorted(live - reference),
            }
        return report

    @classmethod
    def setting_paths(cls, path: str) -> set[str]:
        """ The dotted paths of every setting of a YAML file (a list or a text is one setting). """
        with open(path, encoding="utf-8") as handle:
            data = yaml.safe_load(handle) or {}
        return set(cls._leaves(data))

    @classmethod
    def _leaves(cls, data, prefix: str = ""):
        if isinstance(data, dict) and data:
            for key, value in data.items():
                yield from cls._leaves(value, f"{prefix}{key}.")
        elif prefix:
            yield prefix[:-1]
