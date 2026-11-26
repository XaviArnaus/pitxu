"""The announcement: what Pitxu shows by itself (a reminder) lives by its own flag, not by the speech."""
import os
import sys
import types
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from support import *  # noqa: F401,F403
import definitions

VISUALIZER = "pitxu/lib/canvas_v2/visualizer.py"


class Capture:
    """ Stands in for the paints: keeps how it was built. """
    def __init__(self, **kwargs):
        self.__dict__.update(kwargs)


class FakePainter:
    def __init__(self): self.painted = []
    def paint(self, paint_object): self.painted.append(paint_object)


class FakeAnimations:
    FRAMES = {"reminder": 12, "smile-small": 8}
    def get_animation(self, name):
        if name not in self.FRAMES:
            raise KeyError(name)
        return types.SimpleNamespace(get_frame_count=lambda: self.FRAMES[name])


def visualizer():
    Holder = methods_of(VISUALIZER, ["_arbitrary_text_while_flag", "arbitrary_text_while_speaking",
                                     "_animation_while_flag", "animation_while_speaking", "arbitrary_text_while_announcing",
                                     "animation_while_announcing"], {
        "ForegroundPaint": Capture, "AnimationPaint": Capture,
        "PaintObject": lambda paints_by_queue: types.SimpleNamespace(paints=paints_by_queue),
        "PainterQueue": types.SimpleNamespace(FOREGROUND="foreground", ANIMATIONS="animations"),
        "ForegroundCommand": type("ForegroundCommand", (), {"ARBITRARY_TEXT_ICON": "text", "__init__": lambda self, c: None}),
        "AnimationsCommand": type("AnimationsCommand", (), {"EMOTION": "emotion", "__init__": lambda self, c: None}),
        "SHARED_SPEAKER_BUSY": definitions.SHARED_SPEAKER_BUSY,
        "SHARED_ANNOUNCEMENT_BUSY": definitions.SHARED_ANNOUNCEMENT_BUSY,
    })
    v = Holder()
    v.painter, v.animations, v._xlog = FakePainter(), FakeAnimations(), Log()
    v.macros_foreground = types.SimpleNamespace(draw_arbitrary_text_with_icon=lambda *a: None)
    v.macros_animation = types.SimpleNamespace(merge_animation=lambda *a: None)
    v.interaction_delays = {}
    return v


class FlagTests(unittest.TestCase):

    def test_01_the_flag_is_the_next_one_and_the_shared_list_has_room_for_it(self):
        self.assertEqual(definitions.SHARED_ANNOUNCEMENT_BUSY, 18)
        source = read_file(os.path.join(REPO, "pitxu/lib/core/shared_memory_manager.py"))
        block = source[source.index("self._shared_memory_flags = shared_memory.ShareableList(["):source.index("], name=SHARED_MEMORY_FLAGS)")]
        entries = [line for line in block.splitlines() if line.strip().startswith("False,")]
        flags = [value for name, value in vars(definitions).items() if name.startswith("SHARED_") and name in
                 ("SHARED_SPEAKER_BUSY", "SHARED_EINK_BUSY", "SHARED_MATRIX_BUSY", "SHARED_LCD_BUSY", "SHARED_DSI_LCD_BUSY",
                  "SHARED_MICROPHONE_MUTED", "SHARED_CHATBOT_BUSY", "SHARED_CHATBOT_ANSWER_IS_ERROR", "SHARED_IDLE_MODE",
                  "SHARED_LCD_IDLE_MODE", "SHARED_DSI_LCD_IDLE_MODE", "SHARED_NETWORK_BUSY", "SHARED_VAD_DETECTED",
                  "SHARED_SUPPORT_BUSY", "SHARED_STT_BUSY", "SHARED_TRANSCRIBER_BUSY", "SHARED_WAKE_UP_BUTTON_PRESSED",
                  "SHARED_SPEECH_INTERRUPT_REQUESTED", "SHARED_ANNOUNCEMENT_BUSY")]
        self.assertEqual(len(entries), len(flags))
        self.assertEqual(sorted(flags), list(range(len(flags))))

    def test_02_it_is_known_by_the_painter_the_busy_waiters_and_the_closing(self):
        source = read_file(os.path.join(REPO, "pitxu/lib/core/shared_memory_manager.py"))
        self.assertIn('"announcement_busy": SHARED_ANNOUNCEMENT_BUSY', source)           # _shared_flags: closing and waiters
        self.assertIn('SHARED_ANNOUNCEMENT_BUSY: "announcement_busy"', source)           # _map_index_to_flag: the painter checks it

    def test_03_the_interaction_raises_lowers_and_reads_it(self):
        source = read_file(os.path.join(REPO, "pitxu/lib/interaction/interaction.py"))
        for name in ["set_announcement_busy", "unset_announcement_busy", "is_announcement_busy",
                     "show_arbitrary_text_on_foreground_while_announcing", "show_animation_while_announcing",
                     "wait_for_animation_display_queue_to_empty", "wait_for_busy_animation_display_to_idle"]:
            self.assertIn(f"def {name}(", source)
        # It is not part of "an interaction is going on": the hold of the announcement itself would look like one.
        busy = source[source.index("def get_busy_interaction_flags"):source.index("def set_wake_up_button_pressed")]
        self.assertNotIn("announcement", busy)


class PlumbingTests(unittest.TestCase):
    """ The same way as the ones while speaking: the text to the foreground display, the animation to the animations one. """

    def test_01_each_action_goes_to_its_display_and_the_others_ignore_it(self):
        actions = read_file(os.path.join(REPO, "pitxu/lib/objects/xproc_action.py"))
        for name in ["SHOW_ARBITRARY_TEXT_FOREGROUND_ANNOUNCING", "SHOW_ANIMATION_WHILE_ANNOUNCING"]:
            self.assertIn(f'{name}: str = "{name}"', actions)
        self.assertIn("XprocAction.SHOW_ARBITRARY_TEXT_FOREGROUND_ANNOUNCING", read_file(os.path.join(REPO, "pitxu/lib/interaction/shortcuts/foreground.py")))
        self.assertIn("XprocAction.SHOW_ANIMATION_WHILE_ANNOUNCING", read_file(os.path.join(REPO, "pitxu/lib/interaction/shortcuts/animations.py")))
        foreground = read_file(os.path.join(REPO, "pitxu/lib/abstract/xprocess_display_foreground.py"))
        self.assertIn("self.show_arbitrary_text_while_announcing(param)", foreground)
        self.assertIn("Ignoring it", foreground[foreground.index("def show_arbitrary_text_while_announcing"):][:300])
        animations = read_file(os.path.join(REPO, "pitxu/lib/abstract/xprocess_display_animations.py"))
        self.assertIn("self.show_animation_while_announcing(param)", animations)
        self.assertIn("Ignoring it", animations[animations.index("def show_animation_while_announcing"):][:300])
        lcd = read_file(os.path.join(REPO, "pitxu/lib/dsi_lcd/dsi_lcd.py"))
        self.assertIn("self.visualizer.arbitrary_text_while_announcing(param)", lcd)
        self.assertIn("self.visualizer.animation_while_announcing(param)", lcd)

    def test_02_the_waits_use_the_queue_of_the_animations_display(self):
        source = read_file(os.path.join(REPO, "pitxu/lib/interaction/interaction.py"))
        self.assertIn("wait_for_queue_to_empty(self.animations.get_queue())", source)
        self.assertIn("self.animations.get_display_busy_flag()", source)


class VisualizerTests(unittest.TestCase):

    def test_01_the_announcement_text_and_animation_live_by_the_announcement_flag_each_in_its_area(self):
        v = visualizer()
        v.arbitrary_text_while_announcing({"icon": "📝", "text": "milk", "header": "Reminders"})
        v.animation_while_announcing({"animation": "reminder"})
        text, animation = (p.paints for p in v.painter.painted)
        self.assertEqual(set(text), {"foreground"})
        self.assertEqual(set(animation), {"animations"})
        for paint in (text["foreground"], animation["animations"]):
            self.assertEqual(paint.while_shared_memory_flag, definitions.SHARED_ANNOUNCEMENT_BUSY)
            self.assertTrue(paint.while_shared_memory_flag_value)
        self.assertEqual(text["foreground"].name, "ArbitraryContentWhileAnnouncingForegroundPaint")
        self.assertEqual(text["foreground"].drawing_callback_parameters, {"icon": "📝", "text": "milk", "header": "Reminders"})
        self.assertEqual(animation["animations"].name, "AnimationWhileAnnouncingAnimationPaint_reminder")
        self.assertEqual(animation["animations"].loop_iterations, 11)
        self.assertEqual(animation["animations"].drawing_callback_parameters, {"animation": "reminder"})

    def test_02_an_unavailable_animation_paints_nothing(self):
        v = visualizer()
        v.animation_while_announcing({"animation": "nope"})
        self.assertEqual(v.painter.painted, [])

    def test_03_the_speaking_ones_still_live_by_the_speaker_flag(self):
        v = visualizer()
        v.arbitrary_text_while_speaking({"text": "hi"})
        v.animation_while_speaking({"animation": "smile-small"})
        text, animation = (p.paints for p in v.painter.painted)
        self.assertEqual(text["foreground"].while_shared_memory_flag, definitions.SHARED_SPEAKER_BUSY)
        self.assertEqual(text["foreground"].name, "ArbitraryContentWhileSpeakingForegroundPaint")
        self.assertEqual(animation["animations"].while_shared_memory_flag, definitions.SHARED_SPEAKER_BUSY)
        self.assertEqual(animation["animations"].name, "AnimationWhileSpeakingAnimationPaint_smile-small")
        v.animation_while_speaking({"animation": "nope"})
        self.assertEqual(len(v.painter.painted), 2)  # nothing painted for an animation that is not there


class ConfigTests(unittest.TestCase):

    def test_01_the_reminder_animation_is_defined_and_exists(self):
        config = read_yaml(os.path.join(REPO, "config/animations.yaml.dist"))["animations"]
        self.assertEqual(config["reminder"], "reminder")
        composite = config["composites"]["reminder"]
        self.assertEqual((composite["base"], composite["badge"], composite["position"]), ("smile-small", "bell", "top-right"))
        for name in (composite["base"], composite["badge"]):
            self.assertIn(name, config["map"])
            self.assertTrue(os.path.exists(os.path.join(REPO, config["path"], config["map"][name])), name)
        # Same look as the listening one, with another badge.
        listening = config["composites"]["listening"]
        self.assertEqual((composite["base"], composite["badge_scale"]), (listening["base"], listening["badge_scale"]))


if __name__ == "__main__":
    unittest.main()
