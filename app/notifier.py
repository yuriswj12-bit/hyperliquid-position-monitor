import httpx

from app.config import Settings
from app.models import AlertEvent


class TelegramNotifier:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    @property
    def enabled(self) -> bool:
        return bool(self.settings.telegram_bot_token and self.settings.telegram_chat_id)

    async def send_alerts(self, alerts: list[AlertEvent]) -> None:
        if not self.enabled or not alerts:
            return

        text = "\n".join(f"[{event.severity.upper()}] {event.message}\n{event.user}" for event in alerts)
        url = f"https://api.telegram.org/bot{self.settings.telegram_bot_token}/sendMessage"
        async with httpx.AsyncClient(timeout=15) as client:
            await client.post(
                url,
                json={
                    "chat_id": self.settings.telegram_chat_id,
                    "text": text,
                    "disable_web_page_preview": True,
                },
            )
