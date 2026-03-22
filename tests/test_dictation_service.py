import unittest

from core.dictation_service import DictationService


class DictationServiceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.service = DictationService(logger=lambda _msg: None)

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


if __name__ == "__main__":
    unittest.main()
