from __future__ import annotations
from threading import Thread

from pyxavi import Config, Dictionary
from pitxu.lib.abstract.pyxavi import PyXavi
from pitxu.lib.canvas.macros import Macros
from pitxu.lib.interaction.CommConstants import BackgroundComm, ForegroundComm
from pitxu.lib.utils.xtime import Xtime
# from pitxu.lib.utils.shared_memory_manager import SharedMemoryManager
from pitxu.lib.canvas.painter_busy_flags import PainterBusyFlags

from definitions import SHARED_LCD_BUSY, SHARED_MATRIX_BUSY, SHARED_SPEAKER_BUSY, SHARED_CHATBOT_BUSY, SHARED_CHATBOT_ANSWER_IS_ERROR,\
                        FOREGROUND_CHANNEL, BACKGROUND_CHANNEL, LOOP_START, LOOP_END

from PIL import ImageDraw
import time

class Painter(PyXavi, Thread):

    # This controls whether the painting loop is running or not
    running: bool = False
    # This controls whether the thread needs to finish completely
    should_finish: bool = False

    macros: Macros = None
    draw: ImageDraw = None
    # shared_memory: SharedMemoryManager = None
    painter_busy_flags: PainterBusyFlags = None

    foreground_paint: list[dict[str, any]] = []
    background_paint: list[dict[str, any]] = []
    delay_between_iterations: float = None  # 50 ms between iterations
    maintain_foreground_paint_for_seconds: float = None  # No pause after full paint by default
    ignore_foreground_maintain_time: dict = {}
    foreground_remove_requested_after_painting: dict = {}
    background_remove_requested_after_painting: dict = {}

    DEFAULT_DELAY_BETWEEN_ITERATIONS: float = 0.05  # 50 ms between iterations
    DEFAULT_MAINTAIN_FOREGROUND_PAINT_FOR_SECONDS: float = 3.0  # No pause after full paint by default

    BACKGROUND_DEFAULT: str = "default"
    LED_EFFECT_LOOP_ITERATIONS: dict = {
        BackgroundComm.THINKING: 16,
        BackgroundComm.SPEAKING: 8,
        BackgroundComm.INITIAL_PHASE: 1,
        BackgroundComm.HOLDER_PERCENTAGE: 1,
        BACKGROUND_DEFAULT: 1
    }

    BACKGROUND_TO_BUSY_FLAG: dict = {
        BackgroundComm.THINKING: SHARED_CHATBOT_BUSY,
        BackgroundComm.SPEAKING: SHARED_SPEAKER_BUSY,
    }

    VERBOSE_DEBUG: bool = True

    def __init__(self, config: Config = None, params: Dictionary = None):
        super(Painter, self).init_pyxavi(config=config, params=params)

        self._xlog.debug(f"Initializing PainterLoop for LCD display.")

        if params.key_exists("macros"):
            self.macros = params.get("macros")
        else:
            self._xlog.error(f"No macros provided to {self.__class__.__name__}")
            raise ValueError(f"No macros provided to {self.__class__.__name__}")
        
        # if params.key_exists("shared_memory"):
        #     self.shared_memory = params.get("shared_memory")
        # else:
        #     self.shared_memory = SharedMemoryManager(config=config)
        #     self.shared_memory.initialize_existing_shared_memory_flags()
        self.painter_busy_flags = PainterBusyFlags(config=config, params=params)
        
        # Set default delay between iterations
        self.reset_delay_between_iterations()
        # Set the defaulttime that we want to maintain the foreground paint being shown
        self.reset_maintain_foreground_paint_for_seconds()

        # Initialize the Thread and start it. It won't paint anything until we set the running flag to True.
        Thread.__init__(self)
        self.start()

    # -------- Methods for instructing what to paint --------

    def set_foreground_interaction(self, interaction: str, parameter: any = None):
        self._log_debug(f"Setting foreground interaction to [{interaction}] with parameter [{parameter}].")
        self.foreground_paint.append({
            "interaction": interaction,
            "parameter": parameter
        })
    
    def get_foreground_interaction(self, just_name: bool = False) -> dict:
        current_foreground_paint = self.foreground_paint[0] if len(self.foreground_paint) > 0 else None
        if current_foreground_paint is None:
            return None
        if just_name:
            return current_foreground_paint["interaction"]
        return current_foreground_paint
    
    def set_background_interaction(self, interaction: str, parameter: any = None):
        self._log_debug(f"Setting background interaction to [{interaction}] with parameter [{parameter}].")
        self.background_paint.append({
            "interaction": interaction,
            "parameter": parameter
        })
    
    def get_background_interaction(self, just_name: bool = False) -> dict:
        current_background_paint = self.background_paint[0] if len(self.background_paint) > 0 else None
        if current_background_paint is None:
            return None
        if just_name:
            return current_background_paint["interaction"]
        return current_background_paint
    
    # def remove_current_foreground_interaction(self):
    #     """Remove the foreground paint at position 0, currently used to paint"""
    #     current = None
    #     if len(self.foreground_paint) > 0:
    #         current = self.foreground_paint.pop(0)
    #     next_foreground = self.get_foreground_interaction(just_name=True) if self.get_foreground_interaction() is not None else "None"
    #     self._log_debug(f"Removed current foreground interaction [{current['interaction']}]. Next one is: {next_foreground}.")

    def remove_foreground_interaction(self, interaction_name: str = None, by_the_end_of_the_painting: bool = False):
        if by_the_end_of_the_painting and interaction_name is not None:
            self._log_debug(f"Foreground interaction [{interaction_name}] wants to be removed by the end of the painting.")
            self.foreground_remove_requested_after_painting[interaction_name] = True
        else:
            self._log_debug(f"Foreground interaction [{interaction_name}] wants to be removed now.")
            if len(self.foreground_paint) > 0:
                if self.foreground_paint[0]["interaction"] == interaction_name:
                    self.foreground_paint.pop(0)
                else:
                    self._log_debug(f"🛑 Foreground interaction [{interaction_name}] is not the current one. Skipping.")
                    current_queue = ", ".join([item["interaction"] for item in self.foreground_paint])
                    self._log_debug(f"Current foreground interaction queue: [{current_queue}].")
    
    def remove_all_foreground_interactions(self):
        self._log_debug("Removing all foreground interactions.")
        self.foreground_paint = []
    
    def remove_background_interaction(self, interaction_name: str = None, by_the_end_of_the_painting: bool = False):
        if by_the_end_of_the_painting and interaction_name is not None:
            self._log_debug(f"Background interaction [{interaction_name}] wants to be removed by the end of the painting.")
            self.background_remove_requested_after_painting[interaction_name] = True
        else:
            self._log_debug(f"Background interaction [{interaction_name}] wants to be removed now.")
            if len(self.background_paint) > 0:
                if self.background_paint[0]["interaction"] == interaction_name:
                    self.background_paint.pop(0)
                else:
                    self._log_debug(f"🛑 Background interaction [{interaction_name}] is not the current one. Skipping.")
                    current_queue = ", ".join([item["interaction"] for item in self.background_paint])
                    self._log_debug(f"Current background interaction queue: [{current_queue}].")
    
    def remove_all_background_interactions(self):
        self._log_debug("Removing all background interactions.")
        self.background_paint = []

    def remove_all_interactions(self):
        self._log_debug("Removing all interactions.")
        self.remove_foreground_interaction()
        self.remove_background_interaction()
    
    def set_delay_between_iterations(self, delay: float):
        self._log_debug(f"Setting delay between iterations to [{delay}] seconds.")
        self.delay_between_iterations = delay
    
    def get_delay_between_iterations(self) -> float:
        return self.delay_between_iterations

    def reset_delay_between_iterations(self):
        self._log_debug("Resetting delay between iterations to default (0.05 seconds).")
        self.delay_between_iterations = self.DEFAULT_DELAY_BETWEEN_ITERATIONS

    def set_maintain_foreground_paint_for_seconds(self, seconds: float):
        self._log_debug(f"Setting maintain foreground paint for [{seconds}] seconds.")
        self.maintain_foreground_paint_for_seconds = seconds

    def get_maintain_foreground_paint_for_seconds(self) -> float:
        return self.maintain_foreground_paint_for_seconds

    def reset_maintain_foreground_paint_for_seconds(self):
        self._log_debug("Resetting maintain foreground paint for to default (0.0 seconds).")
        self.maintain_foreground_paint_for_seconds = self.DEFAULT_MAINTAIN_FOREGROUND_PAINT_FOR_SECONDS
    
    def set_ignore_foreground_maintain_time_for_interaction(self, interaction_name: str, ignore: bool = True):
        self._log_debug(f"Setting ignore foreground maintain time for interaction [{interaction_name}] to [{ignore}].")
        self.ignore_foreground_maintain_time[interaction_name] = ignore
    
    def remove_ignore_foreground_maintain_time_for_interaction(self, interaction_name: str):
        self._log_debug(f"Removing ignore foreground maintain time for interaction [{interaction_name}].")
        if interaction_name in self.ignore_foreground_maintain_time:
            del self.ignore_foreground_maintain_time[interaction_name]
    
    def should_ignore_foreground_maintain_time_for_interaction(self, interaction_name: str) -> bool:
        return self.ignore_foreground_maintain_time.get(interaction_name, False)

    # -------- Methods for controlling and executing the thread / loop --------
    
    def start_or_resume_paint(self):

        # If we're actually not running anything inside the thread, do it now.
        if not self.is_running():
            self._log_debug("PainterLoop not running, starting painting loop now.")

            # Prepare the drawing tools outside the loop, so it's more efficient
            self.draw = self.macros.get_canvas().get_canvas(reset_base_image=False)
            self.macros._soft_clear_rectangle(draw=self.draw)

            # Set the running flag to True, so the loop starts painting
            self.running = True
    
    def stop(self):
        # This stops the loop
        self.running = False
    
    def close(self):
        self._xlog.debug("Closing PainterLoop.")

        # This finishes the painting loop
        if self.is_running():
            self.stop()
        
        # This finishes the thread
        self.should_finish = True
        self.join()
    
    def flush_drawing(self):
        self.macros.get_device().display(self.macros.get_canvas().get_image())
    
    def is_running(self) -> bool:
        return self.running
    
    def should_thread_finish(self) -> bool:
        return self.should_finish

    def just_paint(self, 
                    foreground_interaction: str = None, foreground_parameter: any = None, 
                    background_interaction: str = None, background_parameter: any = None,
                    show_for_seconds: float = 1.0,
                    remove_foreground_after_painting: bool = False,
                    remove_background_after_painting: bool = False):
        # Set the interactions if provided
        if foreground_interaction is not None:
            self.set_foreground_interaction(foreground_interaction, foreground_parameter)
            self.set_maintain_foreground_paint_for_seconds(show_for_seconds)
        if background_interaction is not None:
            self.set_background_interaction(background_interaction, background_parameter)

        # Start the painting loop
        self.start_or_resume_paint()

        # # Remove related interactions
        # if foreground_interaction is not None and remove_foreground_after_painting:
        #     self.remove_foreground_interaction(interaction_name=foreground_interaction, by_the_end_of_the_painting=True)
        # if background_interaction is not None and remove_background_after_painting:
        #     self.remove_background_interaction(interaction_name=background_interaction, by_the_end_of_the_painting=True)
    
    def paint_into_foreground_while_speaking(self, foreground_interaction: str = None, foreground_parameter: any = None):
        
        # 1. First we definethe start callback, that waits for the speaker to be busy and then sets the interactions
        # 2. Then we define the end callback to stop the painting when the speaker is not busy anymore
        # 3. Then we start the loop. It should wait until the speaker is busy to start painting, and then stop when it is not busy anymore.

        # # Start callback definition:
        # def start_callback():
        #     self._log_debug(f"Painter Start Callback for Foreground: Speaker busy flag changed to True, starting painting while speaking.")

        #     # Set the interactions if provided
        #     if foreground_interaction is not None:
        #         self.set_foreground_interaction(foreground_interaction, foreground_parameter)
        #         # Remove the callback itself to avoid multiple triggers
        #         self.painter_busy_flags.remove_busy_flag_callback(when=LOOP_START, channel=FOREGROUND_CHANNEL, flag_name=SHARED_SPEAKER_BUSY, for_value=True)
        
        # # End callback definition:
        # def end_callback():
        #     self._log_debug(f"Painter End Callback for Foreground: Speaker busy flag changed to False, stopping painting while speaking.")

        #     # Remove related interactions
        #     if foreground_interaction is not None:
        #         self.remove_foreground_interaction()
        #         # Remove the callbacks themselves
        #         self.painter_busy_flags.remove_busy_flag_callback(when=LOOP_START, channel=FOREGROUND_CHANNEL, flag_name=SHARED_SPEAKER_BUSY, for_value=True)

        # Start callback definition: we want to paint when the speaker is busy
        start_callback = self._generate_callback(
            interaction=foreground_interaction,
            when=LOOP_START,
            channel=FOREGROUND_CHANNEL,
            flag_name=SHARED_SPEAKER_BUSY,
            for_value=True,
            parameter=foreground_parameter
        )
        # End callback definition: we want to stop painting when the speaker is not busy anymore
        end_callback = self._generate_callback(
            interaction=foreground_interaction,
            when=LOOP_END,
            channel=FOREGROUND_CHANNEL,
            flag_name=SHARED_SPEAKER_BUSY,
            for_value=False
        )
        
        # 1. Register the start callback
        self.painter_busy_flags.set_busy_flag_callback(when=LOOP_START, channel=FOREGROUND_CHANNEL, flag_name=SHARED_SPEAKER_BUSY, for_value=True, callback=start_callback)
        # 2. Register the end callback
        self.painter_busy_flags.set_busy_flag_callback(when=LOOP_END, channel=FOREGROUND_CHANNEL, flag_name=SHARED_SPEAKER_BUSY, for_value=False, callback=end_callback)

        # As we want to paint while speaking, avoid removing the interaction due to maintain time reached.
        self.set_ignore_foreground_maintain_time_for_interaction(interaction_name=foreground_interaction, ignore=True)

        # 3. Start the painting loop
        self.start_or_resume_paint()
    
    def paint_into_background_while_speaking(self, background_interaction: str = None, background_parameter: any = None):
        
        # 1. First we definethe start callback, that waits for the speaker to be busy and then sets the interactions
        # 2. Then we define the end callback to stop the painting when the speaker is not busy anymore
        # 3. Then we start the loop. It should wait until the speaker is busy to start painting, and then stop when it is not busy anymore.

        # Start callback definition: we want to paint when the speaker is busy
        start_callback = self._generate_callback(
            interaction=background_interaction,
            when=LOOP_START,
            channel=BACKGROUND_CHANNEL,
            flag_name=SHARED_SPEAKER_BUSY,
            for_value=True,
            parameter=background_parameter,
            delay_between_frames=0.01
        )
        # End callback definition: we want to stop painting when the speaker is not busy anymore
        end_callback = self._generate_callback(
            interaction=background_interaction,
            when=LOOP_END,
            channel=BACKGROUND_CHANNEL,
            flag_name=SHARED_SPEAKER_BUSY,
            for_value=False
        )
        
        # 1. Register the start callback
        self.painter_busy_flags.set_busy_flag_callback(when=LOOP_START, channel=BACKGROUND_CHANNEL, flag_name=SHARED_SPEAKER_BUSY, for_value=True, callback=start_callback)
        # 2. Register the end callback
        self.painter_busy_flags.set_busy_flag_callback(when=LOOP_END, channel=BACKGROUND_CHANNEL, flag_name=SHARED_SPEAKER_BUSY, for_value=False, callback=end_callback)
        # 3. Start the painting loop
        self.start_or_resume_paint()
    
    def paint_into_foreground_while_thinking(self, foreground_interaction: str = None, foreground_parameter: any = None):
        
        # 1. First we definethe start callback, that waits for the speaker to be busy and then sets the interactions
        # 2. Then we define the end callback to stop the painting when the speaker is not busy anymore
        # 3. Then we start the loop. It should wait until the speaker is busy to start painting, and then stop when it is not busy anymore.

        # Start callback definition: we want to paint when the speaker is busy
        start_callback = self._generate_callback(
            interaction=foreground_interaction,
            when=LOOP_START,
            channel=FOREGROUND_CHANNEL,
            flag_name=SHARED_CHATBOT_BUSY,
            for_value=True,
            parameter=foreground_parameter
        )
        # End callback definition: we want to stop painting when the speaker is not busy anymore
        end_callback = self._generate_callback(
            interaction=foreground_interaction,
            when=LOOP_END,
            channel=FOREGROUND_CHANNEL,
            flag_name=SHARED_CHATBOT_BUSY,
            for_value=False
        )
        
        # 1. Register the start callback
        self.painter_busy_flags.set_busy_flag_callback(when=LOOP_START, channel=FOREGROUND_CHANNEL, flag_name=SHARED_CHATBOT_BUSY, for_value=True, callback=start_callback)
        # 2. Register the end callback
        self.painter_busy_flags.set_busy_flag_callback(when=LOOP_END, channel=FOREGROUND_CHANNEL, flag_name=SHARED_CHATBOT_BUSY, for_value=False, callback=end_callback)

        # As we want to paint while thinking, avoid removing the interaction due to maintain time reached.
        self.set_ignore_foreground_maintain_time_for_interaction(interaction_name=foreground_interaction, ignore=True)

        # 3. Start the painting loop
        self.start_or_resume_paint()
    
    def paint_into_background_while_thinking(self, background_interaction: str = None, background_parameter: any = None):
        
        # 1. First we definethe start callback, that waits for the speaker to be busy and then sets the interactions
        # 2. Then we define the end callback to stop the painting when the speaker is not busy anymore
        # 3. Then we start the loop. It should wait until the speaker is busy to start painting, and then stop when it is not busy anymore.

        # Start callback definition: we want to paint when the speaker is busy
        start_callback = self._generate_callback(
            interaction=background_interaction,
            when=LOOP_START,
            channel=BACKGROUND_CHANNEL,
            flag_name=SHARED_CHATBOT_BUSY,
            for_value=True,
            parameter=background_parameter
        )
        # End callback definition: we want to stop painting when the speaker is not busy anymore
        end_callback = self._generate_callback(
            interaction=background_interaction,
            when=LOOP_END,
            channel=BACKGROUND_CHANNEL,
            flag_name=SHARED_CHATBOT_BUSY,
            for_value=False
        )
        
        # 1. Register the start callback
        self.painter_busy_flags.set_busy_flag_callback(when=LOOP_START, channel=BACKGROUND_CHANNEL, flag_name=SHARED_CHATBOT_BUSY, for_value=True, callback=start_callback)
        # 2. Register the end callback
        self.painter_busy_flags.set_busy_flag_callback(when=LOOP_END, channel=BACKGROUND_CHANNEL, flag_name=SHARED_CHATBOT_BUSY, for_value=False, callback=end_callback)
        # 3. Start the painting loop
        self.start_or_resume_paint()
    
    
    def _generate_callback(self,
                           interaction: str,
                           when: str,
                           channel: str,
                           flag_name: int,
                           for_value: bool,
                           parameter: any = None,
                           final_screen_clearing: bool = False,
                           delay_between_frames: float = None) -> callable:
        
        start_interaction_function = self.set_background_interaction if channel == BACKGROUND_CHANNEL else self.set_foreground_interaction
        end_interaction_function = self.remove_background_interaction if channel == BACKGROUND_CHANNEL else self.remove_foreground_interaction
        
        # callback_template for the loop start section
        def start_callback_template():
            self._log_debug(f"Painter [{when}] Callback for [{channel}]: [{self.painter_busy_flags._flag_string(flag_name)}] busy flag changed to [{for_value}].")

            # Set the interactions if provided
            if interaction is not None:
                start_interaction_function(interaction, parameter)
                # Remove the callback itself to avoid multiple triggers
                self.painter_busy_flags.remove_busy_flag_callback(when=LOOP_START, channel=channel, flag_name=flag_name, for_value=for_value)
                # If we want to clear the screen at the end of the interaction, we can set a final callback here
                if final_screen_clearing:
                    self.macros._soft_clear_rectangle(draw=self.draw)
                # If we want to use a different delay between frames during this interaction
                if delay_between_frames is not None:
                    self._log_debug(f"Painter [{when}] Callback for [{channel}]: Setting delay between iterations to [{delay_between_frames}] seconds for interaction [{interaction}].")
                    self.set_delay_between_iterations(delay_between_frames)
        
        # callback_template for the loop end section
        def end_callback_template():
            self._log_debug(f"Painter [{when}] Callback for [{channel}]: [{self.painter_busy_flags._flag_string(flag_name)}] busy flag changed to [{for_value}].")

            # Remove related interactions
            if interaction is not None:
                end_interaction_function(interaction_name=interaction)
                # Remove the callbacks themselves
                self.painter_busy_flags.remove_busy_flag_callback(when=LOOP_END, channel=channel, flag_name=flag_name, for_value=for_value)
                # If we want to clear the screen at the end of the interaction, we can set a final callback here
                if final_screen_clearing:
                    self.macros._soft_clear_rectangle(draw=self.draw)
                # Whatever the delay between frames we set for this interaction, we reset it to default now
                self.reset_delay_between_iterations()
        
        return start_callback_template if when == LOOP_START else end_callback_template

    def run(self):
        # We need an overall loop that keeps the thread alive.
        # The close() method will set the should_finish flag to True, which will break this loop.
        while not self.should_thread_finish():

            # Each time we enter this loop, we reset the iteration counter.
            current_iteration = 0

            # We calculate the showing time for the foreground paint from the first showing instant,
            #   so we depend on paint changes. Start with None.
            foreground_starting_time = None

            # We control the painting loop via the running flag.
            while self.is_running():

                # Trigger any busy flag callbacks at the start of the loop
                self.painter_busy_flags.trigger_busy_flags_callbacks_at_loop_start()

                # Getting the current interactions, to avoid gathering over and over again
                current_foreground_interaction = self.get_foreground_interaction()
                current_background_interaction = self.get_background_interaction()
                current_foreground_interaction_name = current_foreground_interaction["interaction"] if current_foreground_interaction is not None else None
                current_background_interaction_name = current_background_interaction["interaction"] if current_background_interaction is not None else None

                # What if we try the whole drawing startig by a clear screen?
                if current_background_interaction is not None or current_foreground_interaction is not None:
                    self._log_debug(f"Painter Loop: Clearing screen on LCD display at the beginning of the loop.")
                    self.macros._soft_clear_rectangle(draw=self.draw)

                # We need to draw from background to foreground.
                # At this point, LED effects are the most background, so we draw them first.
                # Some of the LED effects are loops, so we need to handle the drawing via a frame iterations.
                # And then flush to the display after drawing each frame fully.
                if current_background_interaction is not None:
                    # Calculating max iterations for the current background interaction
                    background_iterations = self.LED_EFFECT_LOOP_ITERATIONS.get(current_background_interaction_name, 1)\
                                    if current_background_interaction_name in self.LED_EFFECT_LOOP_ITERATIONS\
                                    else self.LED_EFFECT_LOOP_ITERATIONS.get(self.BACKGROUND_DEFAULT, 1)

                    if current_background_interaction_name == BackgroundComm.THINKING:
                        frame = current_iteration % 8
                        if current_iteration < 8:
                            self._log_debug(f"Painter Loop: Drawing Thinking Right screen on LCD display, frame [{frame}].")
                            self.macros.draw_kitt_horizontal_effect_right(draw=self.draw, frame=frame)
                        else:
                            self._log_debug(f"Painter Loop: Drawing Thinking Left screen on LCD display, frame [{frame}].")
                            self.macros.draw_kitt_horizontal_effect_left(draw=self.draw, frame=frame)
                    elif current_background_interaction_name == BackgroundComm.SPEAKING:
                        frame = current_iteration % 4
                        if current_iteration < 4:
                            self._log_debug(f"Painter Loop: Drawing Speaking Increase screen on LCD display, frame [{frame}].")
                            self.macros.draw_kitt_speaking_effect_increase(draw=self.draw, frame=frame)
                        else:
                            self._log_debug(f"Painter Loop: Drawing Speaking Decrease screen on LCD display, frame [{frame}].")
                            self.macros.draw_kitt_speaking_effect_decrease(draw=self.draw, frame=frame)
                    elif current_background_interaction_name == BackgroundComm.INITIAL_PHASE:
                        self._log_debug(f"Painter Loop: Drawing Init Steps screen on LCD display")
                        # self.macros._soft_clear_rectangle(draw=self.draw)
                        self.macros.draw_init_phase(draw=self.draw, phase=current_background_interaction["parameter"])
                    elif current_background_interaction_name == BackgroundComm.HOLDER_PERCENTAGE:
                        self._log_debug(f"Painter Loop: Drawing Holder Percentage screen on LCD display")
                        self.macros.draw_interaction_holding_percentage(draw=self.draw, percentage=current_background_interaction["parameter"])
                    elif current_background_interaction_name == BackgroundComm.ERROR:
                        self._log_debug(f"Painter Loop: Drawing Error screen on LCD display")
                        self.macros.draw_cross(draw=self.draw)
                    elif current_background_interaction_name == BackgroundComm.CLEAR:
                        # As opposite to foreground, we do clear the background because we may have to remove the previous paint.
                        self._log_debug(f"Painter Loop: Clearing background interaction on LCD display")
                        # self.macros._soft_clear_rectangle(draw=self.draw)
                    else:
                        self._xlog.warning(f"Painter: Unknown interaction [{current_background_interaction_name}] for drawing on LCD display, discarding.")

                # There are no loops for foreground interactions yet, so we just draw them once.
                # - We may not receive any foreground interaction.
                # - We may want to hold this paint for X time. Therefore, we avoid repainting during that time.
                #       Keep in mind that this ignores new possible foregrounds to show meanwhile.
                if current_foreground_interaction is not None:

                    # We have a foreground paint. Is it the first loop iteration to see it?
                    if foreground_starting_time is None:
                        # It was, so we set the starting time and then we control how much it is getting shown.
                        self._log_debug(f"Painter: New foreground paint detected: [{current_foreground_interaction_name}], starting to show it now.")
                        foreground_starting_time = Xtime.now_milliseconds()

                    # Because we may have painted anything related to the background first, we need to paint again the foreground over it.
                    # That's why, even a flushed image stays until changed, we need to keep on repainting it.
                
                    # Whatever we print here, make it over a semi-transparent frame
                    self.macros.draw_foreground_frame(draw=self.draw)

                    # Now the expected interactions.
                    if current_foreground_interaction_name == ForegroundComm.STARTUP:
                        self._log_debug("Painter Loop: Drawing startup splash screen on LCD display.")
                        self.macros.draw_startup_splash(draw=self.draw) 
                    elif current_foreground_interaction_name == ForegroundComm.ARBITRARY_TEXT:
                        self._log_debug("Painter Loop: Drawing arbitrary text on LCD display.")
                        self.macros.draw_arbitrary_text_centered(draw=self.draw, text=current_foreground_interaction["parameter"])
                    elif current_foreground_interaction_name == ForegroundComm.ARBITRARY_TEXT_ICON:
                        self._log_debug("Painter Loop: Drawing arbitrary text with icon on LCD display.")
                        self.macros.draw_arbitrary_text_with_icon(draw=self.draw, 
                                                            text=current_foreground_interaction["parameter"].get("text"),
                                                            icon=current_foreground_interaction["parameter"].get("icon"),
                                                            font_size=current_foreground_interaction["parameter"].get("font_size", 24),
                                                            header=current_foreground_interaction["parameter"].get("header"),
                                                            font_header_size=current_foreground_interaction["parameter"].get("font_header_size", 32),
                                                            padding=current_foreground_interaction["parameter"].get("padding", 5))
                    elif current_foreground_interaction_name == ForegroundComm.CLEAR:
                        # If we need to clear the foreground, actualy we use the iteration to draw nothing.
                        # this is because if we clean the foreground, we may loose the background that was painted before.
                        self._log_debug("Painter Loop: Clearing foreground interaction on LCD display: Drawing nothing.")
                        # self.macros._soft_clear_rectangle(draw=self.draw)
                    else:
                        self._xlog.warning(f"Painter: Unknown interaction [{current_foreground_interaction_name}] for drawing on LCD display, discarding.")
                    
                    # We may have reached the end of the foreground paint showing time.
                    # We now allow new foregrounds to be painted. This is useful when the expected time for a foreground is shorter than
                    #   the background showing time. We can show the next foreground paint.
                    if Xtime.now_minus_seconds_milliseconds(self.maintain_foreground_paint_for_seconds) > foreground_starting_time and\
                        not self.should_ignore_foreground_maintain_time_for_interaction(current_foreground_interaction_name):
                        # If we remove the foreground we may loose the one that may have been set while showing the previous interaction, so no.
                        # The start of the foreground_starting_time must happen at the beginning of the loop's iteration
                        #   so we start with a new paint.

                        self._log_debug(f"Painter: Foreground interaction [{current_foreground_interaction_name}] showing time elapsed, moving to next foreground interaction if any.")

                        # What we do here is to set it to None so that the IF at the beginning of the iteration knows that it needs to be started.
                        foreground_starting_time = None

                        # And remove the current foreground paint, so we can pick the next.
                        self.remove_foreground_interaction(interaction_name=current_foreground_interaction_name)

                        # Also remove the ignore flag
                        self.remove_ignore_foreground_maintain_time_for_interaction(current_foreground_interaction_name)

                # Show the image on the device
                self._log_debug(f"Painter: Flushing drawing to LCD display: Foreground is {current_foreground_interaction_name}, Background is {current_background_interaction_name}.")
                self.flush_drawing()

                # Wait for the specified delay between iterations
                self._log_debug(f"Painter: Waiting for [{self.get_delay_between_iterations()}] seconds before next iteration.")
                time.sleep(self.get_delay_between_iterations())

                # Increment the iteration counter
                current_iteration += 1

                # If we have reached the max iterations for background, we reset the iterations counter.
                # This means that this loop will go forever until we stop the thread or change the background interaction.
                if current_iteration >= background_iterations:
                    self._log_debug(f"Reached max iterations for background interaction [{current_background_interaction_name}], reseting the counter.")
                    current_iteration = 0

                # If we had a request to clean the background after the full painting is done, we do it now.
                if current_background_interaction_name in self.background_remove_requested_after_painting and \
                    self.background_remove_requested_after_painting[current_background_interaction_name]:

                    self._log_debug(f"Painter: Removing background interaction [{current_background_interaction_name}] after full painting is done as requested.")
                    del self.background_remove_requested_after_painting[current_background_interaction_name]
                    # We remove the background interaction now.
                    self.remove_background_interaction(interaction_name=current_background_interaction_name)
                
                # If the list of background interactions contains more than the current item, we remove the current one to move to the next.
                # This should override the request to avoid removing at the end of the painting.
                # It's an else-if because we may have just removed it in the previous IF.
                elif len(self.background_paint) > 1:
                    self._log_debug(f"Painter: More than one background interaction in the queue, removing current background interaction [{current_background_interaction_name}] to move to next.")
                    self.remove_background_interaction(interaction_name=current_background_interaction_name)
                    # We may have other flags to delete too.
                    if current_background_interaction_name in self.background_remove_requested_after_painting:
                        del self.background_remove_requested_after_painting[current_background_interaction_name]
                    if current_background_interaction_name in self.BACKGROUND_TO_BUSY_FLAG.keys():
                        if self.painter_busy_flags.callback_exists_for_busy_flag(when=LOOP_START, channel=BACKGROUND_CHANNEL, flag_name=self.BACKGROUND_TO_BUSY_FLAG[current_background_interaction_name], for_value=True):
                            self.painter_busy_flags.remove_busy_flag_callback(when=LOOP_START, channel=BACKGROUND_CHANNEL, flag_name=self.BACKGROUND_TO_BUSY_FLAG[current_background_interaction_name], for_value=True)
                        if self.painter_busy_flags.callback_exists_for_busy_flag(when=LOOP_END, channel=BACKGROUND_CHANNEL, flag_name=self.BACKGROUND_TO_BUSY_FLAG[current_background_interaction_name], for_value=False):
                            self.painter_busy_flags.remove_busy_flag_callback(when=LOOP_END, channel=BACKGROUND_CHANNEL, flag_name=self.BACKGROUND_TO_BUSY_FLAG[current_background_interaction_name], for_value=False)
                
                # If we had a request to clean the foreground after the painting, we do it now,
                #   just in case we didn't remove it yet
                #   (we know it's removed if foreground_starting_time is None, because it's reset when the maintain_foreground_paint_for_seconds is exceeded).
                if current_foreground_interaction_name in self.foreground_remove_requested_after_painting and \
                    self.foreground_remove_requested_after_painting[current_foreground_interaction_name] and foreground_starting_time is None:
                    self._log_debug(f"Painter: Removing foreground interaction [{current_foreground_interaction_name}] after painting as requested.")
                    del self.foreground_remove_requested_after_painting[current_foreground_interaction_name]
                    # We remove the foreground interaction now.
                    self.remove_foreground_interaction(interaction_name=current_foreground_interaction_name)
                    # Also remove the possible ignore flag
                    self.remove_ignore_foreground_maintain_time_for_interaction(current_foreground_interaction_name)
                
                # Check the busy flags and call their callbacks if needed
                self.painter_busy_flags.trigger_busy_flags_callbacks_at_loop_end()
                
                # Finally, if there is no foreground nor background paint, we can stop the loop.
                if current_foreground_interaction is None and current_background_interaction is None:
                    self._log_debug("No foreground nor background paint remaining, stopping the painting loop.")
                    self.stop()