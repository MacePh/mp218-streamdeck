import unittest
from typing import Any

from core.action_runner import ActionRunner


class _FakeDictationService:
    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

    def start_recording(
        self,
        model: str = "base.en",
        language: str = "en",
        input_device: str | int | None = None,
    ) -> dict[str, Any] | None:
        self.calls.append(
            {
                "model": model,
                "language": language,
                "input_device": input_device,
            }
        )
        return {"ok": True}


class ActionRunnerDictateTests(unittest.TestCase):
    def test_dictate_passes_input_device(self) -> None:
        runner = ActionRunner(
            logger=lambda _msg: None,
            on_profile_change=lambda _name: None,
            on_toggle_flag=lambda _name: False,
        )
        fake = _FakeDictationService()
        runner._dictation_service = fake

        runner.run_pad_action(
            {"type": "dictate", "model": "base.en", "language": "en", "input_device": "pulse"},
            note=75,
            velocity=127,
        )

        self.assertEqual(len(fake.calls), 1)
        self.assertEqual(fake.calls[0]["input_device"], "pulse")

    def test_dictate_defaults_to_none_input_device(self) -> None:
        runner = ActionRunner(
            logger=lambda _msg: None,
            on_profile_change=lambda _name: None,
            on_toggle_flag=lambda _name: False,
        )
        fake = _FakeDictationService()
        runner._dictation_service = fake

        runner.run_pad_action(
            {"type": "dictate", "model": "base.en", "language": "en"},
            note=75,
            velocity=127,
        )

        self.assertEqual(len(fake.calls), 1)
        self.assertIsNone(fake.calls[0]["input_device"])

    def test_dictate_warns_when_recording_does_not_start(self) -> None:
        logs: list[str] = []

        class _NoopDictation:
            def start_recording(self, **_kw: object) -> None:
                return None

        runner = ActionRunner(
            logger=lambda msg: logs.append(msg),
            on_profile_change=lambda _name: None,
            on_toggle_flag=lambda _name: False,
        )
        runner._dictation_service = _NoopDictation()

        runner.run_pad_action(
            {"type": "dictate", "model": "base.en", "language": "en"},
            note=75,
            velocity=127,
        )

        self.assertTrue(
            any("recording did not start" in m for m in logs),
            f"expected warn in logs, got {logs!r}",
        )


if __name__ == "__main__":
    unittest.main()
