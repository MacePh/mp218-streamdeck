from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Callable

from core import platform_utils


class MarkdownCapture:
    def __init__(self, logger: Callable[[str], None]):
        self._log = logger

    def append_daily_entry(self, text: str, directory: str, open_in_typora: bool = False) -> Path:
        message = str(text).strip()
        if not message:
            raise RuntimeError("Cannot append empty markdown text")

        now = datetime.now()
        target_dir = Path(directory)
        target_dir.mkdir(parents=True, exist_ok=True)
        file_path = target_dir / f"{now.strftime('%Y-%m-%d')}.md"

        header = f"# Ideas — {now.strftime('%Y-%m-%d')}\n\n"
        entry = f"## {now.strftime('%I:%M %p').lstrip('0')}\n{message}\n\n"

        if file_path.exists():
            existing = file_path.read_text(encoding='utf-8')
            content = existing
            if existing and not existing.endswith(("\n", "\r\n")):
                content += "\n"
            content += entry
        else:
            content = header + entry

        file_path.write_text(content, encoding='utf-8')
        self._log(f"[markdown] appended daily idea: {file_path}")
        if open_in_typora:
            self.open_in_typora(file_path)
        return file_path

    def create_new_document(
        self,
        directory: str,
        template_title: str = "Untitled Idea",
        open_in_typora: bool = True,
    ) -> Path:
        now = datetime.now()
        target_dir = Path(directory)
        target_dir.mkdir(parents=True, exist_ok=True)
        base_name = now.strftime('%Y-%m-%d_%H-%M-%S')
        file_path = target_dir / f"{base_name}.md"

        content = (
            f"# {template_title}\n\n"
            f"Created: {now.strftime('%Y-%m-%d %I:%M %p').lstrip('0')}\n\n"
            "## Notes\n\n"
        )
        file_path.write_text(content, encoding='utf-8')
        self._log(f"[markdown] created new document: {file_path}")
        if open_in_typora:
            self.open_in_typora(file_path)
        return file_path

    def open_in_typora(self, path: Path) -> None:
        quoted = f'"{str(path)}"'
        command_windows = f'cmd /c start "" typora {quoted}'
        command_linux = f'typora {quoted}'
        command = command_windows if platform_utils.use_windows_paths() else command_linux
        platform_utils.run_command(command)
        self._log(f"[markdown] opened in Typora: {path}")
