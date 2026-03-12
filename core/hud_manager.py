import ctypes
import ctypes.wintypes
import queue
import subprocess
import sys
import threading
import time
import tkinter as tk
from tkinter import font as tkfont
from typing import Callable
from urllib.parse import urlparse


def get_pad_grid(bank: str) -> list[list[int]]:
    base = {"A": 36, "B": 52, "C": 68}[bank]
    grid: list[list[int]] = []
    for row in range(3, -1, -1):
        grid.append([base + row * 4 + col for col in range(4)])
    return grid


class HUDManager:
    WM_HOTKEY = 0x0312
    MOD_ALT = 0x0001
    MOD_CONTROL = 0x0002
    MOD_SHIFT = 0x0004
    MOD_WIN = 0x0008
    HOTKEY_ID = 1

    def __init__(self, logger: Callable[[str], None], on_pad_trigger: Callable[[int], None]):
        self._log = logger
        self._on_pad_trigger = on_pad_trigger
        self._queue: queue.Queue[tuple[str, dict]] = queue.Queue()
        self._thread: threading.Thread | None = None
        self._ui_ready = threading.Event()
        self._visible = False

        self._hud_config = {"width": 600, "height": 450, "opacity": 0.92}
        self._controller_config: dict = {}
        self._last_model: dict = {}
        self._search_index: list[tuple[str, int]] = []
        self._auto_hide_at: float | None = None
        self._visible_grid_notes: list[int] = []
        self._last_seen_pad: int | None = None
        self._highlight_note: int | None = None
        self._highlight_until: float = 0.0

        self._pad_bg_normal = "#1B1E22"
        self._pad_bg_highlight = "#3C5A86"

        self._hotkey_registered = False
        self._hotkey_mod = 0
        self._hotkey_vk = 0
        self._is_windows = sys.platform == "win32"

    def configure(self, hud_config: dict, controller_config: dict) -> None:
        self._hud_config = {
            "width": int(hud_config.get("width", 600)),
            "height": int(hud_config.get("height", 450)),
            "opacity": float(hud_config.get("opacity", 0.92)),
            "enabled": bool(hud_config.get("enabled", True)),
        }
        self._controller_config = controller_config
        if self._hud_config.get("enabled", True):
            self._register_hotkey(controller_config.get("hud_toggle_key", "ctrl+shift+h"))
        else:
            self._unregister_hotkey()
            self._queue.put(("hide", {}))
        self._queue.put(("configure", {}))

    def start(self) -> None:
        if self._thread is not None:
            return
        self._thread = threading.Thread(target=self._run_ui, name="HUDThread", daemon=True)
        self._thread.start()
        self._ui_ready.wait(timeout=2.0)

    def update(self, model: dict) -> None:
        self._last_model = model
        self._queue.put(("update", model))

    def toggle(self, model: dict, duration_seconds: float) -> None:
        self._last_model = model
        self._queue.put(("toggle", {"model": model, "duration_seconds": duration_seconds}))

    def poll_hotkey(self) -> bool:
        if not self._is_windows or not self._hotkey_registered:
            return False
        msg = ctypes.wintypes.MSG()
        triggered = False
        while ctypes.windll.user32.PeekMessageW(
            ctypes.byref(msg), None, self.WM_HOTKEY, self.WM_HOTKEY, 0x0001
        ):
            if msg.message == self.WM_HOTKEY and msg.wParam == self.HOTKEY_ID:
                triggered = True
        return triggered

    def _parse_hotkey(self, combo: str) -> tuple[int, int]:
        key_map = {
            "h": 0x48,
            "f1": 0x70,
            "f2": 0x71,
            "f3": 0x72,
            "f4": 0x73,
            "f5": 0x74,
            "f6": 0x75,
            "f7": 0x76,
            "f8": 0x77,
            "f9": 0x78,
            "f10": 0x79,
            "f11": 0x7A,
            "f12": 0x7B,
        }
        mod = 0
        parts = [part.strip().lower() for part in str(combo).split("+") if part.strip()]
        key = "h"
        for part in parts:
            if part == "ctrl":
                mod |= self.MOD_CONTROL
            elif part == "shift":
                mod |= self.MOD_SHIFT
            elif part == "alt":
                mod |= self.MOD_ALT
            elif part == "win":
                mod |= self.MOD_WIN
            else:
                key = part
        return mod, key_map.get(key, 0x48)

    def _register_hotkey(self, hotkey: str) -> None:
        if not self._is_windows:
            self._hotkey_registered = False
            return
        self._unregister_hotkey()
        self._hotkey_mod, self._hotkey_vk = self._parse_hotkey(hotkey)
        ok = ctypes.windll.user32.RegisterHotKey(
            None, self.HOTKEY_ID, self._hotkey_mod, self._hotkey_vk
        )
        self._hotkey_registered = bool(ok)
        if self._hotkey_registered:
            self._log(f"[hud] hotkey registered: {hotkey}")
        else:
            self._log(f"[hud] hotkey registration failed: {hotkey}")

    def _unregister_hotkey(self) -> None:
        if not self._is_windows:
            self._hotkey_registered = False
            return
        if self._hotkey_registered:
            ctypes.windll.user32.UnregisterHotKey(None, self.HOTKEY_ID)
            self._hotkey_registered = False

    def _run_ui(self) -> None:
        self.root = tk.Tk()
        self.root.withdraw()
        self.root.overrideredirect(True)
        self.root.attributes("-topmost", True)
        self.root.configure(bg="#111214")
        self.root.protocol("WM_DELETE_WINDOW", self._hide)

        mono = tkfont.Font(family="Consolas", size=11)
        title_font = tkfont.Font(family="Consolas", size=13, weight="bold")

        frame = tk.Frame(self.root, bg="#111214", padx=12, pady=10)
        frame.pack(fill="both", expand=True)

        self.profile_var = tk.StringVar(value="PROFILE: DEV")
        self.bank_var = tk.StringVar(value="BANK: A")
        self.app_var = tk.StringVar(value="ACTIVE APP: unknown")
        self.last_pad_var = tk.StringVar(value="LAST PAD: -")
        self.flags_var = tk.StringVar(value="FLAGS: obs=0 mic=0 docker=0")

        tk.Label(frame, textvariable=self.profile_var, fg="#F6F6F6", bg="#111214", font=title_font).pack(anchor="w")
        tk.Label(frame, textvariable=self.bank_var, fg="#D8D8D8", bg="#111214", font=mono).pack(anchor="w")
        tk.Label(frame, textvariable=self.app_var, fg="#AFAFAF", bg="#111214", font=mono).pack(anchor="w")
        tk.Label(frame, textvariable=self.last_pad_var, fg="#AFAFAF", bg="#111214", font=mono).pack(anchor="w", pady=(0, 6))
        tk.Label(frame, textvariable=self.flags_var, fg="#8FD68F", bg="#111214", font=mono).pack(anchor="w", pady=(0, 8))

        bank_row = tk.Frame(frame, bg="#111214")
        bank_row.pack(fill="x", pady=(0, 8))
        self.bank_buttons: dict[str, tk.Button] = {}
        for bank in ["A", "B", "C"]:
            button = tk.Button(
                bank_row,
                text=f"Bank {bank}",
                width=10,
                bg="#1F2228",
                fg="#D6D6D6",
                activebackground="#2C313A",
                activeforeground="#FFFFFF",
                relief="flat",
                command=lambda b=bank: self._set_bank_from_button(b),
            )
            button.pack(side="left", padx=(0, 6))
            self.bank_buttons[bank] = button

        grid_frame = tk.Frame(frame, bg="#111214")
        grid_frame.pack(fill="both", expand=True)
        for row in range(4):
            grid_frame.grid_rowconfigure(row, weight=1, uniform="padrow", minsize=68)
        for col in range(4):
            grid_frame.grid_columnconfigure(col, weight=1, uniform="padcol")
        self.pad_buttons: list[tk.Button] = []
        for index in range(16):
            button = tk.Button(
                grid_frame,
                text="--",
                bg="#1B1E22",
                fg="#DFDFDF",
                activebackground="#2B313A",
                activeforeground="#FFFFFF",
                relief="flat",
                justify="left",
                anchor="w",
                wraplength=125,
                command=lambda i=index: self._trigger_grid_pad(i),
            )
            row = index // 4
            col = index % 4
            button.grid(row=row, column=col, sticky="nsew", padx=4, pady=4)
            self.pad_buttons.append(button)

        palette_frame = tk.Frame(frame, bg="#111214")
        palette_frame.pack(fill="x", pady=(8, 0))

        self.search_var = tk.StringVar(value="")
        self.search_var.trace_add("write", lambda *_: self._refresh_search_results())

        tk.Label(palette_frame, text="Command Palette", fg="#C8C8C8", bg="#111214", font=mono).pack(anchor="w")
        search_entry = tk.Entry(
            palette_frame,
            textvariable=self.search_var,
            bg="#17191D",
            fg="#EFEFEF",
            insertbackground="#EFEFEF",
            relief="flat",
            font=mono,
        )
        search_entry.pack(fill="x", pady=(3, 4))
        self.result_list = tk.Listbox(
            palette_frame,
            height=4,
            bg="#17191D",
            fg="#DFDFDF",
            selectbackground="#2A3240",
            relief="flat",
            font=mono,
        )
        self.result_list.pack(fill="x")
        self.result_list.bind("<Double-Button-1>", self._trigger_palette_selection)
        self.result_list.bind("<Return>", self._trigger_palette_selection)

        self._ui_ready.set()
        self.root.after(30, self._tick)
        self.root.mainloop()

    def _action_label(self, action: dict) -> str:
        action_type = action.get("type", "noop")
        value = str(action.get("value", ""))
        if action_type == "focus_or_launch":
            process = str(action.get("process", "")).strip()
            return process.title() if process else "Focus/Launch"
        if action_type == "cmd":
            first = value.strip().split(" ")[0] if value.strip() else "Command"
            return first.replace("start", "").strip().title() or "Command"
        if action_type == "url":
            try:
                hostname = urlparse(value).hostname or value
                base = hostname.replace("www.", "").split(".")[0]
                return base.title()
            except Exception:
                return "URL"
        if action_type == "profile":
            return f"Profile {value.upper()}"
        if action_type == "log":
            return "Log"
        if action_type == "hud":
            return "HUD"
        if action_type == "noop":
            return "--"
        return action_type.title()

    def _bank_start(self, bank: str) -> int:
        if bank == "A":
            return 36
        if bank == "B":
            return 52
        return 68

    def _set_bank_from_button(self, bank: str) -> None:
        model = dict(self._last_model)
        model["bank"] = bank
        self._apply_model(model)

    def _trigger_grid_pad(self, index: int) -> None:
        if index < 0 or index >= len(self._visible_grid_notes):
            return
        note = self._visible_grid_notes[index]
        self._on_pad_trigger(note)

    def _trigger_palette_selection(self, _event: object) -> None:
        selection = self.result_list.curselection()
        if not selection:
            return
        text = self.result_list.get(selection[0])
        marker = text.split("]")[0].replace("[", "")
        note = int(marker.split(":")[1])
        self._on_pad_trigger(note)

    def _rebuild_search_index(self, profiles: dict) -> None:
        self._search_index = []
        for profile_name, profile_data in profiles.items():
            for note, action in profile_data.get("pads", {}).items():
                label = self._action_label(action)
                self._search_index.append(
                    (f"[{profile_name}:{note}] {label} ({action.get('type', 'noop')})", int(note))
                )

    def _refresh_search_results(self) -> None:
        text = self.search_var.get().strip().lower()
        self.result_list.delete(0, "end")
        for label, note in self._search_index:
            if text and text not in label.lower():
                continue
            self.result_list.insert("end", f"[note:{note}] {label}")

    def _fade_in(self) -> None:
        target = float(self._hud_config.get("opacity", 0.92))
        self.root.attributes("-alpha", 0.0)
        self.root.deiconify()
        self._visible = True

        def step(alpha: float) -> None:
            if not self._visible:
                return
            self.root.attributes("-alpha", min(alpha, target))
            if alpha < target:
                self.root.after(18, lambda: step(alpha + 0.08))

        step(0.08)

    def _hide(self) -> None:
        self._visible = False
        self._auto_hide_at = None
        self.root.withdraw()

    def _center_window(self) -> None:
        width = int(self._hud_config.get("width", 600))
        height = int(self._hud_config.get("height", 450))
        self.root.update_idletasks()
        requested_width = int(self.root.winfo_reqwidth())
        requested_height = int(self.root.winfo_reqheight())
        width = max(width, requested_width + 8)
        height = max(height, requested_height + 8)
        screen_w = self.root.winfo_screenwidth()
        screen_h = self.root.winfo_screenheight()
        width = min(width, max(220, screen_w - 32))
        height = min(height, max(220, screen_h - 32))

        x = int((screen_w - width) / 2)
        y = int((screen_h - height) / 2)

        pointer_pos = self._pointer_position()
        if pointer_pos is not None:
            px, py = pointer_pos
            x = int(px - (width / 2))
            y = int(py - (height / 2))

        x = max(0, min(x, max(0, screen_w - width)))
        y = max(0, min(y, max(0, screen_h - height)))
        self.root.geometry(f"{width}x{height}+{x}+{y}")

    def _pointer_position(self) -> tuple[int, int] | None:
        if self._is_windows:
            try:
                point = ctypes.wintypes.POINT()
                ok = ctypes.windll.user32.GetCursorPos(ctypes.byref(point))
                if not ok:
                    return None
                return int(point.x), int(point.y)
            except Exception:
                return None

        try:
            result = subprocess.run(
                ["xdotool", "getmouselocation", "--shell"],
                capture_output=True,
                text=True,
                timeout=1,
            )
            if result.returncode != 0:
                return None
            values: dict[str, int] = {}
            for line in result.stdout.splitlines():
                if "=" not in line:
                    continue
                key, value = line.split("=", 1)
                if key in {"X", "Y"}:
                    values[key] = int(value.strip())
            if "X" in values and "Y" in values:
                return values["X"], values["Y"]
            return None
        except Exception:
            return None

    def _highlight_profile(self, profile: str) -> None:
        upper = profile.upper()
        color = "#FFD166" if upper == "AI" else "#7FDBCA" if upper == "DEV" else "#A7F070"
        self.profile_var.set(f"PROFILE: {upper}")
        self.root.after(0, lambda: None)
        self.root.configure(bg="#111214")
        # Brief profile highlight pulse on top label.
        # Keep this lightweight to avoid flicker with frequent updates.
        for _ in range(2):
            pass
        self.profile_label_color = color

    def _apply_model(self, model: dict) -> None:
        self._last_model = model
        profile = str(model.get("profile", "dev"))
        bank = str(model.get("bank", "A"))
        app = str(model.get("active_app", "unknown"))
        state = model.get("state", {})
        actions = model.get("actions", {})

        self.profile_var.set(f"PROFILE: {profile.upper()}")
        self.bank_var.set(f"BANK: {bank}")
        self.app_var.set(f"ACTIVE APP: {app}")
        self.last_pad_var.set(f"LAST PAD: {state.get('last_pressed_pad', '-')}")
        last_pad = state.get("last_pressed_pad")
        if isinstance(last_pad, int) and last_pad != self._last_seen_pad:
            self._last_seen_pad = last_pad
            self._highlight_note = last_pad
            self._highlight_until = time.monotonic() + 0.3
        flags = state.get("flags", {})
        self.flags_var.set(
            f"FLAGS: obs={int(bool(flags.get('obs_recording', False)))} "
            f"mic={int(bool(flags.get('mic_muted', False)))} "
            f"docker={int(bool(flags.get('docker_running', False)))}"
        )

        for key, button in self.bank_buttons.items():
            button.configure(bg="#2B313A" if key == bank else "#1F2228")

        physical_grid = get_pad_grid(bank)
        self._visible_grid_notes = [note for row in physical_grid for note in row]
        for offset, button in enumerate(self.pad_buttons):
            note = self._visible_grid_notes[offset]
            action = actions.get(str(note), {"type": "noop"})
            label = self._action_label(action)
            button.configure(text=f"{note} {label}")

        self._refresh_pad_highlight()

        profiles = model.get("profiles", {})
        if profiles:
            self._rebuild_search_index(profiles)
            self._refresh_search_results()

    def _refresh_pad_highlight(self) -> None:
        now = time.monotonic()
        active_highlight = (
            self._highlight_note if self._highlight_note is not None and now < self._highlight_until else None
        )
        if active_highlight is None:
            self._highlight_note = None

        for index, button in enumerate(self.pad_buttons):
            if index >= len(self._visible_grid_notes):
                button.configure(bg=self._pad_bg_normal)
                continue
            note = self._visible_grid_notes[index]
            if active_highlight == note:
                button.configure(bg=self._pad_bg_highlight)
            else:
                button.configure(bg=self._pad_bg_normal)

    def _tick(self) -> None:
        try:
            while True:
                command, payload = self._queue.get_nowait()
                if command == "configure":
                    self._center_window()
                    self.root.attributes("-alpha", float(self._hud_config.get("opacity", 0.92)))
                elif command == "hide":
                    self._hide()
                elif command == "update":
                    self._apply_model(payload)
                elif command == "toggle":
                    model = payload.get("model", {})
                    duration_seconds = float(payload.get("duration_seconds", 6))
                    self._apply_model(model)
                    if self._visible:
                        self._hide()
                    else:
                        self._center_window()
                        self._fade_in()
                        if duration_seconds > 0:
                            self._auto_hide_at = time.monotonic() + duration_seconds
                self._queue.task_done()
        except queue.Empty:
            pass

        if self._visible and self._auto_hide_at is not None and time.monotonic() >= self._auto_hide_at:
            self._hide()

        self._refresh_pad_highlight()
        self.root.after(30, self._tick)
