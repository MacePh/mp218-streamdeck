import unittest
from unittest.mock import MagicMock, patch

import core.action_runner as action_runner_mod
import core.openclaw_env as openclaw_env_mod
from core.action_runner import ActionRunner
from core.openclaw_sender import OpenClawSender


class OpenClawSmartStartupActionTests(unittest.TestCase):
    @patch.object(openclaw_env_mod, "start_openclaw_tui")
    @patch.object(openclaw_env_mod, "is_openclaw_tui_running", return_value=False)
    @patch.object(openclaw_env_mod, "ensure_clawcommand_running")
    @patch("core.action_runner.time.sleep")
    @patch.object(action_runner_mod.platform_utils, "open_url_in_firefox", return_value=True)
    @patch.object(OpenClawSender, "open_control_dashboard")
    @patch.object(OpenClawSender, "ensure_gateway_running")
    def test_pipeline_calls_order(
        self,
        mock_ensure_gw: MagicMock,
        mock_dash: MagicMock,
        mock_ff: MagicMock,
        _mock_sleep: MagicMock,
        mock_cc: MagicMock,
        _mock_tui_running: MagicMock,
        mock_tui_start: MagicMock,
    ) -> None:
        runner = ActionRunner(
            logger=lambda _m: None,
            on_profile_change=lambda _n: None,
            on_toggle_flag=lambda _n: False,
        )
        action = {
            "type": "openclaw_smart_startup",
            "clawcommand_url": "http://127.0.0.1:4310",
        }
        runner._run_openclaw_smart_startup(action)
        mock_ensure_gw.assert_called_once()
        mock_dash.assert_called_once()
        mock_cc.assert_called_once_with(action, runner._log)
        mock_ff.assert_called_once_with("http://127.0.0.1:4310")
        mock_tui_start.assert_called_once()

    @patch.object(openclaw_env_mod, "start_openclaw_tui")
    @patch.object(openclaw_env_mod, "is_openclaw_tui_running", return_value=True)
    @patch.object(openclaw_env_mod, "ensure_clawcommand_running")
    @patch("core.action_runner.time.sleep")
    @patch.object(action_runner_mod.platform_utils, "open_url_in_firefox", return_value=True)
    @patch.object(OpenClawSender, "open_control_dashboard")
    @patch.object(OpenClawSender, "ensure_gateway_running")
    def test_skips_tui_when_already_running(
        self,
        _mock_ensure_gw: MagicMock,
        mock_dash: MagicMock,
        _mock_ff: MagicMock,
        _mock_sleep: MagicMock,
        _mock_cc: MagicMock,
        _mock_tui_running: MagicMock,
        mock_tui_start: MagicMock,
    ) -> None:
        runner = ActionRunner(
            logger=lambda _m: None,
            on_profile_change=lambda _n: None,
            on_toggle_flag=lambda _n: False,
        )
        runner._run_openclaw_smart_startup({"type": "openclaw_smart_startup"})
        mock_tui_start.assert_not_called()

    @patch.object(openclaw_env_mod, "start_openclaw_tui")
    @patch.object(openclaw_env_mod, "is_openclaw_tui_running", return_value=False)
    @patch.object(openclaw_env_mod, "ensure_clawcommand_running")
    @patch("core.action_runner.time.sleep")
    @patch.object(action_runner_mod.platform_utils, "open_url", return_value=True)
    @patch.object(action_runner_mod.platform_utils, "open_url_in_firefox", return_value=False)
    @patch.object(OpenClawSender, "open_control_dashboard")
    @patch.object(OpenClawSender, "ensure_gateway_running")
    def test_falls_back_to_default_browser_when_no_firefox(
        self,
        _mock_ensure_gw: MagicMock,
        mock_dash: MagicMock,
        _mock_ffox: MagicMock,
        mock_open_url: MagicMock,
        _mock_sleep: MagicMock,
        _mock_cc: MagicMock,
        _mock_tui_running: MagicMock,
        mock_tui_start: MagicMock,
    ) -> None:
        runner = ActionRunner(
            logger=lambda _m: None,
            on_profile_change=lambda _n: None,
            on_toggle_flag=lambda _n: False,
        )
        runner._run_openclaw_smart_startup(
            {"type": "openclaw_smart_startup", "clawcommand_url": "http://127.0.0.1:4310"}
        )
        mock_open_url.assert_called_once_with("http://127.0.0.1:4310")

    @patch.object(OpenClawSender, "notify")
    @patch.object(OpenClawSender, "open_control_dashboard")
    @patch.object(OpenClawSender, "ensure_gateway_running", side_effect=RuntimeError("gw down"))
    def test_gateway_failure_stops_before_dashboard(
        self,
        _mock_ensure: MagicMock,
        mock_dash: MagicMock,
        _mock_notify: MagicMock,
    ) -> None:
        runner = ActionRunner(
            logger=lambda _m: None,
            on_profile_change=lambda _n: None,
            on_toggle_flag=lambda _n: False,
        )
        runner._run_openclaw_smart_startup({"type": "openclaw_smart_startup"})
        mock_dash.assert_not_called()


class EnsureClawCommandTests(unittest.TestCase):
    @patch.object(openclaw_env_mod.subprocess, "Popen")
    @patch.object(openclaw_env_mod, "service_url_reachable", return_value=True)
    def test_no_start_when_reachable(self, _mock_reach: MagicMock, mock_popen: MagicMock) -> None:
        openclaw_env_mod.ensure_clawcommand_running(
            {
                "clawcommand_url": "http://127.0.0.1:4310",
                "clawcommand_dir_windows": r"F:\ClawCommand",
            },
            logger=lambda _m: None,
        )
        mock_popen.assert_not_called()

    @patch.object(openclaw_env_mod.subprocess, "Popen")
    @patch.object(openclaw_env_mod, "service_url_reachable", return_value=False)
    @patch.object(openclaw_env_mod.platform_utils, "use_windows_paths", return_value=True)
    @patch.object(openclaw_env_mod.Path, "is_dir", return_value=True)
    @patch.object(openclaw_env_mod.Path, "is_file", return_value=True)
    def test_starts_server_when_down(
        self,
        _mock_is_file: MagicMock,
        _mock_is_dir: MagicMock,
        _mock_win: MagicMock,
        _mock_reach: MagicMock,
        mock_popen: MagicMock,
    ) -> None:
        openclaw_env_mod.ensure_clawcommand_running(
            {
                "clawcommand_url": "http://127.0.0.1:4310",
                "clawcommand_dir_windows": r"F:\ClawCommand",
            },
            logger=lambda _m: None,
        )
        mock_popen.assert_called_once()


class OpenClawSenderGatewayTests(unittest.TestCase):
    @patch.object(OpenClawSender, "_is_gateway_running_fast", return_value=True)
    @patch("core.openclaw_sender.subprocess.run")
    def test_ensure_gateway_skips_start_when_running(
        self,
        mock_run: MagicMock,
        _mock_running: MagicMock,
    ) -> None:
        sender = OpenClawSender(logger=lambda _m: None)
        with patch.object(OpenClawSender, "_resolve_openclaw_executable", return_value="openclaw"):
            sender.ensure_gateway_running()
        gateway_starts = [
            c
            for c in mock_run.call_args_list
            if c.args and len(c.args[0]) >= 2 and c.args[0][1:3] == ("gateway", "start")
        ]
        self.assertEqual(gateway_starts, [])


if __name__ == "__main__":
    unittest.main()
