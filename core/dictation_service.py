from __future__ import annotations

from typing import Any, Callable
import subprocess
import sys
import tempfile
import threading
import time
from pathlib import Path

try:
    import numpy as np
    import sounddevice as sd
    import soundfile as sf
except ImportError:
    np = None
    sd = None
    sf = None

try:
    from faster_whisper import WhisperModel
except ImportError:
    WhisperModel = None


class DictationService:
    def __init__(self, logger: Callable[[str], None]):
        self._log = logger
        self._model_cache: dict[str, Any] = {}

    def _get_model(self, model_size: str) -> Any:
        if WhisperModel is None:
            raise RuntimeError("faster_whisper is not installed")
        if model_size not in self._model_cache:
            self._log(f"[dictation] loading model '{model_size}'...")
            self._model_cache[model_size] = WhisperModel(
                model_size,
                device="cpu",
                compute_type="int8",
            )
            self._log(f"[dictation] model '{model_size}' ready")
        return self._model_cache[model_size]

    def start_recording(self, model: str = "base.en", language: str = "en") -> dict[str, Any] | None:
        if sd is None or np is None or sf is None:
            self._log("[dictation] missing dependencies: sounddevice/soundfile/numpy")
            return None
        if WhisperModel is None:
            self._log("[dictation] missing dependency: faster-whisper")
            return None

        session: dict[str, Any] = {
            "audio_data": [],
            "stream": None,
            "samplerate": 16000,
            "model": model,
            "language": language,
            "started_at": time.monotonic(),
        }

        try:
            def _audio_callback(indata: Any, _frames: int, _time_info: Any, status: Any) -> None:
                if status:
                    self._log(f"[dictation] input status: {status}")
                try:
                    session["audio_data"].append(indata[:, 0].copy())
                except Exception:
                    pass

            stream = sd.InputStream(
                samplerate=16000,
                channels=1,
                dtype="float32",
                callback=_audio_callback,
            )
            stream.start()
            session["stream"] = stream
            self._log("[dictation] recording started")
            return session
        except Exception as exc:
            self._log(f"[dictation] start recording error: {exc}")
            return None

    def stop_and_transcribe(self, session: dict[str, Any]) -> None:
        thread = threading.Thread(
            target=self._do_transcribe,
            args=(session,),
            daemon=True,
        )
        thread.start()

    def _do_transcribe(self, session: dict[str, Any]) -> None:
        temp_path: Path | None = None
        try:
            stream = session.get("stream")
            if stream is not None:
                try:
                    stream.stop()
                    stream.close()
                except Exception as exc:
                    self._log(f"[dictation] stream stop error: {exc}")

            chunks = session.get("audio_data", [])
            if not chunks:
                self._log("[dictation] no audio captured")
                return
            if np is None or sf is None:
                self._log("[dictation] missing dependencies for post-processing")
                return

            try:
                audio = np.concatenate(chunks, axis=0).astype("float32")
            except Exception as exc:
                self._log(f"[dictation] audio concat error: {exc}")
                return

            if audio.size == 0:
                self._log("[dictation] empty audio buffer")
                return

            samplerate = int(session.get("samplerate", 16000))
            with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
                temp_path = Path(tmp.name)

            sf.write(str(temp_path), audio, samplerate=samplerate)

            model_size = str(session.get("model", "base.en"))
            language = str(session.get("language", "en"))
            model = self._get_model(model_size)
            segments, _info = model.transcribe(str(temp_path), language=language)
            text = " ".join(segment.text for segment in segments).strip()
            if not text:
                self._log("[dictation] no speech detected")
                return

            elapsed = time.monotonic() - float(session.get("started_at", time.monotonic()))
            self._log(f"[dictation] transcription ready ({elapsed:.2f}s): {text}")
            self._inject_text(text)
        except Exception as exc:
            self._log(f"[dictation] transcribe error: {exc}")
        finally:
            if temp_path is not None:
                try:
                    temp_path.unlink(missing_ok=True)
                except Exception:
                    pass

    def _inject_text(self, text: str) -> None:
        if not text:
            return
        if sys.platform == "win32":
            try:
                import pyautogui
                import pyperclip

                original = pyperclip.paste()
                pyperclip.copy(text)
                pyautogui.hotkey("ctrl", "v")
                threading.Timer(1.0, lambda: pyperclip.copy(original)).start()
            except Exception as exc:
                self._log(f"[dictation] text injection error (win32): {exc}")
            return

        try:
            subprocess.run(
                ["xdotool", "type", "--delay", "5", "--", text],
                timeout=10,
                capture_output=True,
            )
        except Exception as exc:
            self._log(f"[dictation] text injection error (linux): {exc}")
