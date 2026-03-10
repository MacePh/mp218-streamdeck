import os
import subprocess
import webbrowser


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


def volume_step_placeholder(step: int) -> None:
    print(f"[platform][warning] volume_step is not implemented yet (step={step})")
