"""
Cross-platform mic + speaker loopback capture using `soundcard`.
Windows: WASAPI loopback (loopback=True)
Linux:   PulseAudio/PipeWire monitor via speaker.recorder()
"""

from __future__ import annotations

import sys, logging
from typing import Optional

try:
    import soundcard as sc
    import numpy as np
    _AVAILABLE = True
except ImportError:
    _AVAILABLE = False

logger = logging.getLogger(__name__)

SAMPLE_RATE = 16000


def soundcard_available() -> bool:
    return _AVAILABLE


def get_microphone():
    if not _AVAILABLE:
        return None
    try:
        mic = sc.default_microphone()
        logger.info(f"[audio_capture] mic: {mic.name}")
        return mic
    except Exception as e:
        logger.error(f"[audio_capture] mic error: {e}")
        return None


def get_speaker_loopback():
    if not _AVAILABLE:
        return None
    try:
        spk = sc.default_speaker()
        logger.info(f"[audio_capture] speaker: {spk.name}")
        return spk
    except Exception as e:
        logger.error(f"[audio_capture] speaker error: {e}")
        return None


def record_chunk(
    mic,
    speaker,
    num_frames: int,
    sample_rate: int = SAMPLE_RATE,
) -> "Optional[np.ndarray]":
    """
    Record num_frames from mic and/or speaker loopback.
    Mix both if available. Returns mono float32 array or None.
    """
    if not _AVAILABLE:
        return None
    mic_mono = spk_mono = None

    if mic is not None:
        try:
            with mic.recorder(samplerate=sample_rate, channels=1) as rec:
                d = rec.record(numframes=num_frames)
            mic_mono = (d[:, 0] if d.ndim > 1 else d).astype(np.float32)
        except Exception as e:
            logger.warning(f"[audio_capture] mic record error: {e}")

    if speaker is not None:
        try:
            kwargs = dict(samplerate=sample_rate, channels=1)
            if sys.platform == "win32":
                kwargs["loopback"] = True
            with speaker.recorder(**kwargs) as rec:
                d = rec.record(numframes=num_frames)
            spk_mono = (d[:, 0] if d.ndim > 1 else d).astype(np.float32)
        except Exception as e:
            logger.warning(f"[audio_capture] speaker record error: {e}")

    if mic_mono is not None and spk_mono is not None:
        n = min(len(mic_mono), len(spk_mono))
        return (mic_mono[:n] + spk_mono[:n]) / 2.0
    return mic_mono if mic_mono is not None else spk_mono
