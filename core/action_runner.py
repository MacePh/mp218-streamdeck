from typing import Any, Callable
from typing import Optional

from core import platform_utils
import psutil

try:
    import win32gui
    import win32process
except Exception:
    win32gui = None
    win32process = None


class ActionRunner:
    def __init__(
        self,
        logger: Callable[[str], None],
        on_profile_change: Callable[[str], None],
        on_toggle_flag: Callable[[str], bool],
    ):
        self._log = logger
        self.on_profile_change = on_profile_change
        self.on_toggle_flag = on_toggle_flag

    def run_pad_action(self, action: dict[str, Any], note: int, velocity: int) -> bool:
        return self._run(action, source=f"pad:{note}", value=velocity)

    def run_knob_action(self, action: dict[str, Any], cc: int, cc_value: int) -> bool:
        return self._run(action, source=f"knob:{cc}", value=cc_value)

    def _find_process_pid(self, process_substring: str) -> Optional[int]:
        lowered = process_substring.lower()
        for process in psutil.process_iter(attrs=["pid", "name"]):
            try:
                name = (process.info.get("name") or "").lower()
                if lowered in name:
                    return int(process.info["pid"])
            except Exception:
                continue
        return None

    def _focus_window_by_pid(self, pid: int) -> bool:
        if win32gui is None or win32process is None:
            return False

        matched_windows: list[int] = []

        def collect_windows(hwnd: int, _extra: Any) -> bool:
            try:
                if not win32gui.IsWindowVisible(hwnd):
                    return True
                _, window_pid = win32process.GetWindowThreadProcessId(hwnd)
                if window_pid == pid:
                    matched_windows.append(hwnd)
            except Exception:
                return True
            return True

        try:
            win32gui.EnumWindows(collect_windows, None)
            if not matched_windows:
                return False
            target_hwnd = matched_windows[0]
            try:
                # Restore minimized windows before foreground focus attempt.
                win32gui.ShowWindow(target_hwnd, 9)  # SW_RESTORE
            except Exception:
                pass
            win32gui.SetForegroundWindow(target_hwnd)
            return True
        except Exception:
            return False

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

            if action_type == "focus_or_launch":
                process_substring = str(action.get("process", "")).strip().lower()
                launch_command = str(action.get("command", action_value)).strip()
                if not process_substring:
                    self._log("[action/error] focus_or_launch requires 'process'")
                    return False
                if not launch_command:
                    self._log("[action/error] focus_or_launch requires 'command'")
                    return False

                matched_pid = self._find_process_pid(process_substring)
                if matched_pid is not None:
                    self._log(f"[action] focus process {process_substring}")
                    if self._focus_window_by_pid(matched_pid):
                        return False
                    self._log(f"[action] failed to focus process {process_substring}")
                    self._log(f"[action] launching process {process_substring}")
                    platform_utils.run_command(launch_command)
                    return False

                self._log(f"[action] launching process {process_substring}")
                platform_utils.run_command(launch_command)
                return False

            if action_type == "url":
                platform_utils.open_url(str(action_value))
                return False

            if action_type == "profile":
                self.on_profile_change(str(action_value))
                return True

            if action_type == "toggle_flag":
                flag_name = str(action_value).strip()
                if not flag_name:
                    self._log("[action/error] toggle_flag requires flag name in 'value'")
                    return False
                new_value = self.on_toggle_flag(flag_name)
                self._log(f"[action] toggled flag {flag_name} -> {int(new_value)}")
                return False

            if action_type == "volume_step":
                step = int(action_value) if str(action_value).strip() else 1
                platform_utils.volume_step_placeholder(step)
                return False

            self._log(f"[action] unknown type='{action_type}'")
            return False
        except Exception as exc:
            self._log(f"[action/error] source={source} error={exc}")
            return False
