from pitxu.lib.canvas.painter_commands import BackgroundComm, ForegroundComm

class Paint:
    
    # Basic attributes
    name: str = None
    interaction: BackgroundComm | ForegroundComm = None
    parameter: any = None

    # Painting desired flow control
    delay_between_frames: float = 0.05  # Delay between frames in seconds
    final_screen_clearing: bool = False  # Whether to clear the screen at the end of the interaction
    remove_interaction_after_painting: bool = True  # Whether to remove the interaction after painting
    overwrite_current_interaction_with_same_type: bool = False  # Whether to overwrite the current interaction with the same type

    # Mirrors the activerness of a paint, between 2 events of Busy Flag callbacks
    is_expecting_end_callback: bool = False

    # Optional START/END callbacks
    start_callback: callable = None
    end_callback: callable = None

    def __init__(self, 
                 name: str,
                 interaction: BackgroundComm | ForegroundComm,
                 parameter: any = None,
                 delay_between_frames: float = 0.05,
                 final_screen_clearing: bool = False,
                 remove_interaction_after_painting: bool = True,
                 overwrite_current_interaction_with_same_type: bool = False,
                 start_callback: callable = None,
                 end_callback: callable = None):
        self.name = name
        self.interaction = interaction
        self.parameter = parameter
        self.delay_between_frames = delay_between_frames
        self.final_screen_clearing = final_screen_clearing
        self.remove_interaction_after_painting = remove_interaction_after_painting
        self.overwrite_current_interaction_with_same_type = overwrite_current_interaction_with_same_type
        # They are not used yet.
        self.start_callback = start_callback
        self.end_callback = end_callback


class ForegroundPaint(Paint):
    
    maintain_paint_for_seconds: float = 3.0  # Time to maintain the painting after the interaction is painted
    ignore_maintain_time: bool = False  # Whether to ignore the global foreground maintain time setting

    def __init__(self, 
                 name: str,
                 interaction: ForegroundComm,
                 parameter: any = None,
                 delay_between_frames: float = 0.05,
                 final_screen_clearing: bool = False,
                 remove_interaction_after_painting: bool = True,
                 overwrite_current_interaction_with_same_type: bool = False,
                 maintain_paint_for_seconds: float = 3.0,
                 ignore_maintain_time: bool = False,
                 start_callback: callable = None,
                 end_callback: callable = None):
        super(ForegroundPaint, self).__init__(
            name=name,
            interaction=interaction,
            parameter=parameter,
            delay_between_frames=delay_between_frames,
            final_screen_clearing=final_screen_clearing,
            remove_interaction_after_painting=remove_interaction_after_painting,
            overwrite_current_interaction_with_same_type=overwrite_current_interaction_with_same_type,
            start_callback=start_callback,
            end_callback=end_callback
        )
        self.maintain_paint_for_seconds = maintain_paint_for_seconds
        self.ignore_maintain_time = ignore_maintain_time


class BackgroundPaint(Paint):
    
    loop_iterations: int = 1  # Number of loop iterations to paint the background interaction

    def __init__(self, 
                 name: str,
                 interaction: BackgroundComm,
                 parameter: any = None,
                 delay_between_frames: float = 0.05,
                 final_screen_clearing: bool = False,
                 remove_interaction_after_painting: bool = True,
                 overwrite_current_interaction_with_same_type: bool = False,
                 loop_iterations: int = 1,
                 start_callback: callable = None,
                 end_callback: callable = None):
        super(BackgroundPaint, self).__init__(
            name=name,
            interaction=interaction,
            parameter=parameter,
            delay_between_frames=delay_between_frames,
            final_screen_clearing=final_screen_clearing,
            remove_interaction_after_painting=remove_interaction_after_painting,
            overwrite_current_interaction_with_same_type=overwrite_current_interaction_with_same_type,
            start_callback=start_callback,
            end_callback=end_callback
        )
        self.loop_iterations = loop_iterations

class SpeakingBackgroundPaint(BackgroundPaint):

    def __init__(self, name = None, delay_between_frames: float = 0.05):
        if name is None:
            name = "SpeakingBackgroundPaint"
        super(SpeakingBackgroundPaint, self).__init__(
            name=name,
            interaction=BackgroundComm.SPEAKING,
            delay_between_frames=delay_between_frames,
            final_screen_clearing=True,
            remove_interaction_after_painting=False,
            loop_iterations=8
        )

class ThinkingBackgroundPaint(BackgroundPaint):

    def __init__(self, name = None, delay_between_frames: float = 0.05):
        if name is None:
            name = "ThinkingBackgroundPaint"
        super(ThinkingBackgroundPaint, self).__init__(
            name=name,
            interaction=BackgroundComm.THINKING,
            delay_between_frames=delay_between_frames,
            final_screen_clearing=True,
            remove_interaction_after_painting=False,
            loop_iterations=16
        )

class NetworkingBackgroundPaint(BackgroundPaint):

    def __init__(self, name = None, delay_between_frames: float = 0.05):
        if name is None:
            name = "NetworkingBackgroundPaint"
        super(NetworkingBackgroundPaint, self).__init__(
            name=name,
            interaction=BackgroundComm.NETWORKING,
            delay_between_frames=delay_between_frames,
            final_screen_clearing=True,
            remove_interaction_after_painting=False,
            loop_iterations=16
        )

class InitPhaseBackgroundPaint(BackgroundPaint):

    def __init__(self, name = None, parameter: any = None):
        if name is None:
            name = "InitPhaseBackgroundPaint"
        super(InitPhaseBackgroundPaint, self).__init__(
            name=name,
            interaction=BackgroundComm.INITIAL_PHASE,
            parameter=parameter,
            final_screen_clearing=False,
            remove_interaction_after_painting=False
        )

class HoldingPercentageBackgroundPaint(BackgroundPaint):

    def __init__(self, name = None, parameter: any = None):
        if name is None:
            name = "HoldingPercentageBackgroundPaint"
        super(HoldingPercentageBackgroundPaint, self).__init__(
            name=name,
            interaction=BackgroundComm.HOLDER_PERCENTAGE,
            parameter=parameter,
            final_screen_clearing=False,
            remove_interaction_after_painting=True
        )

class ArbitraryContentForegroundPaint(ForegroundPaint):

    def __init__(self, name = None, parameter: any = None, for_seconds: float = 3.0):
        if name is None:
            name = "ArbitraryContentForegroundPaint"
        super(ArbitraryContentForegroundPaint, self).__init__(
            name=name,
            interaction=ForegroundComm.ARBITRARY_TEXT_ICON,
            parameter=parameter,
            # Be careful with this, this places a black screen over whatever is already painted in the canvas.
            # (so, it removes the background when painting combined)
            final_screen_clearing=True,
            remove_interaction_after_painting=True,
            maintain_paint_for_seconds=for_seconds,
            ignore_maintain_time=False
        )

class ArbitraryIconForegroundPaint(ForegroundPaint):

    def __init__(self, name = None, parameter: any = None):
        if name is None:
            name = "ArbitraryIconForegroundPaint"
        super(ArbitraryIconForegroundPaint, self).__init__(
            name=name,
            interaction=ForegroundComm.ARBITRARY_ICON,
            parameter=parameter,
            # Be careful with this, this places a black screen over whatever is already painted in the canvas.
            # (so, it removes the background when painting combined)
            final_screen_clearing=True,
            remove_interaction_after_painting=True,
            ignore_maintain_time=True
        )

class ArbitraryContentWhileSpeakingForegroundPaint(ForegroundPaint):

    def __init__(self, name = None, parameter: any = None):
        if name is None:
            name = "ArbitraryContentWhileSpeakingForegroundPaint"
        super(ArbitraryContentWhileSpeakingForegroundPaint, self).__init__(
            name=name,
            interaction=ForegroundComm.ARBITRARY_TEXT_ICON,
            parameter=parameter,
            # Be careful with this, ensure that avoids painting and not places a black screen 
            # (that removes the background when painting combined)
            final_screen_clearing=True,
            remove_interaction_after_painting=True,
            ignore_maintain_time=True
        )

class ArbitraryContentWhileUserSpeakingForegroundPaint(ForegroundPaint):

    def __init__(self, name = None, parameter: any = None):
        if name is None:
            name = "ArbitraryContentWhileUserSpeakingForegroundPaint"
        super(ArbitraryContentWhileUserSpeakingForegroundPaint, self).__init__(
            name=name,
            interaction=ForegroundComm.ARBITRARY_TEXT_ICON,
            parameter=parameter,
            # Be careful with this, ensure that avoids painting and not places a black screen 
            # (that removes the background when painting combined)
            final_screen_clearing=True,
            remove_interaction_after_painting=True,
            ignore_maintain_time=True
        )

class ArbitraryContentWhileThinkingForegroundPaint(ForegroundPaint):

    def __init__(self, name = None, parameter: any = None):
        if name is None:
            name = "ArbitraryContentWhileThinkingForegroundPaint"
        super(ArbitraryContentWhileThinkingForegroundPaint, self).__init__(
            name=name,
            interaction=ForegroundComm.ARBITRARY_TEXT_ICON,
            parameter=parameter,
            # Be careful with this, ensure that avoids painting and not places a black screen 
            # (that removes the background when painting combined)
            final_screen_clearing=True,
            remove_interaction_after_painting=True,
            ignore_maintain_time=True
        )

class ArbitraryContentWhileNetworkingForegroundPaint(ForegroundPaint):

    def __init__(self, name = None, parameter: any = None):
        if name is None:
            name = "ArbitraryContentWhileNetworkingForegroundPaint"
        super(ArbitraryContentWhileNetworkingForegroundPaint, self).__init__(
            name=name,
            interaction=ForegroundComm.ARBITRARY_TEXT_ICON,
            parameter=parameter,
            # Be careful with this, ensure that avoids painting and not places a black screen 
            # (that removes the background when painting combined)
            final_screen_clearing=True,
            remove_interaction_after_painting=True,
            ignore_maintain_time=True
        )

class ArbitraryContentWhileIdleForegroundPaint(ForegroundPaint):

    def __init__(self, name = None, parameter: any = None, for_seconds: float = 5.0):
        if name is None:
            name = "ArbitraryContentWhileIdleForegroundPaint"
        super(ArbitraryContentWhileIdleForegroundPaint, self).__init__(
            name=name,
            interaction=ForegroundComm.ARBITRARY_TEXT_ICON,
            parameter=parameter,
            # Be careful with this, ensure that avoids painting and not places a black screen 
            # (that removes the background when painting combined)
            final_screen_clearing=True,
            remove_interaction_after_painting=True,
            maintain_paint_for_seconds=for_seconds,
            ignore_maintain_time=False
        )

class StartupForegroundPaint(ForegroundPaint):

    def __init__(self, name = None, for_seconds: float = 5.0):
        if name is None:
            name = "StartUpForegroundPaint"
        super(StartupForegroundPaint, self).__init__(
            name=name,
            interaction=ForegroundComm.STARTUP,
            # Be careful with this, ensure that avoids painting and not places a black screen 
            # (that removes the background when painting combined)
            final_screen_clearing=True,
            remove_interaction_after_painting=True,
            maintain_paint_for_seconds=for_seconds,
            ignore_maintain_time=False
        )

class StartupWithPhaseForegroundPaint(ForegroundPaint):

    def __init__(self, name = None, parameter: any = None):
        if name is None:
            name = "StartupWithPhaseForegroundPaint"
        super(StartupWithPhaseForegroundPaint, self).__init__(
            name=name,
            interaction=ForegroundComm.STARTUP_WITH_PHASE,
            parameter=parameter,
            final_screen_clearing=True,
            remove_interaction_after_painting=False,
            overwrite_current_interaction_with_same_type = True
        )

class ErrorForegroundPaint(ForegroundPaint):

    def __init__(self, name = None, parameter: dict = None, for_seconds: float = 5.0):
        if name is None:
            name = "ErrorForegroundPaint"
        super(ErrorForegroundPaint, self).__init__(
            name=name,
            interaction=ForegroundComm.ARBITRARY_TEXT_ICON,
            parameter={
                "text": parameter.get("text"),
                "icon": "❌",
                "font_size": parameter.get("font_size", 24),
                "header": "Error",
                "font_header_size": parameter.get("font_header_size", 32),
                "padding": parameter.get("padding", 5)
            },
            # Be careful with this, ensure that avoids painting and not places a black screen 
            # (that removes the background when painting combined)
            final_screen_clearing=True,
            remove_interaction_after_painting=True,
            maintain_paint_for_seconds=for_seconds,
            ignore_maintain_time=False
        )

class CodeBlockForegroundPaint(ForegroundPaint):

    def __init__(self, name = None, parameter: dict = None, for_seconds: float = 10.0):
        if name is None:
            name = "CodeBlockForegroundPaint"
        super(CodeBlockForegroundPaint, self).__init__(
            name=name,
            interaction=ForegroundComm.CODE_BLOCK,
            parameter=parameter,
            # Be careful with this, this places a black screen over whatever is already painted in the canvas.
            # (so, it removes the background when painting combined)
            final_screen_clearing=True,
            remove_interaction_after_painting=True,
            maintain_paint_for_seconds=for_seconds,
            ignore_maintain_time=False
        )

class TextBlockForegroundPaint(ForegroundPaint):

    def __init__(self, name = None, parameter: dict = None, for_seconds: float = 10.0):
        if name is None:
            name = "TextBlockForegroundPaint"
        super(TextBlockForegroundPaint, self).__init__(
            name=name,
            interaction=ForegroundComm.TEXT_BLOCK,
            parameter=parameter,
            # Be careful with this, this places a black screen over whatever is already painted in the canvas.
            # (so, it removes the background when painting combined)
            final_screen_clearing=True,
            remove_interaction_after_painting=True,
            maintain_paint_for_seconds=for_seconds,
            ignore_maintain_time=False
        )

class TextBlockWhileSpeakingForegroundPaint(ForegroundPaint):

    def __init__(self, name = None, parameter: any = None):
        if name is None:
            name = "TextBlockWhileSpeakingForegroundPaint"
        super(TextBlockWhileSpeakingForegroundPaint, self).__init__(
            name=name,
            interaction=ForegroundComm.TEXT_BLOCK,
            parameter=parameter,
            # Be careful with this, ensure that avoids painting and not places a black screen 
            # (that removes the background when painting combined)
            final_screen_clearing=True,
            remove_interaction_after_painting=True,
            ignore_maintain_time=True
        )

class ClearForegroundPaint(ForegroundPaint):

    def __init__(self, name = None):
        if name is None:
            name = "ClearForegroundPaint"
        super(ClearForegroundPaint, self).__init__(
            name=name,
            interaction=ForegroundComm.CLEAR,
            final_screen_clearing=False,
            remove_interaction_after_painting=True
        )

class ClearBackgroundPaint(BackgroundPaint):

    def __init__(self, name = None):
        if name is None:
            name = "ClearBackgroundPaint"
        super(ClearBackgroundPaint, self).__init__(
            name=name,
            interaction=BackgroundComm.CLEAR,
            final_screen_clearing=False,
            remove_interaction_after_painting=True
        )
        