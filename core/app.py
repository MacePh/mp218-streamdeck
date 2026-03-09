import argparse
import json
import time
import queue
from typing import Any

from core.action_runner import ActionRunner
from core.config_loader import ConfigLoader
from core.context_manager import ContextManager
from core.hot_reload import HotReloadWatcher
from core.hud_manager import HUDManager
from core.led_manager import LEDManager
from core.midi_manager import MidiManager
from core.profile_manager import ProfileManager
from core.state_manager import StateManager


class ControlSurfaceApp:
    def __init__(self, config_path: str):
        self.config_path = config_path
        self.config_loader = ConfigLoader(config_path)
        self.config: dict[str, Any] = {}
        self.profile_manager: ProfileManager | None = None
        self.state: StateManager | None = None
        self.midi: MidiManager | None = None
        self.led: LEDManager | None = None
        self.action_runner: ActionRunner | None = None
        self.hot_reload: HotReloadWatcher | None = None
        self.context_manager: ContextManager | None = None
        self.knob_last_values: dict[int, int] = {}
        self.pending_led_restore: list[tuple[int, float]] = []
        self.current_bank = "A"
        self.hud_manager: HUDManager | None = None
        self.hud_trigger_queue: queue.Queue[int] = queue.Queue()

    def log(self, message: str) -> None:
        print(message, flush=True)

    def _bank_for_note(self, note: int) -> str:
        if 36 <= note <= 51:
            return "A"
        if 52 <= note <= 67:
            return "B"
        return "C"

    def _active_app_name(self) -> str:
        if self.context_manager is None:
            return "unknown"
        return self.context_manager.last_detected_process or "unknown"

    def _hud_model(self) -> dict:
        assert self.profile_manager is not None
        assert self.state is not None
        return {
            "profile": self.profile_manager.get_active_profile(),
            "bank": self.current_bank,
            "active_app": self._active_app_name(),
            "state": self.state.snapshot(),
            "actions": self.profile_manager.get_active_pad_actions(),
            "profiles": self.config.get("profiles", {}),
        }

    def _on_hud_pad_trigger(self, note: int) -> None:
        self.hud_trigger_queue.put(int(note))

    def _configure_hud_manager(self) -> None:
        hud_cfg = self.config.get("hud", {})
        enabled = bool(hud_cfg.get("enabled", False))

        if self.hud_manager is None:
            self.hud_manager = HUDManager(
                logger=self.log,
                on_pad_trigger=self._on_hud_pad_trigger,
            )
            self.hud_manager.start()

        self.hud_manager.configure(hud_cfg, self.config.get("controller", {}))
        if enabled:
            self.hud_manager.update(self._hud_model())

    def toggle_hud(self) -> None:
        if self.hud_manager is None or not bool(self.config.get("hud", {}).get("enabled", False)):
            return
        duration = float(self.config["controller"].get("hud_duration_seconds", 6))
        self.hud_manager.toggle(self._hud_model(), duration)

    def refresh_hud(self) -> None:
        if self.hud_manager is None or not bool(self.config.get("hud", {}).get("enabled", False)):
            return
        self.hud_manager.update(self._hud_model())

    def setup(self) -> None:
        self.config = self.config_loader.load_initial()
        self.log(f"[config] loaded '{self.config_path}'")
        self.log(
            f"[config] summary {json.dumps({'profiles': list(self.config['profiles'].keys()), 'default_profile': self.config['controller']['default_profile']})}"
        )

        self.profile_manager = ProfileManager(self.config)
        self.state = StateManager(
            active_profile=self.profile_manager.get_active_profile(),
            flags=self.config.get("status_flags_defaults", {}),
        )

        midi_config = self.config["midi"]
        self.midi = MidiManager(
            input_port_name=midi_config["input_port"],
            output_port_name=midi_config["output_port"],
            auto_detect=bool(midi_config.get("auto_detect_ports", True)),
            match_substring=str(midi_config.get("auto_detect_match", "MPD218")),
            logger=self.log,
        )
        self.midi.open()

        self.led = LEDManager(
            midi=self.midi,
            midi_config=midi_config,
            led_config=self.config["led"],
            logger=self.log,
        )

        self.action_runner = ActionRunner(
            logger=self.log,
            on_profile_change=self.switch_profile,
            on_toggle_flag=lambda flag: self.state.toggle_flag(flag) if self.state else False,
        )

        hot_reload_ms = int(self.config["controller"].get("hot_reload_interval_ms", 750))
        self.hot_reload = HotReloadWatcher(hot_reload_ms)
        self._configure_context_manager()
        self._configure_hud_manager()

        self.led.startup_animation()
        self.render_active_profile()
        self.log("[app] MPD218 controller ready")

    def _configure_context_manager(self) -> None:
        assert self.profile_manager is not None

        mapping = self.config.get("context_profiles", {})
        if not mapping:
            self.context_manager = None
            return

        self.context_manager = ContextManager(mapping=mapping, logger=self.log)
        self.context_manager.sync_profile(self.profile_manager.get_active_profile())
        self.log(f"[context] enabled mappings={mapping}")

    def render_active_profile(self) -> None:
        assert self.profile_manager is not None
        assert self.led is not None
        profile = self.profile_manager.get_active_profile()
        actions = self.profile_manager.get_active_pad_actions()
        self.log(f"[profile] active={profile} actions={list(actions.keys())}")
        if self.state is not None:
            self.log(f"[state] {self.state.snapshot()}")
        self.led.render_profile(profile, actions)
        self.refresh_hud()

    def switch_profile(self, profile_name: str) -> None:
        assert self.profile_manager is not None
        assert self.state is not None
        assert self.led is not None

        old_profile = self.profile_manager.get_active_profile()
        if not self.profile_manager.set_active_profile(profile_name):
            self.log(f"[profile/error] unknown profile '{profile_name}'")
            return

        self.state.set_active_profile(profile_name)
        if self.context_manager is not None:
            self.context_manager.sync_profile(profile_name)
        self.pending_led_restore = []
        self.log(f"[profile] switched {old_profile} -> {profile_name}")
        self.led.profile_switch_animation()
        self.render_active_profile()

    def handle_pad_press(self, note: int, velocity: int, channel: int) -> None:
        assert self.profile_manager is not None
        assert self.state is not None
        assert self.led is not None
        assert self.action_runner is not None

        self.state.set_last_pressed_pad(note)
        self.current_bank = self._bank_for_note(note)
        action = self.profile_manager.get_pad_action(note)
        active_before = self.profile_manager.get_active_profile()
        reserved = set(self.config["led"].get("reserved_pads", []))
        hud_pad = int(self.config["controller"].get("hud_pad", 67))

        self.log(
            f"[pad] note={note} velocity={velocity} channel={channel} profile={active_before}"
        )

        if note == hud_pad or action.get("type") == "hud":
            self.toggle_hud()
            self.refresh_hud()
            return

        if note in reserved and action.get("type") not in ("profile", "hud"):
            self.log(f"[pad] note {note} is reserved; ignoring non-profile action")
            return

        self.led.send_note_on(note, self.led.pressed_brightness)
        profile_changed = self.action_runner.run_pad_action(action, note, velocity)
        active_after = self.profile_manager.get_active_profile()
        if profile_changed:
            manual_lock_seconds = float(
                self.config["controller"].get("manual_lock_seconds", 8)
            )
            self.state.activate_manual_lock(manual_lock_seconds)
            self.log(f"[context] manual lock for {manual_lock_seconds}s")
            self.refresh_hud()
            return

        # If profile changed externally, profile render already updated LEDs.
        if active_after != active_before:
            return

        self.pending_led_restore.append(
            (note, time.monotonic() + self.led.press_flash_seconds)
        )
        self.refresh_hud()

    def handle_knob_change(self, cc: int, value: int, channel: int) -> None:
        assert self.profile_manager is not None
        assert self.action_runner is not None
        threshold = int(self.config["controller"].get("knob_change_threshold", 2))
        previous = self.knob_last_values.get(cc)
        if previous is not None and abs(value - previous) < threshold:
            return
        self.knob_last_values[cc] = value
        action = self.profile_manager.get_knob_action(cc)
        self.log(f"[knob] cc={cc} value={value} channel={channel}")
        self.action_runner.run_knob_action(action, cc, value)

    def try_hot_reload(self) -> None:
        assert self.hot_reload is not None
        assert self.profile_manager is not None
        assert self.led is not None

        if not self.hot_reload.should_check():
            return

        changed, config, error = self.config_loader.reload_if_changed()
        if not changed:
            return
        if error:
            self.log(f"[config/error] reload failed: {error}")
            return
        assert config is not None

        self.config = config
        self.profile_manager.apply_new_config(config)
        self.led.update_settings(config["midi"], config["led"])
        self._configure_context_manager()
        self._configure_hud_manager()
        self.log("[config] hot reload successful")
        self.render_active_profile()

    def poll_context_profile(self) -> None:
        assert self.profile_manager is not None
        assert self.state is not None

        if self.context_manager is None:
            return

        if self.state.is_manual_locked():
            return

        target_profile = self.context_manager.update()
        if target_profile is None:
            return

        current_profile = self.profile_manager.get_active_profile()
        if target_profile == current_profile:
            return

        self.log(f"[context] switching profile {current_profile} -> {target_profile}")
        self.switch_profile(target_profile)

    def process_pending_led_restores(self) -> None:
        assert self.profile_manager is not None
        assert self.led is not None

        if not self.pending_led_restore:
            return

        now = time.monotonic()
        remaining: list[tuple[int, float]] = []
        active_profile = self.profile_manager.get_active_profile()
        active_actions = self.profile_manager.get_active_pad_actions()

        for note, restore_time in self.pending_led_restore:
            if now < restore_time:
                remaining.append((note, restore_time))
                continue

            if str(note) not in active_actions:
                self.led.off(note)
                continue
            action = active_actions[str(note)]
            if action.get("type") == "noop":
                self.led.off(note)
                continue

            self.led.send_note_on(note, self.led.note_idle_brightness(active_profile, note))

        self.pending_led_restore = remaining

    def run_loop(self) -> None:
        assert self.midi is not None

        midi_config = self.config["midi"]
        pad_min = int(midi_config.get("pad_note_range", {}).get("min", 36))
        pad_max = int(midi_config.get("pad_note_range", {}).get("max", 83))
        pad_channel = int(midi_config.get("pad_channel", 9))
        log_midi = bool(self.config["controller"].get("log_midi_input", True))

        while True:
            self.try_hot_reload()
            self.poll_context_profile()
            self.process_pending_led_restores()
            if self.hud_manager is not None and self.hud_manager.poll_hotkey():
                self.toggle_hud()

            try:
                while True:
                    note = self.hud_trigger_queue.get_nowait()
                    self.handle_pad_press(note, 127, pad_channel)
                    self.hud_trigger_queue.task_done()
            except queue.Empty:
                pass

            for msg in self.midi.poll_messages():
                if log_midi:
                    self.log(f"[midi/in] {msg}")

                try:
                    if msg.type == "note_on" and msg.velocity > 0 and msg.channel == pad_channel:
                        if pad_min <= msg.note <= pad_max:
                            self.handle_pad_press(msg.note, msg.velocity, msg.channel)
                        continue

                    if msg.type == "control_change" and msg.channel == pad_channel:
                        self.handle_knob_change(msg.control, msg.value, msg.channel)
                except Exception as exc:
                    self.log(f"[loop/error] event handling failed: {exc}")

            time.sleep(0.01)

    def run(self) -> int:
        try:
            self.setup()
            self.run_loop()
            return 0
        except KeyboardInterrupt:
            self.log("[app] stopped by user")
            return 0
        except Exception as exc:
            self.log(f"[app/error] {exc}")
            return 1
        finally:
            if self.midi is not None:
                try:
                    self.midi.close()
                except Exception:
                    pass


def main() -> int:
    parser = argparse.ArgumentParser(description="MPD218 control surface")
    parser.add_argument("--config", default="config.json", help="Path to config file")
    args = parser.parse_args()

    app = ControlSurfaceApp(config_path=args.config)
    return app.run()
