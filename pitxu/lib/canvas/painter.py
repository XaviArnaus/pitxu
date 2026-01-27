from __future__ import annotations
from threading import Thread

from pyxavi import Config, Dictionary
from pitxu.lib.abstract.pyxavi import PyXavi
from pitxu.lib.canvas.macros import Macros
from pitxu.lib.interaction.CommConstants import BackgroundComm, ForegroundComm
from pitxu.lib.utils.xtime import Xtime

from PIL import ImageDraw
import time

class Painter(PyXavi, Thread):

    # This controls whether the painting loop is running or not
    running: bool = False
    # This controls whether the thread needs to finish completely
    should_finish: bool = False

    macros: Macros = None
    draw: ImageDraw = None

    foreground_paint: list[dict[str, any]] = []
    background_paint: dict[str, any] = None
    delay_between_iterations: float = None  # 50 ms between iterations
    maintain_foreground_paint_for_seconds: float = None  # No pause after full paint by default
    foreground_clean_requested_after_maintain_time: bool = False
    background_clean_requested_after_painting: bool = False

    DEFAULT_DELAY_BETWEEN_ITERATIONS: float = 0.05  # 50 ms between iterations
    DEFAULT_MAINTAIN_FOREGROUND_PAINT_FOR_SECONDS: float = 0.0  # No pause after full paint by default

    BACKGROUND_DEFAULT: str = "default"
    LED_EFFECT_LOOP_ITERATIONS: dict = {
        BackgroundComm.THINKING: 16,
        BackgroundComm.SPEAKING: 8,
        BackgroundComm.INITIAL_PHASE: 1,
        BackgroundComm.HOLDER_PERCENTAGE: 1,
        BACKGROUND_DEFAULT: 1
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
    
    def get_foreground_interaction(self) -> dict:
        return self.foreground_paint[0] if len(self.foreground_paint) > 0 else None
    
    def vanish_current_foreground_interaction(self):
        """Remove the foreground paint at position 0, currently used to paint"""
        if len(self.foreground_paint) > 0:
            self.foreground_paint.pop(0) 
    
    def set_background_interaction(self, interaction: str, parameter: any = None):
        self._log_debug(f"Setting background interaction to [{interaction}] with parameter [{parameter}].")
        self.background_paint = {
            "interaction": interaction,
            "parameter": parameter
        }

    def clear_foreground_interaction(self, by_the_end_of_the_maintain_time: bool = False):
        self._log_debug(f"Clearing foreground interaction (by the end of maintain time: {by_the_end_of_the_maintain_time}).")
        if by_the_end_of_the_maintain_time:
            self.foreground_clean_requested_after_maintain_time = True
        else:
            self.foreground_paint = []
    
    def clear_background_interaction(self, by_the_end_of_the_painting: bool = False):
        self._log_debug(f"Clearing background interaction (by the end of painting: {by_the_end_of_the_painting}).")
        if by_the_end_of_the_painting:
            self.background_clean_requested_after_painting = True
        else:
            self.background_paint = None

    def clear_all_interactions(self):
        self._log_debug("Clearing all interactions.")
        self.clear_foreground_interaction()
        self.clear_background_interaction()
    
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
                    clean_foreground_after_maintain_time: bool = False,
                    clean_background_after_painting: bool = False):
        # Set the interactions if provided
        if foreground_interaction is not None:
            self.set_foreground_interaction(foreground_interaction, foreground_parameter)
            self.set_maintain_foreground_paint_for_seconds(show_for_seconds)
        if background_interaction is not None:
            self.set_background_interaction(background_interaction, background_parameter)

        # Start the painting loop
        self.start_or_resume_paint()

        # Clear related interactions
        if foreground_interaction is not None and clean_foreground_after_maintain_time:
            self.clear_foreground_interaction(by_the_end_of_the_maintain_time=True)
        if background_interaction is not None and clean_background_after_painting:
            self.clear_background_interaction(by_the_end_of_the_painting=True)

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

                # We need to draw from background to foreground.
                # At this point, LED effects are the most background, so we draw them first.

                # Some of the LED effects are loops, so we need to handle the drawing via a loop
                # And then flush to the display at each step.
                if self.background_paint is not None:
                    # Calculating max iterations for the current background interaction
                    background_iterations = self.LED_EFFECT_LOOP_ITERATIONS.get(self.background_paint["interaction"], 1)\
                                    if self.background_paint["interaction"] in self.LED_EFFECT_LOOP_ITERATIONS\
                                    else self.LED_EFFECT_LOOP_ITERATIONS.get(self.BACKGROUND_DEFAULT, 1)

                    if self.background_paint["interaction"] == BackgroundComm.THINKING:
                        step = current_iteration % 8
                        if current_iteration < 8:
                            self._log_debug(f"Painter Loop: Drawing Thinking Right screen on LCD display, step [{step}].")
                            self.macros.draw_kitt_horizontal_effect_right(draw=self.draw, step=step)
                        else:
                            self._log_debug(f"Painter Loop: Drawing Thinking Left screen on LCD display, step [{step}].")
                            self.macros.draw_kitt_horizontal_effect_left(draw=self.draw, step=step)
                    elif self.background_paint["interaction"] == BackgroundComm.SPEAKING:
                        # For speaking, we simulate some VU meter values
                        step = current_iteration % 4
                        if current_iteration < 4:
                            self._log_debug(f"Painter Loop: Drawing Speaking screen on LCD display, step [{step}].")
                            self.macros.draw_kitt_speaking_effect_vu_meter_increase(draw=self.draw, step=step)
                        else:
                            self._log_debug(f"Painter Loop: Cleaning Speaking screen on LCD display, step [{step}].")
                            self.macros.draw_kitt_speaking_effect_vu_meter_decrease(draw=self.draw, step=step)
                    elif self.background_paint["interaction"] == BackgroundComm.INITIAL_PHASE:
                        self._log_debug(f"Painter Loop: Drawing Init Steps screen on LCD display")
                        self.macros._soft_clear_rectangle(draw=self.draw)
                        self.macros.draw_init_phase(draw=self.draw, phase=self.background_paint["parameter"])
                    elif self.background_paint["interaction"] == BackgroundComm.HOLDER_PERCENTAGE:
                        self._log_debug(f"Painter Loop: Drawing Holder Percentage screen on LCD display")
                        self.macros.draw_interaction_holding_percentage(draw=self.draw, percentage=self.background_paint["parameter"])
                    elif self.background_paint["interaction"] == BackgroundComm.ERROR:
                        self._log_debug(f"Painter Loop: Drawing Error screen on LCD display")
                        self.macros.draw_cross(draw=self.draw)
                    elif self.background_paint["interaction"] == BackgroundComm.CLEAR:
                        self._log_debug(f"Painter Loop: Clearing background interaction on LCD display")
                        self.macros._soft_clear_rectangle(draw=self.draw)
                    else:
                        self._xlog.warning(f"Painter: Unknown interaction [{self.background_paint['interaction']}] for drawing on LCD display, discarding.")

                # There are no loops for foreground interactions yet, so we just draw them once.
                # - We may not receive any foreground interaction.
                # - We may want to hold this paint for X time. Therefore, we avoid repainting during that time.
                #       Keep in mind that this ignores new possible foregrounds to show meanwhile.
                foreground_paint = self.get_foreground_interaction()
                if foreground_paint is not None:

                    # We have a foreground paint. Is it the first loop iteration to see it?
                    if foreground_starting_time is None:
                        # It was, so we set the starting time and then we control how much it is getting shown.
                        self._log_debug(f"Painter: New foreground paint detected: [{foreground_paint['interaction']}], starting to show it now.")
                        foreground_starting_time = Xtime.now_milliseconds()

                    # Because we may have painted anything related to the background first, we need to paint again the foreground over it.
                    # That's why, even a flushed image stays until changed, we need to keep on repainting it.
                
                    # Whatever we print here, make it over a semi-transparent frame
                    self.macros.draw_foreground_frame(draw=self.draw)

                    # Now the expected interactions.
                    if foreground_paint["interaction"] == ForegroundComm.STARTUP:
                        self._log_debug("Painter Loop: Drawing startup splash screen on LCD display.")
                        self.macros.draw_startup_splash(draw=self.draw) 
                    elif foreground_paint["interaction"] == ForegroundComm.ARBITRARY_TEXT:
                        self._log_debug("Painter Loop: Drawing arbitrary text on LCD display.")
                        self.macros.draw_arbitrary_text_centered(draw=self.draw, text=foreground_paint["parameter"])
                    elif foreground_paint["interaction"] == ForegroundComm.ARBITRARY_TEXT_ICON:
                        self._log_debug("Painter Loop: Drawing arbitrary text with icon on LCD display.")
                        self.macros.draw_arbitrary_text_with_icon(draw=self.draw, 
                                                            text=foreground_paint["parameter"].get("text"),
                                                            icon=foreground_paint["parameter"].get("icon"),
                                                            font_size=foreground_paint["parameter"].get("font_size", 24),
                                                            header=foreground_paint["parameter"].get("header"),
                                                            font_header_size=foreground_paint["parameter"].get("font_header_size", 32),
                                                            padding=foreground_paint["parameter"].get("padding", 5))
                    elif foreground_paint["interaction"] == ForegroundComm.CLEAR:
                        self._log_debug("Painter Loop: Clearing foreground interaction on LCD display")
                        self.macros._soft_clear_rectangle(draw=self.draw)
                    else:
                        self._xlog.warning(f"Painter: Unknown interaction [{foreground_paint['interaction']}] for drawing on LCD display, discarding.")
                    
                    # We may have reached the end of the foreground paint maintain time.
                    # We now allow new foregrounds to be painted. This is useful when the expected time for a foreground is shorter than
                    #   the background showing time. We can show the next foreground paint.
                    if Xtime.now_minus_seconds_milliseconds(self.maintain_foreground_paint_for_seconds) > foreground_starting_time:
                        # If we clean the foreground we may loose the one that may have been set while showing the previous, so no.
                        # The start of the foreground_starting_time must happen at the beginning of the loop's iteration
                        #   so we start with a new paint.

                        self._log_debug("Painter: Foreground paint showing time elapsed, moving to next foreground interaction if any.")

                        # What we do here is to set it to None so that the IF at the beginning of the iteration knows that it needs to be started.
                        foreground_starting_time = None
                        # And vanish the current foreground paint, so we can pick the next.
                        self.vanish_current_foreground_interaction()
                        # If we had a request to clean the foreground after the maintain time, we do it now.
                        if self.foreground_clean_requested_after_maintain_time:
                            self._log_debug("Painter: Cleaning foreground interaction after maintain time as requested.")
                            self.foreground_clean_requested_after_maintain_time = False
                            self.macros._soft_clear_rectangle(draw=self.draw)

                # Show the image on the device
                self.flush_drawing()

                # Wait for the specified delay between iterations
                self._log_debug(f"Painter: Waiting for [{self.get_delay_between_iterations()}] seconds before next iteration.")
                time.sleep(self.get_delay_between_iterations())

                # Increment the iteration counter
                current_iteration += 1

                # If we have reached the max iterations for background, we reset the iterations counter.
                # This means that this loop will go forever until we stop the thread or change the background interaction.
                if current_iteration >= background_iterations:
                    self._log_debug("Reached max iterations for background interaction, reseting the counter.")
                    current_iteration = 0

                    # If we had a request to clean the background after the full painting is done, we do it now.
                    if self.background_clean_requested_after_painting:
                        self._log_debug("Painter: Cleaning background interaction after full painting is done as requested.")
                        self.background_clean_requested_after_painting = False
                        self.macros._soft_clear_rectangle(draw=self.draw)
                
                # Finally, if there is no foreground nor background paint, we can stop the loop.
                if self.get_foreground_interaction() is None and self.background_paint is None:
                    self._log_debug("No foreground nor background paint remaining, stopping the painting loop.")
                    self.stop()