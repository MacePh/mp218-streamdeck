import json
import os
from typing import Any


class ConfigError(Exception):
    pass


class ConfigLoader:
    def __init__(self, path: str):
        self.path = path
        self.last_mtime: float | None = None
        self.current_config: dict[str, Any] | None = None

    def load_initial(self) -> dict[str, Any]:
        config = self._read_and_validate()
        self.current_config = config
        self.last_mtime = self._get_mtime()
        return config

    def reload_if_changed(self) -> tuple[bool, dict[str, Any] | None, str | None]:
        current_mtime = self._get_mtime()
        if self.last_mtime is not None and current_mtime <= self.last_mtime:
            return False, None, None

        try:
            config = self._read_and_validate()
        except Exception as exc:
            return True, None, str(exc)

        self.current_config = config
        self.last_mtime = current_mtime
        return True, config, None

    def _get_mtime(self) -> float:
        return os.path.getmtime(self.path)

    def _read_and_validate(self) -> dict[str, Any]:
        with open(self.path, "r", encoding="utf-8") as config_file:
            raw = json.load(config_file)
        return self._validate_and_normalize(raw)

    def _validate_and_normalize(self, config: dict[str, Any]) -> dict[str, Any]:
        if "config_version" not in config:
            raise ConfigError("Missing required key: config_version")
        if not isinstance(config["config_version"], int):
            raise ConfigError("config_version must be an integer")
        if config["config_version"] != 1:
            raise ConfigError(
                f"Unsupported config_version '{config['config_version']}'. Expected 1."
            )

        for key in ["midi", "led", "controller", "profiles"]:
            if key not in config:
                raise ConfigError(f"Missing required key: {key}")

        midi = config["midi"]
        if "input_port" not in midi or "output_port" not in midi:
            raise ConfigError("midi.input_port and midi.output_port are required")
        if "pad_channel" not in midi:
            raise ConfigError("midi.pad_channel is required")
        if not isinstance(midi["pad_channel"], int) or not (0 <= midi["pad_channel"] <= 15):
            raise ConfigError("midi.pad_channel must be an integer between 0 and 15")
        if "auto_detect_ports" in midi and not isinstance(midi["auto_detect_ports"], bool):
            raise ConfigError("midi.auto_detect_ports must be true or false")
        if "auto_detect_match" in midi and not isinstance(midi["auto_detect_match"], str):
            raise ConfigError("midi.auto_detect_match must be a string")

        controller = config["controller"]
        default_profile = controller.get("default_profile")
        if not default_profile:
            raise ConfigError("controller.default_profile is required")
        if "knob_change_threshold" in controller and (
            not isinstance(controller["knob_change_threshold"], int)
            or controller["knob_change_threshold"] < 0
        ):
            raise ConfigError("controller.knob_change_threshold must be an integer >= 0")
        if "manual_lock_seconds" in controller and (
            not isinstance(controller["manual_lock_seconds"], (int, float))
            or controller["manual_lock_seconds"] < 0
        ):
            raise ConfigError("controller.manual_lock_seconds must be a number >= 0")
        if "hud_pad" in controller and (
            not isinstance(controller["hud_pad"], int)
            or controller["hud_pad"] < 0
            or controller["hud_pad"] > 127
        ):
            raise ConfigError("controller.hud_pad must be an integer between 0 and 127")
        if "hud_toggle_key" in controller and not isinstance(
            controller["hud_toggle_key"], str
        ):
            raise ConfigError("controller.hud_toggle_key must be a string")
        if "hud_duration_seconds" in controller and (
            not isinstance(controller["hud_duration_seconds"], (int, float))
            or controller["hud_duration_seconds"] < 0
        ):
            raise ConfigError("controller.hud_duration_seconds must be a number >= 0")

        led = config["led"]
        reserved = led.get("reserved_pads", [])
        if not isinstance(reserved, list):
            raise ConfigError("led.reserved_pads must be a list")
        for note in reserved:
            if not isinstance(note, int):
                raise ConfigError("led.reserved_pads values must be integers")

        hud = config.get("hud")
        if hud is not None:
            if not isinstance(hud, dict):
                raise ConfigError("hud must be an object")
            if "enabled" in hud and not isinstance(hud["enabled"], bool):
                raise ConfigError("hud.enabled must be true or false")
            if "width" in hud and (not isinstance(hud["width"], int) or hud["width"] <= 0):
                raise ConfigError("hud.width must be an integer > 0")
            if "height" in hud and (
                not isinstance(hud["height"], int) or hud["height"] <= 0
            ):
                raise ConfigError("hud.height must be an integer > 0")
            if "opacity" in hud and (
                not isinstance(hud["opacity"], (int, float))
                or hud["opacity"] <= 0
                or hud["opacity"] > 1
            ):
                raise ConfigError("hud.opacity must be a number > 0 and <= 1")

        profiles = config["profiles"]
        for profile_name in ["dev", "ai", "stream"]:
            if profile_name not in profiles:
                raise ConfigError(f"Missing required profile: {profile_name}")
        if default_profile not in profiles:
            raise ConfigError(f"default_profile '{default_profile}' does not exist in profiles")

        context_profiles = config.get("context_profiles")
        if context_profiles is not None:
            if not isinstance(context_profiles, dict):
                raise ConfigError("context_profiles must be an object")
            for process_substring, profile_name in context_profiles.items():
                if not isinstance(process_substring, str):
                    raise ConfigError("context_profiles keys must be strings")
                if not isinstance(profile_name, str):
                    raise ConfigError("context_profiles values must be profile names")
                if profile_name not in profiles:
                    raise ConfigError(
                        f"context_profiles maps to unknown profile '{profile_name}'"
                    )

        for profile_name, profile_config in profiles.items():
            pads = profile_config.get("pads", {})
            knobs = profile_config.get("knobs", {})
            if not isinstance(pads, dict):
                raise ConfigError(f"profiles.{profile_name}.pads must be an object")
            if not isinstance(knobs, dict):
                raise ConfigError(f"profiles.{profile_name}.knobs must be an object")
            profile_config["pads"] = {str(note): action for note, action in pads.items()}
            profile_config["knobs"] = {str(cc): action for cc, action in knobs.items()}

        if context_profiles is not None:
            config["context_profiles"] = {
                process_substring.lower(): profile_name
                for process_substring, profile_name in context_profiles.items()
            }

        return config
