"""
Live meeting transcription worker.

Captures mic + speaker loopback in 5-second chunks, transcribes with
faster-whisper, and appends to a timestamped file in transcripts/.

Uses `initial_prompt` with a rolling 20-line context buffer for accuracy.
Uses `vad_filter=True` to skip silence.
Runs in a daemon thread — never blocks the MIDI loop.
"""

from __future__ import annotations

import os, threading, time, logging
from datetime import datetime
from typing import Callable, Optional

try:
    from faster_whisper import WhisperModel
    _WHISPER_OK = True
except ImportError:
    WhisperModel = None
    _WHISPER_OK = False

try:
    import numpy as np
    _NUMPY_OK = True
except ImportError:
    np = None
    _NUMPY_OK = False

from core.audio_capture import (
    get_microphone,
    get_speaker_loopback,
    record_chunk,
    soundcard_available,
    SAMPLE_RATE,
)

CHUNK_SECONDS = 5
CHUNK_FRAMES = SAMPLE_RATE * CHUNK_SECONDS
TRANSCRIPT_DIR = "transcripts"
CONTEXT_LINES = 20


class MeetingTranscriber:
    def __init__(
        self,
        logger: Optional[Callable[[str], None]] = None,
        model_size: str = "base.en",
    ):
        self._log = logger or logging.getLogger(__name__).info
        self._model_size = model_size
        self._model = None
        self._stop_event = threading.Event()
        self.running = False
        self.thread: Optional[threading.Thread] = None
        self.transcript_path: Optional[str] = None
        self.context_buffer: list[str] = []

    def start(self) -> None:
        if self.running:
            self._log("[transcriber] already running"); return
        for name, ok in [("faster-whisper", _WHISPER_OK),
                          ("soundcard", soundcard_available()),
                          ("numpy", _NUMPY_OK)]:
            if not ok:
                self._log(f"[transcriber] {name} not installed — cannot start"); return
        self._stop_event.clear()
        self.context_buffer = []
        self.transcript_path = self._make_path()
        self.running = True
        self.thread = threading.Thread(target=self._worker,
                                       name="MeetingTranscriber", daemon=True)
        self.thread.start()
        self._log(f"[transcriber] started → {self.transcript_path}")

    def stop(self) -> None:
        if not self.running:
            self._log("[transcriber] not running"); return
        self._stop_event.set()
        self.running = False
        self._log("[transcriber] stopping")

    # ── Helpers ───────────────────────────────────────────────────────

    def _make_path(self) -> str:
        os.makedirs(TRANSCRIPT_DIR, exist_ok=True)
        stamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        return os.path.join(TRANSCRIPT_DIR, f"meeting_{stamp}.txt")

    def _load_model(self) -> bool:
        if self._model: return True
        try:
            self._log(f"[transcriber] loading Whisper '{self._model_size}' …")
            self._model = WhisperModel(self._model_size, device="cpu", compute_type="int8")
            self._log("[transcriber] model ready")
            return True
        except Exception as e:
            self._log(f"[transcriber] model load failed: {e}"); return False

    def _prompt(self) -> str:
        return " ".join(self.context_buffer[-CONTEXT_LINES:])

    def _write(self, line: str) -> None:
        try:
            with open(self.transcript_path, "a", encoding="utf-8") as f:
                f.write(line + "\n")
        except Exception as e:
            self._log(f"[transcriber] write error: {e}")

    def _transcribe(self, audio, chunk_start: float) -> None:
        try:
            segments, _ = self._model.transcribe(
                audio, language="en",
                vad_filter=True, initial_prompt=self._prompt(),
            )
            for seg in segments:
                text = seg.text.strip()
                if not text: continue
                line = f"[{chunk_start + seg.start:.2f}] {text}"
                self._write(line)
                self._log(f"[transcriber] {line}")
                self.context_buffer.append(text)
                if len(self.context_buffer) > CONTEXT_LINES:
                    self.context_buffer = self.context_buffer[-CONTEXT_LINES:]
        except Exception as e:
            self._log(f"[transcriber] transcribe error: {e}")

    # ── Worker ────────────────────────────────────────────────────────

    def _worker(self) -> None:
        if not self._load_model():
            self.running = False; return
        mic = get_microphone()
        spk = get_speaker_loopback()
        if mic is None and spk is None:
            self._log("[transcriber] no audio devices — aborting")
            self.running = False; return

        t0 = time.monotonic()
        self._log("[transcriber] capture loop started")
        while not self._stop_event.is_set():
            chunk_start = time.monotonic() - t0
            audio = record_chunk(mic, spk, CHUNK_FRAMES, SAMPLE_RATE)
            if audio is None or len(audio) == 0:
                self._log("[transcriber] empty chunk — skipping")
                self._stop_event.wait(timeout=1.0)
                continue
            self._transcribe(audio, chunk_start)
            # audio array goes out of scope here — no memory accumulation
        self._log("[transcriber] stopped")
