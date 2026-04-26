"""
Telegram-бот с кнопкой ручного запуска дневного скрининга.

Запускается автоматически из main.py в фоновом потоке.
Чтобы кнопка появилась — отправь боту /start.
"""

import logging
import threading
import time

import requests

from config import TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID

logger = logging.getLogger(__name__)

# Постоянная клавиатура (прилипает к низу чата)
REPLY_KEYBOARD = {
    "keyboard": [[{"text": "🔍 Check Inplay"}]],
    "resize_keyboard": True,
    "persistent": True,
    "one_time_keyboard": False,
}


class TelegramBot:
    def __init__(self):
        self.token  = TELEGRAM_BOT_TOKEN
        self.api    = f"https://api.telegram.org/bot{self.token}"
        self.offset = 0
        self._client = None   # BinanceClient — создаётся лениво

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
            self._run_scan(chat_id)

    def _run_scan(self, chat_id: str):
        from binance_client import BinanceClient
        from daily_scan import build_message, run_scan

        if self._client is None:
            self._client = BinanceClient()

        # Отправляем начальное сообщение и сохраняем его id
        msg_id = self._send_get_id(chat_id, "🔍 Сканирую рынок на наличие INPLAY...")

        frames = ["⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏"]
        state  = {"frame": 0, "current": 0, "total": 0, "running": True}

        def animate():
            """Крутит спиннер каждую секунду пока идёт скан."""
            while state["running"]:
                icon = frames[state["frame"] % len(frames)]
                state["frame"] += 1
                if state["total"] > 0:
                    pct    = int(state["current"] / state["total"] * 100)
                    filled = int(pct / 10)
                    bar    = "█" * filled + "░" * (10 - filled)
                    text   = (
                        f"{icon} <b>Сканирую рынок на наличие INPLAY...</b>\n"
                        f"<code>[{bar}] {pct}%</code>\n"
                        f"{state['current']} / {state['total']} монет"
                    )
                else:
                    text = f"{icon} <b>Сканирую рынок на наличие INPLAY...</b>"
                self._edit(chat_id, msg_id, text)
                time.sleep(1)

        anim = threading.Thread(target=animate, daemon=True)
        anim.start()

        def progress(current: int, total: int):
            state["current"] = current
            state["total"]   = total

        try:
            top = run_scan(self._client, progress_callback=progress)
            state["running"] = False
            anim.join(timeout=2)
            message = build_message(top)
            if msg_id:
                self._edit(chat_id, msg_id, message)
            else:
                self._send(chat_id, message)

        except Exception as e:
            logger.error(f"Scan error: {e}", exc_info=True)
            state["running"] = False
            self._edit(chat_id, msg_id, f"⚠️ Ошибка скана: {e}")

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
        """Запускает polling в фоновом daemon-потоке и сразу шлёт клавиатуру."""
        # Отправляем приветствие с клавиатурой при запуске
        self._send(
            TELEGRAM_CHAT_ID,
            "👋 <b>Inplay Screener запущен</b>\n\n"
            "Нажми <b>🔍 Check Inplay</b> чтобы увидеть какие монеты "
            "сейчас активны на рынке.\n\n"
            "Если появится новый inplay — пришлю оповещение автоматически.",
            reply_markup=REPLY_KEYBOARD,
        )
        t = threading.Thread(target=self._poll, daemon=True, name="tg-bot")
        t.start()
        logger.info("Telegram bot started")
