from __future__ import annotations
from threading import Thread

from pyxavi import Config, Dictionary
from pitxu.lib.abstract.pyxavi import PyXavi
from pitxu.lib.canvas.macros import Macros
from pitxu.lib.canvas.painter_commands import BackgroundComm, ForegroundComm
from pitxu.lib.canvas.paint_objects import ForegroundPaint, BackgroundPaint
from pitxu.lib.utils.xtime import Xtime
from pitxu.lib.canvas.painter_busy_flags import PainterBusyFlags

from definitions import SHARED_SPEAKER_BUSY, SHARED_CHATBOT_BUSY, SHARED_CHATBOT_ANSWER_IS_ERROR, \
                        SHARED_NETWORK_BUSY, SHARED_IDLE_MODE, SHARED_VAD_DETECTED, \
                        FOREGROUND_CHANNEL, BACKGROUND_CHANNEL, LOOP_START, LOOP_END

from PIL import ImageDraw
import time
import os, signal

class Painter(PyXavi, Thread):

    # This controls whether the painting loop is running or not
    running: bool = False
    # This controls whether the thread needs to finish completely
    should_finish: bool = False

    macros: Macros = None
    draw: ImageDraw = None
    painter_busy_flags: PainterBusyFlags = None

    foreground_paint: list[ForegroundPaint] = []
    background_paint: list[BackgroundPaint] = []

    BACKGROUND_TO_BUSY_FLAG: dict = {
        BackgroundComm.THINKING: SHARED_CHATBOT_BUSY,
        BackgroundComm.SPEAKING: SHARED_SPEAKER_BUSY,
    }

    PRIORITY_BACKGROUND_INTERACTIONS: list = [
        BackgroundComm.SPEAKING
    ]

    VERBOSE_DEBUG: bool = False

    def __init__(self, config: Config = None, params: Dictionary = None):
        super(Painter, self).init_pyxavi(config=config, params=params)

        self._xlog.debug(f"Initializing PainterLoop for LCD display.")

        if params.key_exists("macros"):
            self.macros = params.get("macros")
        else:
            self._xlog.error(f"No macros provided to {self.__class__.__name__}")
            raise ValueError(f"No macros provided to {self.__class__.__name__}")
        
        self.painter_busy_flags = PainterBusyFlags(config=config, params=params)

        # Initialize the Thread and start it. It won't paint anything until we set the running flag to True.
        Thread.__init__(self, name="Painter", daemon=True)
        self.start()

    # -------- Methods for instructing what to paint --------

    def set_foreground_interaction(self, interaction: ForegroundPaint):
        self._log_debug(f"Setting foreground interaction to [{interaction.name}] with parameter [{interaction.parameter}].")
        # In case we have anything from the same type waiting to be shown, we discard it first.
        #   If we didn't show it yet, there is no point to keep waiting, the flow already went somewhere else.
        self._remove_duplicated_interaction_types_from_queue(interaction=interaction)

        # If the interaction is actually a CLEAR, we want to remove all the previous interactions of the same type,
        # to have the inmediate effect of clearing the Foreground.
        if interaction.interaction == ForegroundComm.CLEAR:
            self._log_debug(f"Foreground interaction [{interaction.name}] is a CLEAR. Removing all previous interactions from the queue.")
            self.remove_all_foreground_interactions()
        else:
            # Now add the new interaction to the queue
            self.foreground_paint.append(interaction)

        self._log_debug(f"Foreground interaction queue after setting last: {', '.join([item.name for item in self.foreground_paint])}.")
    
    def get_current_foreground_interaction(self) -> ForegroundPaint:
        current_foreground_paint = self.foreground_paint[0] if len(self.foreground_paint) > 0 else None
        if current_foreground_paint is None:
            return None
        return current_foreground_paint
    
    def set_background_interaction(self, interaction: BackgroundPaint):
        self._log_debug(f"Setting background interaction to [{interaction.name}] with parameter [{interaction.parameter}].")
        self._log_debug(f"begin, queue status: [{', '.join([item.name for item in self.background_paint])}].")
        # Some interactions are priority, so we remove previous ones from the queue in case the given one is priority.
        self._remove_previous_background_interactions_if_given_is_priority(interaction=interaction)
        self._log_debug(f"after remove_due_to_prio(), queue status: [{', '.join([item.name for item in self.background_paint])}].")
        # In case we have anything from the same type waiting in the queue, we discard it first.
        #   Example: INITIAL_PHASE 3 is waiting, and we want to set INITIAL_PHASE 4.
        #   If we didn't show it yet, there is no point to keep waiting, the flow already went somewhere else.
        self._remove_duplicated_interaction_types_from_queue(interaction=interaction)
        self._log_debug(f"after remove_duplicated(), queue status: [{', '.join([item.name for item in self.background_paint])}].")
        # Now add the new interaction to the queue
        self.background_paint.append(interaction)

        self._log_debug(f"Background interaction queue after setting last: [{', '.join([item.name for item in self.background_paint])}].")

    def get_current_background_interaction(self) -> BackgroundPaint:
        current_background_paint = self.background_paint[0] if len(self.background_paint) > 0 else None
        if current_background_paint is None:
            return None
        return current_background_paint

    def remove_foreground_interaction(self, interaction: ForegroundPaint):
        self._log_debug(f"Foreground interaction [{interaction.name}] wants to be removed now.")
        if len(self.foreground_paint) > 0:
            if self.foreground_paint[0].name == interaction.name:
                self.foreground_paint.pop(0)
            else:
                self._log_debug(f"🛑 Foreground interaction [{interaction.name}] is not the current one. Skipping.")
                current_queue = ", ".join([item.name for item in self.foreground_paint])
                self._log_debug(f"Current foreground interaction queue: [{current_queue}].")
    
    def remove_all_foreground_interactions(self):
        self._log_debug("Removing all foreground interactions.")
        self.foreground_paint = []
    
    def remove_background_interaction(self, interaction: BackgroundPaint):
        self._log_debug(f"Background interaction [{interaction.name}] wants to be removed now.")
        if len(self.background_paint) > 0:
            if self.background_paint[0].name == interaction.name:
                self._log_debug(f"Removing background interaction: [{interaction.name}].")
                self.background_paint.pop(0)
            else:
                self._log_debug(f"🛑 Background interaction [{interaction.name}] is not the current one. Skipping.")
                # TODO: The logs show 2 times the same interaction when this happens. Not sure why.
                current_queue = ", ".join([item.name for item in self.background_paint])
                self._log_debug(f"Current background interaction queue: [{current_queue}].")
    
    def remove_all_background_interactions(self):
        self._log_debug("Removing all background interactions.")
        self.background_paint = []

    def remove_all_interactions(self):
        self._log_debug("Removing all interactions.")
        self.remove_foreground_interaction()
        self.remove_background_interaction()

    # -------- Methods for controlling and executing the thread / loop --------
    
    def start_or_resume_paint(self):

        # If we're actually not running anything inside the thread, do it now.
        if not self.is_running():
            self._log_debug("PainterLoop not running, starting painting loop now.")

            # Prepare the drawing tools outside the loop, so it's more efficient
            self.draw = self.macros.get_canvas().get_canvas(reset_base_image=False)

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

        self._xlog.debug("PainterLoop closed.")
    
    def flush_drawing(self):
        self.macros.get_device().display(self.macros.get_canvas().get_image())
    
    def is_running(self) -> bool:
        return self.running
    
    def should_thread_finish(self) -> bool:
        return self.should_finish

    def just_paint(self, foreground_interaction: ForegroundPaint = None, background_interaction: BackgroundPaint = None):

        # Set the interactions if provided
        if foreground_interaction is not None:
            self.set_foreground_interaction(foreground_interaction)
        if background_interaction is not None:
            self.set_background_interaction(background_interaction)

        # Start the painting loop
        self.start_or_resume_paint()
    
    def paint_into_foreground_while_speaking(self, foreground_interaction: ForegroundPaint):
        
        # 1. First we definethe start callback, that waits for the speaker to be busy and then sets the interactions
        # 2. Then we define the end callback to stop the painting when the speaker is not busy anymore
        # 3. Then we start the loop. It should wait until the speaker is busy to start painting, and then stop when it is not busy anymore.

        # Start callback definition: we want to paint when the speaker is busy
        start_callback = self._generate_callback(
            interaction=foreground_interaction,
            when=LOOP_START,
            channel=FOREGROUND_CHANNEL,
            flag_name=SHARED_SPEAKER_BUSY,
            for_value=True,
            extra_callback=lambda interaction=foreground_interaction: setattr(interaction, "is_expecting_end_callback", True)
        )
        # End callback definition: we want to stop painting when the speaker is not busy anymore
        end_callback = self._generate_callback(
            interaction=foreground_interaction,
            when=LOOP_END,
            channel=FOREGROUND_CHANNEL,
            flag_name=SHARED_SPEAKER_BUSY,
            for_value=False,
            extra_callback=lambda interaction=foreground_interaction: setattr(interaction, "is_expecting_end_callback", False)
        )
        
        # 1. Register the start callback
        self.painter_busy_flags.set_busy_flag_callback(when=LOOP_START, channel=FOREGROUND_CHANNEL, flag_name=SHARED_SPEAKER_BUSY, for_value=True, callback=start_callback)
        # 2. Register the end callback
        self.painter_busy_flags.set_busy_flag_callback(when=LOOP_END, channel=FOREGROUND_CHANNEL, flag_name=SHARED_SPEAKER_BUSY, for_value=False, callback=end_callback)
        # 3. Start the painting loop
        self.start_or_resume_paint()
    
    def paint_into_background_while_speaking(self, background_interaction: BackgroundPaint):
        
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
            extra_callback=lambda interaction=background_interaction: setattr(interaction, "is_expecting_end_callback", True)
        )
        # End callback definition: we want to stop painting when the speaker is not busy anymore
        end_callback = self._generate_callback(
            interaction=background_interaction,
            when=LOOP_END,
            channel=BACKGROUND_CHANNEL,
            flag_name=SHARED_SPEAKER_BUSY,
            for_value=False,
            extra_callback=lambda interaction=background_interaction: setattr(interaction, "is_expecting_end_callback", False)
        )
        
        # 1. Register the start callback
        self.painter_busy_flags.set_busy_flag_callback(when=LOOP_START, channel=BACKGROUND_CHANNEL, flag_name=SHARED_SPEAKER_BUSY, for_value=True, callback=start_callback)
        # 2. Register the end callback
        self.painter_busy_flags.set_busy_flag_callback(when=LOOP_END, channel=BACKGROUND_CHANNEL, flag_name=SHARED_SPEAKER_BUSY, for_value=False, callback=end_callback)
        # 3. Start the painting loop
        self.start_or_resume_paint()
    
    def paint_into_foreground_while_thinking(self, foreground_interaction: ForegroundPaint):
        
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
            extra_callback=lambda interaction=foreground_interaction: setattr(interaction, "is_expecting_end_callback", True)
        )
        # End callback definition: we want to stop painting when the speaker is not busy anymore
        end_callback = self._generate_callback(
            interaction=foreground_interaction,
            when=LOOP_END,
            channel=FOREGROUND_CHANNEL,
            flag_name=SHARED_CHATBOT_BUSY,
            for_value=False,
            extra_callback=lambda interaction=foreground_interaction: setattr(interaction, "is_expecting_end_callback", False)
        )
        
        # 1. Register the start callback
        self.painter_busy_flags.set_busy_flag_callback(when=LOOP_START, channel=FOREGROUND_CHANNEL, flag_name=SHARED_CHATBOT_BUSY, for_value=True, callback=start_callback)
        # 2. Register the end callback
        self.painter_busy_flags.set_busy_flag_callback(when=LOOP_END, channel=FOREGROUND_CHANNEL, flag_name=SHARED_CHATBOT_BUSY, for_value=False, callback=end_callback)
        # 3. Start the painting loop
        self.start_or_resume_paint()
    
    def paint_into_background_while_thinking(self, background_interaction: BackgroundPaint):
        
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
            extra_callback=lambda interaction=background_interaction: setattr(interaction, "is_expecting_end_callback", True)
        )
        # End callback definition: we want to stop painting when the speaker is not busy anymore
        end_callback = self._generate_callback(
            interaction=background_interaction,
            when=LOOP_END,
            channel=BACKGROUND_CHANNEL,
            flag_name=SHARED_CHATBOT_BUSY,
            for_value=False,
            extra_callback=lambda interaction=background_interaction: setattr(interaction, "is_expecting_end_callback", False)
        )
        
        # 1. Register the start callback
        self.painter_busy_flags.set_busy_flag_callback(when=LOOP_START, channel=BACKGROUND_CHANNEL, flag_name=SHARED_CHATBOT_BUSY, for_value=True, callback=start_callback)
        # 2. Register the end callback
        self.painter_busy_flags.set_busy_flag_callback(when=LOOP_END, channel=BACKGROUND_CHANNEL, flag_name=SHARED_CHATBOT_BUSY, for_value=False, callback=end_callback)
        # 3. Start the painting loop
        self.start_or_resume_paint()
    
    def paint_into_background_while_networking(self, background_interaction: BackgroundPaint):
        
        # 1. First we definethe start callback, that waits for the speaker to be busy and then sets the interactions
        # 2. Then we define the end callback to stop the painting when the speaker is not busy anymore
        # 3. Then we start the loop. It should wait until the speaker is busy to start painting, and then stop when it is not busy anymore.

        # Start callback definition: we want to paint when the speaker is busy
        start_callback = self._generate_callback(
            interaction=background_interaction,
            when=LOOP_START,
            channel=BACKGROUND_CHANNEL,
            flag_name=SHARED_NETWORK_BUSY,
            for_value=True,
            extra_callback=lambda interaction=background_interaction: setattr(interaction, "is_expecting_end_callback", True)
        )
        # End callback definition: we want to stop painting when the speaker is not busy anymore
        end_callback = self._generate_callback(
            interaction=background_interaction,
            when=LOOP_END,
            channel=BACKGROUND_CHANNEL,
            flag_name=SHARED_NETWORK_BUSY,
            for_value=False,
            extra_callback=lambda interaction=background_interaction: setattr(interaction, "is_expecting_end_callback", False)
        )
        
        # 1. Register the start callback
        self.painter_busy_flags.set_busy_flag_callback(when=LOOP_START, channel=BACKGROUND_CHANNEL, flag_name=SHARED_NETWORK_BUSY, for_value=True, callback=start_callback)
        # 2. Register the end callback
        self.painter_busy_flags.set_busy_flag_callback(when=LOOP_END, channel=BACKGROUND_CHANNEL, flag_name=SHARED_NETWORK_BUSY, for_value=False, callback=end_callback)
        # 3. Start the painting loop
        self.start_or_resume_paint()
    
    def paint_into_foreground_while_networking(self, foreground_interaction: ForegroundPaint):
        
        # 1. First we definethe start callback, that waits for the speaker to be busy and then sets the interactions
        # 2. Then we define the end callback to stop the painting when the speaker is not busy anymore
        # 3. Then we start the loop. It should wait until the speaker is busy to start painting, and then stop when it is not busy anymore.

        # Start callback definition: we want to paint when the speaker is busy
        start_callback = self._generate_callback(
            interaction=foreground_interaction,
            when=LOOP_START,
            channel=FOREGROUND_CHANNEL,
            flag_name=SHARED_NETWORK_BUSY,
            for_value=True,
            extra_callback=lambda interaction=foreground_interaction: setattr(interaction, "is_expecting_end_callback", True)
        )
        # End callback definition: we want to stop painting when the speaker is not busy anymore
        end_callback = self._generate_callback(
            interaction=foreground_interaction,
            when=LOOP_END,
            channel=FOREGROUND_CHANNEL,
            flag_name=SHARED_NETWORK_BUSY,
            for_value=False,
            extra_callback=lambda interaction=foreground_interaction: setattr(interaction, "is_expecting_end_callback", False)
        )
        
        # 1. Register the start callback
        self.painter_busy_flags.set_busy_flag_callback(when=LOOP_START, channel=FOREGROUND_CHANNEL, flag_name=SHARED_NETWORK_BUSY, for_value=True, callback=start_callback)
        # 2. Register the end callback
        self.painter_busy_flags.set_busy_flag_callback(when=LOOP_END, channel=FOREGROUND_CHANNEL, flag_name=SHARED_NETWORK_BUSY, for_value=False, callback=end_callback)
        # 3. Start the painting loop
        self.start_or_resume_paint()
    
    def paint_into_foreground_while_idle(self, foreground_interaction: ForegroundPaint):
        
        # 1. First we definethe start callback, that waits for the speaker to be busy and then sets the interactions
        # 2. Then we define the end callback to stop the painting when the speaker is not busy anymore
        # 3. Then we start the loop. It should wait until the speaker is busy to start painting, and then stop when it is not busy anymore.

        # Start callback definition: we want to paint when the speaker is busy
        start_callback = self._generate_callback(
            interaction=foreground_interaction,
            when=LOOP_START,
            channel=FOREGROUND_CHANNEL,
            flag_name=SHARED_IDLE_MODE,
            for_value=True,
            extra_callback=lambda interaction=foreground_interaction: setattr(interaction, "is_expecting_end_callback", True)
        )
        # End callback definition: we want to stop painting when the speaker is not busy anymore
        end_callback = self._generate_callback(
            interaction=foreground_interaction,
            when=LOOP_END,
            channel=FOREGROUND_CHANNEL,
            flag_name=SHARED_IDLE_MODE,
            for_value=False,
            extra_callback=lambda interaction=foreground_interaction: setattr(interaction, "is_expecting_end_callback", False)
        )
        
        # 1. Register the start callback
        self.painter_busy_flags.set_busy_flag_callback(when=LOOP_START, channel=FOREGROUND_CHANNEL, flag_name=SHARED_IDLE_MODE, for_value=True, callback=start_callback)
        # 2. Register the end callback
        self.painter_busy_flags.set_busy_flag_callback(when=LOOP_END, channel=FOREGROUND_CHANNEL, flag_name=SHARED_IDLE_MODE, for_value=False, callback=end_callback)
        # 3. Start the painting loop
        self.start_or_resume_paint()
    
    def paint_into_foreground_while_user_speaking(self, foreground_interaction: ForegroundPaint):
        
        # 1. First we definethe start callback, that waits for the speaker to be busy and then sets the interactions
        # 2. Then we define the end callback to stop the painting when the speaker is not busy anymore
        # 3. Then we start the loop. It should wait until the speaker is busy to start painting, and then stop when it is not busy anymore.

        # Start callback definition: we want to paint when the speaker is busy
        start_callback = self._generate_callback(
            interaction=foreground_interaction,
            when=LOOP_START,
            channel=FOREGROUND_CHANNEL,
            flag_name=SHARED_VAD_DETECTED,
            for_value=True,
            extra_callback=lambda interaction=foreground_interaction: setattr(interaction, "is_expecting_end_callback", True)
        )
        # End callback definition: we want to stop painting when the speaker is not busy anymore
        end_callback = self._generate_callback(
            interaction=foreground_interaction,
            when=LOOP_END,
            channel=FOREGROUND_CHANNEL,
            flag_name=SHARED_VAD_DETECTED,
            for_value=False,
            extra_callback=lambda interaction=foreground_interaction: setattr(interaction, "is_expecting_end_callback", False)
        )
        
        # 1. Register the start callback
        self.painter_busy_flags.set_busy_flag_callback(when=LOOP_START, channel=FOREGROUND_CHANNEL, flag_name=SHARED_VAD_DETECTED, for_value=True, callback=start_callback)
        # 2. Register the end callback
        self.painter_busy_flags.set_busy_flag_callback(when=LOOP_END, channel=FOREGROUND_CHANNEL, flag_name=SHARED_VAD_DETECTED, for_value=False, callback=end_callback)
        # 3. Start the painting loop
        self.start_or_resume_paint()
    
    
    def _generate_callback(self,
                           interaction: ForegroundPaint | BackgroundPaint,
                           when: str,
                           channel: str,
                           flag_name: int,
                           for_value: bool,
                           extra_callback: callable = None) -> callable:
        
        start_interaction_function = self.set_background_interaction if channel == BACKGROUND_CHANNEL else self.set_foreground_interaction
        end_interaction_function = self.remove_background_interaction if channel == BACKGROUND_CHANNEL else self.remove_foreground_interaction
        
        # callback_template for the loop start section
        def start_callback_template():
            self._log_debug(f"Painter [{when}] Callback for [{channel}]: [{self.painter_busy_flags._flag_string(flag_name)}] busy flag changed to [{for_value}], {"with" if extra_callback is not None else "without"} extra callback.")
            self._log_debug(f"Painter [{when}] Callback for [{channel}]: interaction.is_expecting_end_callback = {interaction.is_expecting_end_callback}.")

            info_to_return = {}

            # Set the interactions if provided
            if interaction is not None:
                start_interaction_function(interaction=interaction)
                # Remove the callback itself to avoid multiple triggers
                self.painter_busy_flags.remove_busy_flag_callback(when=LOOP_START, channel=channel, flag_name=flag_name, for_value=for_value)
                # Give the chance to execute an extra callback if provided
                if extra_callback is not None:
                    info_to_return["extra_callback_result"] = extra_callback()
            
            # Return any info if needed
            return info_to_return

        # callback_template for the loop end section
        def end_callback_template():
            self._log_debug(f"Painter [{when}] Callback for [{channel}]: [{self.painter_busy_flags._flag_string(flag_name)}] busy flag changed to [{for_value}], {"with" if extra_callback is not None else "without"} extra callback.")
            self._log_debug(f"Painter [{when}] Callback for [{channel}]: interaction.is_expecting_end_callback = {getattr(interaction, 'is_expecting_end_callback', 'N/A')}.")

            info_to_return = {}

            # Remove related interactions
            if interaction is not None and getattr(interaction, 'is_expecting_end_callback', False):
                end_interaction_function(interaction=interaction)
                # Remove the callbacks themselves
                self.painter_busy_flags.remove_busy_flag_callback(when=LOOP_END, channel=channel, flag_name=flag_name, for_value=for_value)
                # Any foreground interaction that we remove ALSO from callback, needs to restart the time counting for the maintain_paint_for_seconds logic.
                if isinstance(interaction, ForegroundPaint):
                    info_to_return["request_foreground_starting_time_reset"] = True
                # If we want to clear the screen at the end of the interaction, we can set a final callback here
                if interaction.final_screen_clearing:
                    # Be careful, a blank rectangle will override anything we had painted until now.
                    # Not suitable for ForegroundPaint and pretty dangerous for LOOP_START
                    self._log_debug(f"Painter [{when}] Callback for [{channel}]: Final Clearing intended, telling to painter loop")
                    # self.macros._soft_clear_rectangle(draw=self.draw)
                    info_to_return["final_clearing"] = True

                # Give the chance to execute an extra callback if provided
                if extra_callback is not None:
                    info_to_return["extra_callback_result"] = extra_callback()
            
            # Return any info if needed
            return info_to_return
        
        return start_callback_template if when == LOOP_START else end_callback_template

    def _remove_duplicated_interaction_types_from_queue(self, interaction: ForegroundPaint | BackgroundPaint):
        """
        Removes previous duplicated interactions of the same type as the given one from the corresponding queue.
        Keeps only the given interaction.

        Useful for schenarios like the init_phase when next phase comes and we didin't show the previous one.

        Args:
            interaction (ForegroundPaint | BackgroundPaint): The interaction to keep in the queue and search for previous same-types.
        """
        current_interaction = None
        if isinstance(interaction, ForegroundPaint):
            queue = self.foreground_paint
            current_interaction = self.get_current_foreground_interaction()
        else:
            queue = self.background_paint
            current_interaction = self.get_current_background_interaction()
        
        new_queue = []
        for item in queue:
            # Over the interactions with the same type, 
            if item.interaction == interaction.interaction:
                # We keep the current interaction being painted, to avoid fucking up the current painting loop iteration.
                # Unless it is explicitly defined.
                if current_interaction is not None and item.name == current_interaction.name and \
                    item.overwrite_current_interaction_with_same_type == False:
                    new_queue.append(item)
                # We keep the given interaction as parameter. This function is called at the moment of setting a new interaction,
                #   so we actually shouldn't end up here ever.
                elif item.name == interaction.name:
                    new_queue.append(item)
                # We skip adding the duplicated interaction to the new queue
                else:
                    self._log_debug(f"Removing previous duplicated interaction [{item.name}] of type [{item.interaction}] from the queue:.")
            # All the rest interaction types are kept.
            else:
                new_queue.append(item)
        
        if isinstance(interaction, ForegroundPaint):
            self.foreground_paint = new_queue
        else:
            self.background_paint = new_queue
    
    def _remove_previous_background_interactions_if_given_is_priority(self, interaction: BackgroundPaint):
        if interaction.interaction in self.PRIORITY_BACKGROUND_INTERACTIONS:
            self._log_debug(f"Background interaction [{interaction.name}] is priority. Removing previous background interactions from the queue.")
            self.remove_all_background_interactions()
    
    def apply_delay_between_frames(self, foreground_interaction: ForegroundPaint = None, background_interaction: BackgroundPaint = None):
        foreground_delay = None
        background_delay = None
        # Apply delay between frames according to the current interactions
        if foreground_interaction is not None and foreground_interaction.delay_between_frames is not None:
            foreground_delay = foreground_interaction.delay_between_frames
        if background_interaction is not None and background_interaction.delay_between_frames is not None:
            background_delay = background_interaction.delay_between_frames
        # We apply the minimum delay between both interactions
        min_delay = 0.0
        if foreground_delay is None and background_delay is None:
            min_delay = 0.0
        elif foreground_delay is None and background_delay is not None:
            min_delay = background_delay
        elif foreground_delay is not None and background_delay is None:
            min_delay = foreground_delay
        elif foreground_delay is not None and background_delay is not None:
            self._log_debug(f"Choosing background delay [{background_delay}] over foreground delay [{foreground_delay}] for delay between frames, besides taking the min().")
            # min_delay = min(foreground_delay, background_delay)
            min_delay = background_delay  # Prefer background delay over foreground delay
        if min_delay > 0.0:
            self._log_debug(f"Applying delay between frames of [{min_delay}] sec as: " +
                            f"{foreground_interaction.name + '(' + str(foreground_interaction.delay_between_frames) + ')' if foreground_interaction else 'None'} | " +
                            f"{background_interaction.name + '(' + str(background_interaction.delay_between_frames) + ')' if background_interaction else 'None'}")
            time.sleep(min_delay)

    def run(self):
        self._log_debug(f"Painter run(): 🟢 About to start the Painter's main thread loop.")

        try:

            # We need an overall loop that keeps the thread alive.
            # The close() method will set the should_finish flag to True, which will break this loop.
            while not self.should_thread_finish():

                # Each time we enter this loop, we reset the iteration counter.
                current_iteration = None

                # We calculate the showing time for the foreground paint from the first showing instant,
                #   so we depend on paint changes. Start with None.
                foreground_starting_time = None

                # Should do an extra screen clearing at the end of the current interaction?
                # It is set via the end-callbacks when registering painting while busy flags.
                final_clearing_needed = False

                # Keep track of what were the previous interactions, so we can try to avoid unnecessary drawings if the interactions didn't change.
                previous_foreground_interaction: ForegroundPaint = None
                previous_background_interaction: BackgroundPaint = None

                # We control the painting loop via the running flag.
                while self.is_running():

                    self._log_debug(f"Painter Loop: 🔄 Starting new painting loop iteration.")

                    self._log_debug(f"Painter Loop: Current interactions and busy flags status BEFORE triggering callbacks at START.")
                    self._log_debug(f"  - Current Foreground Interaction: [{self.get_current_foreground_interaction().name if self.get_current_foreground_interaction() is not None else 'None'}].")
                    self._log_debug(f"  - Current Background Interaction: [{self.get_current_background_interaction().name if self.get_current_background_interaction() is not None else 'None'}].")
                    self._log_debug(f"  - Callbacks at START pre-trigger [{", ".join(self.painter_busy_flags.get_registered_callbacks_list(when=LOOP_START))}].")
                    self._log_debug(f"  - Callbacks at END pre-trigger [{", ".join(self.painter_busy_flags.get_registered_callbacks_list(when=LOOP_END))}].")
                    self._log_debug(f"  - Busy Flags: ")
                    for busy_flag in self.painter_busy_flags.AVAILABLE_BUSY_FLAGS:
                        self._log_debug(f"    - {self.painter_busy_flags._flag_string(busy_flag)}: {self.painter_busy_flags.shared_memory.read_shared_memory_flag(int(busy_flag))}")

                    # Trigger any busy flag callbacks at the start of the loop
                    self.painter_busy_flags.trigger_busy_flags_callbacks_at_loop_start()

                    # Getting the current interactions one last time, to avoid gathering over and over again
                    current_foreground_interaction = self.get_current_foreground_interaction()
                    current_background_interaction = self.get_current_background_interaction()

                    self._log_debug(f"Painter Loop: Current interactions and busy flags status AFTER triggering callbacks at START.")
                    self._log_debug(f"  - Current Foreground Interaction: [{current_foreground_interaction.name if current_foreground_interaction is not None else 'None'}].")
                    self._log_debug(f"  - Current Background Interaction: [{current_background_interaction.name if current_background_interaction is not None else 'None'}].")
                    self._log_debug(f"  - Callbacks at START post-trigger [{", ".join(self.painter_busy_flags.get_registered_callbacks_list(when=LOOP_START))}].")
                    self._log_debug(f"  - Callbacks at END post-trigger [{", ".join(self.painter_busy_flags.get_registered_callbacks_list(when=LOOP_END))}].")
                    self._log_debug(f"  - Busy Flags: ")
                    for busy_flag in self.painter_busy_flags.AVAILABLE_BUSY_FLAGS:
                        self._log_debug(f"    - {self.painter_busy_flags._flag_string(busy_flag)}: {self.painter_busy_flags.shared_memory.read_shared_memory_flag(int(busy_flag))}")

                    # What if we try the whole drawing, starting by a clear screen?
                    if current_background_interaction is not None or current_foreground_interaction is not None:
                        self._log_debug(f"Painter Loop: Clearing screen on LCD display at the beginning of the loop.")
                        self.macros._soft_clear_rectangle(draw=self.draw, display_area="full_screen")
                    
                        # This is new from v0.4.2: The frame should always be here.
                        # The idea is that from now on, all interactions need to fit in the frame.
                        # The only exception is when we have nothing to paint.
                        foreground_frame_color = self.macros.get_canvas().COLOR_ORANGE
                        foreground_frame_opacity = 0.25
                        self.macros.draw_foreground_frame(
                                draw=self.draw, 
                                frame_color=foreground_frame_color, 
                                opacity=foreground_frame_opacity)
                        # ⚠️ Aparently, it paints forever, even we have nothing to paint.
                    
                    # We need to draw from background to foreground.
                    # At this point, LED effects are the most background, so we draw them first.
                    # Some of the LED effects are loops, so we need to handle the drawing via a frame iterations.
                    # And then flush to the display after drawing each frame fully.
                    self._log_debug(f"Painter Loop: 🔙 Drawing Background interactions")
                    if current_background_interaction is not None:

                        # Do we need to initialize the current iteration counter?
                        if current_iteration is None:
                            self._log_debug(f"Initializing iteration counter for background interaction [{current_background_interaction.name}]. Counter was None")
                            current_iteration = 0

                        if current_background_interaction.interaction == BackgroundComm.THINKING:
                            frame = current_iteration % (current_background_interaction.loop_iterations // 2)
                            if current_iteration < (current_background_interaction.loop_iterations // 2):
                                self._log_debug(f"Painter Loop: Drawing Thinking Right screen on LCD display, frame [{frame}].")
                                self.macros.draw_kitt_horizontal_effect_right(draw=self.draw, frame=frame)
                            else:
                                self._log_debug(f"Painter Loop: Drawing Thinking Left screen on LCD display, frame [{frame}].")
                                self.macros.draw_kitt_horizontal_effect_left(draw=self.draw, frame=frame)
                        elif current_background_interaction.interaction == BackgroundComm.NETWORKING:
                            frame = current_iteration % (current_background_interaction.loop_iterations // 2)
                            if current_iteration < (current_background_interaction.loop_iterations // 2):
                                self._log_debug(f"Painter Loop: Drawing Communicating Right screen on LCD display, frame [{frame}].")
                                self.macros.draw_kitt_horizontal_effect_right(draw=self.draw, frame=frame, color=self.macros.get_canvas().COLOR_BLUE)
                            else:
                                self._log_debug(f"Painter Loop: Drawing Communicating Left screen on LCD display, frame [{frame}].")
                                self.macros.draw_kitt_horizontal_effect_left(draw=self.draw, frame=frame, color=self.macros.get_canvas().COLOR_BLUE)
                        elif current_background_interaction.interaction == BackgroundComm.SPEAKING:
                            frame = current_iteration % (current_background_interaction.loop_iterations // 2)
                            if current_iteration < (current_background_interaction.loop_iterations // 2):
                                self._log_debug(f"Painter Loop: Drawing Speaking Increase screen on LCD display, frame [{frame}].")
                                self.macros.draw_kitt_speaking_effect_increase(draw=self.draw, frame=frame)
                            else:
                                self._log_debug(f"Painter Loop: Drawing Speaking Decrease screen on LCD display, frame [{frame}].")
                                self.macros.draw_kitt_speaking_effect_decrease(draw=self.draw, frame=frame)
                        elif current_background_interaction.interaction == BackgroundComm.INITIAL_PHASE:
                            self._log_debug(f"Painter Loop: Drawing Init Steps screen on LCD display")
                            # self.macros._soft_clear_rectangle(draw=self.draw)
                            self.macros.draw_init_phase(draw=self.draw, parameter=current_background_interaction.parameter)
                        elif current_background_interaction.interaction == BackgroundComm.HOLDER_PERCENTAGE:
                            self._log_debug(f"Painter Loop: Drawing Holder Percentage screen on LCD display")
                            self.macros.draw_interaction_holding_percentage(draw=self.draw, percentage=current_background_interaction.parameter)
                        elif current_background_interaction.interaction == BackgroundComm.ERROR:
                            self._log_debug(f"Painter Loop: Drawing Error screen on LCD display")
                            self.macros.draw_cross(draw=self.draw)
                        elif current_background_interaction.interaction == BackgroundComm.CLEAR:
                            # As opposite to foreground, we do clear the background because we may have to remove the previous paint.
                            self._log_debug(f"Painter Loop: Clearing background interaction on LCD display")
                            # self.macros._soft_clear_rectangle(draw=self.draw)
                        else:
                            self._xlog.warning(f"Painter: Unknown interaction [{current_background_interaction.interaction}] for drawing on LCD display, discarding.")
                        
                        # Increment the iteration counter
                        current_iteration += 1

                        # If we have reached the max iterations for background, we set the iterations counter to None.
                        #   Then, the next loop iteration will re-initialize it to 0 again.
                        # This means that this loop will go forever until we stop the thread or change/remove the background interaction.
                        if current_iteration >= current_background_interaction.loop_iterations:
                            self._log_debug(f"Reached max iterations for background interaction [{current_background_interaction.name if current_background_interaction is not None else 'None'}], Cleaning the counter.")
                            current_iteration = None

                    # There are no loops for foreground interactions yet, so we just draw them once.
                    # - We may not receive any foreground interaction.
                    # - We may want to hold this paint for X time. Therefore, we avoid repainting during that time.
                    #       Keep in mind that this ignores new possible foregrounds to show meanwhile.
                    self._log_debug(f"Painter Loop: 🔝 Drawing Foreground interactions")
                    if current_foreground_interaction is not None:

                        # We have a foreground paint. Is it the first loop iteration to see it?
                        if foreground_starting_time is None:
                            # It was, so we set the starting time and then we control how much it is getting shown.
                            self._log_debug(f"Painter: New foreground paint detected: [{current_foreground_interaction.name}], starting to show it now.")
                            foreground_starting_time = Xtime.now_as_milliseconds()

                        # Because we may have painted anything related to the background first, we need to paint again the foreground over it.
                        # That's why, even a flushed image stays until changed, we need to keep on repainting it.
                    
                        # Now the expected interactions.
                        if current_foreground_interaction.interaction == ForegroundComm.STARTUP:
                            self._log_debug("Painter Loop: Drawing startup splash screen on LCD display.")
                            self.macros.draw_startup_splash(draw=self.draw)
                        elif current_foreground_interaction.interaction == ForegroundComm.STARTUP_WITH_PHASE:
                            self._log_debug("Painter Loop: Drawing startup with phase screen on LCD display.")
                            # self.macros.draw_foreground_init_phase(draw=self.draw, parameter=current_foreground_interaction.parameter)
                            self.macros.draw_combined_init_phase(draw=self.draw, parameter=current_foreground_interaction.parameter)
                        elif current_foreground_interaction.interaction == ForegroundComm.ARBITRARY_TEXT:
                            self._log_debug("Painter Loop: Drawing arbitrary text on LCD display.")
                            self.macros.draw_arbitrary_text_centered(draw=self.draw, text=current_foreground_interaction.parameter)
                        elif current_foreground_interaction.interaction == ForegroundComm.ARBITRARY_TEXT_ICON:
                            self._log_debug("Painter Loop: Drawing arbitrary text with icon on LCD display.")
                            self.macros.draw_arbitrary_text_with_icon(draw=self.draw, 
                                                                text=current_foreground_interaction.parameter.get("text"),
                                                                icon=current_foreground_interaction.parameter.get("icon"),
                                                                font_size=current_foreground_interaction.parameter.get("font_size", 24),
                                                                header=current_foreground_interaction.parameter.get("header"),
                                                                font_header_size=current_foreground_interaction.parameter.get("font_header_size", 32),
                                                                padding=current_foreground_interaction.parameter.get("padding", 5))
                        elif current_foreground_interaction.interaction == ForegroundComm.ARBITRARY_ICON:
                            self._log_debug("Painter Loop: Drawing arbitrary icon on LCD display.")
                            self.macros.draw_arbitrary_icon(draw=self.draw,
                                                            icon=current_foreground_interaction.parameter.get("icon"),
                                                            text=current_foreground_interaction.parameter.get("text", None),
                                                            color=current_foreground_interaction.parameter.get("color", None)),

                        elif current_foreground_interaction.interaction in [ForegroundComm.CODE_BLOCK, ForegroundComm.TEXT_BLOCK]:
                            # First we want to paint an overall frame for them.
                            foreground_frame_color = self.macros.get_canvas().COLOR_WHITE
                            foreground_frame_opacity = 0.75
                            self.macros.draw_overall_full_frame(
                                draw=self.draw, 
                                frame_color=foreground_frame_color, 
                                opacity=foreground_frame_opacity)
                            # And now we paint what we're meant to.
                            if current_foreground_interaction.interaction == ForegroundComm.CODE_BLOCK:
                                self._log_debug("Painter Loop: Drawing code block on LCD display.")
                                self.macros.draw_code_block(draw=self.draw, text=current_foreground_interaction.parameter.get("text", ""))
                            elif current_foreground_interaction.interaction == ForegroundComm.TEXT_BLOCK:
                                self._log_debug("Painter Loop: Drawing text block on LCD display.")
                                self.macros.draw_text_block(draw=self.draw, text=current_foreground_interaction.parameter.get("text", ""))

                        elif current_foreground_interaction.interaction == ForegroundComm.CLEAR:
                            # If we need to clear the foreground, actualy we use the iteration to draw nothing.
                            # this is because if we clean the foreground, we may loose the background that was painted before.
                            self._log_debug("Painter Loop: Clearing foreground interaction on LCD display: Drawing nothing.")
                            # self.macros._soft_clear_rectangle(draw=self.draw)
                        else:
                            self._xlog.warning(f"Painter: Unknown interaction [{current_foreground_interaction.interaction}] for drawing on LCD display, discarding.")
                        
                        # We may have reached the end of the foreground paint showing time.
                        # We now allow new foregrounds to be painted. This is useful when the expected time for a foreground is shorter than
                        #   the background showing time. We can show the next foreground paint.
                        if Xtime.now_minus_seconds_as_milliseconds(current_foreground_interaction.maintain_paint_for_seconds) > foreground_starting_time and\
                            not current_foreground_interaction.ignore_maintain_time:
                            # If we remove the foreground we may loose the one that may have been set while showing the previous interaction, so no.
                            # The start of the foreground_starting_time must happen at the beginning of the loop's iteration
                            #   so we start with a new paint.

                            self._log_debug(f"Painter: Foreground interaction [{current_foreground_interaction.name}] showing time of " +
                                            f"[{current_foreground_interaction.maintain_paint_for_seconds}] elapsed, requesting remove.")
                            self._log_debug(f"Painter: Foreground interaction ignore time is [{'INGONE' if current_foreground_interaction.ignore_maintain_time else 'NOT IGNORE'}]")
                            self._log_debug(f"Painter: Initial time was [{foreground_starting_time}], current time is [{Xtime.now_as_milliseconds()}]," +
                                            f" diff is [{(Xtime.now_as_milliseconds() - foreground_starting_time) / 1000}]sec.")

                            # What we do here is to set it to None so that the IF at the beginning of the iteration knows that it needs to be started.
                            foreground_starting_time = None

                            # And remove the current foreground paint, so we can pick the next.
                            self.remove_foreground_interaction(interaction=current_foreground_interaction)

                    
                    self._log_debug(f"Painter Loop: ⏹️ End section: Flushing, delays and cleaning up.")

                    # A final clearing was requested by a callback at the end of the previous loop iteration?
                    if final_clearing_needed:
                        self._log_debug(f"Painter Loop: Final clearing requested by an END callback, will clear the screen.")
                        self.macros._soft_clear_rectangle(draw=self.draw, display_area="full_screen")
                        final_clearing_needed = False

                    # Show the image on the device
                    self._log_debug(f"Painter: Flushing drawing to LCD display: ")
                    self._log_debug(f"  - Foreground is {current_foreground_interaction.name if current_foreground_interaction is not None else 'None'}.")
                    self._log_debug(f"  - Background is {current_background_interaction.name if current_background_interaction is not None else 'None'}.")
                    self.flush_drawing()

                    # Wait for the specified delay between iterations
                    self.apply_delay_between_frames(
                        foreground_interaction=current_foreground_interaction,
                        background_interaction=current_background_interaction)

                    # If we had a request to clean the background after the full painting is done, we do it now.
                    # ATTENTION: Overriding this rule if we have a foreground paint ongoing, as it continues to redraw
                    #   and then we would loose the background while foreground is still being shown.
                    if current_background_interaction is not None and \
                        current_background_interaction.remove_interaction_after_painting is True and \
                        current_foreground_interaction is None:

                        self._log_debug(f"Painter: Removing background interaction [{current_background_interaction.name}] after full painting is done.")
                        self.remove_background_interaction(interaction=current_background_interaction)
                    
                    # If the list of background interactions contains more than the current item, we remove the current one to move to the next.
                    # This should override the request to avoid removing at the end of the painting.
                    # The only exception is the speaking, that should be kept ALWAYS while speaking.
                    # It's an else-if because we may have just removed it in the previous IF.
                    elif current_background_interaction is not None and \
                        len(self.background_paint) > 1 and current_background_interaction.interaction != BackgroundComm.SPEAKING:
                        previous_background_interaction_name = current_background_interaction.name
                        self.remove_background_interaction(interaction=current_background_interaction)
                        # We do not want to replace the current_background_interaction variable, as we may need it later until the end of the loop.
                        # It is just for the logging.
                        new_current_background_interaction = self.get_current_background_interaction()
                        self._log_debug(f"Painter: More than one background interaction in the queue, removing current background interaction [{previous_background_interaction_name}] to move to next: [{new_current_background_interaction.name}].")
                        # We may have other things to delete too.
                        if current_background_interaction.interaction in self.BACKGROUND_TO_BUSY_FLAG.keys():
                            if self.painter_busy_flags.callback_exists_for_busy_flag(when=LOOP_START, channel=BACKGROUND_CHANNEL, flag_name=self.BACKGROUND_TO_BUSY_FLAG[current_background_interaction.interaction], for_value=True):
                                self.painter_busy_flags.remove_busy_flag_callback(when=LOOP_START, channel=BACKGROUND_CHANNEL, flag_name=self.BACKGROUND_TO_BUSY_FLAG[current_background_interaction.interaction], for_value=True)
                            if self.painter_busy_flags.callback_exists_for_busy_flag(when=LOOP_END, channel=BACKGROUND_CHANNEL, flag_name=self.BACKGROUND_TO_BUSY_FLAG[current_background_interaction.interaction], for_value=False):
                                self.painter_busy_flags.remove_busy_flag_callback(when=LOOP_END, channel=BACKGROUND_CHANNEL, flag_name=self.BACKGROUND_TO_BUSY_FLAG[current_background_interaction.interaction], for_value=False)
                    
                    # If we had a request to remove the foreground after the painting, we do it now,
                    #   just in case we didn't remove it yet
                    #   (we know it's removed if foreground_starting_time is None, because it's reset
                    #   when the current_foreground_interaction.maintain_paint_for_seconds is exceeded).
                    # Attention: needs to be BEFORE the end callbacks, because when the end callbacks are triggered,
                    #   they may request to restart the foreground_starting_time, so this IF would not fit.
                    if current_foreground_interaction is not None and \
                        current_foreground_interaction.remove_interaction_after_painting is True and \
                        foreground_starting_time is None:

                        # Before removing it, check if it also included a final screen clearing.
                        if current_foreground_interaction.final_screen_clearing:
                            self._log_debug(f"Painter: Foreground interaction [{current_foreground_interaction.name}] included a final screen clearing, telling to painter loop.")
                            final_clearing_needed = True

                        # And now we can safely remove the foreground interaction.
                        self._log_debug(f"Painter: Removing foreground interaction [{current_foreground_interaction.name}] after painting as requested.")
                        self.remove_foreground_interaction(interaction=current_foreground_interaction)
                    
                    # Check the busy flags and call their callbacks if needed
                    callback_results = self.painter_busy_flags.trigger_busy_flags_callbacks_at_loop_end()

                    # Check if any of the callbacks requested a final clearing of the screen
                    for callback_result in callback_results:
                        if callback_result.get("final_clearing", False):
                            final_clearing_needed = True
                        if callback_result.get("request_foreground_starting_time_reset", False):
                            if foreground_starting_time is None:
                                self._xlog.warning(f"🟠 Painter: A callback requested a reset of the foreground starting time, but was already 'None'")
                            self._log_debug(f"Painter: A callback requested a reset of the foreground starting time, resetting it to current time.")
                            foreground_starting_time = None
                    
                    # Finally, if there is no foreground nor background paint, we can stop the loop.
                    # Please note that here we're not using the current_background_interaction variable directly,
                    #   but rather calling the getter method to ensure we're getting the latest state.
                    # Also, we should not stop the loop if there are callbacks still registered, as apparently
                    #   they were set but never triggered, and by stopping the loop these callbacks would never be called
                    #   (for example, due to a busy flag change)
                    # Also, we let one iteration more to happen if the end callbacks wanted to do a final clearing of the screen,
                    #   that needs to happen before we flush the canvas.
                    if self.get_current_foreground_interaction() is None and self.get_current_background_interaction() is None and \
                        len(self.painter_busy_flags.get_registered_callbacks_list(when=LOOP_START)) == 0 and \
                        len(self.painter_busy_flags.get_registered_callbacks_list(when=LOOP_END)) == 0 and \
                        not final_clearing_needed:

                        self._log_debug("No foreground nor background paints nor callbacks nor screen clears remaining, stopping the painting loop.")
                        self.stop()
                    
                    # If we only have a foreground paint, reduce the speed of the loop to avoid burning the CPU for example.
                    # Please note that here we're not using the current_background_interaction variable directly,
                    #   but rather calling the getter method to ensure we're getting the latest state.
                    if self.get_current_foreground_interaction() is not None and self.get_current_background_interaction() is None:

                        self._log_debug("Only foreground paint remaining, applying extra delay.")
                        time.sleep(0.5)

        except KeyboardInterrupt:
            self._xlog.debug("Pressed Control + C while running Painter loop.")
            os.kill(os.getpid(), signal.SIGTERM)