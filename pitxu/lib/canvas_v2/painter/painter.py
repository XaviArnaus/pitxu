import logging
import time

from pyxavi import Config, Dictionary
from pitxu.lib.abstract.pyxavi import PyXavi

from pitxu.lib.canvas_v2.canvas import Canvas
from pitxu.lib.canvas_v2.painter.painter_shared_memory import PainterSharedMemory
from pitxu.lib.canvas_v2.painter.paint_object import PaintObject, BasePaint, FramedPaint, AnimationPaint
from pitxu.lib.canvas_v2.painter.painting_command import PaintingCommand
from pitxu.lib.canvas_v2.painter.painter_queue import PainterQueue
from pitxu.lib.canvas_v2.painter.painter_area import PainterArea
from pitxu.lib.canvas_v2.painter.painter_timings import PainterTimings

from pitxu.lib.objects.point import Point
from pitxu.lib.objects.rectangle import Rectangle

import threading
from PIL import Image, ImageDraw

class IntermediatePainterQueueAction:
    """
    This class is meant to control the actions to be done in by every item in the intermediate queue.
    """
    SET: str = "set"
    REMOVE: str = "remove"

class Painter(PyXavi):
    """
    This class performs the hard work of painting, using given canvas and macros for tools.
    The painting itself is done in a separate thread.

    The flow is the following:

    1. We receive the painting object to paint, with the interactions to paint in each area (Foreground, Background, Overall).
        - This contains: 
            - name (to use to compare dupes), 
            - interaction (the PaintingCommand to paint, for identification purposes)
            - parameter (the parameter to paint, for example the text to show)
            - drawing_callback (the callback to trigger to draw the interaction, 
                so the Painter is agnostic of how to draw it, read as "the macros related method")
            - while_shared_memory_flag and while_shared_memory_flag_value 
                (optional, if provided, it will trigger the painting of this interaction 
                only when the shared memory flag is in the desired value, and will trigger its removal 
                when it changes to any other value)
            - other parameters to control how to show the interaction.

    2. We add the interactions to the corresponding queue, with some logic to manage the dupe interactions.
        - If we receive while_shared_memory_flag and while_shared_memory_flag_value, we register a pair of callbacks that
            basically are start_painting_callback (for the given paint in the given shared memory info) 
            and stop_painting_callback (for the given paint in the opposite value of the given shared memory info)
        - The queues are basically lists of interactions to paint, but they also have some logic to manage the dupe interactions:
        - If we receive an interaction with the same type as another one already in the queue, we remove the previous one,
            to avoid having several interactions of the same type waiting to be painted, which doesn't make sense (for example,
            in the Init Phases, the changes are too quick, and makes no sense to paint an older status). This may have to be
            revisited when we have a status log, because we want to add/show them all anyways.

    3. We then trigger or resume the painting loop.
        - It takes the first in the queue and paint it using the corresponding macros callback.
        - There are loop mecanisms to control how the interactions are painted.
        - If an interaction does not get removed from the queue, it gets painted in the next loop iteration.
            - The control of this behaviour relies in the paint object parameters.
        - When a shared memory flag changes, it will trigger the corresponding callback (which is to add/remove the interaction to the queue)
          AND also trigger the painting loop.
            - This means that the shared memory flag changes behave like a waiting room for interactions to be set/removed from the
                painting loop, which is pretty neat.
    
    4. All painted objects that are drawn should be kept in a cache (the draw canvas object?) so that if we have to paint
        exactly the same again (check parameters!!) then we just simply show the cached one. This should improve the performance
        at memory expenses.
        - Clean the draw related to the given paint when we remove the paint from the queue.
        - What we want to avoid is the same paint in every loop iteration of the same interaction,
            but if the same paint is requested time later, we'll repaint it.
    """

    _worker_thread: threading.Thread = None
    _thread_event: threading.Event = None

    # Set by the maintain-time timers. Only the loop thread consumes it: the timers must never touch the canvas.
    _blank_screen_pending: bool = False
    # True while the screen is deliberately blank. Only the loop thread touches it.
    # It is set when a blank is requested and cleared by the next flush of a drawing.
    _screen_is_blank: bool = False
    # Serialises resume_paint(), which is called from the shared memory worker, the timers and the loop itself.
    _resume_lock: threading.Lock = None

    THREAD_NAME: str = "Painter"

    # Controls if the loop should work. Set to False to exit the loop and finish the thread.
    is_active: bool = True

    canvas: Canvas = None
    # The callbacks defined on the caller regarding the frames to draw
    drawing_callbacks: dict[str, dict[str, any]] = None
    # The layout info, to know the sizes for the sub-canvases to paint the interactions.
    layout_info: dict[str, dict[str, Rectangle]] = None
    # The areas of the screen, one per queue, in painting order.
    # The idea is that we register the interactions to paint in the queue of each area (area.paints),
    #   and the Painter loop will consume them and paint them.
    # Each area also knows its position in the layout and its rules (exception commands, slowing down the loop).
    areas: dict[str, PainterArea] = None

    # This is the queue for the interactions to be set or removed, so we do it in a controlled way inside the painting loop.
    intermediate_interactions_queue: list[tuple[IntermediatePainterQueueAction, PainterQueue, BasePaint]] = []

    # This class controls the transitions of the shared memory flags and values in a separate thread.
    #   and triggers callbacks when it happens.
    painter_shared_memory: PainterSharedMemory = None

    VERBOSE_DEBUG: bool = False

    def __init__(self, config: Config, params: Dictionary):
        super(Painter, self).init_pyxavi(config, params)

        # We need the definition of the queues to play with, and where each one is in the layout.
        if not params.key_exists("painter_queues"):
            raise ValueError("'painter_queues' parameter is required for Painter.")
        if not params.key_exists("layout_position_to_queue_name"):
            raise ValueError("'layout_position_to_queue_name' parameter is required for Painter.")
        queue_names = params.get("painter_queues")
        queue_name_to_layout_position = {v: k for k, v in params.get("layout_position_to_queue_name").items()}

        # We may (or may not) have exceptions for the end of the loop
        exception_loop_interactions = params.get("painter_exception_loop_interactions", {})
        # Maybe we have some queues that when they have paints (and the others not), make the loop to slow down, to avoid burning the CPU.
        queues_that_slow_down_the_loop = params.get("painter_queues_with_paints_that_slow_down_the_loop", [])

        # A name that is not a queue is a typo: better to know it now than when it is used.
        for param_name, names in (
            ("painter_exception_loop_interactions", exception_loop_interactions.keys()),
            ("painter_queues_with_paints_that_slow_down_the_loop", queues_that_slow_down_the_loop),
        ):
            unknown_names = [name for name in names if name not in queue_names]
            if unknown_names:
                raise ValueError(f"'{param_name}' has queues that are not in 'painter_queues': {unknown_names}.")

        # One area per queue, in painting order. Created per instance, so it is never shared.
        self.areas = {}
        for queue_name in queue_names:
            if queue_name not in queue_name_to_layout_position:
                raise ValueError(f"The queue [{queue_name}] has no position in 'layout_position_to_queue_name'.")
            self.areas[queue_name] = PainterArea(
                name=queue_name,
                layout_position=queue_name_to_layout_position[queue_name],
                exception_loop_commands=exception_loop_interactions.get(queue_name, []),
                slows_down_loop=queue_name in queues_that_slow_down_the_loop)

        if params.key_exists("canvas"):
            self.canvas = params.get("canvas")
        else:
            raise ValueError("'canvas' parameter is required by the Painter.")
        
        if params.key_exists("drawing_callbacks"):
            self.drawing_callbacks = params.get("drawing_callbacks")
        else:
            raise ValueError("'drawing_callbacks' parameter is required for Painter.")
        
        if params.key_exists("layout_info"):
            self.layout_info = params.get("layout_info")
        else:
            raise ValueError("'layout_info' parameter is required for Painter.")

        # The screen is composed only for what changed, as long as the canvas still has what was composed last time.
        # Anything that clears the canvas (or the display, from outside) makes it not valid, and the next one is a whole one.
        self._screen_valid: bool = False
        self._composed_image: Image.Image | None = None
        # Debug: compose the whole screen apart on every partial one, compare, and log (and fix) if they differ.
        self._verify_partial: bool = bool(self._xconfig.get("dsi_lcd.painter.verify_partial", False))
        # To go back to the whole screen every time (as before partial composition): dsi_lcd.painter.partial_composition: False
        self._partial_composition: bool = bool(self._xconfig.get("dsi_lcd.painter.partial_composition", True))

        # Where the time of the loop goes. Off unless the config asks for it, then it costs nothing.
        self.timings = PainterTimings(
            enabled=bool(self._xconfig.get("dsi_lcd.painter.timing_log", False)),
            log_callback=lambda title, lines: self.log_summary(title, lines, log_level=logging.INFO),
            interval=float(self._xconfig.get("dsi_lcd.painter.timing_log_interval", 10.0)))

        # Before setting the worker, we create the event.
        self._thread_event = threading.Event()

        self._resume_lock = threading.Lock()

        # Here is the Painter thread.
        self._worker_thread = threading.Thread(
            name=self.THREAD_NAME,
            target=self._paint_worker,
            args=(self._thread_event,),
            daemon=True)
        
        # We start the thread in paused mode, so it doesn't start working until we have something to paint.
        self.start_paused()

        # Initialize the queue that is used to set and remove interactions in a controlled way.
        self.intermediate_interactions_queue = []

        # Initialized, but we need to set up the callbacks per each flag to monitor.
        painter_shared_memory_params = Dictionary({
            "shared_memory": params.get("shared_memory"),
            "painter_resume_callback": self.resume_paint
        })
        self.painter_shared_memory = PainterSharedMemory(self._xconfig, painter_shared_memory_params)

        self._xlog.debug("Initialized Painter.")
    
    def paint(self, painting_object: PaintObject):
        """
        The main method to call to paint something.
        """

        for queue_name, paint in painting_object.get_all_paints_by_queue().items():
            # We add the painting object to the corresponding queue, and the loop will consume it and paint it.
            if paint.while_shared_memory_flag is not None and paint.while_shared_memory_flag_value is not None:                
                self._log_debug(f"Painting object [{paint.name}] has a shared memory flag condition: flag [{self._get_shared_memory_flag_name_for(paint.while_shared_memory_flag)}] must be [{paint.while_shared_memory_flag_value}] to be painted.")
                # We're meant to register the callbacks to trigger and clean the interaction based on the shared memory flag value.
                self._register_callbacks_for_shared_memory_flag(
                    paint.while_shared_memory_flag, 
                    paint.while_shared_memory_flag_value, 
                    paint,
                    queue_name
                )
            else:
                self.add_to_intermediate_queue(paint, queue_name, IntermediatePainterQueueAction.SET)
        
        # Start the painting loop
        self.resume_paint()
    
    # ------------------------------>
    #         Painter Loop
    # ------------------------------>
    def _paint_worker(self, event):
        """
        The Painter loop.
        Gets triggered when anything needs to be painted, loops until the work is done, and then finishes.
        """
        self._log_debug(f"Painter _paint_worker(): 🟢 About to start the Painter's main thread loop.")

        try:

            # Should do an extra screen clearing at the end of the current interaction?
            # It is set via the end-callbacks when registering painting while busy flags.
            final_clearing_needed = False

            # The painting loop
            while self.is_active:
                # The big difference with the previous approach is that we do not check the shared memory flags
                # per iteration. It has its own worker in the PainterSharedMemory class that triggers
                # the registration or unregistration of the interactions to paint, and then triggers the painting loop when it happens.
                # this should reduce the painting loop iterations drastically, and make it more simple and efficient, 
                # because we only paint when we actually have to, not checking the flags every time.

                # We wait here until we resume() the paint.
                # This is the actual PAUSE for the loop, RESUMED from outside by calling resume_paint(),
                # which is triggered when we receive a new painting object to paint, 
                # or when a shared memory flag changes that affects the interactions to paint.
                event.wait()

                self.timings.iteration_start()
                drew = False
                paused_now = False

                self._log_debug(f"🎨 1️⃣ Starting new painting loop iteration.")

                # The very first thing to do is to apply the pending interactions to set or remove that we have in the intermediate queue,
                # which are triggered by the shared memory flags callbacks or other events.
                self.process_intermediate_queue()

                # A timed paint was removed: the screen must end up blank if nothing else is drawn.
                blank_requested = self._blank_screen_pending
                self._blank_screen_pending = False
                # From here on, passive paints (like the buttons) can't wake the screen up until something else is drawn.
                if blank_requested:
                    self._screen_is_blank = True

                # This is just some logging at the beginning of the loop iteration.
                self._logging_start_painter_loop_iteration()

                # Only work if we have anything to paint.
                with self.timings.measure("decide"):
                    should_draw = self._should_draw_this_loop_iteration()
                if should_draw:
                    drew = True

                    # Get the current iterations to draw, if they exist.
                    # The order matters: we need to paint from bottom layer to upper layer.
                    current_interaction_by_queue: dict[PainterQueue, BasePaint | None] = {
                        queue_name: self.get_current_interaction(queue_name) for queue_name in self.areas.keys()
                    }

                    # What every area puts on the screen in this iteration, in painting order: its image (None for nothing)
                    #   and a token that says which picture it is. The areas only PREPARE their image here, the screen is
                    #   composed afterwards, so it can be done only for the part of the screen that changed.
                    contributions: dict[PainterQueue, tuple[Image.Image | None, tuple]] = {}

                    # We prepare the interactions in order, from background to overall.
                    for queue_name in self.areas.keys():
                        current_interaction: BasePaint | None = current_interaction_by_queue[queue_name]

                        # Do we have anything to paint in this queue?
                        if current_interaction is None:

                            # Only in the case that we have nothing to paint, we need to at least show an empty soft frame,
                            #  to avoid having lost empty spaces in the layout. It is made once, and kept.
                            # Also, ignore OVERALL!
                            if queue_name == PainterQueue.OVERALL:
                                self._log_debug(f"🎨 Nothing to paint in queue [{queue_name}].")
                                contributions[queue_name] = (None, ("nothing",))
                            else:
                                self._log_debug(f"🎨 Nothing to paint in queue [{queue_name}]. Using the empty frame to keep the layout.")
                                with self.timings.measure(f"empty_frame:{queue_name}"):
                                    contributions[queue_name] = (self._empty_image_for_queue(queue_name), ("empty",))

                        else:
                            self._log_debug(f"🎨 Painting interaction [{current_interaction.name}] from queue [{queue_name}].")

                            # Pre-painting loop actions.
                            if isinstance(current_interaction, FramedPaint):
                                # The area knows which frame of the paint is the one to draw now: the next one if it is due, or
                                #   the same as before if it is not (then the cache gives the drawing back).
                                frame = self.areas[queue_name].frame_for(current_interaction, time.monotonic())
                                current_interaction.current_loop_iteration = frame

                                # The frame needs to be added into the parameters of the drawing callback, so we update them here.
                                # The max iteration counter is set by the caller when it creates the painting object.
                                # The internal callback will take it and calculate which frame to show based on it.
                                # Note: The cache key is build using the param on the callback, not the attributes on the Paint object.
                                if current_interaction.drawing_callback_parameters is None:
                                    current_interaction.drawing_callback_parameters = {}
                                current_interaction.drawing_callback_parameters["current_loop_iteration"] = frame
                                current_interaction.drawing_callback_parameters["max_loop_iterations"] = current_interaction.loop_iterations

                            # Parameters that must be read live on every iteration (e.g. a level from the shared memory).
                            # They go into the drawing parameters before the cache key is built from them.
                            for param_name, param_provider in current_interaction.dynamic_parameters.items():
                                current_interaction.drawing_callback_parameters[param_name] = param_provider()

                            # --- START painting the interaction, with cache support ---

                            self._log_debug(f"🎨 2️⃣ Actual painting section.")

                            # We check if we have already painted this interaction in the previous iteration, and if so, we retrieve it from the cache.
                            # If not, we trigger the drawing callback to paint it, and then store it in the cache.
                            interaction_image = self._draw_or_retrieve_from_cache(current_interaction, queue_name)

                            # The token is the version of the drawing in the cache: if it did not change, it is the same picture.
                            contributions[queue_name] = (interaction_image, ("paint", self.areas[queue_name].cache_version))

                            # --- END painting the interaction ---

                            # Post-painting loop actions.
                            if isinstance(current_interaction, FramedPaint):

                                # If we have reached the last frame, the area makes the next one start again at 0.
                                # This means that this loop will go forever until we stop the thread or change/remove the interaction.
                                if self.areas[queue_name].finish_frame(current_interaction):
                                    self._log_debug(f"🎨 Reached the last frame of interaction [{current_interaction.name}] in queue [{queue_name}], the next one starts again.")

                    self._log_debug(f"🎨 3️⃣ Flushing, and delays")

                    # Could be that any removal callback requests a final clearing. 
                    # We need to read it from the requests, remove it from there, and apply it if any is True.
                    # Attention, it is not meant as a full screen clearing, but per queue.
                    callback_final_screen_clearing_request = False
                    queues_to_clear: list[PainterQueue] = []
                    for queue_name in self.areas.keys():
                        # Taking the requests consumes them, to avoid carrying them on into the next loop iteration.
                        callback_final_area_clearing_request = False
                        for callback_name in self.areas[queue_name].take_area_clearing_requests():
                            callback_final_area_clearing_request = True
                            self._log_debug(f"🎨 Callback [{callback_name}] for queue [{queue_name}] requested a final clearing of the area.")
                        for callback_name in self.areas[queue_name].take_screen_clearing_requests():
                            callback_final_screen_clearing_request = True
                            self._log_debug(f"🎨 Callback [{callback_name}] for queue [{queue_name}] requested a final clearing of the screen.")
                        if callback_final_area_clearing_request:
                            # TRANSITION FIX (bugfix/transition-fails-when-user-interacts-too-quickly):
                            # The final clearing wipes the last frame of the interaction that was just removed
                            #   (like the last phase of the speaking effect).
                            # But when there is already a replacement waiting in that queue (like the holding bar queued
                            #   behind the speaking effect), it has been painted in THIS iteration, after the full clear
                            #   at the top, so there is no old frame to wipe. Wiping it would erase the new paint, and as
                            #   its cache key does not change the Painter would not draw it again: blank area until the next change.
                            if current_interaction_by_queue[queue_name] is not None:
                                self._log_debug(f"🎨 Skipping the final clearing of the area of [{queue_name}]: [{current_interaction_by_queue[queue_name].name}] has just replaced the removed interaction.")
                            else:
                                queues_to_clear.append(queue_name)

                    # A final clearing was requested during loop iteration or by a removal callback?
                    # ⚠️ Does this make any sense? I believe it is a legacy from the previous approach, that now we covered
                    #   with the callback_final_clearing_request snippet.
                    clear_the_screen = final_clearing_needed or callback_final_screen_clearing_request
                    final_clearing_needed = False

                    # Compose the screen. Only the rectangle that changed, if the rest is known to be right.
                    # Any clearing request is a rare, non incremental case: the whole screen is composed, as always.
                    with self.timings.measure("compose"):
                        flush_region, flush_needed = self._compose_screen(
                            contributions, full=bool(queues_to_clear) or clear_the_screen)

                    for queue_name in queues_to_clear:
                        # Be careful with this, it may paint the empty frame of the BACKGROUND once the OVERALL has ben just painted!
                        self._reset_display_area_for_queue(queue_name)
                    if clear_the_screen:
                        self._log_debug(f"🎨 Final clearing requested by an END callback, will clear the screen.")
                        self._full_clear()
                    if queues_to_clear or clear_the_screen:
                        # What is on the canvas is not what the areas contributed any more: next time, everything again.
                        self._screen_valid = False

                    # Show the image on the device
                    self._log_debug(f"🎨 Flushing drawing to LCD display: ")
                    for queue_name in self.areas.keys():
                        self._log_debug(f"  - {queue_name} is {current_interaction_by_queue[queue_name].name if current_interaction_by_queue[queue_name] is not None else 'None'}.")
                    if flush_needed:
                        with self.timings.measure("flush"):
                            self.flush_drawing(None if (queues_to_clear or clear_the_screen) else flush_region)
                    else:
                        self.timings.count("flush_skipped")
                    # Something was drawn, so the screen is not blank any more.
                    self._screen_is_blank = False

                    # Wait for the next frame that is due, or apply the delay based on the current interactions.
                    with self.timings.measure("wait"):
                        self._wait_for_next_frame()

                    self._log_debug(f"🎨 4️⃣ Removal interactions and deciding to pause the loop")

                    # ⚠️ Recently replaced per-queue checks for the removal of the interactions by a single loop that checks all the queues,
                    # to be able to apply the logic of the final clearing request in a more general way.
                    # Please elaborate it more, it's just an initial merge.
                    for queue_name in self.areas.keys():

                        # Anything here?
                        if current_interaction_by_queue[queue_name] is None:
                            continue

                        # We may have a remove interaction request by the Paint Object itself.
                        if current_interaction_by_queue[queue_name].remove_interaction_after_painting:
                            self._log_debug(f"Interaction [{current_interaction_by_queue[queue_name].name}] requested to be removed after painting.")

                            # Before removing, check if it also included a final screen clearing.
                            if current_interaction_by_queue[queue_name].final_screen_clearing:
                                self._log_debug(f"Painter: Interaction [{current_interaction_by_queue[queue_name].name}] included a final screen clearing, telling to painter loop.")
                                final_clearing_needed = True

                            self._remove_interaction(interaction=current_interaction_by_queue[queue_name], queue_name=queue_name)

                    # If we only have a foreground or overall paint, reduce the speed of the loop to avoid burning the CPU for example.
                    # Please note that here we're not using the current_background_interaction variable directly,
                    #   but rather calling the getter method to ensure we're getting the latest state.
                    # elif self.get_current_interaction(PainterQueue.FOREGROUND) is not None and \ ... # the `elif`
                    if self._should_slow_down_loop_iterations():

                        self._log_debug("We have only paints that not need fast loop iterations. Slowing down the loop.")
                        with self.timings.measure("slow_down_sleep"):
                            time.sleep(0.5)
                else:
                    if blank_requested:
                        # Same wipe the timers used to do, but now in the loop thread, so it can't interleave with a draw.
                        self._log_debug("🎨 Blanking the screen after a timed interaction was removed.")
                        self._full_clear()
                        self.flush_drawing()
                    if not final_clearing_needed:
                        self._log_debug("No interactions to paint in any queue, pausing the painting loop.")
                        self.pause()
                        paused_now = True
                        # Something may have been enqueued between process_intermediate_queue() and pause(),
                        #   and its resume_paint() saw the loop still running. Don't lose that wake-up.
                        if self.intermediate_interactions_queue or self._blank_screen_pending:
                            self.resume_paint()

                self.timings.iteration_end(drew)
                if paused_now:
                    # The activity is over: report what was measured.
                    self.timings.loop_paused()

        except KeyboardInterrupt:
            self._xlog.debug("Pressed Control + C while running Painter loop.")
            self.stop()
            # os.kill(os.getpid(), signal.SIGTERM)

    # <------------------------------
    #         Painter Loop
    # <------------------------------

    # ---- Helpers for the painter loop ----

    def _logging_start_painter_loop_iteration(self):
        # Log the current interactions in each queue at the beginning of the loop iteration.
        logging_parts: list = []
        for queue_name in self.areas.keys():
            current_interaction = self.get_current_interaction(queue_name)
            if current_interaction is not None:
                logging_parts.append((f"Current interaction for {queue_name}", f"- name: {current_interaction.name}"))
                logging_parts.append(("", f"- interaction: {current_interaction.command.get()}"))
                logging_parts.append(("", f"- drawing_callback_parameters: {current_interaction.drawing_callback_parameters}"))
                logging_parts.append(("", f"- while_shared_memory_flag: {self._get_shared_memory_flag_name_for(current_interaction.while_shared_memory_flag)}"))
                logging_parts.append(("", f"- while_shared_memory_flag_value: {current_interaction.while_shared_memory_flag_value}"))
                logging_parts.append(("", f"- cache_key: {current_interaction.get_cache_key()}"))
                # Now some parameters depending on which queue we're talking about.
                if isinstance(current_interaction, FramedPaint):
                    logging_parts.append(("", f"- Current Loop iteration counter: {self.areas[queue_name].frame}"))
                    logging_parts.append(("", f"- Max Loop iterations: {current_interaction.loop_iterations}"))
            else:
                logging_parts.append((f"Current interaction for {queue_name}", "[None]"))
        self.log_summary(f"Painter loop new iteration", logging_parts, attend_verbose_debug_flag=True)
        logging_parts: list = []
        # Log the current status of the shared memory flags that we're monitoring.
        for name, flag_idx, flag_name, activation_value, current_value, callback_name, is_dependant in self.painter_shared_memory.get_shared_memory_flags_current_status():
            previous_value = self.painter_shared_memory._shared_memory_flag_previous_value[flag_idx]
            logging_parts.append((flag_name.upper(), f"Previous: {str(previous_value).ljust(5)}, Current: {str(current_value).ljust(5)}, Expected: {str(activation_value).ljust(5)}, Callback: {name}, is_dependant: {is_dependant}"))
        if not logging_parts:
            logging_parts.append(("No shared memory flags being monitored", ""))
        self.log_summary(f"Current Shared Memory Monitoring Flags status", logging_parts, attend_verbose_debug_flag=True)
    
    def flush_drawing(self, region: tuple[int, int, int, int] | None = None):
        """
        Sends the image of the canvas to the display.
        With region (left, top, right, bottom), the display is told that only that rectangle changed, so it can write only that.
        (The display decides: the mocked one always stores the whole frame.)
        """
        if region is None:
            self.drawing_callbacks["display"]["callback"](self.canvas.get_image(clear_background=False))
        else:
            self.drawing_callbacks["display"]["callback"](self.canvas.get_image(clear_background=False), region=region)

    def invalidate_screen(self):
        """
        To call when anything else than the Painter changed what the display shows (like clearing it directly).
        The next time that the Painter draws, it composes and sends the whole screen, instead of only what changed.
        """
        self._screen_valid = False

    def _clear_color(self):
        return self.drawing_callbacks["soft_full_clear"]["parameters"].get("color", self.canvas.COLOR_BACKGROUND)

    def _screen_rectangle(self) -> tuple[int, int, int, int]:
        size = self.canvas.get_screen_size()
        return (0, 0, int(size.x), int(size.y))

    def _area_rectangle(self, queue_name: PainterQueue) -> tuple[int, int, int, int]:
        """ Where the image of the area goes on the screen: left, top, right, bottom (excluded), cut to the screen. """
        base: Rectangle = self.layout_info["base"][self.areas[queue_name].layout_position]
        screen = self._screen_rectangle()
        return (max(screen[0], int(base.point_1.x)), max(screen[1], int(base.point_1.y)),
                min(screen[2], int(base.point_2.x)), min(screen[3], int(base.point_2.y)))

    def _compose_screen(self, contributions: dict, full: bool) -> tuple[tuple[int, int, int, int] | None, bool]:
        """
        Puts what every area contributes into the image of the canvas, in painting order.

        The canvas keeps the screen of the last time. If it is valid and only some areas contribute something different
        from last time, only the rectangle that holds them is cleared and composed again (every area that touches it,
        so anything semi transparent over it ends up right). Otherwise, the whole screen is composed.

        Args:
            contributions: Per queue, in painting order: (image or None, token). Same token as last time is the same picture.
            full: Compose the whole screen whatever the state is.

        Returns:
            (region, needed): the rectangle that changed (None: the whole screen), and False if nothing changed
            at all, so there is no need to send the screen to the display again.
        """
        canvas_image = self.canvas.get_image(clear_background=False)
        reusable = self._partial_composition and self._screen_valid and canvas_image is self._composed_image and not full

        region = None
        if reusable:
            dirty = [queue_name for queue_name in self.areas.keys()
                     if contributions[queue_name][1] != self.areas[queue_name].composed_token]
            if not dirty:
                self.timings.count("frames_unchanged")
                return None, False
            rectangles = [self._area_rectangle(queue_name) for queue_name in dirty]
            region = (min(r[0] for r in rectangles), min(r[1] for r in rectangles),
                      max(r[2] for r in rectangles), max(r[3] for r in rectangles))

        # We clean first. This is because we merge the screen using alfa composite, and otherwise we would
        # have fill colors being merged again and again with alpha transparency, so ends up in a mess.
        if region is None:
            self._log_debug("🎨 Composing the whole screen.")
            with self.timings.measure("clear"):
                self._full_clear()
            canvas_image = self.canvas.get_image(clear_background=False)
            box = self._screen_rectangle()
            self.timings.count("frames_full")
        else:
            self._log_debug(f"🎨 Composing only the rectangle {region}.")
            with self.timings.measure("clear"):
                ImageDraw.Draw(canvas_image).rectangle((region[0], region[1], region[2] - 1, region[3] - 1), fill=self._clear_color())
            box = region
            self.timings.count("frames_partial")
        self.timings.count("pixels_composed", (box[2] - box[0]) * (box[3] - box[1]))

        for queue_name, (image, token) in contributions.items():
            if image is None:
                continue
            area_box = self._area_rectangle(queue_name)
            left, top = max(box[0], area_box[0]), max(box[1], area_box[1])
            right, bottom = min(box[2], area_box[2]), min(box[3], area_box[3])
            if right <= left or bottom <= top:
                continue
            with self.timings.measure(f"merge:{queue_name}"):
                if (left, top, right, bottom) == (area_box[0], area_box[1], area_box[2], area_box[3]) and image.size == (area_box[2] - area_box[0], area_box[3] - area_box[1]):
                    self.canvas.combine_into_image(image, position=Point(left, top), use_alpha_composite=True)
                else:
                    self.canvas.combine_into_image(
                        image, position=Point(left, top), use_alpha_composite=True,
                        source_box=(left - area_box[0], top - area_box[1], right - area_box[0], bottom - area_box[1]))

        for queue_name, (_, token) in contributions.items():
            self.areas[queue_name].composed_token = token
        self._composed_image = canvas_image
        self._screen_valid = True

        if region is not None and self._verify_partial:
            region = self._verify_partial_composition(contributions, region)
        return region, True

    def _verify_partial_composition(self, contributions: dict, region: tuple[int, int, int, int]) -> tuple[int, int, int, int] | None:
        """
        Debug only (dsi_lcd.painter.verify_partial): composes the whole screen apart, and compares it with what the partial
        composition left in the canvas. If they differ, it logs it and fixes the canvas, so the display never shows the wrong one.
        Returns the region to flush: the same one if all right, None (the whole screen) if it had to be fixed.
        """
        from PIL import ImageChops

        reference = self.canvas.create_new_image()
        ImageDraw.Draw(reference).rectangle((0, 0, reference.size[0] - 1, reference.size[1] - 1), fill=self._clear_color())
        for queue_name, (image, _) in contributions.items():
            if image is None:
                continue
            area_box = self._area_rectangle(queue_name)
            reference.alpha_composite(image, dest=(area_box[0], area_box[1]))

        canvas_image = self.canvas.get_image(clear_background=False)
        difference = ImageChops.difference(reference, canvas_image).getbbox()
        self.timings.count("verify_checked")
        if difference is None:
            return region
        self.timings.count("verify_MISMATCH")
        self._xlog.warning(f"🛑 The partial composition of {region} differs from the full one at {difference}. Fixing it, and composing everything next time.")
        canvas_image.paste(reference)
        self._screen_valid = False
        return None
    
    def _draw_or_retrieve_from_cache(self, interaction: BasePaint, queue_name: str) -> Image.Image:
        """
        This method checks if we have already painted the given interaction in the given queue, and if so, retrieves it from the cache.
        If not, it triggers the drawing callback to paint it, and then stores it in the cache.

        This is useful to avoid painting the same interaction in every loop iteration, which can be expensive, especially for complex interactions.
        """
        # Check if we have already painted this interaction in the previous iteration.
        if self._paint_matches_cache(queue_name, interaction):
            self._log_debug(f"Interaction [{interaction.get_cache_key()}] in queue [{queue_name}] is cached. Retrieving it from the cache.")
            self.timings.count(f"cache_hit:{queue_name}")
            return self.areas[queue_name].cached_image
        else:
            self.timings.count(f"cache_miss:{queue_name}")
            with self.timings.measure(f"draw:{queue_name}"):
                return self._draw_and_store_in_cache(interaction, queue_name)

    def _draw_and_store_in_cache(self, interaction: BasePaint, queue_name: str) -> Image.Image:
        """ Triggers the drawing callback of the interaction and stores the result in the cache of its area. """
        # We trigger the drawing callback for this interaction, which should be defined in the painting object.
        self._log_debug(f"Interaction [{interaction.get_cache_key()}] in queue [{queue_name}] is not cached. Painting it now.")
        # Get the initialized image to draw on for this queue, or initialize it if it doesn't exist.
        image_to_draw_on: Image.Image = self.areas[queue_name].image
        canvas_to_draw_on: ImageDraw.ImageDraw = ImageDraw.Draw(image_to_draw_on)
        if isinstance(interaction, AnimationPaint):
            # For animations we need to pass the base image instead of the drawing canvas..
            interaction.drawing_callback(base_image=image_to_draw_on, params=interaction.drawing_callback_parameters)
        else:
            interaction.drawing_callback(draw=canvas_to_draw_on, params=interaction.drawing_callback_parameters)

        # Store the key of the current interaction and its drawing in the cache for the next iterations.
        self.areas[queue_name].store_in_cache(interaction.get_cache_key(), image_to_draw_on.copy())

        # The copy that is in the cache: it is the picture of this version, and nothing draws on it.
        return self.areas[queue_name].cached_image
    
    def _wait_for_next_frame(self):
        """
        Called after flushing. If any area has a paint with several frames, each one is scheduled after the delay
        of its paint, and we sleep until the earliest next frame is due (the areas that are not due keep their drawing).
        If not, the delay is the one of the current interactions, see apply_delay_between_frames().
        """
        now = time.monotonic()
        next_frames_due: list[float] = []
        for area in self.areas.values():
            area.schedule_next_frame(now)
            if area.is_multi_frame():
                next_frames_due.append(area.next_frame_at)

        if not next_frames_due:
            self.apply_delay_between_frames()
            return

        wait = min(next_frames_due) - time.monotonic()
        if wait > 0.0:
            self._log_debug(f"Waiting [{wait:.3f}] sec for the next frame.")
            time.sleep(wait)

    def apply_delay_between_frames(self):
        delays = {}

        observed_queues = [PainterQueue.FOREGROUND, PainterQueue.BACKGROUND, PainterQueue.OVERALL]
        for queue_name in observed_queues:
            interaction = self.get_current_interaction(queue_name)
            if interaction is not None and interaction.delay_between_frames is not None:
                delays[queue_name] = (interaction.delay_between_frames, interaction.name)

        # The delays have priority: 1st Background, then Foreground, then Overall. So if we have several delays, we apply the one with more priority.
        delay = 0.0
        delay_from = None
        if PainterQueue.BACKGROUND in delays:
            delay = delays[PainterQueue.BACKGROUND][0]
            delay_from = delays[PainterQueue.BACKGROUND][1]
        elif PainterQueue.FOREGROUND in delays:
            delay = delays[PainterQueue.FOREGROUND][0]
            delay_from = delays[PainterQueue.FOREGROUND][1]
        elif PainterQueue.OVERALL in delays:
            delay = delays[PainterQueue.OVERALL][0]
            delay_from = delays[PainterQueue.OVERALL][1]

        if delay > 0.0:
            self._log_debug(f"Applying delay between frames of [{delay}] sec as defined by: {delay_from}")
            time.sleep(delay)
    
    def _should_draw_this_loop_iteration(self) -> bool:
        """
        This method decides if the loop iteration that we're about to start makes any sense to be painted.
        The idea is to reduce as much as possible the work to be done, and pause the loop as much as possible.
        """

        # First of all, do we have any elements in the queues to paint?
        queues_have_elements = [self.areas[queue_name].has_paints() for queue_name in self.areas.keys()]
        if not any(queues_have_elements):
            self._log_debug(f"⏹️  Loop Control: No interactions in any queue to paint.")
            return False
        
        # So we have anything in any queue.
        # Are the current interactions the same as the previous ones in their related queues?
        for queue_name in self.areas.keys():
            
            # If this interaction should always be painted while it is in the queue, we skip the cache check and just paint it.
            if self.get_current_interaction(queue_name) is not None and \
                self.areas[queue_name].is_exception_loop(self.get_current_interaction(queue_name)):
                self._log_debug(f"*️⃣  Loop Control: Current Paint [{self.get_current_interaction(queue_name).name}] in [{queue_name}] is in the exception list. We draw this loop iteration.")
                return True
            # If we have a paint with several frames (background, animation...), we assume that it is meant to be painted in every loop iteration until it finishes, so we skip the cache check and just paint it.
            # ⚠️ This appears to me overlapping the previous condition.
            #   - A paint will loop until the end of the paint. And will repeat.
            #   - It could also be part of the exception list, so it will be painted even if it is cached, until it is removed from the queue.
            elif self.areas[queue_name].is_multi_frame():
                self._log_debug(f"*️⃣  Loop Control: Current Paint [{self.get_current_interaction(queue_name).name}] in [{queue_name}] has multiple loop iterations. We draw this loop iteration.")
                return True
            # If the current interaction is different than the previous one, in theory we should paint it.
            elif not self._paint_matches_cache(queue_name, self.get_current_interaction(queue_name)):
                # A passive paint (like the buttons) must not wake up a screen that is deliberately blank.
                # The queue already has its new state, so it will be shown at the next draw triggered by anything else.
                passive_candidate = self.get_current_interaction(queue_name)
                if self._screen_is_blank and passive_candidate is not None and not passive_candidate.trigger_draw_when_blank:
                    self._log_debug(f"🔄  Loop Control: Current Paint [{passive_candidate.name}] in [{queue_name}] changed, but the screen is blank and it is passive. Not drawing.")
                    continue
                # If we're not in idle mode, we just paint it.
                if not self.get_painter_shared_memory().is_idle_mode_on():
                    # Careful, can be None.
                    current_interaction = self.get_current_interaction(queue_name)
                    self._log_debug(f"🔄  Loop Control: Current Paint [{current_interaction.name if current_interaction is not None else 'None'}] in [{queue_name}] has a different cache key than the previous one. We draw this loop iteration.")
                    return True
                # We're in idle mode, so we only paint in case that the interaction is meant to interrupt the idle mode, otherwise we skip it and wait for the next loop iteration.
                else:
                    # Is the interaction meant to be painted even during idle mode? If so, we paint it.
                    if self.get_current_interaction(queue_name) is not None and self.get_current_interaction(queue_name).show_during_idle_mode:
                        self._log_debug(f"🔄  Loop Control: Current Paint [{self.get_current_interaction(queue_name).name}] in [{queue_name}] has a different cache key than the previous one, and is meant to interrupt idle mode. We draw this loop iteration.")
                        return True
                    # If not, we need to paint a black screen in the display area of the interaction, because otherwise we're painting an old value.
                    # Example: Status area gets updated with new debug lines, but we don't want to interrupt the idle mode. so we don't update it, and avoid painting even the cache.
                    # COMMENTED: It's not doing what it should.
                    # else:
                    #     self._log_debug(f"🔄  Loop Control: Current Paint [{self.get_current_interaction(queue_name).name if self.get_current_interaction(queue_name) is not None else 'None'}] in [{queue_name}] has a different cache key than the previous one, but is NOT meant to interrupt idle mode. We will paint a black screen in the display area of this interaction.")
                    #     self._reset_display_area_for_queue(queue_name)
                    #     return True

        self._log_debug(f"⏹️  Loop Control: No changes in interactions detected. Skipping this loop iteration.")
        return False

    def _paint_matches_cache(self, queue_name: PainterQueue, paint: BasePaint | None) -> bool:
        matches = self.areas[queue_name].matches_cache(paint)
        self._log_debug(f"↔️  Cache Control: [{paint.get_cache_key() if paint is not None else None}] in queue [{queue_name}] matches the cache: {matches}.")
        return matches

    def _empty_image_for_queue(self, queue_name: PainterQueue) -> Image.Image:
        """
        The empty frame of the area (what the layout shows when there is nothing to paint in it).
        It is always the same, so it is drawn the first time that it is needed and kept.
        """
        area = self.areas[queue_name]
        if area.empty_image is None:
            image = self._initialize_draw_for_queue(queue_name)
            self.drawing_callbacks["base_frame_for_display_area"]["callback"](
                ImageDraw.Draw(image),
                params={"display_area": area.layout_position}
            )
            area.empty_image = image
        return area.empty_image

    def _reset_display_area_for_queue(self, queue_name: PainterQueue):
        """ Paints the empty frame of the area over the canvas, in its position. """
        layout_position_name = self.areas[queue_name].layout_position
        layout_position: Point = self.layout_info["base"][layout_position_name].point_1
        self.canvas.combine_into_image(self._empty_image_for_queue(queue_name),
                                        position=layout_position,
                                        use_alpha_composite=True)

    def _full_clear(self):
        # The canvas gets a new image: whatever was composed on it is gone.
        self._screen_valid = False
        self.drawing_callbacks["soft_full_clear"]["callback"](
            self.canvas.get_canvas(), 
            params=self.drawing_callbacks["soft_full_clear"]["parameters"]
        )
    
    def _any_current_interaction_wants_final_screen_clearing(self) -> bool:
        for queue_name in self.areas:
            current_interaction = self.get_current_interaction(queue_name)
            if current_interaction and current_interaction.final_screen_clearing:
                return True
        return False
    
    def _should_slow_down_loop_iterations(self) -> bool:
        """
        If we have paints in the defined queues to slow down (and not in the others), we say yes.
        """
        # queues_with_interactions = []
        self._log_debug(f"🎨 Queues with paints: {[queue_name for queue_name in self.areas if self.get_current_interaction(queue_name) is not None]}")
        self._log_debug(f"🎨 Queues defined to slow down the loop: {[name for name, area in self.areas.items() if area.slows_down_loop]}")
        for queue_name in self.areas:
            current_interaction = self.get_current_interaction(queue_name)
            # if current_interaction is None and self.areas[queue_name].slows_down_loop:
            #     # This queue should have a paint. Early exit.
            #     # self._log_debug
            #     return False
            if current_interaction is not None and not self.areas[queue_name].slows_down_loop:
                # This queue should not have a paint. Early exit.
                self._log_debug(f"🎨 Queue [{queue_name}] has a paint [{current_interaction.name}] but is not defined to slow down the loop. We won't slow down the loop.")
                return False
            # Still here? Then this is a valid
        # If we get here, it means that we have paints in the defined queues to slow down, and not in the others, so we say yes.
        self._log_debug(f"🎨 We have paints only in the defined queues to slow down the loop. We will slow down the loop.")
        return True

                
    # ---- Managing the Painting queues and interactions ----

    def add_to_intermediate_queue(self, interaction: BasePaint, queue_name: PainterQueue, action: IntermediatePainterQueueAction):
        self._log_debug(f"Adding [{action}] interaction [{interaction.name}] to intermediate [{queue_name}] queue.")
        self.intermediate_interactions_queue.append((action, queue_name, interaction))
    
    def process_intermediate_queue(self):
        # Process the intermediate interactions queue, which may contain interactions that need to be added to the main queues with some control over how they are added.
        self._log_debug(f"Processing intermediate interactions queue with {len(self.intermediate_interactions_queue)} items.")
        while len(self.intermediate_interactions_queue) > 0:
            action, queue_name, interaction = self.intermediate_interactions_queue.pop(0)
            self._log_debug(f"Triggering [{action}] interaction [{interaction.name}] over [{queue_name}].")
            if action == IntermediatePainterQueueAction.SET:
                self._set_interaction(interaction=interaction, queue_name=queue_name)
            elif action == IntermediatePainterQueueAction.REMOVE:
                self._remove_interaction(interaction=interaction, queue_name=queue_name)
    
    def _set_interaction(self, interaction: BasePaint, queue_name: PainterQueue):
        self._log_debug(f"Setting [{queue_name}] interaction to [{interaction.name}] with parameters [{interaction.drawing_callback_parameters}].")

        # In case we have anything from the same type waiting to be shown, we discard it first.
        #   If we didn't show it yet, there is no point to keep waiting, the flow already went somewhere else.
        for dropped in self.areas[queue_name].drop_duplicates_of_type(interaction):
            self._log_debug(f"Removing previous duplicated interaction [{dropped.get_cache_key()}] from the queue.")

        # Get the current interaction so we can compare it with the new one and decide if we need to replace it or ignore it.
        current_interaction = self.get_current_interaction(queue_name)

        # So we got a new one? Is a valid interaction and is not self/flag managed?
        if current_interaction is not None and \
            current_interaction.while_shared_memory_flag is None and \
            not current_interaction.remove_interaction_after_painting:

            # The same paint as the current one, again: it would be drawn exactly as it is already, so there is nothing to do.
            # Replacing it would reset the cache of the area, and so make a new draw (and flush) for the same picture.
            # Only for the paints that declare what their cache key depends on (cache_control_parameters), because the
            #   others (empty list) may change their parameters without it being visible in the key, and need the redraw.
            # Not for the paints that come back to be maintained again, nor the ones that live by a flag or remove themselves.
            if len(interaction.cache_control_parameters) > 0 and \
                current_interaction.get_cache_key() == interaction.get_cache_key() and \
                current_interaction is not interaction and \
                current_interaction.while_shared_memory_flag is None and \
                current_interaction.maintain_paint_for_seconds is None and \
                interaction.maintain_paint_for_seconds is None and \
                not interaction.remove_interaction_after_painting and \
                not (isinstance(current_interaction, FramedPaint) and current_interaction.is_multi_frame()):
                self.timings.count(f"same_paint_ignored:{queue_name}")
                self._log_debug(f"Interaction [{interaction.get_cache_key()}] is the same as the current one in [{queue_name}]. Nothing changes on screen, ignoring it.")
                return

            # In case that the current interaction is set to stay after painting, it could stay forever,
            #   actually blocking anything else that comes afterwards.
            # When it's managed by the busy flags, it will be removed whenever the flag changes,
            #   but when it's a normal one, we should simply remove the current one once we get a new one.
            self._log_debug(f"Current {queue_name} interaction [{current_interaction.name}] is set to stay after painting, but we received a new {queue_name} interaction [{interaction.name}]. Removing the current one to give priority to the new one.")
            self._remove_interaction(interaction=current_interaction, queue_name=queue_name)
        
        # If we're meant to keep the interaction for an amount of seconds, set up a scheduler to remove it after the defined time.
        if interaction.maintain_paint_for_seconds is not None:
            self._log_debug(f"{queue_name} interaction [{interaction.name}] is meant to be maintained for [{interaction.maintain_paint_for_seconds}] seconds. Setting up a scheduler to remove it after the defined time.")

            def remove_interaction_after_time():
                # This runs in a Timer thread. It must NOT touch the queues or the canvas:
                #   it only asks the Painter loop to do it, so there is a single writer.
                self._log_debug(f"Scheduler triggered to remove {queue_name} interaction [{interaction.name}] after maintaining it for [{interaction.maintain_paint_for_seconds}] seconds.")
                self.request_removal(interaction, queue_name, blank_screen=True)

            # The timer belongs to the area, and replaces any older one with the same key.
            self.areas[queue_name].start_timer(
                interaction.get_cache_key(), interaction.maintain_paint_for_seconds, remove_interaction_after_time)

        # Now add the new interaction to the queue
        self.areas[queue_name].paints.append(interaction)

        self._log_debug(f"The {queue_name} queue after setting last: {', '.join([item.get_cache_key() for item in self.areas[queue_name].paints])}.")
    
    def get_current_interaction(self, queue_name: PainterQueue) -> BasePaint | None:
        return self.areas[queue_name].current()

    def request_removal(self, interaction: BasePaint, queue_name: PainterQueue, blank_screen: bool = False):
        """
        The thread-safe way to remove an interaction: it only asks the loop to do it.
        With blank_screen=True the loop also blanks the screen if nothing else is drawn.
        """
        self.add_to_intermediate_queue(interaction, queue_name, IntermediatePainterQueueAction.REMOVE)
        if blank_screen:
            self._blank_screen_pending = True
        self.resume_paint()

    def _remove_interaction(self, interaction: BasePaint, queue_name: PainterQueue):
        self._log_debug(f"Removing interaction [{interaction.name}] from [{queue_name}] queue.")
        area = self.areas[queue_name]
        # When we remove an interaction, the area also cleans the cache related to it, to avoid retrieving it again
        #   if it comes back in the future, and registers the final clearing requests that the interaction asked for.
        requester = f"{IntermediatePainterQueueAction.REMOVE}_{interaction.name}"
        if area.remove(interaction, requester):
            self._log_debug(f"Interaction [{interaction.name}] removed from [{queue_name}] queue successfully.")
            # Removing the interaction means to stop drawing it.
            # It's the moment to check for a final cleaning requests from the callbacks.
            if interaction.final_screen_clearing:
                self._log_debug(f"🔃 Painter callback [{requester}] for [{queue_name}]: Final ScreenClearing intended, telling to painter loop")
            if interaction.final_area_clearing:
                self._log_debug(f"🔃 Painter callback [{requester}] for [{queue_name}]: Final Area Clearing intended, telling to painter loop")
        elif area.has_paints():
            # Could be that meanwhile anything else (like a dupe) came in and then
            #   the "current" one was already removed.
            self._log_debug(f"🟠 Interaction [{interaction.name}] is not the current one. Skipping.")
            current_queue = ", ".join([item.name for item in area.paints])
            self._log_debug(f"Current [{queue_name}] interaction queue: [{current_queue}].")

    def _initialize_draw_for_queue(self, queue_name: PainterQueue) -> Image.Image:
        # We create a new image to draw the interaction, based on the size of the layout position corresponding to this queue.
        layout_position_name = self.areas[queue_name].layout_position
        layout_position_info = self.layout_info["base"].get(layout_position_name, None)
        if layout_position_info is not None and isinstance(layout_position_info, Rectangle):
            size = Point(
                layout_position_info.point_2.x - layout_position_info.point_1.x,
                layout_position_info.point_2.y - layout_position_info.point_1.y
            )
            self._log_debug(f"Initializing drawing for queue [{queue_name}] with size [{size.x}, {size.y}] based on layout position [{layout_position_name}].")
            # Create the base image.
            return self.canvas.create_new_image(size=size)
        else:
            self._xlog.warning(f"🟠 No valid layout position info found for queue [{queue_name}] at position [{layout_position_name}]. Creating a default image.")
            return self.canvas.create_new_image()
        
    
    # ---- Managing the Thread and the class control ----

    def shutdown(self):
        self._xlog.debug("Shutting down Painter.")
        self.is_active = False
    
    def close(self):
        self.shutdown()

        # Its shared memory monitor has a worker thread (and a doorbell) of its own, that nobody else closes.
        if self.painter_shared_memory is not None:
            self.painter_shared_memory.close()

        if self._worker_thread is not None and self._worker_thread.is_alive():
            self._xlog.debug("Joining Painter worker thread.")
            self._worker_thread.join(timeout=2)
            if self._worker_thread.is_alive():
                self._xlog.warning("Painter worker thread did not finish in time.")
            else:
                self._xlog.debug("Painter worker thread finished successfully.")
        else:
            self._xlog.debug("Painter worker thread is not alive or was never started.")
        
        for area in self.areas.values():
            for interaction_cache_key in area.cancel_timers():
                self._log_debug(f"Cancelling timer for interaction cache key [{interaction_cache_key}].")
        self._log_debug("Painter shutdown complete.")
    
    def start_paused(self):
        """
        This method starts the painter thread but in a paused state, 
        so it doesn't start painting until we call resume_paint(). 
        This is useful to prepare everything and then start painting when we want to, for example at the end of the init phase.
        """
        self._log_debug("Starting painter thread in paused state.")

        # Set the loop to work. Still, it will wait for the _thread_event to be set, to start any actual painting.
        self.is_active = True

        # And let the worker to start.
        self._worker_thread.start()
    
    def resume_paint(self) -> None:

        with self._resume_lock:
            # If we're actually not running anything inside the thread, do it now.
            if not self._thread_event.is_set():
                self._log_debug("Painter thread not running, starting it now.")

                for queue_name in self.areas.keys():
                    self.areas[queue_name].image = self._initialize_draw_for_queue(queue_name)
                    self._log_debug(f"Initialized drawing for queue [{queue_name}].")

                # Tell the worker that it can start painting.
                self._thread_event.set()
    
    def pause(self):
        # This pauses the loop, but doesn't stop it. It will wait for the _thread_event to be set again to resume painting.
        self._thread_event.clear()
    
    def stop(self):
        # This stops the loop
        self.is_active = False
    
    # ---- Managing the Shared Memory dependencies ----

    def get_painter_shared_memory(self) -> PainterSharedMemory:
        return self.painter_shared_memory
    
    def _get_shared_memory_flag_name_for(self, shared_memory_flag: int) -> str:
        return self.painter_shared_memory.get_shared_memory_flag_name_for(shared_memory_flag)
    
    def load_painter_shared_memory_list_to_control(self, shared_memory_list_to_control: list[tuple[str, int, bool, callable, bool]]):
        """
        A shortcut to load a list of shared memory flags to control in the painter_shared_memory instance.
        Useful to load several in one shot, for example some default ones like THINKING or SPEAKING.
        Each one is (name, flag, activation value, callback, is dependant).
        """
        self.painter_shared_memory.load_list_control(shared_memory_list_to_control)
    
    def _register_callbacks_for_shared_memory_flag(self, shared_memory_flag: int, activation_value: bool, paint: BasePaint, queue_name: PainterQueue):
        """
        This is an internal shortcut to register the pair of callbacks for a shared memory flag in the painter_shared_memory instance.

        Attention: There are always 2 callbacks: one for starting and one for ending.
            The removal callback needs to be set as dependant to the setting callback. 
                We need to control the order of execution, and treat them as twins, always together.
        """

        # We register the callback to trigger the painting of this interaction when the shared memory flag changes to the desired value.
        self.painter_shared_memory.set_callback_for_shared_memory_flag(
            name=f"{IntermediatePainterQueueAction.SET}_{paint.name}",
            shared_memory_flag=shared_memory_flag, 
            activation_value=activation_value, 
            callback=self._generate_callback(
                name=f"{IntermediatePainterQueueAction.SET}_{paint.name}",
                interaction=paint,
                queue_name=queue_name,
                intermediate_queue_action=IntermediatePainterQueueAction.SET,
                flag=shared_memory_flag,
                for_value=activation_value,
                is_removal_callback=False
            ),
            is_dependant=False
        )

        # We register the callback to trigger the removal of this interaction when the shared memory flag changes to any other value.
        self.painter_shared_memory.set_callback_for_shared_memory_flag(
            name=f"{IntermediatePainterQueueAction.REMOVE}_{paint.name}",
            shared_memory_flag=shared_memory_flag, 
            activation_value=not activation_value, 
            callback=self._generate_callback(
                name=f"{IntermediatePainterQueueAction.REMOVE}_{paint.name}",
                interaction=paint,
                queue_name=queue_name,
                intermediate_queue_action=IntermediatePainterQueueAction.REMOVE,
                flag=shared_memory_flag,
                for_value=not activation_value,
                is_removal_callback=True
            ),
            is_dependant=True
        )
    
    def _generate_callback(self,
                           name: str,
                           interaction: BasePaint,
                           queue_name: PainterQueue,
                           intermediate_queue_action: IntermediatePainterQueueAction, 
                           flag: int,
                           for_value: bool,
                           is_removal_callback: bool,
                           extra_callback: callable = None) -> callable:
        """
        Once the simple callback is not enough, this generates a more complex one that triggers the interaction callback, 
        but also does some extra work like shared memory monitoring control, extra callback and flow control.
        """
        
        # the template itself
        def callback_template():
            flag_name = self.painter_shared_memory.shared_memory._map_index_to_flag.get(flag, f"Unknown flag index [{flag}]")
            self._log_debug(f"🔃 Painter callback [{name}] for [{queue_name}]: [{flag_name.upper()}] busy flag changed to [{for_value}], {'with' if extra_callback is not None else 'without'} extra callback.")

            # Set the interactions if provided
            if interaction is not None:
                # 1. Trigger the callback of the interaction based on the shared memory flag value.
                # interaction_callback(interaction=interaction, queue_name=queue_name)
                self.add_to_intermediate_queue(interaction=interaction, queue_name=queue_name, action=intermediate_queue_action)
                # 2. Remove the callback itself to avoid multiple triggers
                self.painter_shared_memory.remove_callback_for_shared_memory_flag(
                    name=name,
                    shared_memory_flag=flag, 
                    activation_value=for_value
                )

                # 3. Give the chance to execute an extra callback if provided
            #     if extra_callback is not None:
            #         info_to_return["extra_callback_result"] = extra_callback()

        return callback_template