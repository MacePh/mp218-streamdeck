import os
import subprocess
import webbrowser
import ctypes
import ctypes.wintypes

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

KEYEVENTF_KEYUP  = 0x0002
INPUT_KEYBOARD   = 1


# ── ctypes input structs ───────────────────────────────────────────────────────
class KEYBDINPUT(ctypes.Structure):
    _fields_ = [
        ("wVk",         ctypes.wintypes.WORD),
        ("wScan",       ctypes.wintypes.WORD),
        ("dwFlags",     ctypes.wintypes.DWORD),
        ("time",        ctypes.wintypes.DWORD),
        ("dwExtraInfo", ctypes.POINTER(ctypes.c_ulong)),
    ]


class _INPUT_UNION(ctypes.Union):
    _fields_ = [("ki", KEYBDINPUT)]


class INPUT(ctypes.Structure):
    _fields_ = [("type", ctypes.wintypes.DWORD), ("_input", _INPUT_UNION)]


def _send_key(vk: int, flags: int = 0) -> None:
    inp = INPUT(
        type=INPUT_KEYBOARD,
        _input=_INPUT_UNION(ki=KEYBDINPUT(wVk=vk, dwFlags=flags)),
    )
    ctypes.windll.user32.SendInput(1, ctypes.byref(inp), ctypes.sizeof(inp))


def _press(vk: int) -> None:
    _send_key(vk, 0)
    _send_key(vk, KEYEVENTF_KEYUP)


def _combo(*vks: int) -> None:
    """Press all keys down in order, then release in reverse."""
    for vk in vks:
        _send_key(vk, 0)
    for vk in reversed(vks):
        _send_key(vk, KEYEVENTF_KEYUP)


# ── Platform helpers ───────────────────────────────────────────────────────────
def is_windows() -> bool:
    return os.name == "nt"


def is_linux() -> bool:
    return os.name == "posix"


def run_command(command: str) -> subprocess.Popen:
    if is_windows():
        return subprocess.Popen(command, shell=True)
    return subprocess.Popen(command, shell=True)


def open_url(url: str) -> bool:
    return webbrowser.open(url)


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
