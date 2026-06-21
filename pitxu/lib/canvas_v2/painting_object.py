from __future__ import annotations

from pitxu.lib.canvas_v2.painting_command import ForegroundCommand, OverallCommand, PaintingCommand, BackgroundCommand
from pitxu.lib.canvas_v2.painter_queue import PainterQueue

class PaintObject:
    """
    This is the object passed into the Painter so it knows what to paint.
    """

    paint_by_queue: dict[PainterQueue, ForegroundPaint | BackgroundPaint | OverallPaint] = None  # Dictionary that maps the queue name to the paint to be painted in that queue.

    def __init__(self, paints_by_queue: dict[PainterQueue, ForegroundPaint | BackgroundPaint | OverallPaint]):
        self.paint_by_queue = paints_by_queue
    
    def has_paint_for(self, queue: PainterQueue):
        return self.paint_by_queue.get(queue) is not None
    
    def has_any_paint(self):
        return any(self.paint_by_queue.values())
    
    def get_paint_for(self, queue: PainterQueue):
        return self.paint_by_queue.get(queue)
    
    def get_all_paints_by_queue(self) -> list[tuple[PainterQueue, BasePaint]]:
        paint_by_queue_as_tuples = [(queue, paint) for queue, paint in self.paint_by_queue.items() if paint is not None]
        return paint_by_queue_as_tuples
    
    def get_queues(self):
        return self.paint_by_queue.keys()

class PaintingObject:
    """
    This is the object passed into the Painter so it knows what to paint.
    """

    foreground: ForegroundPaint = None
    background: BackgroundPaint = None
    overall: OverallPaint = None

    def __init__(self, foreground: ForegroundPaint = None, background: BackgroundPaint = None, overall: OverallPaint = None):
        self.foreground = foreground
        self.background = background
        self.overall = overall
    
    def has_foreground(self):
        return self.foreground is not None
    
    def has_background(self):
        return self.background is not None
    
    def has_overall(self):
        return self.overall is not None
    
    def has_any(self):
        return self.has_foreground() or self.has_background() or self.has_overall()
    
    def get_foreground(self):
        return self.foreground
    
    def get_background(self):
        return self.background
    
    def get_overall(self):
        return self.overall

class BasePaint:
    
    # Basic attributes
    name: str = None
    command: PaintingCommand = None

    # Painting desired flow control
    delay_between_frames: float = 0.05  # Delay between frames in seconds
    final_area_clearing: bool = False  # Whether to clear the display area at the end of the interaction
    final_screen_clearing: bool = False  # Whether to clear the screen at the end of the interaction
    remove_interaction_after_painting: bool = True  # Whether to remove the interaction after painting
    overwrite_current_interaction_with_same_type: bool = False  # Whether to overwrite the current interaction with the same type

    # Keep the painting for some seconds after the interaction is painted, so that it doesn't disappear immediately.
    maintain_paint_for_seconds: float = None  # Time to maintain the painting after the interaction is painted
    ignore_maintain_time: bool = False  # Whether to ignore the global foreground maintain time setting

    # Macro callback to trigger for drawing the interaction.
    # The idea is that the drawing action is set by the caller, not manually in the painter, making the painter agnostic.
    drawing_callback: callable = None
    # Macro callback parameters to trigger for drawing the interaction.
    # This is a dictionary of parameters that will be passed to the drawing callback.
    drawing_callback_parameters: dict = None
    # Which of the drawing_callback_parameters are going to be used to control the painter cache.
    # It should be a list of parameter names that refer to string or integer values, that will be stringified
    #  and added to the cache key, so that different values of these parameters will lead to different cache entries.
    # If empty, it will take only the interaction name and type as cache key,
    #   so different parameters will not lead to different cache entries.
    cache_control_parameters: list[str] = []

    # Allow to draw it under the activeness (or not) of a Shared Memory Flag.
    # This defines which one (the definition is an integer)
    while_shared_memory_flag: int = None
    # This defines the value of this shared memory flag. Defaults to True.
    while_shared_memory_flag_value: bool = True

    def __init__(self,
                    # Basic attributes
                    name: str,
                    command: PaintingCommand,
                    # Macro callback to trigger for drawing the interaction.
                    drawing_callback: callable = None,
                    # Macro callback parameters to trigger for drawing the interaction.
                    # This is a dictionary of parameters that will be passed to the drawing callback.
                    drawing_callback_parameters: dict = None,
                    # Which of the drawing_callback_parameters are going to be used to control the painter cache.
                    # It should be a list of parameter names that refer to string or integer values, that will be stringified
                    #  and added to the cache key, so that different values of these parameters will lead to different cache entries.
                    cache_control_parameters: list[str] = [],
                    # Painting desired flow control
                    delay_between_frames: float = 0.05,
                    final_area_clearing: bool = False,
                    final_screen_clearing: bool = False,
                    remove_interaction_after_painting: bool = False,
                    overwrite_current_interaction_with_same_type: bool = False,
                    # Keep the painting for some seconds after the interaction is painted, so that it doesn't disappear immediately.
                    maintain_paint_for_seconds: float = None,
                    ignore_maintain_time: bool = False,
                    # Allow to draw it under the activeness (or not) of a Shared Memory Flag.
                    while_shared_memory_flag: int = None,
                    while_shared_memory_flag_value: bool = True,
                    ):
        
        # Basic attributes
        self.name = name
        self.command = command
        # Macro callback to trigger for drawing the interaction.
        self.drawing_callback = drawing_callback
        # Macro callback parameters to trigger for drawing the interaction.
        self.drawing_callback_parameters = drawing_callback_parameters if drawing_callback_parameters is not None else {}
        # Which of the drawing_callback_parameters are going to be used to control the painter cache.
        self.cache_control_parameters = cache_control_parameters if cache_control_parameters is not None else []
        # Painting desired flow control
        self.delay_between_frames = delay_between_frames
        self.final_area_clearing = final_area_clearing
        self.final_screen_clearing = final_screen_clearing
        self.remove_interaction_after_painting = remove_interaction_after_painting
        self.overwrite_current_interaction_with_same_type = overwrite_current_interaction_with_same_type
        # Keep the painting for some seconds after the interaction is painted, so that it doesn't disappear immediately.
        self.maintain_paint_for_seconds = maintain_paint_for_seconds
        self.ignore_maintain_time = ignore_maintain_time
        # Allow to draw it under the activeness (or not) of a Shared Memory Flag.
        self.while_shared_memory_flag = while_shared_memory_flag
        self.while_shared_memory_flag_value = while_shared_memory_flag_value
    
    def depends_on_any_shared_memory_flag(self) -> bool:
        """
        Just a boolean helper to know if this paint depends on a shared memory flag or not.
        """
        return self.while_shared_memory_flag is not None

    def depends_on_specific_shared_memory_flag(self, shared_memory_flag: int) -> bool:
        """
        Just a boolean helper to know if this paint depends on a specific shared memory flag or not.
        """
        return self.while_shared_memory_flag == shared_memory_flag
    
    def get_shared_memory_flag_dependency(self) -> tuple[int, bool] | None:
        """
        Gets the shared memory flag dependency of this paint, if it has any. Otherwise, returns None.
        This means that we get a tuple with the flag index and the value it depends on to be active (True or False).
        """
        if not self.depends_on_any_shared_memory_flag():
            return None
        return self.while_shared_memory_flag, self.while_shared_memory_flag_value
    
    def get_cache_key(self) -> str:
        """
        Builds and returns this Paint's cache key, based on its name, type and the values of the parameters that control the cache.
        """
        key = f"{self.command.get()}_{self.name}"
        for param_name in self.cache_control_parameters:
            param_value = self.drawing_callback_parameters.get(param_name, None)
            key += f"_{param_name}:{param_value}"
        return key

class OverallPaint(BasePaint):

    def __init__(self, name: str, command: OverallCommand, **kwargs):

        super(OverallPaint, self).__init__(name=name, command=command, **kwargs)

class ForegroundPaint(BasePaint):

    def __init__(self, name: str, command: ForegroundCommand, **kwargs):

        super(ForegroundPaint, self).__init__(name=name, command=command, **kwargs)

class BackgroundPaint(BasePaint):

    current_loop_iteration: int = 0  # Current loop iteration for the background interaction, useful for animations
    loop_iterations: int = 1  # Number of loop iterations to paint the background interaction

    def __init__(self, name: str, command: BackgroundCommand, **kwargs):

        if "loop_iterations" in kwargs:
            self.loop_iterations = kwargs["loop_iterations"]
            del kwargs["loop_iterations"]
        if "current_loop_iteration" in kwargs:
            self.current_loop_iteration = kwargs["current_loop_iteration"]
            del kwargs["current_loop_iteration"]
        super(BackgroundPaint, self).__init__(name=name, command=command, **kwargs)

class AnimationPaint(BackgroundPaint):
    """
    This is a special type of paint that is meant to be used for animations. 
    Requires to receive the base image instead of the canvas to draw on.

    The painter is meant to handle it, so it gives the right parameters.
    As a start, it is inheriting from BackgroundPaint as it is meant to paint animated emojis in the background,
        but this could change in the future.
    """

    def __init__(self, name: str, command: BackgroundCommand, **kwargs):

        super(AnimationPaint, self).__init__(name=name, command=command, **kwargs)