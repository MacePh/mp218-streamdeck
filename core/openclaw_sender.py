from __future__ import annotations

import json
import shutil
import subprocess
import time
from pathlib import Path
from typing import Callable

from core import platform_utils

try:
    import psutil
except Exception:
    psutil = None  # type: ignore


class OpenClawSender:
    _GATEWAY_PROCESS_HINTS = (
        "openclaw gateway",
        "openclaw.cmd gateway",
        "openclaw.exe gateway",
        "gateway start",
    )

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

    def _is_gateway_process_running(self) -> bool:
        if psutil is None:
            return False

        for process in psutil.process_iter(attrs=["name", "cmdline"]):
            try:
                name = (process.info.get("name") or "").lower()
                cmdline = " ".join(process.info.get("cmdline") or []).lower()
                haystack = f"{name} {cmdline}"
                if any(hint in haystack for hint in self._GATEWAY_PROCESS_HINTS):
                    return True
            except Exception:
                continue
        return False

    def _is_gateway_running_fast(self, openclaw_exe: str) -> bool:
        if self._is_gateway_process_running():
            return True

        try:
            status = subprocess.run(
                [openclaw_exe, "gateway", "status"],
                capture_output=True,
                text=True,
                timeout=3,
                check=False,
            )
            return status.returncode == 0 and "Runtime: running" in (status.stdout or "")
        except subprocess.TimeoutExpired:
            self._log("[openclaw] gateway status probe timed out; treating as unavailable")
            return False
        except Exception:
            return False

    def _ensure_gateway_running(self, openclaw_exe: str) -> None:
        if self._is_gateway_running_fast(openclaw_exe):
            self._log("[openclaw] gateway already running")
            return

        self._log("[openclaw] gateway not running; starting it now")
        self.notify("Boris", "Gateway is asleep. Waking it up…")
        start = subprocess.run(
            [openclaw_exe, "gateway", "start"],
            capture_output=True,
            text=True,
            timeout=20,
            check=False,
        )
        if start.returncode != 0:
            raise RuntimeError(start.stderr.strip() or start.stdout.strip() or "gateway start failed")

        for _ in range(12):
            time.sleep(0.5)
            if self._is_gateway_running_fast(openclaw_exe):
                self._log("[openclaw] gateway wake-up confirmed")
                return

        raise RuntimeError("Gateway start requested but runtime never reported running")

    def ensure_gateway_running(self) -> None:
        """Start the gateway only when status/probes say it is down (no restart when healthy)."""
        openclaw_exe = self._resolve_openclaw_executable()
        self._ensure_gateway_running(openclaw_exe)

    def open_control_dashboard(self) -> None:
        """Open the OpenClaw Control UI via the official CLI (tokenized URL / browser handoff)."""
        openclaw_exe = self._resolve_openclaw_executable()
        self._log("[openclaw] opening Control UI (openclaw dashboard)")
        subprocess.Popen(
            [openclaw_exe, "dashboard"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )

    def send_to_boris(self, text: str, action: dict) -> bool:
        message = str(text).strip()
        if not message:
            self._log("[openclaw] skipped empty message")
            return False

        channel = str(action.get("channel", "local")).strip() or "local"
        target = str(action.get("target", "")).strip()
        agent_id = str(action.get("agent_id", "main")).strip() or "main"
        thinking = str(action.get("thinking", "off")).strip() or "off"
        openclaw_exe = self._resolve_openclaw_executable()

        local_mode = channel.lower() in {"local", "webchat", "internal", "desktop"}
        command = [
            openclaw_exe,
            "agent",
            "--agent",
            agent_id,
            "--message",
            message,
            "--thinking",
            thinking,
            "--json",
        ]
        if not local_mode:
            if not target:
                raise RuntimeError(f"OpenClaw target is required for non-local channel '{channel}'")
            command.extend([
                "--channel",
                channel,
                "--to",
                target,
                "--deliver",
            ])

        self._log("[boris] heard you — handing transcript to OpenClaw")
        self.notify("Boris", "Heard you. Sending now…")

        try:
            send_started = time.monotonic()
            gateway_ready_elapsed = 0.0
            if local_mode:
                self._log("[openclaw] local delivery selected; skipping gateway preflight")
            else:
                self._ensure_gateway_running(openclaw_exe)
                gateway_ready_elapsed = time.monotonic() - send_started
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
            total_elapsed = time.monotonic() - send_started
            cli_elapsed = total_elapsed - gateway_ready_elapsed
            destination = "local session" if local_mode else f"{channel}:{target}"
            self._log(
                f"[openclaw] delivered agent message to {destination} gateway={gateway_ready_elapsed:.2f}s cli={cli_elapsed:.2f}s total={total_elapsed:.2f}s"
            )
            self._log("[boris] delivery accepted by OpenClaw")
            self.notify("Boris", "Got it. Processing…")
            return True
        except Exception as exc:
            self.notify("Boris", f"Send failed: {exc}")
            raise RuntimeError(f"OpenClaw send failed: {exc}") from exc
