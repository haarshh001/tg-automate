import asyncio
import re
from typing import Optional
from telethon import TelegramClient
import config

URL_PATTERN = r'https?://[^\s]+'


class LinkConverterService:
    """
    Manages conversational link conversion with Telegram converter bots (e.g. @DW2DW_LinkConverterBot).
    Uses an internal async lock per bot to ensure zero conversation cross-talk during bursts.
    """

    def __init__(self, client: TelegramClient):
        self.client = client
        self._locks = {}

    def _get_lock(self, bot_username: str) -> asyncio.Lock:
        clean = bot_username.lstrip("@").lower()
        if clean not in self._locks:
            self._locks[clean] = asyncio.Lock()
        return self._locks[clean]

    async def convert_link(self, original_url: str, bot_username: str = None) -> Optional[str]:
        """
        Sends the original URL to the specified converter bot and awaits the converted reply.
        Retries up to 2 times on timeout.
        """
        target_bot = (bot_username or config.DEFAULT_CONVERTER_BOT).lstrip("@")
        bot_lock = self._get_lock(target_bot)

        async with bot_lock:
            for attempt in range(1, 3):
                try:
                    # Clean bot entity lookup
                    async with self.client.conversation(target_bot, timeout=config.BOT_CONVERT_TIMEOUT) as conv:
                        await conv.send_message(original_url)

                        # Poll incoming messages from the bot (disregarding status messages)
                        for _ in range(5):
                            reply = await conv.get_response()
                            if reply and reply.text:
                                urls = re.findall(URL_PATTERN, reply.text)
                                if urls:
                                    converted_url = urls[0]
                                    return converted_url
                            await asyncio.sleep(1)

                except asyncio.TimeoutError:
                    print(f"[Converter] Attempt {attempt} timed out waiting for @{target_bot}.")
                    await asyncio.sleep(1.5)
                except Exception as e:
                    print(f"[Converter] Error querying @{target_bot}: {e}")
                    await asyncio.sleep(1.5)

        return None
