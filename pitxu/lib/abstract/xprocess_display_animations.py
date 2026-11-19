import logging

from pyxavi import Config

from pitxu.lib.abstract.xprocess import Xprocess
from pitxu.lib.objects import XprocAction

class XprocessDisplayAnimations(Xprocess):
    '''
    Class to define the protocol for Display animations processes.
    The animations are the emojis shown in their own area of the screen.
    '''

    VERBOSE_DEBUG: bool = False

    def run_with_context(self, config: Config, logger: logging, action: XprocAction, param: any):
        # We're busy
        self._log_debug("XprocessDisplayAnimations: Starting to process action, setting busy status.")
        self.set_busy()

        self._run_animations_interaction(config, logger, action, param)

        # Now we're not
        self._log_debug("XprocessDisplayAnimations: Finished processing action, unsetting busy status.")
        self.unset_busy()

    def _run_animations_interaction(self, config: Config, logger: logging, action: XprocAction, param: any):

        # Loads the animations. It takes time, so it is triggered after the display shows something.
        if action == XprocAction.INITIALIZE_ANIMATIONS:
            self._log_debug("XprocessDisplayAnimations: Initializing animations in Visualizer.")
            self.initialize_animations()

        # Show the thinking animation. Every display decides what it is.
        if action == XprocAction.THINKING:
            self.show_thinking()

        # Clears the animations area only
        if action == XprocAction.ANIMATIONS_CLEAR or action == XprocAction.SOFT_CLEAR:
            self._log_debug("XprocessDisplayAnimations: Clearing animations area only.")
            self.clear_animations()

        # Now see if we need to do any extended action for the given action.
        self.extended_animations_run(config, logger, action, param)

    def extended_animations_run(self, config: Config, logger: logging, action: XprocAction, param: any):
        """
        This is called from _run_animations_interaction(), allowing for child classes
        to easily extend the actions they manage without needing to override the whole method.
        """
        pass

    # ------- Common functions ---------

    def clear(self):
        raise NotImplementedError("clear() must be implemented in Display Animations subclasses.")

    def soft_clear(self):
        raise NotImplementedError("soft_clear() must be implemented in Display Animations subclasses.")

    # The clear for animations only
    def clear_animations(self):
        raise NotImplementedError("clear_animations() must be implemented in Display Animations subclasses.")

    def get_canvas_handler(self):
        raise NotImplementedError("get_canvas_handler() must be implemented in Display Animations subclasses.")

    # ------- Animations Interaction functions ---------

    def initialize_animations(self):
        raise NotImplementedError("initialize_animations() must be implemented in Display Animations subclasses.")

    def show_thinking(self):
        raise NotImplementedError("show_thinking() must be implemented in Display Animations subclasses.")

    # ------- Communication with Flags ---------

    # Display busy control: is it already busy?
    def is_busy(self):
        return self.read_shared_memory_flag(self.get_busy_flag())

    # Display busy control: set as busy
    def set_busy(self):
        self.write_shared_memory_flag(self.get_busy_flag(), True)

    # Display busy control: unset as busy
    def unset_busy(self):
        self.write_shared_memory_flag(self.get_busy_flag(), False)
