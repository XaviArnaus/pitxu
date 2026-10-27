from PIL import Image, GifImagePlugin
GifImagePlugin.LOADING_STRATEGY = GifImagePlugin.LoadingStrategy.RGB_AFTER_DIFFERENT_PALETTE_ONLY

from pitxu.lib.objects.size import Size
from pyxavi import dd

class Animation:
    """
    Represents an animation, which is a sequence of frames (images) that can be displayed in order to create the illusion of motion.
    ATM, the frames are loaded from a GIF file, which can contain multiple frames and transparency information.

    Because the intended use is to merge these animation frames to the given canvas, we only support "RGBA" (to output) and
    recognize "P" mode (palette-based) images, which we convert to "RGBA" to get the transparency working correctly.
    """

    name: str = ""
    file_path: str = None
    frames: list[Image.Image] = []

    OUTPUT_COLOR_MODE: str = "RGBA"

    def __init__(self, name: str, file_path: str, list_of_sizes_to_cache: list[Size] = None):
        self.name = name
        self.file_path = file_path
        self.frames = []
        self.resized_frames_cache: dict[str, list[Image.Image]] = {}
        self.list_of_sizes_to_cache = list_of_sizes_to_cache or []

        try:
            with Image.open(file_path) as gif:
                while True:

                    # Get the current index's frame as a standlone image.
                    frame = gif.copy()

                    # Convert the frame to the output color mode if needed, to get the transparency working correctly.
                    frame = self._convert_frame_to_output_color_mode(frame)

                    # Bring this frame to the frames list, as a copy, because next step is to resize if needed.
                    self.frames.append(frame.copy())

                    # If this animation has some sizes to cache, we prepare the resized frames for these sizes and save them in the cache.
                    if self.list_of_sizes_to_cache is not None:
                        for size in self.list_of_sizes_to_cache:
                            resized_frame = self._resize_frame_to_desired_size(frame.copy(), size)
                            cache_key = self._build_frame_cache_key_per_size(size)
                            if cache_key not in self.resized_frames_cache:
                                self.resized_frames_cache[cache_key] = []
                            self.resized_frames_cache[cache_key].append(resized_frame)
                            # print(f"Cached resized frame for animation '{self.name}' frame {len(self.frames) - 1} with size {size.width}x{size.height}")

                    # Move the pointer to the next frame. If there are no more frames, it will raise an EOFError, 
                    #   which we catch to break the loop.
                    gif.seek(gif.tell() + 1)
        except EOFError:
            pass  # End of sequence
    
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
        Resizes a given frame to the desired size and returns the resized frame.
        """
        return frame.resize(desired_size.to_image_point(), resample=Image.Resampling.LANCZOS)

    def _build_frame_cache_key_per_size(self, desired_size: Size) -> str:
        """
        Builds a cache key for the resized frames cache based on the desired size.
        """
        return f"{desired_size.width}x{desired_size.height}"
    
    def get_frame(self, index: int, desired_size: Size = None) -> Image.Image:
        """
        Gets the frame at the give index from the loaded animation.
        If a desired size is give, it first checks if the resized frame is in the cache and returns it if it is.
        Otherwise, it resizes the frame to the desired size, saves it in the cache, and then returns it.
        """

        cache_key = self._build_frame_cache_key_per_size(desired_size)
        if desired_size is not None and cache_key in self.resized_frames_cache:
            if index < len(self.resized_frames_cache[cache_key]):
                # print(f"Cache hit for animation '{self.name}' frame {index} with size {desired_size.width}x{desired_size.height}")
                return self.resized_frames_cache[cache_key][index]
        # else:
        #     print(f"Cache miss for animation '{self.name}' frame {index} with size {desired_size.width}x{desired_size.height}")
        #     print(f"Available cache keys for animation '{self.name}': {list(self.resized_frames_cache.keys())}")

        if len(self.frames) == 0:
            raise ValueError(f"No frames found in animation '{self.file_path}'")

        frame = self.frames[index]
        
        # Do we need to resize the frame to fit to the given size? If so, resize it before returning it.
        if desired_size is not None:
            frame = self._resize_frame_to_desired_size(frame, desired_size)
            if cache_key not in self.resized_frames_cache:
                self.resized_frames_cache[cache_key] = []
            # We save the resized frame in the cache for future use, but only if it is not already in the cache, to avoid duplicates.
            if index >= len(self.resized_frames_cache[cache_key]):
                self.resized_frames_cache[cache_key].append(frame)
        return frame
    
    def get_frame_count(self) -> int:
        return len(self.frames)