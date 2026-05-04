import ruamel.yaml
from ruamel.yaml.util import load_yaml_guess_indent

class Config(object):

    filename = None

    def __init__(self, filename):
        self.filename = filename
        self.load()

    def load(self):
        self.config, self.ind, self.bsi = load_yaml_guess_indent(open(self.filename))

    def get(self, section, key, default):
        try:
            return self.config[section][key]
        except:
            None
        return default

    def set(self, section, key, value):
        self.config[section][key] = value