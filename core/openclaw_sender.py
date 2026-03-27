from __future__ import annotations

import json
import subprocess
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

    def send_to_boris(self, text: str, action: dict) -> bool:
        message = str(text).strip()
        if not message:
            self._log("[openclaw] skipped empty message")
            return False

        channel = str(action.get("channel", "telegram")).strip() or "telegram"
        target = str(action.get("target", "1636853070")).strip()
        agent_id = str(action.get("agent_id", "main")).strip() or "main"
        thinking = str(action.get("thinking", "off")).strip() or "off"

        command = [
            "openclaw",
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
