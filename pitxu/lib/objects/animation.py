from PIL import Image, GifImagePlugin
GifImagePlugin.LOADING_STRATEGY = GifImagePlugin.LoadingStrategy.RGB_AFTER_DIFFERENT_PALETTE_ONLY

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

    def __init__(self, name: str, file_path: str):
        self.name = name
        self.file_path = file_path
        self.frames = []

        try:
            with Image.open(file_path) as gif:
                while True:
                    # Get the current index's frame as a standlone image and append it to the frames list.
                    self.frames.append(gif.copy())
                    # Move the pointer to the next frame. If there are no more frames, it will raise an EOFError, 
                    #   which we catch to break the loop.
                    gif.seek(gif.tell() + 1)
        except EOFError:
            pass  # End of sequence
    
    def get_frame(self, index: int, desired_size: tuple[int, int] = None) -> Image.Image:
        if len(self.frames) == 0:
            raise ValueError(f"No frames found in animation '{self.file_path}'")
        frame = self.frames[index]

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
        
        # Do we need to resize the frame to fit the display area? If so, resize it before returning it.
        if desired_size is not None:
            frame = frame.resize(desired_size, resample=Image.Resampling.LANCZOS)
        
        return frame
    
    def get_frame_count(self) -> int:
        return len(self.frames)