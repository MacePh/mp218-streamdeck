"""
Pad 48 is configured as restart in profiles; verify the app wires MIDI press -> restart request.

Also verifies Windows uses subprocess spawn (os.execv is unreliable for some console/venv launches).
"""

from __future__ import annotations

import os
import sys
import unittest
from unittest import mock

from core.action_runner import ActionRunner
from core.app import ControlSurfaceApp
from core.profile_manager import ProfileManager
from core.state_manager import StateManager


def _minimal_config_with_restart_on_48() -> dict:
    return {
        "controller": {
            "default_profile": "dev",
            "manual_lock_seconds": 8,
            "hud_pad": 67,
            "log_midi_input": False,
            "hot_reload_interval_ms": 750,
            "hud_duration_seconds": 6,
        },
        "midi": {
            "input_port": "dummy",
            "output_port": "dummy",
            "auto_detect_ports": False,
            "pad_note_range": {"min": 36, "max": 83},
            "pad_channel": 9,
        },
        "led": {
            "pressed_brightness": 127,
            "press_flash_seconds": 0.05,
            "profile_idle_brightness": {"dev": 60},
            "reserved_pads": [],
            "indicator_pads": {},
            "animations": {},
        },
        "profiles": {
            "dev": {
                "pads": {
                    "48": {"type": "restart"},
                },
            },
        },
        "hud": {"enabled": False},
        "context_profiles": {},
        "status_flags_defaults": {},
    }


class AppRestartPad48Tests(unittest.TestCase):
    def setUp(self) -> None:
        self.app = ControlSurfaceApp(config_path="config.json")
        self.app.log = lambda _msg: None
        self.app.config = _minimal_config_with_restart_on_48()
        self.app.profile_manager = ProfileManager(self.app.config)
        self.app.state = StateManager(active_profile="dev", flags={})
        self.app.hud_manager = None
        self.app.led = mock.Mock()
        self.app.led.pressed_brightness = 127
        self.app.led.press_flash_seconds = 0.05
        self.app.action_runner = ActionRunner(
            logger=lambda _m: None,
            on_profile_change=lambda _n: None,
            on_toggle_flag=lambda _f: False,
            on_restart=self.app._request_restart,
        )

    def test_pad_48_press_sets_restart_requested(self) -> None:
        self.assertFalse(self.app._restart_requested)
        self.app.handle_pad_press(48, 127, 9)
        self.assertTrue(
            self.app._restart_requested,
            "restart action should set _restart_requested so run_loop exits and _exec_restart runs",
        )

    def test_profile_resolve_restart_action_for_48(self) -> None:
        self.assertEqual(
            self.app.profile_manager.get_pad_action(48),
            {"type": "restart"},
        )


class ExecRestartTests(unittest.TestCase):
    def test_windows_restart_spawns_subprocess_and_exits(self) -> None:
        if os.name != "nt":
            self.skipTest("Windows-only subprocess restart path")

        app = ControlSurfaceApp(config_path=os.path.abspath("config.json"))
        app.log = lambda _m: None
        argv_holder: list[list[str]] = []

        class _FakePopen:
            def __init__(self, argv: list[str], cwd: str | None = None, **_kw: object) -> None:
                argv_holder.append(list(argv))
                self.cwd = cwd

        with mock.patch.object(sys, "executable", "C:\\Python\\python.exe"):
            with mock.patch("core.app.subprocess.Popen", side_effect=_FakePopen) as popen:
                with mock.patch("core.app.os._exit", side_effect=SystemExit(0)):
                    with self.assertRaises(SystemExit) as ctx:
                        app._exec_restart()
                    self.assertEqual(ctx.exception.code, 0)

        self.assertEqual(len(argv_holder), 1)
        self.assertIn("controller.py", argv_holder[0][1].replace("/", os.sep))
        self.assertEqual(argv_holder[0][2:], ["--config", os.path.abspath("config.json")])
        popen.assert_called_once()

    def test_unix_restart_uses_execv(self) -> None:
        if os.name == "nt":
            self.skipTest("execv path is non-Windows")

        app = ControlSurfaceApp(config_path="/tmp/config.json")
        with mock.patch("core.app.os.execv") as execv:
            app._exec_restart()
        execv.assert_called_once()


if __name__ == "__main__":
    unittest.main()
