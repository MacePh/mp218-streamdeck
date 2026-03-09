import time
from typing import Callable

import mido

from core.midi_manager import MidiManager


class LEDManager:
    def __init__(
        self,
        midi: MidiManager,
        midi_config: dict,
        led_config: dict,
        logger: Callable[[str], None],
    ):
        self.midi = midi
        self._log = logger
        self.current_led_state: dict[int, int] = {}
        self.update_settings(midi_config, led_config)

    def update_settings(self, midi_config: dict, led_config: dict) -> None:
        self.pad_channel = int(midi_config.get("pad_channel", 9))
        note_range = midi_config.get("pad_note_range", {"min": 36, "max": 83})
        self.pad_min = int(note_range.get("min", 36))
        self.pad_max = int(note_range.get("max", 83))

        self.pressed_brightness = int(led_config.get("pressed_brightness", 127))
        self.press_flash_seconds = float(led_config.get("press_flash_seconds", 0.08))
        self.profile_idle = led_config.get("profile_idle_brightness", {})
        self.indicator_pads = led_config.get("indicator_pads", {})
        self.reserved_pads = {int(note) for note in led_config.get("reserved_pads", [])}
        self.bank_multipliers = led_config.get(
            "bank_brightness_multipliers",
            {"A": 0.9, "B": 1.0, "C": 1.1},
        )
        self.animations = led_config.get("animations", {})

    def _clamp_velocity(self, velocity: int) -> int:
        return max(0, min(127, int(velocity)))

    def _bank_for_note(self, note: int) -> str:
        if 36 <= note <= 51:
            return "A"
        if 52 <= note <= 67:
            return "B"
        return "C"

    def note_idle_brightness(self, profile_name: str, note: int) -> int:
        profile_base = int(self.profile_idle.get(profile_name, 60))
        multiplier = float(self.bank_multipliers.get(self._bank_for_note(note), 1.0))
        velocity = int(round(profile_base * multiplier))
        return self._clamp_velocity(velocity)

    def send_note_on(self, note: int, velocity: int) -> None:
        clamped_velocity = self._clamp_velocity(velocity)
        if self.current_led_state.get(int(note)) == clamped_velocity:
            return
        message = mido.Message(
            "note_on",
            note=int(note),
            velocity=clamped_velocity,
            channel=self.pad_channel,
        )
        self.midi.send(message)
        self.current_led_state[int(note)] = clamped_velocity
        self._log(
            f"[led] note_on note={note} velocity={velocity} channel={self.pad_channel}"
        )

    def off(self, note: int) -> None:
        self.send_note_on(note, 0)

    def clear(self) -> None:
        for note in range(self.pad_min, self.pad_max + 1):
            self.off(note)
        self._log("[led] cleared all pad LEDs")

    def startup_animation(self) -> None:
        if not self.animations.get("startup_enabled", False):
            return
        delay_ms = int(self.animations.get("startup_delay_ms", 10))
        delay_seconds = max(0.001, delay_ms / 1000.0)
        for note in range(self.pad_min, self.pad_max + 1):
            self.send_note_on(note, 30)
            time.sleep(delay_seconds)
            self.off(note)
        self._log("[led] startup animation complete")

    def profile_switch_animation(self) -> None:
        if not self.animations.get("profile_switch_enabled", False):
            return
        delay_ms = int(self.animations.get("profile_switch_delay_ms", 5))
        delay_seconds = max(0.001, delay_ms / 1000.0)
        for _ in range(2):
            for note in range(self.pad_min, self.pad_max + 1):
                self.send_note_on(note, 15)
            time.sleep(delay_seconds)
            self.clear()
        self._log("[led] profile switch animation complete")

    def render_profile(self, profile_name: str, pad_actions: dict[str, dict]) -> None:
        target: dict[int, int] = {
            note: 0 for note in range(self.pad_min, self.pad_max + 1)
        }

        for note_key, action in pad_actions.items():
            note = int(note_key)
            if note in self.reserved_pads:
                continue
            if action.get("type") == "noop":
                continue
            target[note] = self.note_idle_brightness(profile_name, note)

        indicator_note = self.indicator_pads.get(profile_name)
        if indicator_note is not None:
            target[int(indicator_note)] = self.pressed_brightness

        for note, velocity in target.items():
            self.send_note_on(note, velocity)

        self._log(
            f"[led] rendered profile='{profile_name}' pads={len(pad_actions)}"
        )
