from typing import Any, Callable
from typing import Optional
import subprocess
import threading

from core import platform_utils
from core.markdown_capture import MarkdownCapture
from core.openclaw_sender import OpenClawSender
from core.telegram_sender import TelegramSender
import psutil

try:
    from core.dictation_service import DictationService
except Exception:
    DictationService = None

try:
    from core.meeting_transcriber import MeetingTranscriber
except Exception:
    MeetingTranscriber = None  # type: ignore

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
        on_restart: Callable[[], None] | None = None,
    ):
        self._log = logger
        self.on_profile_change = on_profile_change
        self.on_toggle_flag = on_toggle_flag
        self.on_restart = on_restart
        self._dictation_sessions: dict[str, dict[str, Any]] = {}
        self._dictation_service = (
            DictationService(logger=self._log) if DictationService else None
        )
        self._transcriber = (
            MeetingTranscriber(logger=self._log) if MeetingTranscriber else None
        )
        self._hold_double_click_sessions: dict[str, threading.Event] = {}
        self._telegram_sender = TelegramSender(logger=self._log)
        self._openclaw_sender = OpenClawSender(logger=self._log)
        self._markdown_capture = MarkdownCapture(logger=self._log)

    def run_pad_action(self, action: dict[str, Any], note: int, velocity: int) -> bool:
        return self._run(action, source=f"pad:{note}", value=velocity)

    def run_knob_action(self, action: dict[str, Any], cc: int, cc_value: int) -> bool:
        return self._run(action, source=f"knob:{cc}", value=cc_value)

    def on_dictate_release(self, note: int) -> None:
        source = f"pad:{note}"
        entry = self._dictation_sessions.pop(source, None)
        if entry is None:
            self._log(f"[action] dictate release: no active session for {source}")
            return
        if self._dictation_service is None:
            return

        session = entry.get("session")
        mode = str(entry.get("mode", "inject"))
        action = entry.get("action", {})
        if session is None:
            self._log(f"[action] dictate release: invalid session for {source}")
            return

        self._log(f"[action] dictate stop + transcribe {source} mode={mode}")
        if mode == "telegram":
            self._dictation_service.stop_and_transcribe(
                session,
                on_text=lambda text: self._send_transcript_to_telegram(text, action),
            )
            return
        if mode == "openclaw":
            self._dictation_service.stop_and_transcribe(
                session,
                on_text=lambda text: self._send_transcript_to_openclaw(text, action),
            )
            return
        if mode == "markdown_daily":
            self._dictation_service.stop_and_transcribe(
                session,
                on_text=lambda text: self._append_transcript_to_markdown(text, action),
            )
            return

        self._dictation_service.stop_and_transcribe(session)

    def _send_transcript_to_telegram(self, text: str, action: dict[str, Any]) -> None:
        try:
            ok = self._telegram_sender.send_message(text, action)
            if ok:
                self._log(f"[action] dictated message sent: {text}")
        except Exception as exc:
            self._log(f"[action/error] dictate_to_telegram failed: {exc}")

    def _append_transcript_to_markdown(self, text: str, action: dict[str, Any]) -> None:
        try:
            directory = str(action.get("path", "")).strip()
            if not directory:
                raise RuntimeError("dictate_to_markdown requires 'path'")
            open_in_typora = bool(action.get("open_in_typora", False))
            self._markdown_capture.append_daily_entry(
                text=text,
                directory=directory,
                open_in_typora=open_in_typora,
            )
            self._log(f"[action] dictated markdown captured: {text}")
        except Exception as exc:
            self._log(f"[action/error] dictate_to_markdown failed: {exc}")

    def _send_transcript_to_openclaw(self, text: str, action: dict[str, Any]) -> None:
        try:
            ok = self._openclaw_sender.send_to_boris(text, action)
            if ok:
                self._log(f"[action] dictated OpenClaw message sent: {text}")
        except Exception as exc:
            self._log(f"[action/error] dictate_to_openclaw failed: {exc}")

    def _perform_double_click(self) -> None:
        if platform_utils.use_windows_paths():
            try:
                import pyautogui
                pyautogui.doubleClick()
            except Exception as exc:
                self._log(f"[action/error] hold_double_click win32: {exc}")
            return

        try:
            subprocess.run(
                ["xdotool", "click", "--repeat", "2", "--delay", "50", "1"],
                capture_output=True,
                timeout=2,
            )
        except Exception as exc:
            self._log(f"[action/error] hold_double_click linux: {exc}")

    def _start_hold_double_click(self, source: str, rate_hz: float) -> None:
        if source in self._hold_double_click_sessions:
            return

        safe_rate = rate_hz if rate_hz > 0 else 3.0
        interval_seconds = 1.0 / safe_rate
        stop_event = threading.Event()
        self._hold_double_click_sessions[source] = stop_event
        self._log(f"[action] hold_double_click start {source} rate={safe_rate:.2f}Hz")

        def _worker() -> None:
            while not stop_event.is_set():
                self._perform_double_click()
                if stop_event.wait(interval_seconds):
                    break

        thread = threading.Thread(target=_worker, daemon=True)
        thread.start()

    def on_hold_double_click_release(self, note: int) -> None:
        source = f"pad:{note}"
        stop_event = self._hold_double_click_sessions.pop(source, None)
        if stop_event is None:
            self._log(f"[action] hold_double_click release: no active session for {source}")
            return
        stop_event.set()
        self._log(f"[action] hold_double_click stop {source}")

    def _find_process_pid(self, process_substring: str) -> Optional[int]:
        lowered = process_substring.lower()
        for process in psutil.process_iter(attrs=["pid", "name", "cmdline"]):
            try:
                name = (process.info.get("name") or "").lower()
                cmdline = " ".join(process.info.get("cmdline") or []).lower()
                if lowered in name or lowered in cmdline:
                    return int(process.info["pid"])
            except Exception:
                continue
        return None

    def _find_all_pids_for_process(self, process_substring: str) -> list[int]:
        lowered = process_substring.lower()
        pids = []
        for process in psutil.process_iter(attrs=["pid", "name", "cmdline"]):
            try:
                name = (process.info.get("name") or "").lower()
                cmdline = " ".join(process.info.get("cmdline") or []).lower()
                if lowered in name or lowered in cmdline:
                    pids.append(int(process.info["pid"]))
            except Exception:
                continue
        return pids

    def _focus_window_linux(self, pid: int) -> bool:
        try:
            result = subprocess.run(
                ["wmctrl", "-l", "-p"],
                capture_output=True, text=True, timeout=3
            )
            if result.returncode == 0:
                for line in result.stdout.splitlines():
                    parts = line.split(None, 4)
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

        try:
            result = subprocess.run(
                ["xdotool", "search", "--pid", str(pid)],
                capture_output=True, text=True, timeout=3
            )
            if result.returncode == 0:
                wids = result.stdout.strip().splitlines()
                if wids:
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

    def _find_window_by_title_substring(
        self, title_substring: str, process_substring: str = ""
    ) -> Optional[int]:
        if win32gui is None:
            return None
        lowered = title_substring.lower()
        process_lowered = process_substring.lower().strip()
        matched: list[tuple[int, str]] = []

        def _cb(hwnd: int, _extra: Any) -> bool:
            try:
                if not win32gui.IsWindowVisible(hwnd):
                    return True
                title = win32gui.GetWindowText(hwnd)
                if not title or lowered not in title.lower():
                    return True
                if process_lowered:
                    if win32process is None:
                        return True
                    _, window_pid = win32process.GetWindowThreadProcessId(hwnd)
                    proc = psutil.Process(window_pid)
                    process_name = (proc.name() or "").lower()
                    process_cmdline = " ".join(proc.cmdline() or []).lower()
                    if (
                        process_lowered not in process_name
                        and process_lowered not in process_cmdline
                    ):
                        return True
                if title:
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
        if not platform_utils.use_windows_paths():
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

    def _collect_windows_for_pids(self, pids: list[int]) -> list[tuple[str, str]]:
        pid_set = {int(pid) for pid in pids}
        if not pid_set:
            return []

        windows: list[tuple[str, str]] = []

        if platform_utils.use_windows_paths():
            if win32gui is None or win32process is None:
                return []

            def _cb(hwnd: int, _extra: Any) -> bool:
                try:
                    if not win32gui.IsWindowVisible(hwnd):
                        return True
                    _, window_pid = win32process.GetWindowThreadProcessId(hwnd)
                    if window_pid not in pid_set:
                        return True
                    title = (win32gui.GetWindowText(hwnd) or "").strip()
                    if title:
                        windows.append((str(hwnd), title))
                except Exception:
                    pass
                return True

            try:
                win32gui.EnumWindows(_cb, None)
            except Exception:
                return []
            return windows

        try:
            result = subprocess.run(
                ["wmctrl", "-l", "-p"],
                capture_output=True,
                text=True,
                timeout=3,
            )
            if result.returncode == 0:
                for line in result.stdout.splitlines():
                    parts = line.split(None, 4)
                    if len(parts) < 5:
                        continue
                    try:
                        window_pid = int(parts[2])
                    except ValueError:
                        continue
                    if window_pid not in pid_set:
                        continue
                    title = (parts[4] or "").strip()
                    if not title:
                        continue
                    windows.append((parts[0], title))
                return windows
        except FileNotFoundError:
            pass
        except Exception:
            return windows

        for pid in pid_set:
            try:
                result = subprocess.run(
                    ["xdotool", "search", "--pid", str(pid)],
                    capture_output=True,
                    text=True,
                    timeout=3,
                )
            except Exception:
                continue
            if result.returncode != 0:
                continue

            for wid in result.stdout.strip().splitlines():
                if not wid:
                    continue
                try:
                    name_result = subprocess.run(
                        ["xdotool", "getwindowname", wid],
                        capture_output=True,
                        text=True,
                        timeout=3,
                    )
                except Exception:
                    continue
                if name_result.returncode != 0:
                    continue
                title = (name_result.stdout or "").strip()
                if title:
                    windows.append((wid, title))

        return windows

    def _show_window_picker(self, windows: list[tuple[str, str]]) -> str | None:
        try:
            import tkinter as tk

            selected_window_id: str | None = None
            root = tk.Tk()
            root.configure(bg="#111214")
            root.overrideredirect(True)
            root.attributes("-topmost", True)

            container = tk.Frame(root, bg="#111214", padx=12, pady=10)
            container.pack(fill="both", expand=True)

            title_label = tk.Label(
                container,
                text="Select Window",
                bg="#111214",
                fg="#EFEFEF",
                anchor="w",
            )
            title_label.pack(fill="x")

            listbox = tk.Listbox(
                container,
                bg="#111214",
                fg="#EFEFEF",
                selectbackground="#2A2D33",
                selectforeground="#EFEFEF",
                highlightthickness=1,
                highlightbackground="#2A2D33",
                activestyle="none",
                relief="flat",
            )
            for _wid, title in windows:
                listbox.insert("end", title)
            listbox.pack(fill="both", expand=True, pady=(8, 0))

            if windows:
                listbox.selection_set(0)
                listbox.activate(0)

            def _confirm(_event: Any = None) -> None:
                nonlocal selected_window_id
                selection = listbox.curselection()
                if not selection:
                    return
                selected_window_id = windows[selection[0]][0]
                root.destroy()

            def _cancel(_event: Any = None) -> None:
                nonlocal selected_window_id
                selected_window_id = None
                root.destroy()

            listbox.bind("<Double-Button-1>", _confirm)
            listbox.bind("<Return>", _confirm)
            listbox.bind("<Escape>", _cancel)
            root.bind("<Escape>", _cancel)
            root.bind("<Return>", _confirm)

            root.update_idletasks()
            width = 560
            row_count = max(1, min(len(windows), 12))
            height = 92 + (row_count * 24)
            screen_width = root.winfo_screenwidth()
            screen_height = root.winfo_screenheight()
            x = max(0, (screen_width - width) // 2)
            y = max(0, (screen_height - height) // 2)
            root.geometry(f"{width}x{height}+{x}+{y}")

            root.grab_set()
            listbox.focus_set()
            root.wait_window()
            return selected_window_id
        except Exception:
            return None

    def _focus_window_by_id(self, window_id_str: str) -> bool:
        if platform_utils.use_windows_paths():
            if win32gui is None:
                return False
            try:
                self._force_foreground(int(window_id_str))
                return True
            except Exception:
                return False

        try:
            result = subprocess.run(
                ["wmctrl", "-i", "-a", window_id_str],
                capture_output=True,
                timeout=3,
            )
            if result.returncode == 0:
                return True
        except FileNotFoundError:
            pass
        except Exception:
            return False

        try:
            result = subprocess.run(
                ["xdotool", "windowactivate", "--sync", window_id_str],
                capture_output=True,
                timeout=3,
            )
            return result.returncode == 0
        except Exception:
            return False

    def _force_foreground(self, hwnd: int) -> None:
        try:
            import ctypes as _ctypes

            if win32gui.IsIconic(hwnd):
                win32gui.ShowWindow(hwnd, 9)

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
            win32gui.ShowWindow(hwnd, 5)

            if attached:
                _ctypes.windll.user32.AttachThreadInput(
                    current_thread, target_thread, False
                )
        except Exception as exc:
            self._log(f"[action] _force_foreground error: {exc}")

    def _run_key_combo(self, combo: str) -> None:
        combo_text = str(combo).strip()
        if not combo_text:
            raise RuntimeError("key_combo requires non-empty 'value'")
        if platform_utils.use_windows_paths():
            try:
                import pyautogui
                keys = [part.strip().lower() for part in combo_text.split("+") if part.strip()]
                if not keys:
                    raise RuntimeError("key_combo resolved to no keys")
                pyautogui.hotkey(*keys)
                return
            except Exception as exc:
                raise RuntimeError(f"key_combo windows failed: {exc}") from exc

        try:
            subprocess.run(
                ["xdotool", "key", combo_text],
                capture_output=True,
                timeout=3,
                check=True,
            )
        except Exception as exc:
            raise RuntimeError(f"key_combo linux failed: {exc}") from exc

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

            if action_type == "restart":
                if self.on_restart is None:
                    self._log("[action/warn] restart: no handler configured")
                    return False
                self._log("[action] restart requested")
                self.on_restart()
                return False

            if action_type == "cmd":
                if platform_utils.use_windows_paths() and action.get("value_windows"):
                    platform_utils.run_command(str(action["value_windows"]))
                else:
                    platform_utils.run_command(str(action_value))
                return False

            if action_type == "new_markdown_doc":
                directory = str(action.get("path", "")).strip()
                if not directory:
                    self._log("[action/error] new_markdown_doc requires 'path'")
                    return False
                title = str(action.get("title", "Untitled Idea")).strip() or "Untitled Idea"
                open_in_typora = bool(action.get("open_in_typora", True))
                self._markdown_capture.create_new_document(
                    directory=directory,
                    template_title=title,
                    open_in_typora=open_in_typora,
                )
                return False

            if action_type == "key_combo":
                self._run_key_combo(str(action_value))
                return False

            if action_type in ("dictate", "dictate_to_telegram", "dictate_to_markdown", "dictate_to_openclaw"):
                if self._dictation_service is None:
                    self._log("[action/warn] dictate: DictationService unavailable")
                    return False
                model = str(action.get("model", "base.en"))
                language = str(action.get("language", "en"))
                input_device = action.get("input_device")
                self._log(f"[action] dictate start note={source} model={model}")
                session = self._dictation_service.start_recording(
                    model=model,
                    language=language,
                    input_device=input_device,
                )
                if session is not None:
                    mode = "inject"
                    if action_type == "dictate_to_telegram":
                        mode = "telegram"
                    elif action_type == "dictate_to_openclaw":
                        mode = "openclaw"
                    elif action_type == "dictate_to_markdown":
                        mode = "markdown_daily"
                    self._dictation_sessions[source] = {
                        "session": session,
                        "mode": mode,
                        "action": action,
                    }
                return False

            if action_type == "hold_double_click":
                rate_hz = float(action.get("rate_hz", 3))
                self._start_hold_double_click(source, rate_hz=rate_hz)
                return False

            if action_type == "focus_or_launch":
                process_substring = str(action.get("process", "")).strip().lower()
                window_title = str(action.get("window_title", "")).strip()
                if platform_utils.use_windows_paths() and action.get("command_windows"):
                    launch_command = str(action["command_windows"]).strip()
                else:
                    launch_command = str(action.get("command", "")).strip()

                if not process_substring and not window_title:
                    self._log("[action/error] focus_or_launch requires 'process' or 'window_title'")
                    return False
                if not launch_command:
                    self._log("[action/error] focus_or_launch requires 'command'")
                    return False

                if window_title and platform_utils.use_windows_paths():
                    hwnd = self._find_window_by_title_substring(
                        window_title, process_substring
                    )
                    if hwnd is not None:
                        self._log(f"[action] focus by window_title '{window_title}' hwnd={hwnd}")
                        self._force_foreground(hwnd)
                        try:
                            if win32gui is not None and win32gui.GetForegroundWindow() == hwnd:
                                return False
                        except Exception:
                            pass
                        self._log(
                            f"[action] foreground check failed for '{window_title}', launching"
                        )
                        platform_utils.run_command(launch_command)
                        return False
                    self._log(f"[action] window_title '{window_title}' not found, launching")
                    platform_utils.run_command(launch_command)
                    return False

                all_pids = self._find_all_pids_for_process(process_substring)
                if all_pids:
                    self._log(f"[action] found {len(all_pids)} pid(s) for '{process_substring}'")
                    windows = self._collect_windows_for_pids(all_pids)
                    self._log(f"[action] found {len(windows)} window(s) for '{process_substring}'")

                    if len(windows) == 1:
                        self._focus_window_by_id(windows[0][0])
                        return False

                    if len(windows) > 1:
                        chosen_id = self._show_window_picker(windows)
                        if chosen_id is not None:
                            self._focus_window_by_id(chosen_id)
                            return False
                        self._log(f"[action] window picker cancelled for '{process_substring}'")
                        return False

                    self._log(f"[action] no windows found for '{process_substring}', launching")
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
                flag_name = str(action_value).strip()
                if not flag_name:
                    self._log("[action/error] toggle_flag requires flag name in 'value'")
                    return False
                new_value = self.on_toggle_flag(flag_name)
                self._log(f"[action] toggled flag {flag_name} -> {int(bool(new_value))}")
                return False

            if action_type == "hud":
                return False

            if action_type == "volume_step":
                step = int(value)
                platform_utils.volume_step(step)
                return False

            if action_type == "media_step":
                step = int(value)
                platform_utils.media_step(step)
                return False

            if action_type == "brightness_step":
                step = int(value)
                platform_utils.brightness_step(step)
                return False

            if action_type == "scroll_step":
                step = int(value)
                platform_utils.scroll_vertical(step)
                return False

            if action_type == "tab_step":
                step = int(value)
                platform_utils.tab_step(step)
                return False

            if action_type == "zoom_step":
                step = int(value)
                platform_utils.zoom_step(step)
                return False

            if action_type == "transcribe_stream":
                if self._transcriber is None:
                    self._log("[action/warn] transcribe_stream: MeetingTranscriber unavailable")
                    return False
                if self._transcriber.running:
                    self._transcriber.stop()
                else:
                    self._transcriber.start()
                return False

            self._log(f"[action/warn] unknown action type: {action_type}")
            return False

        except Exception as exc:
            self._log(f"[action/error] {exc}")
            return False
