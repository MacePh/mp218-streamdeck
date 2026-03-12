from typing import Callable

import mido
import time


class MidiManager:
    def __init__(
        self,
        input_port_name: str,
        output_port_name: str,
        auto_detect: bool,
        match_substring: str,
        logger: Callable[[str], None],
    ):
        self._log = logger
        self.input_port_name = input_port_name
        self.output_port_name = output_port_name
        self.auto_detect = auto_detect
        self.match_substring = match_substring
        self.input_port = None
        self.output_port = None
        self._last_reconnect_attempt = 0.0
        self._reconnect_backoff_seconds = 1.0
        self._reconnect_token = 0

    @staticmethod
    def list_input_ports() -> list[str]:
        return list(mido.get_input_names())

    @staticmethod
    def list_output_ports() -> list[str]:
        return list(mido.get_output_names())

    def _resolve_port_name(
        self,
        requested: str,
        available: list[str],
        preferred_suffix: str,
        direction: str,
    ) -> str:
        if requested in available:
            return requested

        if not self.auto_detect:
            return requested

        candidates = [
            port for port in available if self.match_substring.lower() in port.lower()
        ]
        if not candidates:
            self._log(
                f"[midi] auto-detect enabled but no {direction} port matched '{self.match_substring}'"
            )
            return requested

        for port in candidates:
            if preferred_suffix in port:
                self._log(
                    f"[midi] auto-detected {direction} port '{port}' (requested '{requested}')"
                )
                return port

        detected = candidates[0]
        self._log(
            f"[midi] auto-detected {direction} port '{detected}' (requested '{requested}')"
        )
        return detected

    def open(self) -> None:
        available_inputs = self.list_input_ports()
        available_outputs = self.list_output_ports()
        resolved_input = self._resolve_port_name(
            self.input_port_name, available_inputs, " 0", "input"
        )
        resolved_output = self._resolve_port_name(
            self.output_port_name, available_outputs, " 1", "output"
        )

        try:
            self.input_port = mido.open_input(resolved_input)
        except Exception as exc:
            ports = ", ".join(available_inputs)
            raise RuntimeError(
                f"Could not open MIDI input '{resolved_input}'. "
                f"Available inputs: [{ports}] ({exc})"
            ) from exc

        try:
            self.output_port = mido.open_output(resolved_output)
        except Exception as exc:
            ports = ", ".join(available_outputs)
            raise RuntimeError(
                f"Could not open MIDI output '{resolved_output}'. "
                f"Available outputs: [{ports}] ({exc})"
            ) from exc

        self.input_port_name = resolved_input
        self.output_port_name = resolved_output
        self._log(
            f"[midi] open input='{self.input_port_name}' output='{self.output_port_name}'"
        )

    def reconnect_token(self) -> int:
        return self._reconnect_token

    def _close_ports(self) -> None:
        if self.input_port is not None:
            try:
                self.input_port.close()
            except Exception:
                pass
            self.input_port = None
        if self.output_port is not None:
            try:
                self.output_port.close()
            except Exception:
                pass
            self.output_port = None

    def _maybe_reconnect(self, reason: str) -> None:
        now = time.monotonic()
        if now - self._last_reconnect_attempt < self._reconnect_backoff_seconds:
            return

        self._last_reconnect_attempt = now
        self._log(f"[midi] connection lost ({reason}); attempting reconnect")
        self._close_ports()
        try:
            self.open()
            self._reconnect_token += 1
            self._log("[midi] reconnect successful")
        except Exception as exc:
            self._log(f"[midi] reconnect failed: {exc}")

    def poll_messages(self) -> list[mido.Message]:
        if self.input_port is None:
            self._maybe_reconnect("input not open")
            return []
        try:
            return list(self.input_port.iter_pending())
        except Exception as exc:
            self._maybe_reconnect(f"poll error: {exc}")
            return []

    def send(self, message: mido.Message) -> None:
        if self.output_port is None:
            self._maybe_reconnect("output not open")
            if self.output_port is None:
                raise RuntimeError("MIDI output port is not open")
        try:
            self.output_port.send(message)
        except Exception as exc:
            self._maybe_reconnect(f"send error: {exc}")
            if self.output_port is None:
                raise
            self.output_port.send(message)

    def close(self) -> None:
        self._close_ports()
        self._log("[midi] ports closed")
