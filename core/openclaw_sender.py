from __future__ import annotations

import json
import shutil
import subprocess
import time
from pathlib import Path
from typing import Callable

from core import platform_utils


class OpenClawSender:
    def __init__(self, logger: Callable[[str], None]):
        self._log = logger

    def notify(self, title: str, message: str) -> None:
        short = " ".join(str(message).split())[:120]
        safe_title = title.replace("'", "''")
        safe_short = short.replace("'", "''")
        if platform_utils.use_windows_paths():
            script = (
                "Add-Type -AssemblyName PresentationFramework;"
                f"[System.Windows.MessageBox]::Show('{safe_short}', '{safe_title}') | Out-Null"
            )
            subprocess.Popen(
                ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", script],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            return
        subprocess.Popen(
            ["notify-send", title, short],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )

    def _resolve_openclaw_executable(self) -> str:
        for candidate in ["openclaw", "openclaw.cmd"]:
            resolved = shutil.which(candidate)
            if resolved:
                return resolved

        if platform_utils.use_windows_paths():
            roaming = Path.home() / "AppData" / "Roaming" / "npm"
            for name in ["openclaw.cmd", "openclaw"]:
                candidate = roaming / name
                if candidate.exists():
                    return str(candidate)

        raise RuntimeError("OpenClaw CLI not found in PATH or expected npm-global location")

    def _ensure_gateway_running(self, openclaw_exe: str) -> None:
        status = subprocess.run(
            [openclaw_exe, "gateway", "status"],
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )
        if status.returncode == 0 and "Runtime: running" in (status.stdout or ""):
            self._log("[openclaw] gateway already running")
            return

        self._log("[openclaw] gateway not running; starting it now")
        self.notify("Boris", "Gateway is asleep. Waking it up…")
        start = subprocess.run(
            [openclaw_exe, "gateway", "start"],
            capture_output=True,
            text=True,
            timeout=60,
            check=False,
        )
        if start.returncode != 0:
            raise RuntimeError(start.stderr.strip() or start.stdout.strip() or "gateway start failed")

        for _ in range(10):
            time.sleep(1.0)
            probe = subprocess.run(
                [openclaw_exe, "gateway", "status"],
                capture_output=True,
                text=True,
                timeout=30,
                check=False,
            )
            if probe.returncode == 0 and "Runtime: running" in (probe.stdout or ""):
                self._log("[openclaw] gateway wake-up confirmed")
                return

        raise RuntimeError("Gateway start requested but runtime never reported running")

    def send_to_boris(self, text: str, action: dict) -> bool:
        message = str(text).strip()
        if not message:
            self._log("[openclaw] skipped empty message")
            return False

        channel = str(action.get("channel", "telegram")).strip() or "telegram"
        target = str(action.get("target", "1636853070")).strip()
        agent_id = str(action.get("agent_id", "main")).strip() or "main"
        thinking = str(action.get("thinking", "off")).strip() or "off"
        openclaw_exe = self._resolve_openclaw_executable()

        command = [
            openclaw_exe,
            "agent",
            "--agent",
            agent_id,
            "--channel",
            channel,
            "--to",
            target,
            "--message",
            message,
            "--deliver",
            "--thinking",
            thinking,
            "--json",
        ]

        self._log("[boris] heard you — handing transcript to OpenClaw")
        self.notify("Boris", "Heard you. Sending now…")

        try:
            self._ensure_gateway_running(openclaw_exe)
            result = subprocess.run(
                command,
                capture_output=True,
                text=True,
                timeout=120,
                check=False,
            )
            if result.returncode != 0:
                raise RuntimeError(result.stderr.strip() or result.stdout.strip() or f"exit {result.returncode}")
            raw = (result.stdout or "").strip()
            if raw:
                try:
                    json.loads(raw)
                except Exception:
                    pass
            self._log(f"[openclaw] delivered agent message to {channel}:{target}")
            self._log("[boris] delivery accepted by OpenClaw")
            self.notify("Boris", "Got it. Processing…")
            return True
        except Exception as exc:
            self.notify("Boris", f"Send failed: {exc}")
            raise RuntimeError(f"OpenClaw send failed: {exc}") from exc
