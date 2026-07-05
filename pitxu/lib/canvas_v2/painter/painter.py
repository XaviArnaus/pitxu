import time

from pyxavi import Config, Dictionary, dd
from pitxu.lib.abstract.pyxavi import PyXavi

from pitxu.lib.canvas_v2.canvas import Canvas
from pitxu.lib.canvas_v2.painter.painter_shared_memory import PainterSharedMemory
from pitxu.lib.canvas_v2.painter.paint_object import PaintObject, BasePaint, ForegroundPaint, BackgroundPaint, OverallPaint, AnimationPaint
from pitxu.lib.canvas_v2.painter.painting_command import ForegroundCommand, PaintingCommand, BackgroundCommand
from pitxu.lib.canvas_v2.painter.painter_queue import PainterQueue

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

    2. We add the interactions to the corresponding queue, with some logic to manage the priority and dupe interactions.
        - If we receive while_shared_memory_flag and while_shared_memory_flag_value, we register a pair of callbacks that
            basically are start_painting_callback (for the given paint in the given shared memory info) 
            and stop_painting_callback (for the given paint in the opposite value of the given shared memory info)
        - The queues are basically lists of interactions to paint, but they also have some logic to manage the priority 
            and dupe interactions, for example:
            - If we receive an interaction with priority, we remove all the previous interactions of the same queue.
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
    _timer: dict[str, threading.Timer] = {}

    THREAD_NAME: str = "Painter"

    # Controls if the loop should work. Set to False to exit the loop and finish the thread.
    is_active: bool = True

    canvas: Canvas = None
    # The drawing tool, initialized once we start painting, outside the loop for better performance, per queue
    image_per_queue: dict[str, Image.Image | None] = {}
    # The callbacks defined on the caller regarding the frames to draw
    drawing_callbacks: dict[str, dict[str, any]] = None
    # The layout info, to know the sizes for the sub-canvases to paint the interactions.
    layout_info: dict[str, dict[str, Rectangle]] = None
    # The mapping between the layout positions and the queues, to know where to paint the interactions.
    layout_position_to_queue_name: dict[str, str] = None
    queue_name_to_layout_position: dict[str, str] = None
    # A merged dictionary that comes AFTER executing the callbacks triggered through shared memory flags.
    # For example, requesting a final cleaning after removing the interaction.
    # Be careful, some can be contradictory. We start by classifying them per queue, and see if that's enough.
    # The structure is: {queue_name: {callback_name: {request_name: request_value}}}
    # The loop should remove the entry once consumed, to avoid carrying it on into the next loop iteration.
    flags_callback_returned_requests: dict[str, dict[str, dict[str,any]]] = {}

    # Queues for each display area.
    # The idea is that we register the interactions to paint in these queues, and the Painter loop will consume them and paint them.
    queue: dict[str, list[BasePaint]] = {}

    # These interactions per queue have priority over any other,
    # So when we receive any of them, everything currently in the queue is just discarded.
    priority_interactions: dict[str, list[PaintingCommand]] = {}

    # These interactions per queue are never considered in the calculation for the loop execution.
    exception_loop_interactions: dict[str, list[PaintingCommand]] = {}
    # These queues, when they have paints (and the others not), make the loop to slow down, to avoid burning the CPU.
    queues_with_paints_that_slow_down_the_loop: list[str] = []

    # This should effectively be the drawing cache
    previous_interaction_by_queue: dict[PainterQueue, dict[str, Image.Image | BasePaint | None]] = {}

    # This is the queue for the interactions to be set or removed, so we do it in a controlled way inside the painting loop.
    intermediate_interactions_queue: list[tuple[IntermediatePainterQueueAction, PainterQueue, BasePaint]] = []

    # This class controls the transitions of the shared memory flags and values in a separate thread.
    #   and triggers callbacks when it happens.
    painter_shared_memory: PainterSharedMemory = None

    VERBOSE_DEBUG: bool = True

    def __init__(self, config: Config, params: Dictionary):
        super(Painter, self).init_pyxavi(config, params)

        # We need the definition of the queues to play with
        if params.key_exists("painter_queues"):
            for queue_name in params.get("painter_queues"):
                self._initialize_attributes_per_queue(queue_name)
        else:
            raise ValueError("'painter_queues' parameter is required for Painter.")
        
        # We may (or may not) have exceptions for the end of the loop
        for queue_name, interactions in params.get("painter_exception_loop_interactions", {}).items():
                self._assign_exception_loop_interactions_to_queue(queue_name, interactions)
        
        # We may (or may not) have priority interactions that need to be painted as soon as they are received,
        #   discarding the previous ones in the queue.
        for queue_name, interactions in params.get("painter_priority_interactions", {}).items():
                self._assign_priority_interactions_to_queue(queue_name, interactions)
        
        # Maybe we have some queues that when they have paints (and the others not), make the loop to slow down, to avoid burning the CPU.
        for queue_name in params.get("painter_queues_with_paints_that_slow_down_the_loop", []):
            self.queues_with_paints_that_slow_down_the_loop.append(queue_name)

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

        if params.key_exists("layout_position_to_queue_name"):
            self.layout_position_to_queue_name = params.get("layout_position_to_queue_name")
            self.queue_name_to_layout_position = {v: k for k, v in self.layout_position_to_queue_name.items()}
        else:
            raise ValueError("'layout_position_to_queue_name' parameter is required for Painter.")

        # Before setting the worker, we create the event.
        self._thread_event = threading.Event()

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
    
    def _initialize_attributes_per_queue(self, queue_name: str):
        """
        Initialize the attributes that depend per queue, so we don't need to specifically define the queues in the class.
        """
        
        self.image_per_queue[queue_name] = None
        self.flags_callback_returned_requests[queue_name] = {}
        self.queue[queue_name] = []
        self.priority_interactions[queue_name] = []
        self.exception_loop_interactions[queue_name] = []
        self.previous_interaction_by_queue[queue_name] = {
            "cache_key": None,
            "interaction": None,
            "image": None
        }
    
    def _assign_priority_interactions_to_queue(self, queue_name: str, interactions: list[PaintingCommand]):
        """
        Assign the given interactions as priority interactions for the given queue.
        """
        self.priority_interactions[queue_name] = interactions
    
    def _assign_exception_loop_interactions_to_queue(self, queue_name: str, interactions: list[PaintingCommand]):
        """
        Assign the given interactions as exception loop interactions for the given queue.
        """
        self.exception_loop_interactions[queue_name] = interactions
    
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

            # Each time we enter this loop, we reset the iteration counter.
            background_iteration_counter = None

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

                self._log_debug(f"🎨 1️⃣ Starting new painting loop iteration.")

                # The very first thing to do is to apply the pending interactions to set or remove that we have in the intermediate queue,
                # which are triggered by the shared memory flags callbacks or other events.
                self.process_intermediate_queue()

                # This is just some logging at the beginning of the loop iteration.
                self._logging_start_painter_loop_iteration({
                    "background_iteration_counter": background_iteration_counter,
                })

                # Only work if we have anything to paint.
                if self._should_draw_this_loop_iteration():

                    # Get the current iterations to draw, if they exist.
                    # The order matters: we need to paint from bottom layer to upper layer.
                    current_interaction_by_queue: dict[PainterQueue, BasePaint | None] = {
                        queue_name: self.get_current_interaction(queue_name) for queue_name in self.queue.keys()
                    }

                    # First of all, we clean tha whole screen.
                    # This is because we merge the screen using alfa composite, and otherwise we would
                    # have fill colors being merged again and again with alpha transparency, so ends up in a mess.
                    self._log_debug(f"🎨 Cleaning the whole screen.")
                    self._full_clear()

                    # We paint the interactions in order, from background to overall.
                    for queue_name in self.queue.keys():
                        current_interaction: BasePaint | None = current_interaction_by_queue[queue_name]

                        # Do we have anything to paint in this queue?
                        if current_interaction is None:

                            # Only in the case that we have nothing to paint, we need to at least draw an empty soft frame,
                            #  to avoid having lost empty spaces in the layout.
                            # Also, ignore OVERALL!
                            # TODO: This should be cached.
                            if queue_name == PainterQueue.OVERALL:
                                self._log_debug(f"🎨 Nothing to paint in queue [{queue_name}].")
                            else:
                                self._log_debug(f"🎨 Nothing to paint in queue [{queue_name}]. Drawing the empty frame to keep the layout.")
                                self._reset_display_area_for_queue(queue_name)
                        
                        else:
                            self._log_debug(f"🎨 Painting interaction [{current_interaction.name}] from queue [{queue_name}].")

                            # Pre-painting loop actions.
                            if queue_name == PainterQueue.BACKGROUND:
                                # Maybe we need to restart the background iteration counter. 
                                # It's set to None down the line, to be initialized precisely at the begining of the iteration.
                                if background_iteration_counter is None:
                                    background_iteration_counter = 0
                                else:
                                    background_iteration_counter += 1
                                current_interaction.current_loop_iteration = background_iteration_counter
                                
                                # The iteration counter needs to be added into the parameters of the drawing callback, so we update them here.
                                # The max iteration counter is set by the caller when it creates the painting object, so we assume it is already there.
                                # The internal callback will take it and calculate which frame to show based on it.
                                # ⚠️ Just introduced current_interaction.current_loop_iteration, maybe this IF is not needed anymore, 
                                #   we can just update it directly, and set it to 0 when we initialize the background iteration counter.
                                #   Note: Maybe not, as the cache key is build using the param on the callback, not the attributes on the Paint object.
                                if current_interaction.drawing_callback_parameters is None:
                                    current_interaction.drawing_callback_parameters = {}
                                current_interaction.drawing_callback_parameters["current_loop_iteration"] = background_iteration_counter
                                current_interaction.drawing_callback_parameters["max_loop_iterations"] = current_interaction.loop_iterations
                            
                            # --- START painting the interaction, with cache support ---

                            self._log_debug(f"🎨 2️⃣ Actual painting section.")

                            # We check if we have already painted this interaction in the previous iteration, and if so, we retrieve it from the cache.
                            # If not, we trigger the drawing callback to paint it, and then store it in the cache.
                            interaction_image = self._draw_or_retrieve_from_cache(current_interaction, queue_name)

                            # Now we merge the interaction image in the working image of the canvas, in the corresponding position.
                            # Not using Alpha Composite unless is the overall paint, because it is the only one that may have transparent areas, 
                            # and we want to optimize the painting of the background and foreground paints as much as possible.
                            layout_position_name = self.queue_name_to_layout_position[queue_name]
                            layout_position: Point = self.layout_info["base"][layout_position_name].point_1
                            self._log_debug(f"🎨 Merging interaction [{current_interaction.name}] at position [{layout_position.x}, {layout_position.y}]")
                            self.canvas.combine_into_image(interaction_image, 
                                                           position=layout_position,
                                                           use_alpha_composite=True
                                                           )

                            # --- END painting the interaction ---

                            # Post-painting loop actions.
                            if queue_name == PainterQueue.BACKGROUND:

                                # This is only for typing.
                                current_interaction: BackgroundPaint = current_interaction

                                # If we have reached the max iterations for background, we set the iterations counter to None.
                                #   Then, the next loop iteration will re-initialize it to 0 again.
                                # This means that this loop will go forever until we stop the thread or change/remove the background interaction.
                                if background_iteration_counter >= current_interaction.loop_iterations - 1:
                                    self._log_debug(f"🎨 Reached max iterations for background interaction [{current_interaction.name if current_interaction is not None else 'None'}], Cleaning the counter.")
                                    background_iteration_counter = None
                            
                    self._log_debug(f"🎨 3️⃣ Flushing, and delays")

                    # Could be that any removal callback requests a final clearing. 
                    # We need to read it from the requests, remove it from there, and apply it if any is True.
                    # Attention, it is not meant as a full screen clearing, but per queue.
                    callback_final_screen_clearing_request = False
                    for queue_name in self.queue.keys():
                        callback_final_area_clearing_request = False
                        for callback_name, requests in self.flags_callback_returned_requests[queue_name].items():
                            if "final_area_clearing_needed" in requests:
                                if requests.get("final_area_clearing_needed") == True:
                                    callback_final_area_clearing_request = True
                                    self._log_debug(f"🎨 Callback [{callback_name}] for queue [{queue_name}] requested a final clearing of the area.")
                                # We remove the request once we read it, to avoid carrying it on into the next loop iteration.
                                del self.flags_callback_returned_requests[queue_name][callback_name]["final_area_clearing_needed"]
                            if "final_screen_clearing_needed" in requests:
                                if requests.get("final_screen_clearing_needed") == True:
                                    callback_final_screen_clearing_request = True
                                    self._log_debug(f"🎨 Callback [{callback_name}] for queue [{queue_name}] requested a final clearing of the screen.")
                                # We remove the request once we read it, to avoid carrying it on into the next loop iteration.
                                del self.flags_callback_returned_requests[queue_name][callback_name]["final_screen_clearing_needed"]
                        if callback_final_area_clearing_request:
                            # Be careful with this, it may paint the empty frame of the BACKGROUND once the OVERALL has ben just painted!
                            self._reset_display_area_for_queue(queue_name)

                    # A final clearing was requested during loop iteration or by a removal callback?
                    # ⚠️ Does this make any sense? I believe it is a legacy from the previous approach, that now we covered
                    #   with the callback_final_clearing_request snippet.
                    if final_clearing_needed or callback_final_screen_clearing_request:

                        self._log_debug(f"🎨 Final clearing requested by an END callback, will clear the screen.")
                        self._full_clear()
                        final_clearing_needed = False
                    
                    # Show the image on the device
                    self._log_debug(f"🎨 Flushing drawing to LCD display: ")
                    for queue_name in self.queue.keys():
                        self._log_debug(f"  - {queue_name} is {current_interaction_by_queue[queue_name].name if current_interaction_by_queue[queue_name] is not None else 'None'}.")
                    self.flush_drawing()

                    # Apply delay between frames if needed, based on the current interaction. There is a priority.
                    self.apply_delay_between_frames()

                    self._log_debug(f"🎨 4️⃣ Removal interactions and deciding to pause the loop")

                    # ⚠️ Recently replaced per-queue checks for the removal of the interactions by a single loop that checks all the queues,
                    # to be able to apply the logic of the priority interactions and the final clearing request in a more general way.
                    # Please elaborate it more, it's just an initial merge.
                    for queue_name in self.queue.keys():

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

                            # Avoid removing the interaction if it's a priority one (we're trying to generalize the SPEAKING).
                            if current_interaction_by_queue[queue_name].command in self.priority_interactions[queue_name]:
                                # The if here was:
                                # if current_interaction_by_queue[PainterQueue.BACKGROUND] is not None and \
                                #     len(self.queue[PainterQueue.BACKGROUND]) > 1 and \
                                #     not current_interaction_by_queue[PainterQueue.BACKGROUND].command.matches(BackgroundCommand.SPEAKING):
                                self._log_debug(f"Painter: Interaction [{current_interaction_by_queue[queue_name].name}] is a priority one, won't remove.")
                            else:
                                self._remove_interaction(interaction=current_interaction_by_queue[queue_name], queue_name=queue_name)

                    # If we only have a foreground or overall paint, reduce the speed of the loop to avoid burning the CPU for example.
                    # Please note that here we're not using the current_background_interaction variable directly,
                    #   but rather calling the getter method to ensure we're getting the latest state.
                    # elif self.get_current_interaction(PainterQueue.FOREGROUND) is not None and \ ... # the `elif`
                    if self._should_slow_down_loop_iterations():

                        self._log_debug("We have only paints that not need fast loop iterations. Slowing down the loop.")
                        time.sleep(0.5)
                else:
                    if not final_clearing_needed:
                        self._log_debug("No interactions to paint in any queue, pausing the painting loop.")
                        self.pause()
        
        except KeyboardInterrupt:
            self._xlog.debug("Pressed Control + C while running Painter loop.")
            self.stop()
            # os.kill(os.getpid(), signal.SIGTERM)

    # <------------------------------
    #         Painter Loop
    # <------------------------------

    # ---- Helpers for the painter loop ----

    def _logging_start_painter_loop_iteration(self, extra_info: dict[str, any]):
        # Log the current interactions in each queue at the beginning of the loop iteration.
        logging_parts: list = []
        for queue_name in self.queue.keys():
            current_interaction = self.get_current_interaction(queue_name)
            if current_interaction is not None:
                logging_parts.append((f"Current interaction for {queue_name}", f"- name: {current_interaction.name}"))
                logging_parts.append(("", f"- interaction: {current_interaction.command.get()}"))
                logging_parts.append(("", f"- drawing_callback_parameters: {current_interaction.drawing_callback_parameters}"))
                logging_parts.append(("", f"- while_shared_memory_flag: {self._get_shared_memory_flag_name_for(current_interaction.while_shared_memory_flag)}"))
                logging_parts.append(("", f"- while_shared_memory_flag_value: {current_interaction.while_shared_memory_flag_value}"))
                logging_parts.append(("", f"- cache_key: {current_interaction.get_cache_key()}"))
                # Now some parameters depending on which queue we're talking about.
                if queue_name == PainterQueue.BACKGROUND:
                    current_interaction: BackgroundPaint
                    logging_parts.append(("", f"- Current Loop iteration counter: {extra_info.get('background_iteration_counter', 'N/A')}"))
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
    
    def flush_drawing(self):
        self.drawing_callbacks["display"]["callback"](self.canvas.get_image())
    
    def _draw_or_retrieve_from_cache(self, interaction: BasePaint, queue_name: str) -> Image.Image:
        """
        This method checks if we have already painted the given interaction in the given queue, and if so, retrieves it from the cache.
        If not, it triggers the drawing callback to paint it, and then stores it in the cache.

        This is useful to avoid painting the same interaction in every loop iteration, which can be expensive, especially for complex interactions.
        """
        # Check if we have already painted this interaction in the previous iteration.
        if self._current_interaction_by_queue_is_the_same_as_previous(queue_name, current_interaction=interaction):
            self._log_debug(f"Interaction [{interaction.get_cache_key()}] in queue [{queue_name}] is cached. Retrieving it from the cache.")
            return self.previous_interaction_by_queue[queue_name]["image"]
        else:
            # We trigger the drawing callback for this interaction, which should be defined in the painting object.
            self._log_debug(f"Interaction [{interaction.get_cache_key()}] in queue [{queue_name}] is not cached. Painting it now.")
            # Get the initialized image to draw on for this queue, or initialize it if it doesn't exist.
            image_to_draw_on: Image.Image = self.image_per_queue[queue_name]
            canvas_to_draw_on: ImageDraw.ImageDraw = ImageDraw.Draw(image_to_draw_on)
            if isinstance(interaction, AnimationPaint):
                # For animations we need to pass the base image instead of the drawing canvas..
                interaction.drawing_callback(base_image=image_to_draw_on, params=interaction.drawing_callback_parameters)
            else:
                interaction.drawing_callback(draw=canvas_to_draw_on, params=interaction.drawing_callback_parameters)

            # Store the current interaction and its drawing in the cache for the next iterations.
            self.previous_interaction_by_queue[queue_name]["interaction"] = interaction if interaction is not None else None
            self.previous_interaction_by_queue[queue_name]["image"] = image_to_draw_on.copy()
            self.previous_interaction_by_queue[queue_name]["cache_key"] = interaction.get_cache_key()

            return self.image_per_queue[queue_name]
    
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
        queues_have_elements = [len(self.queue[queue_name]) > 0 for queue_name in self.queue.keys()]
        if not any(queues_have_elements):
            self._log_debug(f"⏹️  Loop Control: No interactions in any queue to paint.")
            return False
        
        # So we have anything in any queue.
        # Are the current interactions the same as the previous ones in their related queues?
        for queue_name in self.queue.keys():
            
            # If this interaction should always be painted while it is in the queue, we skip the cache check and just paint it.
            if self.get_current_interaction(queue_name) is not None and \
                self.get_current_interaction(queue_name).command.included_in(self.exception_loop_interactions[queue_name]):
                self._log_debug(f"*️⃣  Loop Control: Current Paint [{self.get_current_interaction(queue_name).name}] in [{queue_name}] is in the exception list. We draw this loop iteration.")
                return True
            # If we have a background paint or animation paint with several loop iterations, we assume that it is meant to be painted in every loop iteration until it finishes, so we skip the cache check and just paint it.
            # ⚠️ This appears to me overlapping the previous condition.
            #   - A paint will loop until the end of the paint. And will repeat.
            #   - It could also be part of the exception list, so it will be painted even if it is cached, until it is removed from the queue.
            elif (self.get_current_interaction(PainterQueue.BACKGROUND) is not None and self.get_current_interaction(PainterQueue.BACKGROUND).loop_iterations > 1):
                self._log_debug(f"*️⃣  Loop Control: Current Paint [{self.get_current_interaction(PainterQueue.BACKGROUND).name}] in [BACKGROUND] has multiple loop iterations. We draw this loop iteration.")
                return True
            # If the current interaction is different than the previous one, in theory we should paint it.
            elif not self._current_interaction_by_queue_is_the_same_as_previous(queue_name):
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

    def _current_interaction_by_queue_is_the_same_as_previous(self, queue_name: PainterQueue, current_interaction: BasePaint | None = None) -> bool:
        current_interaction = self.get_current_interaction(queue_name) if current_interaction is None else current_interaction
        previous_interaction_cache_key = self.previous_interaction_by_queue[queue_name]["cache_key"]
        if current_interaction is None and previous_interaction_cache_key is None:
            self._log_debug(f"↔️  Cache Control: Current and Previous interactions in queue [{queue_name}] are both None. They are the same.")
            return True
        if (current_interaction is None and previous_interaction_cache_key is not None) or \
            (current_interaction is not None and previous_interaction_cache_key is None):
            self._log_debug(f"⏺️  Cache Control: One of the Current and Previous interactions in queue [{queue_name}] is None while the other is not. They are different.")
            return False
        current_interaction_cache_key = current_interaction.get_cache_key()
        if current_interaction_cache_key == previous_interaction_cache_key:
            self._log_debug(f"↔️  Cache Control: Current interaction [{current_interaction_cache_key}] in queue [{queue_name}] is cached. They are the same.")
            return True
        else:
            self._log_debug(f"⏺️  Cache Control: Current interaction [{current_interaction_cache_key}] in queue [{queue_name}] is not cached. They are different.")
            return False
    
    def _reset_display_area_for_queue(self, queue_name: PainterQueue):
        tmp_draw = ImageDraw.Draw(self.image_per_queue[queue_name])
        self.drawing_callbacks["base_frame_for_display_area"]["callback"](
            tmp_draw, 
            params={"display_area": self.queue_name_to_layout_position[queue_name]}
        )
        layout_position_name = self.queue_name_to_layout_position[queue_name]
        layout_position: Point = self.layout_info["base"][layout_position_name].point_1
        self.canvas.combine_into_image(self.image_per_queue[queue_name], 
                                        position=layout_position, 
                                        use_alpha_composite=True)
    
    def _full_clear(self):
        self.drawing_callbacks["soft_full_clear"]["callback"](
            self.canvas.get_canvas(), 
            params=self.drawing_callbacks["soft_full_clear"]["parameters"]
        )
    
    def _any_current_interaction_wants_final_screen_clearing(self) -> bool:
        for queue_name in self.queue:
            current_interaction = self.get_current_interaction(queue_name)
            if current_interaction and current_interaction.final_screen_clearing:
                return True
        return False
    
    def _should_slow_down_loop_iterations(self) -> bool:
        """
        If we have paints in the defined queues to slow down (and not in the others), we say yes.
        """
        # queues_with_interactions = []
        self._log_debug(f"🎨 Queues with paints: {[queue_name for queue_name in self.queue if self.get_current_interaction(queue_name) is not None]}")
        self._log_debug(f"🎨 Queues defined to slow down the loop: {self.queues_with_paints_that_slow_down_the_loop}")
        for queue_name in self.queue:
            current_interaction = self.get_current_interaction(queue_name)
            # if current_interaction is None and queue_name in self.queues_with_paints_that_slow_down_the_loop:
            #     # This queue should have a paint. Early exit.
            #     # self._log_debug
            #     return False
            if current_interaction is not None and queue_name not in self.queues_with_paints_that_slow_down_the_loop:
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

        # In case that we received anything with priority, we remove the previous interactions of the same queue, to give it the inmediate priority.
        if interaction.command.included_in(self.priority_interactions[queue_name]):
            self._log_debug(f"Received {queue_name} interaction [{interaction.name}] is priority. Removing previous interactions from the queue.")
            self.remove_all_interactions_from_queue(queue_name)

        # In case we have anything from the same type waiting to be shown, we discard it first.
        #   If we didn't show it yet, there is no point to keep waiting, the flow already went somewhere else.
        self._remove_duplicated_interaction_types_from_queue(interaction, queue_name)

        # In case that the current interaction is set to stay after painting, it could stay forever,
        #   actually blocking anything else that comes afterwards.
        # When it's managed by the busy flags, it will be removed whenever the flag changes,
        #   but when it's a normal one, we should simply remove the current one once we get a new one.
        current_interaction = self.get_current_interaction(queue_name)
        if current_interaction is not None and \
            current_interaction.while_shared_memory_flag is None and \
            not current_interaction.remove_interaction_after_painting:
            self._log_debug(f"Current {queue_name} interaction [{current_interaction.name}] is set to stay after painting, but we received a new {queue_name} interaction [{interaction.name}]. Removing the current one to give priority to the new one.")
            self._remove_interaction(interaction=current_interaction, queue_name=queue_name)
        
        # If we're meant to keep the interaction for an amount of seconds, set up a scheduler to remove it after the defined time.
        if interaction.maintain_paint_for_seconds is not None:
            self._log_debug(f"{queue_name} interaction [{interaction.name}] is meant to be maintained for [{interaction.maintain_paint_for_seconds}] seconds. Setting up a scheduler to remove it after the defined time.")
            def remove_interaction_after_time():
                self._log_debug(f"Scheduler triggered to remove {queue_name} interaction [{interaction.name}] after maintaining it for [{interaction.maintain_paint_for_seconds}] seconds.")
                self._remove_interaction(interaction=interaction, queue_name=queue_name)
                # The following lines are to clean the screen after removing the interaction.
                # ⚠️ This does not stand for long. Any waiting_for_seconds besides idle will produce
                #   a full screen clearing after the time is over, which is not ideal. 
                # if interaction.final_screen_clearing:
                #     self._log_debug(f"Scheduler for {queue_name} interaction [{interaction.name}] is performing a final screen clearing as requested by the interaction.")
                self._full_clear()
                self.flush_drawing()
            self._timer[interaction.get_cache_key()] = threading.Timer(interaction.maintain_paint_for_seconds, remove_interaction_after_time)
            self._timer[interaction.get_cache_key()].start()

        # Now add the new interaction to the queue
        self.queue[queue_name].append(interaction)

        self._log_debug(f"The {queue_name} queue after setting last: {', '.join([item.get_cache_key() for item in self.queue[queue_name]])}.")
    
    def get_current_interaction(self, queue_name: PainterQueue) -> BasePaint | None:
        current_paint = self.queue[queue_name][0] if len(self.queue[queue_name]) > 0 else None
        if current_paint is None:
            return None
        return current_paint

    def _remove_interaction(self, interaction: BasePaint, queue_name: PainterQueue):
        self._log_debug(f"Removing interaction [{interaction.name}] from [{queue_name}] queue.")
        if len(self.queue[queue_name]) > 0:
            if self.queue[queue_name][0].name == interaction.name:
                self.queue[queue_name].pop(0)
                # When we remove an interaction, we also:
                #   - Clean the cache related to it, to avoid retrieving it again if it comes back in the future.
                #   - Reset the starting time for the interaction, to avoid issues with the maintain_paint_for_seconds parameter.
                self.reset_interaction_artifacts(queue_name)
                self._log_debug(f"Interaction [{interaction.name}] removed from [{queue_name}] queue successfully.")
                # Removing the interaction means to stop drawing it.
                # It's the moment to check for a final cleaning requests from the callbacks.
                if interaction.final_screen_clearing:
                    name=f"{IntermediatePainterQueueAction.REMOVE}_{interaction.name}"
                    self._log_debug(f"🔃 Painter callback [{name}] for [{queue_name}]: Final ScreenClearing intended, telling to painter loop")
                    if queue_name not in self.flags_callback_returned_requests:
                        self.flags_callback_returned_requests[queue_name] = {}
                    if name not in self.flags_callback_returned_requests[queue_name]:
                        self.flags_callback_returned_requests[queue_name][name] = {}
                    self.flags_callback_returned_requests[queue_name][name]["final_screen_clearing_needed"] = True
                if interaction.final_area_clearing:
                    name=f"{IntermediatePainterQueueAction.REMOVE}_{interaction.name}"
                    self._log_debug(f"🔃 Painter callback [{name}] for [{queue_name}]: Final Area Clearing intended, telling to painter loop")
                    if queue_name not in self.flags_callback_returned_requests:
                        self.flags_callback_returned_requests[queue_name] = {}
                    if name not in self.flags_callback_returned_requests[queue_name]:
                        self.flags_callback_returned_requests[queue_name][name] = {}
                    self.flags_callback_returned_requests[queue_name][name]["final_area_clearing_needed"] = True
            else:
                # Could be that meanwhile anything else with more priority (or a dupe) came in and then
                #   the "current" one was already removed.
                self._log_debug(f"🟠 Interaction [{interaction.name}] is not the current one. Skipping.")
                current_queue = ", ".join([item.name for item in self.queue[queue_name]])
                self._log_debug(f"Current [{queue_name}] interaction queue: [{current_queue}].")

    def remove_all_interactions_from_queue(self, queue_name: PainterQueue):
        self._log_debug(f"Removing all {queue_name} interactions.")
        self.queue[queue_name] = []
        self.reset_interaction_artifacts(queue_name)
        # Cancel any timers associated with interactions in this queue
        for interaction_cache_key, timer in list(self._timer.items()):
            self._log_debug(f"Cancelling timer for interaction cache key [{interaction_cache_key}].")
            timer.cancel()
            del self._timer[interaction_cache_key]
    
    def reset_interaction_artifacts(self, queue_name: PainterQueue):
        self._log_debug(f"Resetting interaction artifacts for queue [{queue_name}].")
        self.previous_interaction_by_queue[queue_name]["interaction"] = None
        self.previous_interaction_by_queue[queue_name]["cache_key"] = None
        self.previous_interaction_by_queue[queue_name]["image"] = None
    
    def _remove_duplicated_interaction_types_from_queue(self, interaction: BasePaint, queue_name: PainterQueue):
        """
        Removes previous duplicated interactions of the same type as the given one from the corresponding queue.
        Keeps only the given interaction.

        Useful for scenarios like the init_phase when next phase comes and we didn't show the previous one.

        Args:
            interaction (BasePaint): The interaction to compare with the ones in the queue. We will remove the ones with the same type as this one.
            queue_name (str): The name of the queue to remove the duplicated interactions from.
        """

        current_interaction = self.get_current_interaction(queue_name)
        queue = self.queue[queue_name]
        
        new_queue = []
        for item in queue:
            # Over the interactions with the same type, 
            if item.command.matches(interaction.command.get()):
                # We keep the current interaction being painted, to avoid fucking up the current painting loop iteration.
                # Unless it is explicitly defined.
                if current_interaction is not None and item.get_cache_key() == current_interaction.get_cache_key() and \
                    item.overwrite_current_interaction_with_same_type == False:
                    new_queue.append(item)
                # We keep the given interaction as parameter. This function is called at the moment of setting a new interaction,
                #   so we actually shouldn't end up here ever.
                elif item.get_cache_key() == interaction.get_cache_key():
                    new_queue.append(item)
                # We skip adding the duplicated interaction to the new queue
                else:
                    self._log_debug(f"Removing previous duplicated interaction [{item.get_cache_key()}] from the queue.")
            # All the rest interaction types are kept.
            else:
                new_queue.append(item)
        
        self.queue[queue_name] = new_queue
    
    def _initialize_draw_for_queue(self, queue_name: PainterQueue) -> Image.Image:
        # We create a new image to draw the interaction, based on the size of the layout position corresponding to this queue.
        layout_position_name = self.queue_name_to_layout_position[queue_name]
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

        if self._worker_thread is not None and self._worker_thread.is_alive():
            self._xlog.debug("Joining Painter worker thread.")
            self._worker_thread.join(timeout=2)
            if self._worker_thread.is_alive():
                self._xlog.warning("Painter worker thread did not finish in time.")
            else:
                self._xlog.debug("Painter worker thread finished successfully.")
        else:
            self._xlog.debug("Painter worker thread is not alive or was never started.")
        
        for interaction_cache_key, timer in self._timer.items():
            self._log_debug(f"Cancelling timer for interaction cache key [{interaction_cache_key}].")
            timer.cancel()
        self._timer = {}
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
    
    def resume_paint(self):

        # If we're actually not running anything inside the thread, do it now.
        if not self._thread_event.is_set():
            self._log_debug("Painter thread not running, starting it now.")

            for queue_name in self.queue.keys():
                self.image_per_queue[queue_name] = self._initialize_draw_for_queue(queue_name)
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
    
    def load_painter_shared_memory_list_to_control(self, shared_memory_list_to_control: list[tuple[int, bool, callable]]):
        """
        A shortcut to load a list of shared memory flags to control in the painter_shared_memory instance.
        Useful to load several in one shot, for example some default ones like THINKING or SPEAKING.
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
            self._log_debug(f"🔃 Painter callback [{name}] for [{queue_name}]: [{flag_name.upper()}] busy flag changed to [{for_value}], {"with" if extra_callback is not None else "without"} extra callback.")

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