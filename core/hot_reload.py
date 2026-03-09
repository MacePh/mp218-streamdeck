import time


class HotReloadWatcher:
    def __init__(self, interval_ms: int):
        self.interval_seconds = max(0.1, interval_ms / 1000.0)
        self._next_check = time.monotonic()

    def should_check(self) -> bool:
        now = time.monotonic()
        if now >= self._next_check:
            self._next_check = now + self.interval_seconds
            return True
        return False
