from pathlib import Path

from buvis.adapters import AdapterResponse


class ConfigAdapter:

    def __init__(self, file_path=""):
        self.config_dict = {}

        if file_path:
            self.path_config_file = Path(file_path).absolute()

    def set_key_value(self, key, value):
        self.config_dict[key] = value

    def get_key_value(self, key):
        if self.config_dict.get(key, ""):
            return AdapterResponse(message=self.config_dict[key])
        else:
            return AdapterResponse(404, f"{key} not found in config store")


cfg = ConfigAdapter()
