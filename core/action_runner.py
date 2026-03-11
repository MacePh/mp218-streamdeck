from typing import Any, Callable
from typing import Optional
import subprocess
import sys

from core import platform_utils
import psutil

try:
    import win32gui
    import win32process
    import win32con
    import ctypes
except Exception:
    win32gui = None
    win32process = None
    win32con = None
    ctypes = None


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

    # ── Process discovery ──────────────────────────────────────────────────────

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

    def _find_all_pids_for_process(self, process_substring: str) -> list[int]:
        """Return all PIDs whose process name contains the substring."""
        lowered = process_substring.lower()
        pids = []
        for process in psutil.process_iter(attrs=["pid", "name"]):
            try:
                name = (process.info.get("name") or "").lower()
                if lowered in name:
                    pids.append(int(process.info["pid"]))
            except Exception:
                continue
        return pids

    # ── Linux focus ───────────────────────────────────────────────────────────

    def _focus_window_linux(self, pid: int) -> bool:
        """
        Focus a window on Linux using wmctrl (preferred) or xdotool (fallback).
        Both tools can target windows by PID.
        """
        # Strategy 1: wmctrl -l -p lists all windows with PIDs
        try:
            result = subprocess.run(
                ["wmctrl", "-l", "-p"],
                capture_output=True, text=True, timeout=3
            )
            if result.returncode == 0:
                for line in result.stdout.splitlines():
                    parts = line.split(None, 4)
                    # format: <wid> <desktop> <pid> <host> <title>
                    if len(parts) >= 3:
                        try:
                            win_pid = int(parts[2])
                        except ValueError:
                            continue
                        if win_pid == pid:
                            wid = parts[0]
                            self._log(f"[action] wmctrl focus wid={wid} pid={pid}")
                            subprocess.run(
                                ["wmctrl", "-i", "-a", wid],
                                capture_output=True, timeout=3
                            )
                            return True
        except FileNotFoundError:
            self._log("[action] wmctrl not found, trying xdotool")
        except Exception as e:
            self._log(f"[action] wmctrl error: {e}")

        # Strategy 2: xdotool search --pid then windowactivate
        try:
            result = subprocess.run(
                ["xdotool", "search", "--pid", str(pid)],
                capture_output=True, text=True, timeout=3
            )
            if result.returncode == 0:
                wids = result.stdout.strip().splitlines()
                if wids:
                    # Use the last wid — for Electron apps the last one is usually
                    # the main visible window (earlier ones are background frames)
                    wid = wids[-1]
                    self._log(f"[action] xdotool focus wid={wid} pid={pid}")
                    subprocess.run(
                        ["xdotool", "windowactivate", "--sync", wid],
                        capture_output=True, timeout=3
                    )
                    return True
        except FileNotFoundError:
            self._log("[action] xdotool not found")
        except Exception as e:
            self._log(f"[action] xdotool error: {e}")

        return False

    # ── Windows focus ─────────────────────────────────────────────────────────

    def _find_window_by_title_substring(self, title_substring: str) -> Optional[int]:
        """Find a visible window whose title contains title_substring (case-insensitive)."""
        if win32gui is None:
            return None
        lowered = title_substring.lower()
        matched: list[tuple[int, str]] = []

        def _cb(hwnd: int, _extra: Any) -> bool:
            try:
                if not win32gui.IsWindowVisible(hwnd):
                    return True
                title = win32gui.GetWindowText(hwnd)
                if title and lowered in title.lower():
                    matched.append((hwnd, title))
            except Exception:
                pass
            return True

        win32gui.EnumWindows(_cb, None)
        if not matched:
            return None
        matched.sort(key=lambda x: (0 if x[1].lower().startswith(lowered) else 1))
        return matched[0][0]

    def _focus_window_by_pid(self, pid: int) -> bool:
        """Focus a window by PID — dispatches to Linux or Windows implementation."""
        if sys.platform != "win32":
            return self._focus_window_linux(pid)

        if win32gui is None or win32process is None:
            return False

        titled_windows: list[int] = []
        untitled_windows: list[int] = []

        def collect_windows(hwnd: int, _extra: Any) -> bool:
            try:
                if not win32gui.IsWindowVisible(hwnd):
                    return True
                _, window_pid = win32process.GetWindowThreadProcessId(hwnd)
                if window_pid == pid:
                    title = win32gui.GetWindowText(hwnd)
                    if title:
                        titled_windows.append(hwnd)
                    else:
                        untitled_windows.append(hwnd)
            except Exception:
                return True
            return True

        try:
            win32gui.EnumWindows(collect_windows, None)
            candidates = titled_windows if titled_windows else untitled_windows
            if not candidates:
                return False
            self._force_foreground(candidates[0])
            return True
        except Exception:
            return False

    def _force_foreground(self, hwnd: int) -> None:
        """Robustly bring a window to foreground, handling the Windows focus-lock."""
        try:
            import ctypes as _ctypes

            if win32gui.IsIconic(hwnd):
                win32gui.ShowWindow(hwnd, 9)  # SW_RESTORE

            current_thread = _ctypes.windll.kernel32.GetCurrentThreadId()
            target_thread, _ = win32process.GetWindowThreadProcessId(hwnd)

            attached = False
            if current_thread != target_thread:
                attached = bool(
                    _ctypes.windll.user32.AttachThreadInput(
                        current_thread, target_thread, True
                    )
                )

            win32gui.BringWindowToTop(hwnd)
            win32gui.SetForegroundWindow(hwnd)
            win32gui.ShowWindow(hwnd, 5)  # SW_SHOW

            if attached:
                _ctypes.windll.user32.AttachThreadInput(
                    current_thread, target_thread, False
                )
        except Exception as exc:
            self._log(f"[action] _force_foreground error: {exc}")

    # ── Main dispatcher ───────────────────────────────────────────────────────

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
                window_title = str(action.get("window_title", "")).strip()
                launch_command = str(action.get("command", action_value)).strip()

                if not process_substring and not window_title:
                    self._log("[action/error] focus_or_launch requires 'process' or 'window_title'")
                    return False
                if not launch_command:
                    self._log("[action/error] focus_or_launch requires 'command'")
                    return False

                # Windows-only: title-based focus for WebCatalog apps
                if window_title and sys.platform == "win32":
                    hwnd = self._find_window_by_title_substring(window_title)
                    if hwnd is not None:
                        self._log(f"[action] focus by window_title '{window_title}' hwnd={hwnd}")
                        self._force_foreground(hwnd)
                        return False
                    self._log(f"[action] window_title '{window_title}' not found, launching")
                    platform_utils.run_command(launch_command)
                    return False

                # Process-based focus (Linux + Windows fallback)
                all_pids = self._find_all_pids_for_process(process_substring)
                if all_pids:
                    self._log(f"[action] found {len(all_pids)} pid(s) for '{process_substring}'")
                    for pid in all_pids:
                        if self._focus_window_by_pid(pid):
                            return False
                    self._log(f"[action] could not focus any window for '{process_substring}', launching")
                    platform_utils.run_command(launch_command)
                    return False

                self._log(f"[action] launching process '{process_substring}'")
                platform_utils.run_command(launch_command)
                return False

            if action_type == "url":
                platform_utils.open_url(str(action_value))
                return False

            if action_type == "profile":
                self.on_profile_change(str(action_value))
                return True

            if action_type == "toggle_flag":
                return self.on_toggle_flag(str(action_value))

            if action_type == "hud":
                return True  # Handled by caller

            if action_type == "volume_step":
                platform_utils.volume_step(int(action_value))
                return False

            self._log(f"[action/warn] unknown action type: {action_type}")
            return False

        except Exception as exc:
            self._log(f"[action/error] {exc}")
            return False
