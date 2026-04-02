from __future__ import annotations

import socket
import subprocess
from pathlib import Path
from typing import Callable
from urllib.parse import urlparse

from core import platform_utils

try:
    import psutil
except Exception:
    psutil = None  # type: ignore


def tcp_port_open(host: str, port: int, timeout_s: float = 1.0) -> bool:
    try:
        with socket.create_connection((host, port), timeout=timeout_s):
            return True
    except OSError:
        return False


def service_url_reachable(url: str, timeout_s: float = 1.0) -> bool:
    parsed = urlparse(str(url).strip())
    if not parsed.hostname or parsed.port is None:
        return False
    if parsed.scheme not in ("http", "https", ""):
        return False
    port = parsed.port
    host = parsed.hostname
    return tcp_port_open(host, port, timeout_s=timeout_s)


def _clawcommand_root_dir(action: dict) -> str | None:
    if platform_utils.use_windows_paths() and str(action.get("clawcommand_dir_windows", "")).strip():
        return str(action["clawcommand_dir_windows"]).strip()
    if str(action.get("clawcommand_dir_linux", "")).strip():
        return str(action["clawcommand_dir_linux"]).strip()
    if str(action.get("clawcommand_dir", "")).strip():
        return str(action["clawcommand_dir"]).strip()
    return None


def _clawcommand_start_argv(action: dict) -> list[str] | None:
    if platform_utils.use_windows_paths() and str(action.get("clawcommand_start_cmd_windows", "")).strip():
        return ["cmd", "/c", str(action["clawcommand_start_cmd_windows"]).strip()]
    if not platform_utils.use_windows_paths() and str(
        action.get("clawcommand_start_cmd_linux", "")
    ).strip():
        return ["bash", "-lc", str(action["clawcommand_start_cmd_linux"]).strip()]
    if str(action.get("clawcommand_start_cmd", "")).strip():
        raw = str(action["clawcommand_start_cmd"]).strip()
        if platform_utils.use_windows_paths():
            return ["cmd", "/c", raw]
        return ["bash", "-lc", raw]
    return None


def ensure_clawcommand_running(
    action: dict[str, object],
    logger: Callable[[str], None],
) -> None:
    url = str(action.get("clawcommand_url", "http://127.0.0.1:4310")).strip()
    if not url:
        logger("[openclaw/env] clawcommand_url empty; skip ClawCommand")
        return
    if service_url_reachable(url):
        logger("[openclaw/env] ClawCommand already reachable")
        return

    root = _clawcommand_root_dir(action)
    if not root:
        logger("[openclaw/env] ClawCommand down; no clawcommand_dir* set — not starting server")
        return

    root_path = Path(root)
    if not root_path.is_dir():
        logger(f"[openclaw/env] ClawCommand dir missing: {root}")
        return

    custom = _clawcommand_start_argv(action)
    cwd = str(root_path)
    if custom:
        logger("[openclaw/env] ClawCommand not reachable; starting server")
        subprocess.Popen(
            custom,
            cwd=cwd,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            shell=False,
        )
        return

    if (root_path / "package.json").is_file():
        logger("[openclaw/env] ClawCommand not reachable; starting server")
        if platform_utils.use_windows_paths():
            subprocess.Popen(
                ["cmd", "/c", "npm", "start"],
                cwd=cwd,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                shell=False,
            )
        else:
            subprocess.Popen(
                "npm start",
                cwd=cwd,
                shell=True,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
        return

    logger(f"[openclaw/env] ClawCommand: no package.json in {root}, cannot start")


def is_openclaw_tui_running() -> bool:
    if psutil is None:
        return False
    for process in psutil.process_iter(attrs=["name", "cmdline"]):
        try:
            name = (process.info.get("name") or "").lower()
            parts = [str(p).lower() for p in (process.info.get("cmdline") or ())]
            cmdline = " ".join(parts)
            if "openclaw" not in name and "openclaw" not in cmdline:
                continue
            if "gateway" in cmdline:
                continue
            if any(p == "tui" for p in parts) or " tui" in cmdline:
                return True
        except Exception:
            continue
    return False


def start_openclaw_tui(logger: Callable[[str], None]) -> None:
    if platform_utils.use_windows_paths():
        cmd = (
            'cmd /c start "" powershell -NoExit -ExecutionPolicy Bypass '
            '-Command "openclaw tui"'
        )
        subprocess.Popen(cmd, shell=True)
        return

    for argv in (
        ["gnome-terminal", "--", "bash", "-lc", "openclaw tui; exec bash"],
        ["x-terminal-emulator", "-e", "bash", "-lc", "openclaw tui; exec bash"],
        ["xterm", "-e", "bash", "-lc", "openclaw tui"],
    ):
        try:
            subprocess.Popen(argv, start_new_session=True)
            return
        except FileNotFoundError:
            continue
    logger("[openclaw/env] could not find a terminal to start openclaw tui")
