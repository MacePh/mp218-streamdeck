from typing import Any
import time


class StateManager:
    def __init__(self, active_profile: str, flags: dict[str, bool] | None = None):
        self.active_profile = active_profile
        self.last_pressed_pad: int | None = None
        self.flags = flags.copy() if flags else {}
        self.manual_lock_until: float = 0.0

    def set_active_profile(self, profile_name: str) -> None:
        self.active_profile = profile_name

    def set_last_pressed_pad(self, note: int) -> None:
        self.last_pressed_pad = note

    def set_flag(self, flag_name: str, value: bool) -> None:
        self.flags[flag_name] = value

    def toggle_flag(self, flag_name: str) -> bool:
        new_value = not bool(self.flags.get(flag_name, False))
        self.flags[flag_name] = new_value
        return new_value

    def activate_manual_lock(self, seconds: float) -> None:
        self.manual_lock_until = time.monotonic() + max(0.0, float(seconds))

    def is_manual_locked(self) -> bool:
        return time.monotonic() < self.manual_lock_until

    def snapshot(self) -> dict[str, Any]:
        return {
            "active_profile": self.active_profile,
            "last_pressed_pad": self.last_pressed_pad,
            "flags": self.flags.copy(),
            "manual_lock_until": self.manual_lock_until,
        }
