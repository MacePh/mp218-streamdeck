"""Reserved pads must still allow dictate (and related) actions when configured."""

from __future__ import annotations

import unittest
from unittest import mock

from core.app import ControlSurfaceApp, _RESERVED_PAD_ALLOWED_TYPES
from core.profile_manager import ProfileManager
from core.state_manager import StateManager


class ReservedPadDictateTests(unittest.TestCase):
    def test_dictate_types_in_reserved_allowlist(self) -> None:
        for t in (
            "dictate",
            "dictate_to_telegram",
            "dictate_to_markdown",
            "dictate_to_openclaw",
        ):
            self.assertIn(t, _RESERVED_PAD_ALLOWED_TYPES)

    def test_reserved_pad_runs_dictate_not_blocked(self) -> None:
        app = ControlSurfaceApp(config_path="config.json")
        app.log = lambda _m: None
        app.config = {
            "controller": {
                "default_profile": "dev",
                "manual_lock_seconds": 8,
                "hud_pad": 67,
                "log_midi_input": False,
            },
            "midi": {"pad_note_range": {"min": 36, "max": 83}, "pad_channel": 9},
            "led": {"reserved_pads": [81], "press_flash_seconds": 0.05},
            "profiles": {"dev": {"pads": {"81": {"type": "dictate", "model": "base.en", "language": "en"}}}},
            "hud": {"enabled": False},
        }
        app.profile_manager = ProfileManager(app.config)
        app.state = StateManager(active_profile="dev", flags={})
        app.hud_manager = None
        app.led = mock.Mock()
        app.led.pressed_brightness = 127
        app.led.press_flash_seconds = 0.05
        app.action_runner = mock.Mock()
        app.action_runner.run_pad_action.return_value = False

        app.handle_pad_press(81, 127, 9)
        app.action_runner.run_pad_action.assert_called_once()


if __name__ == "__main__":
    unittest.main()
