from typing import Callable

import mido


class MidiManager:
    def __init__(
        self,
        input_port_name: str,
        output_port_name: str,
        logger: Callable[[str], None],
    ):
        self._log = logger
        self.input_port_name = input_port_name
        self.output_port_name = output_port_name
        self.input_port = None
        self.output_port = None

    @staticmethod
    def list_input_ports() -> list[str]:
        return list(mido.get_input_names())

    @staticmethod
    def list_output_ports() -> list[str]:
        return list(mido.get_output_names())

    def open(self) -> None:
        try:
            self.input_port = mido.open_input(self.input_port_name)
        except Exception as exc:
            ports = ", ".join(self.list_input_ports())
            raise RuntimeError(
                f"Could not open MIDI input '{self.input_port_name}'. "
                f"Available inputs: [{ports}] ({exc})"
            ) from exc

        try:
            self.output_port = mido.open_output(self.output_port_name)
        except Exception as exc:
            ports = ", ".join(self.list_output_ports())
            raise RuntimeError(
                f"Could not open MIDI output '{self.output_port_name}'. "
                f"Available outputs: [{ports}] ({exc})"
            ) from exc

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
