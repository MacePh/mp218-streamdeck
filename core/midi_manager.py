from typing import Callable

import mido


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

    def poll_messages(self) -> list[mido.Message]:
        if self.input_port is None:
            return []
        return list(self.input_port.iter_pending())

    def send(self, message: mido.Message) -> None:
        if self.output_port is None:
            raise RuntimeError("MIDI output port is not open")
        self.output_port.send(message)

    def close(self) -> None:
        if self.input_port is not None:
            self.input_port.close()
        if self.output_port is not None:
            self.output_port.close()
        self._log("[midi] ports closed")
