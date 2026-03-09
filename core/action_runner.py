from typing import Any, Callable

from core import platform_utils


class ActionRunner:
    def __init__(
        self,
        logger: Callable[[str], None],
        on_profile_change: Callable[[str], None],
    ):
        self._log = logger
        self.on_profile_change = on_profile_change

    def run_pad_action(self, action: dict[str, Any], note: int, velocity: int) -> bool:
        return self._run(action, source=f"pad:{note}", value=velocity)

    def run_knob_action(self, action: dict[str, Any], cc: int, cc_value: int) -> bool:
        return self._run(action, source=f"knob:{cc}", value=cc_value)

    def _run(self, action: dict[str, Any], source: str, value: int) -> bool:
        action_type = action.get("type", "noop")
        action_value = action.get("value", "")
        self._log(
            f"[action] source={source} type={action_type} value={action_value} input={value}"
        )

        try:
            if action_type == "noop":
                return False

            if action_type == "log":
                self._log(f"[action/log] {action_value}")
                return False

            if action_type == "cmd":
                platform_utils.run_command(str(action_value))
                return False

            if action_type == "url":
                platform_utils.open_url(str(action_value))
                return False

            if action_type == "profile":
                self.on_profile_change(str(action_value))
                return True

            if action_type == "volume_step":
                step = int(action_value) if str(action_value).strip() else 1
                platform_utils.volume_step_placeholder(step)
                return False

            self._log(f"[action] unknown type='{action_type}'")
            return False
        except Exception as exc:
            self._log(f"[action/error] source={source} error={exc}")
            return False
