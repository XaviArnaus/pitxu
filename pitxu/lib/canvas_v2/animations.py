from pyxavi import Config, Dictionary
from pitxu.lib.abstract.pyxavi import PyXavi
from pitxu.lib.objects.animation import Animation

from PIL import Image
import os

from pitxu.lib.objects.size import Size

class Animations(PyXavi):
    """
    https://googlefonts.github.io/noto-emoji-animation/
    """

    _animations: dict[str, Animation]

    DEFAULT_ANIMATIONS_PATH: str = "pitxu/animations"

    def __init__(self, config: Config, params: Dictionary):
        super(Animations, self).init_pyxavi(config, params)
    
    def load_animations(self):
        self._xlog.info("Loading animations...")

        base_path = self._xconfig.get("animations.path", self.DEFAULT_ANIMATIONS_PATH)
        if not os.path.exists(base_path):
            self._xlog.warning(f"Animations path '{base_path}' does not exist. No animations will be loaded.")
            return
        
        sizes_to_cache = self._xparams.get("animation_sizes", [])
        
        self._animations = {}
        for animation_name, animation_file in self._xconfig.get("animations.map", {}).items():
            if animation_file is None:
                self._xlog.warning(f"No file path found for animation '{animation_name}' in configuration. Skipping.")
                continue
            
            animation_full_path = os.path.join(base_path, animation_file)
            if not os.path.exists(animation_full_path):
                self._xlog.warning(f"Animation file '{animation_full_path}' does not exist. Skipping animation '{animation_name}'.")
                continue
            
            self._animations[animation_name] = Animation(animation_name, animation_full_path, list_of_sizes_to_cache=sizes_to_cache)
            self._log_debug(f"Loaded animation '{animation_name}' from file '{animation_full_path}' with {len(self._animations[animation_name].frames)} frames.")
    
    def get_animation(self, animation_name: str) -> Animation:
        if animation_name not in self._animations:
            raise ValueError(f"Animation '{animation_name}' not found. Available animations: {list(self._animations.keys())}")
        return self._animations[animation_name]
    
    def get_animation_frame(self, animation_name: str, frame_index: int, desired_size: Size = None) -> Image.Image:
        return self.get_animation(animation_name).get_frame(frame_index, desired_size)