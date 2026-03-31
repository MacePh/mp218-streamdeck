import unittest
from unittest import mock

from core.dictation_service import DictationService


class DictationServiceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.messages: list[str] = []
        self.service = DictationService(logger=self.messages.append)

    def test_suppresses_common_short_low_energy_hallucination(self) -> None:
        suppressed = self.service._should_suppress_transcript(
            " You ",
            audio_rms=0.004,
            duration_seconds=0.8,
        )
        self.assertTrue(suppressed)

    def test_does_not_suppress_valid_longer_phrase(self) -> None:
        suppressed = self.service._should_suppress_transcript(
            "you are amazing",
            audio_rms=0.02,
            duration_seconds=0.8,
        )
        self.assertFalse(suppressed)

    def test_does_not_suppress_low_energy_short_phrase_when_long_capture(self) -> None:
        suppressed = self.service._should_suppress_transcript(
            "thank you",
            audio_rms=0.002,
            duration_seconds=2.4,
        )
        self.assertFalse(suppressed)

    def test_newer_session_marks_older_session_stale(self) -> None:
        fake_stream = mock.Mock()
        with mock.patch("core.dictation_service.sd") as sounddevice, mock.patch(
            "core.dictation_service.np", object()
        ), mock.patch("core.dictation_service.sf", object()), mock.patch(
            "core.dictation_service.WhisperModel", object()
        ):
            sounddevice.InputStream.return_value = fake_stream
            older = self.service.start_recording()
            newer = self.service.start_recording()

        self.assertIsNotNone(older)
        self.assertIsNotNone(newer)
        self.assertTrue(self.service._is_stale_session(int(older["session_id"])))
        self.assertFalse(self.service._is_stale_session(int(newer["session_id"])))

    def test_windows_injection_uses_windows_text_sender(self) -> None:
        with mock.patch("core.dictation_service.sys.platform", "win32"), mock.patch(
            "core.dictation_service.platform_utils.send_text_windows", return_value="clipboard-restored"
        ) as send_text_windows:
            self.service._inject_text("hello", target_hwnd=321)

        send_text_windows.assert_called_once_with("hello", target_hwnd=321)
        self.assertIn("[dictation] windows text injection via clipboard-restored", self.messages)


if __name__ == "__main__":
    unittest.main()
