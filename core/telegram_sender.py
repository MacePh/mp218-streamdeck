from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from typing import Callable


class TelegramSender:
    def __init__(self, logger: Callable[[str], None]):
        self._log = logger

    def _token(self) -> str:
        token = os.getenv("MPD_TELEGRAM_BOT_TOKEN", "").strip()
        if not token:
            token = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
        if not token:
            raise RuntimeError(
                "Telegram bot token not set (MPD_TELEGRAM_BOT_TOKEN or TELEGRAM_BOT_TOKEN)"
            )
        return token

    def _resolve_chat_id(self, action: dict) -> str:
        direct = str(action.get("chat_id", "")).strip()
        if direct:
            return direct

        destination = str(action.get("destination", "")).strip().upper()
        if destination:
            env_name = f"MPD_TELEGRAM_CHAT_ID_{destination}"
            chat_id = os.getenv(env_name, "").strip()
            if chat_id:
                return chat_id

        default_chat_id = os.getenv("MPD_TELEGRAM_CHAT_ID", "").strip()
        if default_chat_id:
            return default_chat_id

        raise RuntimeError(
            "Telegram chat id not set (chat_id action field, MPD_TELEGRAM_CHAT_ID_<DESTINATION>, or MPD_TELEGRAM_CHAT_ID)"
        )

    def send_message(self, text: str, action: dict) -> bool:
        message = str(text).strip()
        if not message:
            self._log("[telegram] skipped empty message")
            return False

        token = self._token()
        chat_id = self._resolve_chat_id(action)
        payload = {
            "chat_id": chat_id,
            "text": message,
        }
        url = f"https://api.telegram.org/bot{token}/sendMessage"
        req = urllib.request.Request(
            url,
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=15) as resp:
                raw = resp.read().decode("utf-8", errors="replace")
            data = json.loads(raw)
            if not data.get("ok"):
                raise RuntimeError(f"Telegram API returned ok=false: {raw}")
            self._log(f"[telegram] sent message to chat {chat_id}")
            return True
        except urllib.error.HTTPError as exc:
            details = exc.read().decode("utf-8", errors="replace")
            raise RuntimeError(f"Telegram HTTP {exc.code}: {details}") from exc
        except Exception as exc:
            raise RuntimeError(f"Telegram send failed: {exc}") from exc
