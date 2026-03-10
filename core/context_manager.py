import sys
import time
from typing import Callable

import psutil

try:
    import win32gui
    import win32process
except Exception:
    win32gui = None
    win32process = None


class ContextManager:
    def __init__(self, mapping: dict[str, str], logger: Callable[[str], None]):
        self._log = logger
        self.mapping = [(key.lower(), value) for key, value in mapping.items()]
        self.poll_interval_seconds = 0.25
        self._last_poll_time = 0.0
        self.last_detected_process: str | None = None
        self.last_profile: str | None = None

    def sync_profile(self, profile_name: str) -> None:
        self.last_profile = profile_name

    def get_foreground_process(self) -> str | None:
        if sys.platform != "win32" or win32gui is None or win32process is None:
            return None

        try:
            hwnd = win32gui.GetForegroundWindow()
            if not hwnd:
                return None
            _, pid = win32process.GetWindowThreadProcessId(hwnd)
            process_name = psutil.Process(pid).name()
            return process_name.lower()
        except Exception:
            return None

    def resolve_profile(self, process_name: str | None) -> str | None:
        if not process_name:
            return None
        lowered = process_name.lower()
        for process_substring, profile_name in self.mapping:
            if process_substring in lowered:
                return profile_name
        return None

    def update(self) -> str | None:
        now = time.monotonic()
        if (now - self._last_poll_time) < self.poll_interval_seconds:
            return None
        self._last_poll_time = now

        process_name = self.get_foreground_process()
        if process_name is None:
            return None

        if process_name != self.last_detected_process:
            self.last_detected_process = process_name
            self._log(f"[context] foreground={process_name}")

        resolved_profile = self.resolve_profile(process_name)
        if resolved_profile is None:
            return None
        if resolved_profile == self.last_profile:
            return None

        self.last_profile = resolved_profile
        return resolved_profile
