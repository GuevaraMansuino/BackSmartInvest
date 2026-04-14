import httpx

from config import settings


class TelegramBotService:
    @staticmethod
    async def send_message(message: str) -> None:
        if not settings.TELEGRAM_BOT_TOKEN or not settings.TELEGRAM_CHAT_ID:
            raise RuntimeError("Telegram credentials are missing in backend/.env.")

        url = f"https://api.telegram.org/bot{settings.TELEGRAM_BOT_TOKEN}/sendMessage"
        payload = {
            "chat_id": settings.TELEGRAM_CHAT_ID,
            "text": message,
        }

        async with httpx.AsyncClient(timeout=15.0) as client:
            response = await client.post(url, json=payload)
            response.raise_for_status()
            response_data = response.json()

        if not response_data.get("ok"):
            description = response_data.get("description", "Telegram API request failed.")
            raise RuntimeError(description)
