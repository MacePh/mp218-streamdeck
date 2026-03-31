import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any
import webbrowser
import ctypes
import ctypes.wintypes
import time

# ── Virtual key codes ──────────────────────────────────────────────────────────
VK_VOLUME_MUTE   = 0xAD
VK_VOLUME_DOWN   = 0xAE
VK_VOLUME_UP     = 0xAF
VK_MEDIA_NEXT    = 0xB0
VK_MEDIA_PREV    = 0xB1
VK_MEDIA_STOP    = 0xB2
VK_MEDIA_PLAY    = 0xB3
VK_CTRL          = 0x11
VK_SHIFT         = 0x10
VK_TAB           = 0x09
VK_OEM_PLUS      = 0xBB   # = / +
VK_OEM_MINUS     = 0xBD   # - / _
VK_PERIOD        = 0xBE   # .   (YouTube speed up)
VK_COMMA         = 0xBC   # ,   (YouTube slow down)
VK_OEM_4         = 0xDB   # [   (VLC slow down)
VK_OEM_6         = 0xDD   # ]   (VLC speed up)
VK_V             = 0x56
VK_MENU          = 0x12  # Alt — brief tap can relax foreground lock before SetForegroundWindow

KEYEVENTF_KEYUP    = 0x0002
KEYEVENTF_UNICODE  = 0x0004
INPUT_KEYBOARD     = 1

CF_UNICODETEXT = 13
GMEM_MOVEABLE = 0x0002

# SendInput expects sizeof(INPUT) to match the Win32 union (keyboard vs mouse).
# A keyboard-only struct is smaller on x64 and can cause SendInput to misread events.
_ULONG_PTR = getattr(ctypes.wintypes, "ULONG_PTR", ctypes.c_size_t)


# ── ctypes input structs ───────────────────────────────────────────────────────
class MOUSEINPUT(ctypes.Structure):
    _fields_ = [
        ("dx",          ctypes.wintypes.LONG),
        ("dy",          ctypes.wintypes.LONG),
        ("mouseData",   ctypes.wintypes.DWORD),
        ("dwFlags",     ctypes.wintypes.DWORD),
        ("time",        ctypes.wintypes.DWORD),
        ("dwExtraInfo", _ULONG_PTR),
    ]


class KEYBDINPUT(ctypes.Structure):
    _fields_ = [
        ("wVk",         ctypes.wintypes.WORD),
        ("wScan",       ctypes.wintypes.WORD),
        ("dwFlags",     ctypes.wintypes.DWORD),
        ("time",        ctypes.wintypes.DWORD),
        ("dwExtraInfo", _ULONG_PTR),
    ]


class _INPUT_UNION(ctypes.Union):
    _fields_ = [("mi", MOUSEINPUT), ("ki", KEYBDINPUT)]


class INPUT(ctypes.Structure):
    _fields_ = [("type", ctypes.wintypes.DWORD), ("_input", _INPUT_UNION)]


def _zeroed_keyboard_input() -> INPUT:
    """Full INPUT (40 bytes on x64) zeroed so the keyboard/mouse union has no garbage tail."""
    return INPUT.from_buffer_copy(bytes(ctypes.sizeof(INPUT)))


def _send_key(vk: int, flags: int = 0) -> int:
    inp = _zeroed_keyboard_input()
    inp.type = INPUT_KEYBOARD
    inp._input.ki.wVk = vk
    inp._input.ki.dwFlags = flags
    return int(ctypes.windll.user32.SendInput(1, ctypes.byref(inp), ctypes.sizeof(inp)))


def _press(vk: int) -> None:
    _send_key(vk, 0)
    _send_key(vk, KEYEVENTF_KEYUP)


def _combo(*vks: int) -> None:
    """Press all keys down in order, then release in reverse."""
    for vk in vks:
        _send_key(vk, 0)
    for vk in reversed(vks):
        _send_key(vk, KEYEVENTF_KEYUP)


def _combo_sendinput(*vks: int) -> bool:
    """Return True if every SendInput call succeeded (each should return 1)."""
    for vk in vks:
        if _send_key(vk, 0) != 1:
            return False
    for vk in reversed(vks):
        if _send_key(vk, KEYEVENTF_KEYUP) != 1:
            return False
    return True


def _paste_ctrl_v() -> None:
    """Synthetic Ctrl+V; fall back to keybd_event if SendInput fails (policies / drivers)."""
    if _combo_sendinput(VK_CTRL, VK_V):
        return
    user32 = ctypes.windll.user32
    for vk in (VK_CTRL, VK_V):
        user32.keybd_event(vk, 0, 0, 0)
    for vk in reversed((VK_CTRL, VK_V)):
        user32.keybd_event(vk, 0, KEYEVENTF_KEYUP, 0)


def _iter_utf16_code_units(text: str) -> list[int]:
    encoded = text.encode("utf-16-le")
    return [int.from_bytes(encoded[index:index + 2], "little") for index in range(0, len(encoded), 2)]


def _get_foreground_window() -> int:
    return int(ctypes.windll.user32.GetForegroundWindow())


def _wait_for_foreground_window(timeout_seconds: float = 0.5, poll_interval_seconds: float = 0.02) -> int:
    deadline = time.monotonic() + max(0.0, timeout_seconds)
    hwnd = 0
    while time.monotonic() <= deadline:
        hwnd = _get_foreground_window()
        if hwnd:
            return hwnd
        time.sleep(poll_interval_seconds)
    return hwnd


def capture_foreground_window() -> int:
    return _wait_for_foreground_window()


def restore_foreground_window(
    hwnd: int,
    settle_delay_seconds: float = 0.05,
    use_alt_unlock: bool = False,
) -> bool:
    if not hwnd:
        return False

    user32 = ctypes.windll.user32
    kernel32 = ctypes.windll.kernel32
    try:
        if not user32.IsWindow(hwnd):
            return False

        if user32.IsIconic(hwnd):
            user32.ShowWindow(hwnd, 9)

        if use_alt_unlock:
            _press(VK_MENU)
            time.sleep(0.02)

        current_foreground = user32.GetForegroundWindow()
        current_thread = kernel32.GetCurrentThreadId()
        target_thread = user32.GetWindowThreadProcessId(hwnd, None)
        foreground_thread = 0
        if current_foreground:
            foreground_thread = user32.GetWindowThreadProcessId(current_foreground, None)

        attached_target = False
        attached_foreground = False
        if target_thread and current_thread != target_thread:
            attached_target = bool(user32.AttachThreadInput(current_thread, target_thread, True))
        if foreground_thread and foreground_thread not in (current_thread, target_thread):
            attached_foreground = bool(user32.AttachThreadInput(current_thread, foreground_thread, True))

        user32.BringWindowToTop(hwnd)
        user32.SetForegroundWindow(hwnd)
        user32.ShowWindow(hwnd, 5)
        time.sleep(max(0.0, settle_delay_seconds))

        if attached_foreground:
            user32.AttachThreadInput(current_thread, foreground_thread, False)
        if attached_target:
            user32.AttachThreadInput(current_thread, target_thread, False)
        return int(user32.GetForegroundWindow()) == int(hwnd)
    except Exception:
        return False


def send_unicode_text(text: str) -> bool:
    """Attempt direct Unicode injection via SendInput.

    Returns True only when every keydown/keyup event was accepted by SendInput.
    Note: some Windows apps still ignore VK_PACKET/WM_CHAR input even when the
    API reports success, so callers that need reliable visible insertion should
    keep a fallback strategy.
    """
    if not text:
        return True

    for code_unit in _iter_utf16_code_units(text):
        key_down = _zeroed_keyboard_input()
        key_down.type = INPUT_KEYBOARD
        key_down._input.ki.wVk = 0
        key_down._input.ki.wScan = code_unit
        key_down._input.ki.dwFlags = KEYEVENTF_UNICODE

        key_up = _zeroed_keyboard_input()
        key_up.type = INPUT_KEYBOARD
        key_up._input.ki.wVk = 0
        key_up._input.ki.wScan = code_unit
        key_up._input.ki.dwFlags = KEYEVENTF_UNICODE | KEYEVENTF_KEYUP

        if ctypes.windll.user32.SendInput(1, ctypes.byref(key_down), ctypes.sizeof(key_down)) != 1:
            return False
        if ctypes.windll.user32.SendInput(1, ctypes.byref(key_up), ctypes.sizeof(key_up)) != 1:
            return False
    return True


def _open_clipboard_with_retries(owner: int = 0, retries: int = 10, delay_seconds: float = 0.02) -> bool:
    for _ in range(max(1, retries)):
        if ctypes.windll.user32.OpenClipboard(owner):
            return True
        time.sleep(delay_seconds)
    return False


def _get_clipboard_unicode_text() -> str | None:
    if not _open_clipboard_with_retries():
        return None
    handle = None
    locked = None
    try:
        if not ctypes.windll.user32.IsClipboardFormatAvailable(CF_UNICODETEXT):
            return ""
        handle = ctypes.windll.user32.GetClipboardData(CF_UNICODETEXT)
        if not handle:
            return ""
        locked = ctypes.windll.kernel32.GlobalLock(handle)
        if not locked:
            return ""
        return ctypes.wstring_at(locked)
    finally:
        if locked:
            ctypes.windll.kernel32.GlobalUnlock(handle)
        ctypes.windll.user32.CloseClipboard()


def _set_clipboard_unicode_text(text: str) -> None:
    data = f"{text}\x00".encode("utf-16-le")
    handle = ctypes.windll.kernel32.GlobalAlloc(GMEM_MOVEABLE, len(data))
    if not handle:
        raise OSError("GlobalAlloc failed for clipboard text")

    locked = ctypes.windll.kernel32.GlobalLock(handle)
    if not locked:
        ctypes.windll.kernel32.GlobalFree(handle)
        raise OSError("GlobalLock failed for clipboard text")

    try:
        ctypes.memmove(locked, data, len(data))
    finally:
        ctypes.windll.kernel32.GlobalUnlock(handle)

    if not _open_clipboard_with_retries():
        ctypes.windll.kernel32.GlobalFree(handle)
        raise OSError("OpenClipboard failed")

    try:
        if not ctypes.windll.user32.EmptyClipboard():
            raise OSError("EmptyClipboard failed")
        if not ctypes.windll.user32.SetClipboardData(CF_UNICODETEXT, handle):
            raise OSError("SetClipboardData failed")
        handle = None
    finally:
        ctypes.windll.user32.CloseClipboard()
        if handle:
            ctypes.windll.kernel32.GlobalFree(handle)


def paste_text_via_clipboard(text: str, restore_delay_seconds: float = 0.15) -> bool:
    if not text:
        return True

    _wait_for_foreground_window()
    original_text = _get_clipboard_unicode_text()
    had_clipboard_text = original_text is not None

    _set_clipboard_unicode_text(text)
    time.sleep(0.06)
    _paste_ctrl_v()
    time.sleep(max(0.0, restore_delay_seconds))

    if had_clipboard_text:
        try:
            _set_clipboard_unicode_text(original_text or "")
        except Exception:
            pass
    return True


def _restore_foreground_with_retries(hwnd: int, attempts: int = 3, retry_delay_seconds: float = 0.07) -> bool:
    for attempt in range(max(1, attempts)):
        if attempt:
            time.sleep(max(0.0, retry_delay_seconds))
        use_alt = attempt > 0
        if restore_foreground_window(hwnd, use_alt_unlock=use_alt):
            return True
    return False


def _try_pywinauto_insert_at_focus(text: str, target_hwnd: int) -> bool:
    """Insert text at the keyboard caret via UI Automation (ValuePattern).

    Uses pywinauto (Microsoft UI Automation) so we avoid SendInput/UIPI issues
    for standard Edit controls. Skips non-Edit focus (e.g. browser Document)
    and returns False so callers can fall back to clipboard paste.

    Runs from a worker thread; initializes COM (STA) per Microsoft guidance.
    """
    if os.name != "nt" or not text.strip() or not target_hwnd:
        return False

    pythoncom: Any = None
    com_initialized = False
    try:
        import pythoncom as _pythoncom

        pythoncom = _pythoncom
        _pythoncom.CoInitialize()
        com_initialized = True
    except Exception:
        pass

    try:
        from pywinauto.controls.uia_controls import EditWrapper
        from pywinauto.controls.uiawrapper import UIAWrapper
        from pywinauto.uia_defines import IUIA
        from pywinauto.uia_element_info import UIAElementInfo
    except ImportError:
        return False

    try:
        focused = IUIA().get_focused_element()
        if focused is None:
            return False
        wrap = UIAWrapper(UIAElementInfo(focused))
        if not isinstance(wrap, EditWrapper):
            return False
        try:
            top = wrap.top_level_parent()
        except Exception:
            return False
        if int(top.handle) != int(target_hwnd):
            return False
        start, end = wrap.selection_indices()
        wrap.set_edit_text(text, pos_start=start, pos_end=end)
        return True
    except Exception:
        return False
    finally:
        if com_initialized and pythoncom is not None:
            try:
                pythoncom.CoUninitialize()
            except Exception:
                pass


def send_text_windows(text: str, target_hwnd: int | None = None) -> str:
    """Send text to the intended Windows app.

    Plain dictation often finishes a moment after the user releases the pad, so
    the foreground window may have changed by the time we inject. When we know
    the original target HWND, restore focus first and then use clipboard paste
    as the dependable insertion path.
    """
    if not text:
        return "noop"

    resolved_target = int(target_hwnd or 0)
    if resolved_target:
        restored = _restore_foreground_with_retries(resolved_target)
        time.sleep(0.04)
        if _try_pywinauto_insert_at_focus(text, resolved_target):
            return "uia-restored" if restored else "uia-fallback"
        if restored:
            paste_text_via_clipboard(text)
            return "clipboard-restored"
        paste_text_via_clipboard(text)
        return "clipboard-fallback"

    hwnd_before = _wait_for_foreground_window()
    unicode_sent = send_unicode_text(text)
    hwnd_after = _get_foreground_window()
    if unicode_sent and hwnd_before and hwnd_after and hwnd_before == hwnd_after:
        # We cannot reliably verify visible insertion for VK_PACKET delivery.
        # Use clipboard paste as the dependable path while keeping the direct
        # injection attempt for apps that do honor it.
        paste_text_via_clipboard(text)
        return "clipboard"

    if unicode_sent:
        return "unicode"

    paste_text_via_clipboard(text)
    return "clipboard"


# ── Platform helpers ───────────────────────────────────────────────────────────
def is_windows() -> bool:
    return os.name == "nt"


def use_windows_paths() -> bool:
    """
    True when Windows-style paths and desktop APIs (cmd.exe, F:\\..., win32gui)
    should be used. Includes CPython win32 plus Git Bash / MSYS2 / Cygwin
    interpreters (sys.platform msys/cygwin), but not WSL (linux).
    """
    return sys.platform in ("win32", "msys", "cygwin")


def is_linux() -> bool:
    return os.name == "posix"


def run_command(command: str) -> subprocess.Popen:
    if is_windows():
        return subprocess.Popen(command, shell=True)
    return subprocess.Popen(command, shell=True)


def open_url(url: str) -> bool:
    return webbrowser.open(url)


def resolve_firefox_executable() -> str | None:
    resolved = shutil.which("firefox")
    if resolved:
        return resolved
    if not use_windows_paths():
        return None
    program_files = os.environ.get("ProgramFiles", r"C:\Program Files")
    program_files_x86 = os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)")
    for candidate in (
        Path(program_files) / "Mozilla Firefox" / "firefox.exe",
        Path(program_files_x86) / "Mozilla Firefox" / "firefox.exe",
    ):
        if candidate.is_file():
            return str(candidate)
    return None


def open_url_in_firefox(url: str) -> bool:
    """Open a URL in Mozilla Firefox. Returns True if firefox.exe was launched."""
    link = str(url).strip()
    if not link:
        return False
    firefox = resolve_firefox_executable()
    if not firefox:
        return False
    subprocess.Popen(
        [firefox, "-url", link],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    return True


# ── Volume ─────────────────────────────────────────────────────────────────────
def volume_up() -> None:
    """Raise system volume by one virtual key tick (~2%)."""
    if is_windows():
        _press(VK_VOLUME_UP)
    else:
        subprocess.run(["pactl", "set-sink-volume", "@DEFAULT_SINK@", "+2%"],
                       capture_output=True, timeout=2)


def volume_down() -> None:
    """Lower system volume by one virtual key tick (~2%)."""
    if is_windows():
        _press(VK_VOLUME_DOWN)
    else:
        subprocess.run(["pactl", "set-sink-volume", "@DEFAULT_SINK@", "-2%"],
                       capture_output=True, timeout=2)


def volume_step(step: int) -> None:
    """
    step > 0 → volume up (called once per unit)
    step < 0 → volume down
    The MIDI knob will call this with step=1 or step=-1 on each tick.
    """
    fn = volume_up if step >= 0 else volume_down
    for _ in range(abs(step)):
        fn()


# ── Media transport ────────────────────────────────────────────────────────────
def media_next() -> None:
    if is_windows():
        _press(VK_MEDIA_NEXT)
    else:
        subprocess.run(["playerctl", "next"], capture_output=True, timeout=2)


def media_prev() -> None:
    if is_windows():
        _press(VK_MEDIA_PREV)
    else:
        subprocess.run(["playerctl", "previous"], capture_output=True, timeout=2)


def media_play_pause() -> None:
    if is_windows():
        _press(VK_MEDIA_PLAY)
    else:
        subprocess.run(["playerctl", "play-pause"], capture_output=True, timeout=2)


def media_step(step: int) -> None:
    """step > 0 → next track, step < 0 → previous track."""
    if step >= 0:
        media_next()
    else:
        media_prev()


# ── Brightness ────────────────────────────────────────────────────────────────
def brightness_up() -> None:
    if is_windows():
        _wmi_brightness(+10)
    else:
        subprocess.run(["xdotool", "key", "XF86MonBrightnessUp"],
                       capture_output=True, timeout=2)


def brightness_down() -> None:
    if is_windows():
        _wmi_brightness(-10)
    else:
        subprocess.run(["xdotool", "key", "XF86MonBrightnessDown"],
                       capture_output=True, timeout=2)


def _wmi_brightness(delta: int) -> None:
    """Adjust brightness via WMI. Works on laptops; desktop monitors usually ignore this."""
    script = (
        "$b = (Get-WmiObject -Namespace root/WMI -Class WmiMonitorBrightness).CurrentBrightness;"
        f"$n = [math]::Max(0,[math]::Min(100,$b+({delta})));"
        "(Get-WmiObject -Namespace root/WMI -Class WmiMonitorBrightnessMethods)"
        ".WmiSetBrightness(1,$n)"
    )
    try:
        subprocess.run(
            ["powershell", "-NoProfile", "-NonInteractive", "-Command", script],
            capture_output=True, timeout=5,
        )
    except Exception as e:
        print(f"[platform][brightness] WMI error: {e}")


def brightness_step(step: int) -> None:
    fn = brightness_up if step >= 0 else brightness_down
    for _ in range(abs(step)):
        fn()


# ── Scroll ────────────────────────────────────────────────────────────────────
def scroll_vertical(step: int) -> None:
    """
    step > 0 → scroll down, step < 0 → scroll up.
    Uses Windows mouse_event for smooth scrolling.
    """
    if is_windows():
        MOUSEEVENTF_WHEEL = 0x0800
        # 120 = one standard notch. Negative = scroll down.
        delta = -120 * step
        ctypes.windll.user32.mouse_event(MOUSEEVENTF_WHEEL, 0, 0, delta, 0)
    else:
        direction = "5" if step > 0 else "4"
        subprocess.run(["xdotool", "click", direction],
                       capture_output=True, timeout=2)


# ── Tab switching ─────────────────────────────────────────────────────────────
def tab_next() -> None:
    """Ctrl+Tab — next tab in browser/editor."""
    if is_windows():
        _combo(VK_CTRL, VK_TAB)
    else:
        subprocess.run(["xdotool", "key", "ctrl+Tab"], capture_output=True, timeout=2)


def tab_prev() -> None:
    """Ctrl+Shift+Tab — previous tab."""
    if is_windows():
        _combo(VK_CTRL, VK_SHIFT, VK_TAB)
    else:
        subprocess.run(["xdotool", "key", "ctrl+shift+Tab"],
                       capture_output=True, timeout=2)


def tab_step(step: int) -> None:
    fn = tab_next if step >= 0 else tab_prev
    for _ in range(abs(step)):
        fn()


# ── Playback speed ────────────────────────────────────────────────────────────
# YouTube / most web players  →  Shift+.  (>)  to speed up,  Shift+,  (<) to slow
# VLC                         →  ]  to speed up,  [  to slow down
# Fallback                    →  YouTube bindings

def _get_foreground_process_name() -> str:
    """Return lowercase exe name of the foreground window, or empty string."""
    try:
        import psutil
        hwnd = ctypes.windll.user32.GetForegroundWindow()
        pid = ctypes.wintypes.DWORD()
        ctypes.windll.user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        proc = psutil.Process(pid.value)
        return proc.name().lower()
    except Exception:
        return ""


def playback_speed_up() -> None:
    name = _get_foreground_process_name()
    if is_windows():
        if "vlc" in name:
            _press(VK_OEM_6)               # ]
        else:
            _combo(VK_SHIFT, VK_PERIOD)    # Shift+. → >
    else:
        if "vlc" in name:
            subprocess.run(["xdotool", "key", "bracketright"],
                           capture_output=True, timeout=2)
        else:
            subprocess.run(["xdotool", "key", "shift+period"],
                           capture_output=True, timeout=2)


def playback_speed_down() -> None:
    name = _get_foreground_process_name()
    if is_windows():
        if "vlc" in name:
            _press(VK_OEM_4)               # [
        else:
            _combo(VK_SHIFT, VK_COMMA)     # Shift+, → <
    else:
        if "vlc" in name:
            subprocess.run(["xdotool", "key", "bracketleft"],
                           capture_output=True, timeout=2)
        else:
            subprocess.run(["xdotool", "key", "shift+comma"],
                           capture_output=True, timeout=2)


def playback_speed_step(step: int) -> None:
    fn = playback_speed_up if step >= 0 else playback_speed_down
    for _ in range(abs(step)):
        fn()


# ── Zoom ──────────────────────────────────────────────────────────────────────
def zoom_in() -> None:
    if is_windows():
        _combo(VK_CTRL, VK_OEM_PLUS)
    else:
        subprocess.run(["xdotool", "key", "ctrl+equal"], capture_output=True, timeout=2)


def zoom_out() -> None:
    if is_windows():
        _combo(VK_CTRL, VK_OEM_MINUS)
    else:
        subprocess.run(["xdotool", "key", "ctrl+minus"], capture_output=True, timeout=2)


def zoom_step(step: int) -> None:
    fn = zoom_in if step >= 0 else zoom_out
    for _ in range(abs(step)):
        fn()


# ── Legacy stub (kept so nothing breaks) ──────────────────────────────────────
def volume_step_placeholder(step: int) -> None:
    volume_step(step)
