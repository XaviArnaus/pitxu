from pyxavi import Config, Dictionary

from pitxu.lib.objects import XprocAction
from pitxu.lib.interaction.shortcuts.shortcut_base import ShortcutBase

class Animations(ShortcutBase):
    """
    Shortcuts to send interactions to the animations display
    """

    VERBOSE_DEBUG: bool = True

    def __init__(self, config: Config = None, params: Dictionary = None):
        super(Animations, self).__init__(config=config, params=params)

        self._xlog.info("Initializing Animations interaction shortcuts.")

    # --------- (Proxy) Functions to trigger interactions ---------

    def initialize_animations(self):
        """
        Asks the display to load its animations. It takes time, so it is meant to be called
        once the display shows something, otherwise the user is left with a black screen meanwhile.
        """

        self._log_debug("🎞️ Triggering the loading of the animations on animations display.")

        self.process_pool.send(self.get_queue(), XprocAction.INITIALIZE_ANIMATIONS)

    def show_thinking(self):
        """
        Triggers a "thinking" interaction on the animations display.

        This needs the SHARED_CHATBOT_BUSY flag to be set by the Chatbot/Main process.
        """

        self._log_debug("🤖 Triggering thinking interaction on animations display.")

        self.process_pool.send(self.get_queue(), XprocAction.THINKING)

    def show_animation_while_speaking(self, animation: str):
        """
        Shows an animation (one of `animations.map`) on the animations display, for as long as the speaker is busy.

        This needs the SHARED_SPEAKER_BUSY flag to be set by the Text To Speech process.
        """

        self._log_debug(f"🎞️ Triggering animation [{animation}] while speaking on animations display.")

        self.process_pool.send(self.get_queue(), XprocAction.SHOW_ANIMATION_WHILE_SPEAKING, {
            "animation": animation
        })

    def show_animation_while_announcing(self, animation: str):
        """
        Shows an animation (one of `animations.map` or `animations.composites`) on the animations display,
        for as long as the announcement flag is up (SHARED_ANNOUNCEMENT_BUSY).
        """

        self._log_debug(f"🎞️ Triggering animation [{animation}] while announcing on animations display.")

        self.process_pool.send(self.get_queue(), XprocAction.SHOW_ANIMATION_WHILE_ANNOUNCING, {
            "animation": animation
        })

    # --------- (Proxy) Functions to clear screens ---------

    def soft_clear(self):
        self.process_pool.send(self.get_queue(), XprocAction.ANIMATIONS_CLEAR)
