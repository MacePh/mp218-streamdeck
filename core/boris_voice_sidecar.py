from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

REPLY_MARKER_RE = re.compile(r"\[\[reply_to_current\]\]\s*", re.IGNORECASE)
WHITESPACE_RE = re.compile(r"\s+")
SENTENCE_SPLIT_RE = re.compile(r"(?<=[.!?])\s+")
DEFAULT_SESSION_ROOT = Path.home() / ".openclaw" / "agents" / "main" / "sessions"
DEFAULT_SESSION_INDEX = DEFAULT_SESSION_ROOT / "sessions.json"
DEFAULT_SESSION_HINT = "agent:main:main"
DEFAULT_STATE_FILE = Path.home() / ".openclaw" / "workspace" / "boris_voice_sidecar_state.json"


@dataclass
class SpokenReply:
    session_file: Path
    message_id: str
    raw_text: str
    spoken_text: str
    timestamp: str


class BorisVoiceSidecar:
    def __init__(
        self,
        logger: Callable[[str], None],
        session_root: Path = DEFAULT_SESSION_ROOT,
        session_hint: str = DEFAULT_SESSION_HINT,
        poll_seconds: float = 0.5,
        state_file: Path = DEFAULT_STATE_FILE,
        voice_name: str = "",
        speech_mode: str = "full",
        max_sentences: int = 2,
        max_chars: int = 240,
    ):
        self._log = logger
        self.session_root = Path(session_root)
        self.session_hint = str(session_hint).strip()
        self.poll_seconds = max(0.5, float(poll_seconds))
        self.state_file = Path(state_file)
        self.voice_name = str(voice_name).strip()
        mode = str(speech_mode).strip().lower() or "full"
        self.speech_mode = mode if mode in {"full", "summary"} else "full"
        self.max_sentences = max(1, int(max_sentences))
        self.max_chars = max(80, int(max_chars))
        self._state = self._load_state()

    def _load_state(self) -> dict:
        if self.state_file.exists():
            try:
                return json.loads(self.state_file.read_text(encoding="utf-8"))
            except Exception as exc:
                self._log(f"[boris-voice] state load failed: {exc}")
        return {"spoken": {}, "last_session": ""}

    def _save_state(self) -> None:
        self.state_file.parent.mkdir(parents=True, exist_ok=True)
        self.state_file.write_text(json.dumps(self._state, indent=2), encoding="utf-8")

    def _spoken_map(self) -> dict[str, str]:
        spoken = self._state.get("spoken")
        if isinstance(spoken, dict):
            return spoken
        self._state["spoken"] = {}
        return self._state["spoken"]

    def _candidate_session_files(self) -> list[Path]:
        if not self.session_root.exists():
            return []
        files = sorted(self.session_root.glob("*.jsonl"), key=lambda p: p.stat().st_mtime, reverse=True)
        return files[:15]

    def _file_contains_hint(self, path: Path) -> bool:
        if not self.session_hint:
            return True
        try:
            with path.open("r", encoding="utf-8", errors="replace") as handle:
                for _ in range(250):
                    line = handle.readline()
                    if not line:
                        break
                    if self.session_hint in line:
                        return True
        except Exception:
            return False
        return False

    def _select_session_file_from_index(self) -> Path | None:
        if not self.session_hint or not DEFAULT_SESSION_INDEX.exists():
            return None
        try:
            data = json.loads(DEFAULT_SESSION_INDEX.read_text(encoding="utf-8"))
        except Exception as exc:
            self._log(f"[boris-voice] session index read failed: {exc}")
            return None
        if not isinstance(data, dict):
            return None
        hint = self.session_hint.strip().lower()
        for session_key, meta in data.items():
            if str(session_key).strip().lower() != hint:
                continue
            if not isinstance(meta, dict):
                continue
            session_file = meta.get("sessionFile")
            if not isinstance(session_file, str) or not session_file.strip():
                continue
            candidate = Path(session_file)
            if candidate.exists():
                return candidate
        return None

    def _select_session_file(self) -> Path | None:
        indexed = self._select_session_file_from_index()
        if indexed is not None:
            return indexed
        candidates = self._candidate_session_files()
        hinted = [path for path in candidates if self._file_contains_hint(path)]
        if hinted:
            return hinted[0]
        return candidates[0] if candidates else None

    def _extract_text(self, content: object) -> str:
        if isinstance(content, str):
            return content
        if not isinstance(content, list):
            return ""
        parts: list[str] = []
        for item in content:
            if not isinstance(item, dict):
                continue
            if item.get("type") != "text":
                continue
            text = item.get("text")
            if isinstance(text, str) and text.strip():
                parts.append(text)
        return "\n".join(parts).strip()

    def _clean_text_for_speech(self, text: str) -> str:
        cleaned = REPLY_MARKER_RE.sub("", text)
        cleaned = cleaned.replace("**", " ")
        cleaned = cleaned.replace("`", " ")
        cleaned = cleaned.replace("•", ", ")
        cleaned = cleaned.replace("—", " - ")
        cleaned = cleaned.replace("–", " - ")
        cleaned = cleaned.replace("…", "...")
        cleaned = cleaned.replace("“", '"').replace("”", '"')
        cleaned = cleaned.replace("’", "'").replace("‘", "'")
        cleaned = cleaned.replace("�", "")
        cleaned = WHITESPACE_RE.sub(" ", cleaned).strip()
        return cleaned

    def _normalize_for_speech(self, text: str) -> str:
        cleaned = self._clean_text_for_speech(text)
        if not cleaned:
            return ""
        if self.speech_mode == "summary":
            sentences = [part.strip() for part in SENTENCE_SPLIT_RE.split(cleaned) if part.strip()]
            if sentences:
                cleaned = " ".join(sentences[: self.max_sentences])
            if len(cleaned) > self.max_chars:
                clipped = cleaned[: self.max_chars].rstrip(" ,;:-")
                cleaned = clipped + "..."
        return cleaned

    def _latest_unspoken_reply(self, session_file: Path) -> SpokenReply | None:
        spoken = self._spoken_map()
        try:
            lines = session_file.read_text(encoding="utf-8", errors="replace").splitlines()
        except Exception as exc:
            self._log(f"[boris-voice] failed to read session file: {exc}")
            return None

        for line in reversed(lines):
            if not line.strip():
                continue
            try:
                entry = json.loads(line)
            except Exception:
                continue
            if entry.get("type") != "message":
                continue
            message = entry.get("message") or {}
            if not isinstance(message, dict) or message.get("role") != "assistant":
                continue
            raw_text = self._extract_text(message.get("content"))
            if not raw_text.strip():
                continue
            message_id = str(entry.get("id") or "")
            dedupe_key = f"{session_file.name}:{message_id}"
            if spoken.get(dedupe_key):
                return None
            spoken_text = self._normalize_for_speech(raw_text)
            if not spoken_text:
                continue
            return SpokenReply(
                session_file=session_file,
                message_id=message_id,
                raw_text=raw_text,
                spoken_text=spoken_text,
                timestamp=str(entry.get("timestamp") or ""),
            )
        return None

    def _mark_spoken(self, reply: SpokenReply) -> None:
        spoken = self._spoken_map()
        spoken[f"{reply.session_file.name}:{reply.message_id}"] = reply.timestamp or str(time.time())
        if len(spoken) > 200:
            trimmed = dict(list(spoken.items())[-120:])
            self._state["spoken"] = trimmed
        self._state["last_session"] = str(reply.session_file)
        self._save_state()

    def _speak_windows(self, text: str) -> None:
        escaped = text.replace("'", "''")
        voice_line = ""
        if self.voice_name:
            safe_voice = self.voice_name.replace("'", "''")
            voice_line = f"$s.SelectVoice('{safe_voice}');"
        script = (
            "Add-Type -AssemblyName System.Speech;"
            "$s=New-Object System.Speech.Synthesis.SpeechSynthesizer;"
            f"{voice_line}"
            "$s.Rate=0;"
            f"$s.Speak('{escaped}');"
        )
        subprocess.run(
            ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", script],
            capture_output=True,
            text=True,
            encoding="utf-8",
            timeout=60,
            check=False,
        )

    def speak(self, text: str) -> None:
        if os.name == "nt":
            self._speak_windows(text)
            return
        raise RuntimeError("Boris voice sidecar Phase 1 currently supports built-in Windows speech only")

    def run_once(self) -> bool:
        session_file = self._select_session_file()
        if session_file is None:
            self._log("[boris-voice] no session files found yet")
            return False
        reply = self._latest_unspoken_reply(session_file)
        if reply is None:
            return False
        mode_label = "summary" if self.speech_mode == "summary" else "full reply"
        self._log(f"[boris-voice] speaking {mode_label} from {reply.session_file.name}: {reply.spoken_text}")
        self.speak(reply.spoken_text)
        self._mark_spoken(reply)
        return True

    def run_forever(self) -> None:
        self._log("[boris-voice] watching OpenClaw session logs for new Boris replies")
        while True:
            try:
                self.run_once()
            except KeyboardInterrupt:
                raise
            except Exception as exc:
                self._log(f"[boris-voice] watcher error: {exc}")
            time.sleep(self.poll_seconds)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Watch Boris replies locally and speak them directly from OpenClaw session logs")
    parser.add_argument("--session-root", default=str(DEFAULT_SESSION_ROOT))
    parser.add_argument("--session-hint", default=DEFAULT_SESSION_HINT)
    parser.add_argument("--poll-seconds", type=float, default=0.5)
    parser.add_argument("--state-file", default=str(DEFAULT_STATE_FILE))
    parser.add_argument("--voice", default="")
    parser.add_argument("--speech-mode", choices=["full", "summary"], default="full")
    parser.add_argument("--max-sentences", type=int, default=2)
    parser.add_argument("--max-chars", type=int, default=240)
    parser.add_argument("--once", action="store_true")
    args = parser.parse_args(argv)

    sidecar = BorisVoiceSidecar(
        logger=lambda message: print(message, flush=True),
        session_root=Path(args.session_root),
        session_hint=args.session_hint,
        poll_seconds=args.poll_seconds,
        state_file=Path(args.state_file),
        voice_name=args.voice,
        speech_mode=args.speech_mode,
        max_sentences=args.max_sentences,
        max_chars=args.max_chars,
    )
    if args.once:
        sidecar.run_once()
        return 0
    sidecar.run_forever()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
