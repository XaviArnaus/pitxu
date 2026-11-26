"""Dimming the display while idle: the IdleDimmer and the brightness of DisplayControl."""
import os
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from support import *  # noqa: F401,F403  (the stand-ins for pyxavi and the quiet logger, when needed)

from pitxu.lib.canvas_v2.idle_dimmer import IdleDimmer
from pitxu.lib.hardware import DisplayControl


class FakeDevice:
    def __init__(self, works=True):
        self.calls, self.works = [], works

    def set_brightness(self, percent):
        self.calls.append(percent)
        return self.works


class FakeConfig:
    def __init__(self, values=None):
        self.values = values or {}

    def get(self, key, default=None):
        return self.values.get(key, default)


def make_dimmer(device, **settings):
    """The dimmer as the Visualizer builds it: config + params with the device."""
    values = {f"dsi_lcd.idle_dimming.{key}": value for key, value in settings.items()}
    params = Dictionary()
    if device is not None:
        params.set("device", device)
    return IdleDimmer(FakeConfig(values), params)


class IdleDimmerTests(unittest.TestCase):

    def test_01_dims_when_idle_and_restores_when_awake(self):
        device = FakeDevice()
        dimmer = make_dimmer(device, brightness_percent=10, active_percent=100)
        dimmer.dim()
        dimmer.restore()
        self.assertEqual(device.calls, [10, 100])

    def test_02_the_same_level_is_not_written_twice(self):
        device = FakeDevice()
        dimmer = make_dimmer(device, brightness_percent=10, active_percent=100)
        dimmer.dim()
        dimmer.dim()
        self.assertEqual(device.calls, [10])

    def test_03_the_last_request_wins_on_a_quick_toggle(self):
        device = FakeDevice()
        dimmer = make_dimmer(device, brightness_percent=10, active_percent=80)
        dimmer.dim()
        dimmer.restore()
        dimmer.dim()
        dimmer.restore()
        self.assertEqual(device.calls, [10, 80, 10, 80])

    def test_04_a_failed_write_is_tried_again(self):
        device = FakeDevice(works=False)
        dimmer = make_dimmer(device, brightness_percent=10)
        dimmer.dim()
        dimmer.dim()
        self.assertEqual(device.calls, [10, 10])

    def test_05_an_error_of_the_device_does_not_propagate(self):
        device = FakeDevice()
        device.set_brightness = mock.Mock(side_effect=OSError("boom"))
        make_dimmer(device).dim()  # Must not raise
        device.set_brightness.assert_called_once()

    def test_06_the_configured_levels_are_used(self):
        device = FakeDevice()
        dimmer = make_dimmer(device, brightness_percent=0, active_percent=60)
        dimmer.dim()
        dimmer.restore()
        self.assertEqual(device.calls, [0, 60])

    def test_07_without_config_the_defaults_are_used(self):
        device = FakeDevice()
        dimmer = make_dimmer(device)
        self.assertTrue(dimmer.is_enabled())
        dimmer.dim()
        dimmer.restore()
        self.assertEqual(device.calls, [10, 100])

    def test_08_it_can_be_disabled_by_config(self):
        self.assertFalse(make_dimmer(FakeDevice(), enabled=False).is_enabled())

    def test_09_the_device_is_required(self):
        with self.assertRaises(ValueError):
            make_dimmer(None)


class DisplayControlBrightnessTests(unittest.TestCase):

    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.dir.cleanup)
        self.max_path = os.path.join(self.dir.name, "max_brightness")
        self.path = os.path.join(self.dir.name, "brightness")
        with open(self.max_path, "w") as f:
            f.write("255\n")
        with open(self.path, "w") as f:
            f.write("200\n")

    def _ok(self):
        return mock.Mock(returncode=0, stderr=b"")

    def test_01_reads_the_values(self):
        self.assertEqual(DisplayControl.max_brightness(self.max_path), 255)
        self.assertEqual(DisplayControl.brightness(self.path), 200)

    def test_02_unreadable_values_are_none(self):
        self.assertIsNone(DisplayControl.brightness(os.path.join(self.dir.name, "nope")))

    def test_03_percent_is_translated_to_the_panel_scale(self):
        with mock.patch("pitxu.lib.hardware.display_control.run", return_value=self._ok()) as run:
            self.assertTrue(DisplayControl.set_brightness(10, self.path, self.max_path))
        # 10% of 255 is 25.5, rounded.
        self.assertIn("echo 26 >", run.call_args[0][0][-1])

    def test_04_out_of_range_percents_are_clamped(self):
        with mock.patch("pitxu.lib.hardware.display_control.run", return_value=self._ok()) as run:
            DisplayControl.set_brightness(500, self.path, self.max_path)
            self.assertIn("echo 255 >", run.call_args[0][0][-1])
            DisplayControl.set_brightness(-5, self.path, self.max_path)
            self.assertIn("echo 0 >", run.call_args[0][0][-1])

    def test_05_without_max_brightness_nothing_is_written(self):
        with mock.patch("pitxu.lib.hardware.display_control.run") as run:
            self.assertFalse(DisplayControl.set_brightness(10, self.path, os.path.join(self.dir.name, "nope")))
        run.assert_not_called()

    def test_06_a_failing_command_returns_false(self):
        failed = mock.Mock(returncode=1, stderr=b"denied")
        with mock.patch("pitxu.lib.hardware.display_control.run", return_value=failed):
            self.assertFalse(DisplayControl.set_brightness(10, self.path, self.max_path))
        with mock.patch("pitxu.lib.hardware.display_control.run", side_effect=subprocess.TimeoutExpired("sudo", 5)):
            self.assertFalse(DisplayControl.set_brightness(10, self.path, self.max_path))


if __name__ == "__main__":
    unittest.main()
