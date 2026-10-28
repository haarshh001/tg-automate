import asyncio
import re
from typing import List, Dict, Optional
from telethon import TelegramClient
import config

URL_PATTERN = r'https?://[^\s]+'


class LinkConverterService:
    """
    Manages conversational link conversion with Telegram converter bots (e.g. @DW2DW_LinkConverterBot).
    Supports ultra-fast bulk conversions (multiple URLs in 1 message) with 1-to-1 order preservation.
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

    async def convert_links_bulk(self, original_urls: List[str], bot_username: str = None) -> Dict[str, str]:
        """
        Sends multiple URLs in a single bulk message to the converter bot.
        Returns a dictionary mapping {original_url: converted_url}.
        Preserves 1-to-1 order and includes automatic fallback if any link is missed.
        """
        if not original_urls:
            return {}

        target_bot = (bot_username or config.DEFAULT_CONVERTER_BOT).lstrip("@")
        bot_lock = self._get_lock(target_bot)
        unique_urls = list(dict.fromkeys(original_urls))  # Preserve order, remove duplicates
        converted_map = {}

        async with bot_lock:
            # Format payload (if 1 URL, send 1; if multiple, send joined by newlines)
            bulk_payload = "\n".join(unique_urls)
            timeout = config.BOT_CONVERT_TIMEOUT

            for attempt in range(1, 3):
                try:
                    async with self.client.conversation(target_bot, timeout=timeout) as conv:
                        await conv.send_message(bulk_payload)

                        # Poll incoming messages from the bot
                        for _ in range(6):
                            reply = await conv.get_response()
                            if reply and reply.text:
                                raw_links = re.findall(URL_PATTERN, reply.text)
                                # Clean trailing markdown formatting (*, _, etc.) from URLs
                                found_links = [re.sub(r'[\*\_\[\]\(\)\<\>\,\.]+$', '', u) for u in raw_links]
                                if found_links:
                                    # If bot returned all converted links in order
                                    if len(found_links) == len(unique_urls):
                                        for orig, conv_link in zip(unique_urls, found_links):
                                            converted_map[orig] = conv_link
                                        return converted_map
                                    elif len(found_links) > 0:
                                        # Partial match: map what we have by index
                                        for i in range(min(len(unique_urls), len(found_links))):
                                            converted_map[unique_urls[i]] = found_links[i]
                                        # If all found, break
                                        if len(converted_map) == len(unique_urls):
                                            return converted_map

                            await asyncio.sleep(1)

                        if len(converted_map) == len(unique_urls):
                            return converted_map

                except asyncio.TimeoutError:
                    print(f"[Converter] Attempt {attempt} timed out waiting for bulk reply from @{target_bot}.")
                    await asyncio.sleep(1.5)
                except Exception as e:
                    print(f"[Converter] Error querying @{target_bot} in bulk: {e}")
                    await asyncio.sleep(1.5)

            # Fallback: If any URL was missed in bulk, convert it 1-by-1
            missing = [u for u in unique_urls if u not in converted_map]
            if missing:
                print(f"[Converter] Fallback: converting {len(missing)} missing links 1-by-1...")
                for miss_u in missing:
                    single_res = await self.convert_link(miss_u, bot_username=target_bot)
                    if single_res:
                        converted_map[miss_u] = single_res

        return converted_map

    async def convert_link(self, original_url: str, bot_username: str = None) -> Optional[str]:
        """Convenience method for single link conversion."""
        res_map = await self.convert_links_bulk([original_url], bot_username=bot_username)
        return res_map.get(original_url)
