import json
import os

import numpy as np
from PIL import Image, GifImagePlugin
GifImagePlugin.LOADING_STRATEGY = GifImagePlugin.LoadingStrategy.RGB_AFTER_DIFFERENT_PALETTE_ONLY

from pitxu.lib.objects.size import Size
from pitxu.lib.utils.animation_cache import compute_fingerprint, build_cache_dir_name

class Animation:
    """
    Represents an animation, which is a sequence of frames (images) that can be displayed in order to create the illusion of motion.
    ATM, the frames are loaded from a GIF file, which can contain multiple frames and transparency information.

    Because the intended use is to merge these animation frames to the given canvas, we only support "RGBA" (to output) and
    recognize "P" mode (palette-based) images, which we convert to "RGBA" to get the transparency working correctly.

    Decoding the GIF and resizing every frame is slow, and keeping the full size frames is expensive in memory.
    So the frames already resized to the sizes we need are stored on disk (see animation_cache.py), one array per size,
    and read back memory-mapped. When there is a cache for all the requested sizes, the GIF is not even opened.
    The cache is keyed by the GIF contents, so changing the GIF (or ANIMATION_CACHE_VERSION) regenerates it.

        <cache_root>/<name>-<fingerprint>/meta.json     frame count and original size
        <cache_root>/<name>-<fingerprint>/<w>x<h>.npy   uint8 array, shape (frames, h, w, 4)
    """

    name: str = ""
    file_path: str = None

    OUTPUT_COLOR_MODE: str = "RGBA"
    META_FILENAME: str = "meta.json"

    def __init__(self, name: str, file_path: str, list_of_sizes_to_cache: list[Size] = None, cache_root: str = None):
        self.name = name
        self.file_path = file_path
        self.cache_root = cache_root

        # Full size frames. Only decoded when really needed, see _ensure_full_frames().
        self.frames: list[Image.Image] = []
        # Frames already resized, by size key. Arrays (frames, h, w, 4), memory-mapped when they come from the disk cache.
        self.resized_frames_cache: dict[str, np.ndarray] = {}
        # Sizes we were not asked to prepare, resized on demand and kept in memory only: size key -> {index: image}.
        self._on_demand_frames: dict[str, dict[int, Image.Image]] = {}
        # What happened with every requested size: "hit", "built" or "built (not saved)". Useful for logging.
        self.cache_status: dict[str, str] = {}

        self.list_of_sizes_to_cache = self._unique_sizes(list_of_sizes_to_cache or [])

        self._frame_count: int = 0
        self._original_size: tuple[int, int] = None

        self._load()

    # --------- Loading and disk cache ---------

    def _unique_sizes(self, sizes) -> list[Size]:
        unique: dict[str, Size] = {}
        for size in sizes:
            unique.setdefault(self._build_frame_cache_key_per_size(size), size)
        return list(unique.values())

    def _load(self):
        cache_dir = None
        meta = None
        if self.cache_root:
            cache_dir = os.path.join(self.cache_root, build_cache_dir_name(self.name, compute_fingerprint(self.file_path)))
            meta = self._read_meta(cache_dir)

        missing_sizes: list[Size] = []
        for size in self.list_of_sizes_to_cache:
            key = self._build_frame_cache_key_per_size(size)
            array = self._read_cached_array(cache_dir, key, size, meta) if meta is not None else None
            if array is None:
                missing_sizes.append(size)
            else:
                self.resized_frames_cache[key] = array
                self.cache_status[key] = "hit"

        if meta is not None:
            self._frame_count = meta["frame_count"]
            self._original_size = (meta["width"], meta["height"])

        # Everything came from the cache: no need to open the GIF.
        if meta is not None and len(missing_sizes) == 0:
            return

        # Something is missing: decode the GIF, resize for the missing sizes, and store them.
        frames = self._decode_frames()
        self._frame_count = len(frames)
        self._original_size = frames[0].size

        for size in missing_sizes:
            key = self._build_frame_cache_key_per_size(size)
            array = np.stack([np.asarray(self._resize_frame_to_desired_size(frame, size)) for frame in frames])
            stored = self._write_cached_array(cache_dir, key, array)
            self.cache_status[key] = "built" if stored is not None else "built (not saved)"
            self.resized_frames_cache[key] = stored if stored is not None else array

        if cache_dir is not None:
            self._write_meta(cache_dir)

        # The full size frames are not kept. If someone needs them, they are decoded again.
        self.frames = []

    def _read_meta(self, cache_dir: str) -> dict | None:
        try:
            with open(os.path.join(cache_dir, self.META_FILENAME), "r") as f:
                meta = json.load(f)
            if all(isinstance(meta.get(k), int) for k in ("frame_count", "width", "height")) and meta["frame_count"] > 0:
                return meta
        except (OSError, ValueError):
            pass
        return None

    def _write_meta(self, cache_dir: str):
        try:
            os.makedirs(cache_dir, exist_ok=True)
            self._atomic_write(os.path.join(cache_dir, self.META_FILENAME), lambda f: f.write(json.dumps({
                "frame_count": self._frame_count,
                "width": self._original_size[0],
                "height": self._original_size[1],
            }).encode()))
        except OSError:
            pass

    def _read_cached_array(self, cache_dir: str, key: str, size: Size, meta: dict) -> np.ndarray | None:
        path = os.path.join(cache_dir, f"{key}.npy")
        if not os.path.exists(path):
            return None
        try:
            array = np.load(path, mmap_mode="r")
            if array.dtype == np.uint8 and array.shape == (meta["frame_count"], size.height, size.width, 4):
                return array
        except (OSError, ValueError):
            pass
        # Corrupted or from something else: remove it so it gets regenerated.
        try:
            os.remove(path)
        except OSError:
            pass
        return None

    def _write_cached_array(self, cache_dir: str, key: str, array: np.ndarray) -> np.ndarray | None:
        """
        Stores the array and returns it memory-mapped, so it doesn't stay in RAM. None if it could not be stored.
        """
        if cache_dir is None:
            return None
        try:
            os.makedirs(cache_dir, exist_ok=True)
            path = os.path.join(cache_dir, f"{key}.npy")
            self._atomic_write(path, lambda f: np.save(f, array))
            return np.load(path, mmap_mode="r")
        except (OSError, ValueError):
            return None

    @staticmethod
    def _atomic_write(path: str, writer) -> None:
        """
        Writes to a temporary file and moves it in place, so nobody ever reads a half written file.
        """
        tmp_path = f"{path}.tmp"
        try:
            with open(tmp_path, "wb") as f:
                writer(f)
            os.replace(tmp_path, path)
        finally:
            if os.path.exists(tmp_path):
                os.remove(tmp_path)

    # --------- Decoding ---------

    def _decode_frames(self) -> list[Image.Image]:
        """
        Decodes the GIF into full size frames in the output color mode.
        """
        frames: list[Image.Image] = []
        try:
            with Image.open(self.file_path) as gif:
                while True:

                    # Get the current index's frame as a standlone image.
                    frame = gif.copy()

                    # Convert the frame to the output color mode if needed, to get the transparency working correctly.
                    frames.append(self._convert_frame_to_output_color_mode(frame))

                    # Move the pointer to the next frame. If there are no more frames, it will raise an EOFError,
                    #   which we catch to break the loop.
                    gif.seek(gif.tell() + 1)
        except EOFError:
            pass  # End of sequence
        return frames

    def _ensure_full_frames(self) -> list[Image.Image]:
        if len(self.frames) == 0:
            self.frames = self._decode_frames()
        if len(self.frames) == 0:
            raise ValueError(f"No frames found in animation '{self.file_path}'")
        return self.frames

    def _convert_frame_to_output_color_mode(self, frame: Image.Image) -> Image.Image:
        """
        Converts a given frame to the output color mode (e.g. "RGBA") if it is not already in that mode, and returns the converted frame.
        """
        # If the frame has a palette (i.e. it's in "P" mode), convert it to "RGBA" mode to get the transparency working correctly.
        if frame.mode == "P":
            frame = frame.convert(self.OUTPUT_COLOR_MODE)

        # If the frame has transparency information in its info dict, we need to apply it to the frame to get the transparency working correctly.
        if "transparency" in frame.info:
            transparency_index = frame.info["transparency"]
            # Create a new image with an alpha channel (RGBA) and paste the original frame onto it, using the transparency index as a mask.
            transparent_frame = Image.new(self.OUTPUT_COLOR_MODE, frame.size)
            transparent_frame.paste(frame, (0, 0), mask=frame.point(lambda p: 255 if p == transparency_index else 0))
            frame = transparent_frame

        return frame

    def _resize_frame_to_desired_size(self, frame: Image.Image, desired_size: Size) -> Image.Image:
        """
        Resizes a given frame to the desired size and returns the resized frame, always in the output color mode.
        """
        resized = frame.resize(desired_size.to_image_point(), resample=Image.Resampling.LANCZOS)
        return resized if resized.mode == self.OUTPUT_COLOR_MODE else resized.convert(self.OUTPUT_COLOR_MODE)

    def _build_frame_cache_key_per_size(self, desired_size: Size) -> str:
        """
        Builds a cache key for the resized frames cache based on the desired size.
        """
        return f"{desired_size.width}x{desired_size.height}"

    # --------- Access ---------

    def get_frame(self, index: int, desired_size: Size = None) -> Image.Image:
        """
        Gets the frame at the give index from the loaded animation.
        If a desired size is given, it takes it from the frames prepared for that size.
        A size that was not prepared is resized on demand from the full size frame, and kept in memory only.
        """

        if desired_size is None:
            return self._ensure_full_frames()[index]

        cache_key = self._build_frame_cache_key_per_size(desired_size)
        prepared = self.resized_frames_cache.get(cache_key)
        if prepared is not None:
            return Image.fromarray(np.array(prepared[index]))

        on_demand = self._on_demand_frames.setdefault(cache_key, {})
        if index not in on_demand:
            on_demand[index] = self._resize_frame_to_desired_size(self._ensure_full_frames()[index], desired_size)
        return on_demand[index]

    def get_frame_count(self) -> int:
        return self._frame_count

    def get_original_size(self) -> tuple[int, int]:
        """
        Size (width, height) of the frames in the original GIF.
        """
        return self._original_size
