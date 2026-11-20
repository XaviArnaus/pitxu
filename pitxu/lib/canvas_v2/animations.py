from pyxavi import Config, Dictionary
from pitxu.lib.abstract.pyxavi import PyXavi
from pitxu.lib.objects.animation import Animation
from pitxu.lib.objects.composite_animation import CompositeAnimation, normalize_composite_spec
from pitxu.lib.utils.animation_cache import get_cache_root

from PIL import Image
import os
import threading
import time

from pitxu.lib.objects.size import Size

class Animations(PyXavi):
    """
    https://googlefonts.github.io/noto-emoji-animation/

    Knows which animations exist (animations.map) and loads them either at start (animations.preload)
    or lazily, the first time they are requested. Each loaded Animation reads its frames from the disk cache when it can.

    It also knows the composite animations (animations.composites): two animations of the map merged into one (a main
    one with a smaller one in a corner), that are used by their name like any other. They are loaded at start, which
    generates them (and their disk cache) the first time and when their GIFs or their definition change.
    """

    _animations: dict[str, Animation]
    _animation_files: dict[str, str]
    _composites: dict[str, dict]

    DEFAULT_ANIMATIONS_PATH: str = "pitxu/animations"

    def __init__(self, config: Config, params: Dictionary):
        super(Animations, self).init_pyxavi(config, params)
        self._animations = {}
        self._animation_files = {}
        self._composites = {}
        self._lock = threading.RLock()

    def load_animations(self):
        self._xlog.info("Loading animations...")

        base_path = self._xconfig.get("animations.path", self.DEFAULT_ANIMATIONS_PATH)
        if not os.path.exists(base_path):
            self._xlog.warning(f"Animations path '{base_path}' does not exist. No animations will be loaded.")
            return

        with self._lock:
            self._animations = {}
            self._animation_files = {}
            self._composites = {}
            for animation_name, animation_file in self._xconfig.get("animations.map", {}).items():
                if animation_file is None:
                    self._xlog.warning(f"No file path found for animation '{animation_name}' in configuration. Skipping.")
                    continue

                animation_full_path = os.path.join(base_path, animation_file)
                if not os.path.exists(animation_full_path):
                    self._xlog.warning(f"Animation file '{animation_full_path}' does not exist. Skipping animation '{animation_name}'.")
                    continue

                self._animation_files[animation_name] = animation_full_path

            self._register_composites()

            # Which ones to load now. Without "animations.preload" all of them are loaded, like it always was.
            # With it, only the listed ones, and the rest are loaded the first time they are requested.
            preload = self._xconfig.get("animations.preload", None)
            if preload is None:
                names_to_preload = list(self._animation_files.keys())
            else:
                names_to_preload = []
                for animation_name in preload:
                    if animation_name in self._animation_files:
                        names_to_preload.append(animation_name)
                    else:
                        self._xlog.warning(f"Animation '{animation_name}' in 'animations.preload' is not available. Skipping.")

            for animation_name in names_to_preload:
                self._load_animation(animation_name)

            # The composites are always generated (or read from the cache) at start, so the first use does not wait for it.
            for animation_name in self._composites:
                self._load_animation(animation_name)

            lazy = [name for name in self._animation_files if name not in self._animations and name not in self._composites]
            if lazy:
                self._xlog.info(f"Animations to be loaded on first use: {lazy}")

    def _load_animation(self, animation_name: str) -> Animation:
        with self._lock:
            if animation_name in self._animations:
                return self._animations[animation_name]

            sizes_to_cache = list(self._xparams.get("animation_sizes", []))
            started = time.monotonic()

            if animation_name in self._composites:
                animation = self._build_composite(animation_name, sizes_to_cache)
                self._animations[animation_name] = animation
                self._xlog.info(f"Loaded composite animation '{animation_name}' "
                                f"({self._composites[animation_name]['base']} + {self._composites[animation_name]['badge']}): "
                                f"{animation.get_frame_count()} frames, "
                                f"cache {animation.cache_status if animation.cache_status else 'disabled or no sizes'}, "
                                f"{time.monotonic() - started:.2f}s.")
                return animation

            animation_full_path = self._animation_files[animation_name]

            try:
                animation = Animation(
                    animation_name,
                    animation_full_path,
                    list_of_sizes_to_cache=sizes_to_cache,
                    cache_root=get_cache_root(self._xconfig))
            except Exception as e:
                # The cache is an optimization, it must never prevent an animation from being available.
                self._xlog.error(f"Could not load animation '{animation_name}' using the cache: {e}. Retrying without it.")
                animation = Animation(
                    animation_name,
                    animation_full_path,
                    list_of_sizes_to_cache=sizes_to_cache,
                    cache_root=None)
            self._animations[animation_name] = animation

            self._xlog.info(f"Loaded animation '{animation_name}' from '{animation_full_path}': "
                            f"{animation.get_frame_count()} frames, "
                            f"cache {animation.cache_status if animation.cache_status else 'disabled or no sizes'}, "
                            f"{time.monotonic() - started:.2f}s.")
            return animation

    def _register_composites(self):
        """
        Reads `animations.composites` and keeps the valid ones. A composite needs its two animations to be in the map,
        and a name that is not already used by an animation of the map.
        """
        for composite_name, composite_spec in (self._xconfig.get("animations.composites", {}) or {}).items():
            try:
                spec = normalize_composite_spec(composite_spec)
            except ValueError as e:
                self._xlog.warning(f"Composite animation '{composite_name}' is not valid: {e}. Skipping.")
                continue
            if composite_name in self._animation_files:
                self._xlog.warning(f"Composite animation '{composite_name}' has the name of an animation of the map. Skipping.")
                continue
            missing = [part for part in (spec["base"], spec["badge"]) if part not in self._animation_files]
            if missing:
                self._xlog.warning(f"Composite animation '{composite_name}' needs animations that are not available: {missing}. Skipping.")
                continue
            self._composites[composite_name] = spec

    def _build_composite(self, animation_name: str, sizes_to_cache: list[Size]) -> Animation:
        spec = self._composites[animation_name]
        arguments = dict(
            name=animation_name,
            base_file=self._animation_files[spec["base"]],
            badge_file=self._animation_files[spec["badge"]],
            spec=spec,
            list_of_sizes_to_cache=sizes_to_cache)
        try:
            return CompositeAnimation(cache_root=get_cache_root(self._xconfig), **arguments)
        except Exception as e:
            # The cache is an optimization, it must never prevent an animation from being available.
            self._xlog.error(f"Could not load composite animation '{animation_name}' using the cache: {e}. Retrying without it.")
            return CompositeAnimation(cache_root=None, **arguments)

    def get_animation(self, animation_name: str) -> Animation:
        if animation_name not in self._animations:
            if animation_name not in self._animation_files and animation_name not in self._composites:
                available = list(self._animation_files.keys()) + list(self._composites.keys())
                raise ValueError(f"Animation '{animation_name}' not found. Available animations: {available}")
            self._load_animation(animation_name)
        return self._animations[animation_name]

    def get_animation_frame(self, animation_name: str, frame_index: int, desired_size: Size = None) -> Image.Image:
        return self.get_animation(animation_name).get_frame(frame_index, desired_size)
