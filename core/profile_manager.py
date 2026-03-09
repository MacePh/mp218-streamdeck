from typing import Any


NOOP_ACTION = {"type": "noop", "value": ""}


class ProfileManager:
    def __init__(self, config: dict[str, Any]):
        self.config = config
        self.active_profile = config["controller"]["default_profile"]

    def apply_new_config(self, config: dict[str, Any]) -> None:
        current_profile = self.active_profile
        self.config = config
        if current_profile in self.config["profiles"]:
            self.active_profile = current_profile
            return
        self.active_profile = self.config["controller"]["default_profile"]

    def set_active_profile(self, profile_name: str) -> bool:
        if profile_name not in self.config["profiles"]:
            return False
        self.active_profile = profile_name
        return True

    def get_active_profile(self) -> str:
        return self.active_profile

    def get_profile_brightness(self) -> int:
        brightness = self.config["led"]["profile_idle_brightness"]
        return int(brightness.get(self.active_profile, 60))

    def get_pad_action(self, note: int) -> dict[str, Any]:
        pads = self.config["profiles"][self.active_profile].get("pads", {})
        return pads.get(str(note), NOOP_ACTION)

    def get_knob_action(self, cc: int) -> dict[str, Any]:
        knobs = self.config["profiles"][self.active_profile].get("knobs", {})
        return knobs.get(str(cc), NOOP_ACTION)

    def get_active_pad_actions(self) -> dict[str, dict[str, Any]]:
        return self.config["profiles"][self.active_profile].get("pads", {})
