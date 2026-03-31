import sys
import unittest
from unittest.mock import MagicMock, patch

import core.action_runner as action_runner_mod
from core.action_runner import ActionRunner


class ActionRunnerCmdTests(unittest.TestCase):
    @patch.object(sys, "platform", "win32")
    @patch.object(action_runner_mod.platform_utils, "run_command")
    def test_cmd_uses_value_windows_on_windows(self, mock_run: MagicMock) -> None:
        runner = ActionRunner(
            logger=lambda _msg: None,
            on_profile_change=lambda _name: None,
            on_toggle_flag=lambda _name: False,
        )
        runner.run_pad_action(
            {
                "type": "cmd",
                "value": "linux-cmd",
                "value_windows": "windows-cmd",
            },
            note=76,
            velocity=127,
        )
        mock_run.assert_called_once_with("windows-cmd")

    @patch.object(sys, "platform", "linux")
    @patch.object(action_runner_mod.platform_utils, "run_command")
    def test_cmd_uses_value_when_not_windows(self, mock_run: MagicMock) -> None:
        runner = ActionRunner(
            logger=lambda _msg: None,
            on_profile_change=lambda _name: None,
            on_toggle_flag=lambda _name: False,
        )
        runner.run_pad_action(
            {
                "type": "cmd",
                "value": "linux-cmd",
                "value_windows": "windows-cmd",
            },
            note=76,
            velocity=127,
        )
        mock_run.assert_called_once_with("linux-cmd")

    @patch.object(sys, "platform", "msys")
    @patch.object(action_runner_mod.platform_utils, "run_command")
    def test_cmd_uses_value_windows_on_msys(self, mock_run: MagicMock) -> None:
        runner = ActionRunner(
            logger=lambda _msg: None,
            on_profile_change=lambda _name: None,
            on_toggle_flag=lambda _name: False,
        )
        runner.run_pad_action(
            {
                "type": "cmd",
                "value": "bash -lc true",
                "value_windows": "windows-cmd",
            },
            note=76,
            velocity=127,
        )
        mock_run.assert_called_once_with("windows-cmd")


if __name__ == "__main__":
    unittest.main()
