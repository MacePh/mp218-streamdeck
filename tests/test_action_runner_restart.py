import unittest

from core.action_runner import ActionRunner


class ActionRunnerRestartTests(unittest.TestCase):
    def test_restart_invokes_callback(self) -> None:
        called: list[bool] = []

        def on_restart() -> None:
            called.append(True)

        runner = ActionRunner(
            logger=lambda _msg: None,
            on_profile_change=lambda _name: None,
            on_toggle_flag=lambda _name: False,
            on_restart=on_restart,
        )
        runner.run_pad_action({"type": "restart"}, note=48, velocity=127)
        self.assertEqual(called, [True])

    def test_restart_without_handler_logs_only(self) -> None:
        logs: list[str] = []

        runner = ActionRunner(
            logger=lambda msg: logs.append(msg),
            on_profile_change=lambda _name: None,
            on_toggle_flag=lambda _name: False,
        )
        runner.run_pad_action({"type": "restart"}, note=48, velocity=127)
        self.assertTrue(any("restart" in m.lower() for m in logs))


if __name__ == "__main__":
    unittest.main()
