"""
Telegram-бот с кнопкой ручного запуска дневного скрининга.

При нажатии кнопки — делает POST запрос на serverless эндпоинт.
"""

import logging
import os

import requests

from config import TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID

logger = logging.getLogger(__name__)

VERCEL_URL = os.getenv("VERCEL_URL") or os.getenv("API_URL")
VERCEL_TOKEN = os.getenv("VERCEL_TOKEN", "")

# Постоянная клавиатура (прилипает к низу чата)
REPLY_KEYBOARD = {
    "keyboard": [[{"text": "🔍 Check Inplay"}]],
    "resize_keyboard": True,
    "persistent": True,
    "one_time_keyboard": False,
}


class TelegramBot:
    def __init__(self):
        self.token = TELEGRAM_BOT_TOKEN
        self.api  = f"https://api.telegram.org/bot{self.token}"

    # ── HTTP ───────────────────────────────────────────────────────

    def _send_get_id(self, chat_id: str, text: str, reply_markup=None):
        """Отправляет сообщение и возвращает его message_id."""
        payload = {
            "chat_id":                  chat_id,
            "text":                     text,
            "parse_mode":               "HTML",
            "disable_web_page_preview": True,
        }
        if reply_markup:
            payload["reply_markup"] = reply_markup
        try:
            r = requests.post(f"{self.api}/sendMessage", json=payload, timeout=10)
            data = r.json()
            if data.get("ok"):
                return data["result"]["message_id"]
        except Exception as e:
            logger.error(f"send_get_id error: {e}")
        return None

    def _edit(self, chat_id: str, message_id: int, text: str) -> bool:
        """Редактирует существующее сообщение (для обновления прогресса)."""
        if not message_id:
            return False
        try:
            r = requests.post(
                f"{self.api}/editMessageText",
                json={
                    "chat_id":                  chat_id,
                    "message_id":               message_id,
                    "text":                     text,
                    "parse_mode":               "HTML",
                    "disable_web_page_preview": True,
                },
                timeout=10,
            )
            return r.json().get("ok", False)
        except Exception as e:
            logger.error(f"edit error: {e}")
            return False

    def _send(self, chat_id: str, text: str, reply_markup=None) -> bool:
        payload = {
            "chat_id":                  chat_id,
            "text":                     text,
            "parse_mode":               "HTML",
            "disable_web_page_preview": True,
        }
        if reply_markup:
            payload["reply_markup"] = reply_markup
        try:
            r = requests.post(f"{self.api}/sendMessage", json=payload, timeout=10)
            return r.json().get("ok", False)
        except Exception as e:
            logger.error(f"Bot send error: {e}")
            return False

    def _get_updates(self):
        try:
            r = requests.get(
                f"{self.api}/getUpdates",
                params={"offset": self.offset, "timeout": 30},
                timeout=35,
            )
            return r.json().get("result", [])
        except Exception as e:
            logger.error(f"getUpdates error: {e}")
            return []

    # ── Обработка сообщений ────────────────────────────────────────

    def _handle(self, update: dict):
        msg     = update.get("message", {})
        text    = msg.get("text", "").strip()
        chat_id = str(msg.get("chat", {}).get("id", ""))

        if not chat_id:
            return

        if text == "/start":
            self._send(
                chat_id,
                "👋 Inplay скринер активен.\nНажми кнопку для ручного сканирования.",
                reply_markup=REPLY_KEYBOARD,
            )
            return

        if text == "🔍 Check Inplay":
            self._call_scan_endpoint(chat_id)

    def _call_scan_endpoint(self, chat_id: str):
        if not VERCEL_URL:
            self._send(chat_id, "⚠️ VERCEL_URL не настроен")
            return

        headers = {"Content-Type": "application/json"}
        if VERCEL_TOKEN:
            headers["Authorization"] = f"Bearer {VERCEL_TOKEN}"

        msg_id = self._send_get_id(chat_id, "🔍 Запрашиваю INPLAY...")
        try:
            r = requests.post(
                VERCEL_URL,
                headers=headers,
                timeout=65,
            )
            if r.status_code == 200:
                self._edit(chat_id, msg_id, "✅ Ответ получен!")
            else:
                self._edit(chat_id, msg_id, f"⚠️ Ошибка: {r.status_code}")
        except Exception as e:
            logger.error(f"Scan request error: {e}")
            self._edit(chat_id, msg_id, f"⚠️ Ошибка запроса: {e}")

    # ── Polling loop ───────────────────────────────────────────────

    def _poll(self):
        logger.info("Bot polling started")
        while True:
            updates = self._get_updates()
            for update in updates:
                self.offset = update["update_id"] + 1
                try:
                    self._handle(update)
                except Exception as e:
                    logger.error(f"Handle error: {e}", exc_info=True)
            if not updates:
                time.sleep(1)

    def start(self):
        """Проверяет что бот работает и отправляет приветствие."""
        self._send(
            TELEGRAM_CHAT_ID,
            "👋 <b>Inplay Screener активен</b>\n\n"
            "Нажми <b>🔍 Check Inplay</b> чтобы увидеть какие монеты "
            "сейчас активны на рынке.",
            reply_markup=REPLY_KEYBOARD,
        )
        logger.info("Telegram bot started")
