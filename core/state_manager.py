from typing import Any


class StateManager:
    def __init__(self, active_profile: str, flags: dict[str, bool] | None = None):
        self.active_profile = active_profile
        self.last_pressed_pad: int | None = None
        self.flags = flags.copy() if flags else {}

    def set_active_profile(self, profile_name: str) -> None:
        self.active_profile = profile_name

    def set_last_pressed_pad(self, note: int) -> None:
        self.last_pressed_pad = note

    def set_flag(self, flag_name: str, value: bool) -> None:
        self.flags[flag_name] = value

    def snapshot(self) -> dict[str, Any]:
        return {
            "active_profile": self.active_profile,
            "last_pressed_pad": self.last_pressed_pad,
            "flags": self.flags.copy(),
        }
