import asyncio
from typing import List
from telethon import TelegramClient, events
from telethon.errors import FloodWaitError
from telethon.tl.types import Message
from database import db
from converter import LinkConverterService
from media_engine import MediaEngine
from pipeline import PostPipeline


class ChannelForwarderService:
    """
    Main forwarder engine that intercepts channel events, coordinates album aggregation,
    transforms content, and broadcasts to target channels.
    """

    def __init__(self, client: TelegramClient):
        self.client = client
        self.converter = LinkConverterService(client)
        self.media_engine = MediaEngine(client)
        self.pipeline = PostPipeline(self.converter)

    def register_handlers(self):
        """Attaches event listeners to the Telethon client."""
        @self.client.on(events.NewMessage())
        async def incoming_message_handler(event):
            # Only process channel / group messages
            if not (event.is_channel or event.is_group):
                return
            await self.handle_incoming_message(event.message)

    async def handle_incoming_message(self, message: Message):
        """Routes an incoming message to matching channel mappings."""
        chat_id = str(message.chat_id)
        # Find matching mappings for this source
        mappings = db.get_mappings_by_source(chat_id)

        # Also check by username if chat has a username
        if not mappings:
            chat = await message.get_chat()
            if getattr(chat, "username", None):
                mappings = db.get_mappings_by_source(f"@{chat.username}")

        if not mappings:
            return

        # Check deduplication
        if db.is_message_processed(chat_id, message.id):
            return

        # Handle albums (media groups)
        if message.grouped_id:
            await self.media_engine.buffer_album_message(
                message,
                on_album_ready=lambda msgs: self.process_album(msgs, mappings)
            )
            return

        # Handle single post (media or text)
        await self.process_single_message(message, mappings)

    async def process_single_message(self, message: Message, mappings: List[dict]):
        """Processes and forwards a single message across its assigned target mappings."""
        chat_id = str(message.chat_id)
        db.mark_message_processed(chat_id, message.id)

        raw_text = message.text or message.caption or ""
        media_type = self.media_engine.get_media_type(message)

        for mapping in mappings:
            target = mapping.get("target_channel")
            # Parse target channel (support numeric ID or username)
            target_entity = int(target) if (str(target).startswith("-") or str(target).isdigit()) else target

            # Process text and convert links
            caption, orig_url, conv_url, buttons = await self.pipeline.process_content(raw_text, mapping)

            # Optional post delay
            delay = mapping.get("post_delay_seconds", 2)
            if delay > 0:
                await asyncio.sleep(delay)

            # Download media if present
            temp_file = None
            try:
                if message.media:
                    temp_file = await self.media_engine.download_single_media(message)
                    if temp_file:
                        await self.client.send_file(
                            target_entity,
                            file=temp_file,
                            caption=caption,
                            buttons=buttons
                        )
                    else:
                        # Fallback to text if download failed
                        await self.client.send_message(target_entity, caption, buttons=buttons)
                else:
                    await self.client.send_message(target_entity, caption, buttons=buttons)

                db.add_history({
                    "source_channel": chat_id,
                    "target_channel": str(target),
                    "original_url": orig_url,
                    "converted_url": conv_url,
                    "media_type": media_type,
                    "status": "success"
                })
                print(f"[Forwarder] Posted single {media_type} to {target}")

            except FloodWaitError as fwe:
                print(f"[Forwarder Alert] Telegram FloodWait: sleeping {fwe.seconds}s...")
                await asyncio.sleep(fwe.seconds + 2)
            except Exception as e:
                print(f"[Forwarder Error] Failed sending to {target}: {e}")
                db.add_history({
                    "source_channel": chat_id,
                    "target_channel": str(target),
                    "original_url": orig_url,
                    "converted_url": conv_url,
                    "media_type": media_type,
                    "status": "error",
                    "error_message": str(e)
                })
            finally:
                self.media_engine.cleanup_path(temp_file)

    async def process_album(self, messages: List[Message], mappings: List[dict]):
        """Processes and forwards a grouped album across assigned target mappings."""
        if not messages:
            return

        first_msg = messages[0]
        chat_id = str(first_msg.chat_id)

        # Mark all messages in the album as processed
        for m in messages:
            db.mark_message_processed(chat_id, m.id)

        # Find the caption across the album messages
        raw_caption = ""
        for m in messages:
            if m.text or m.caption:
                raw_caption = m.text or m.caption
                break

        # Download all album media files
        album_files = await self.media_engine.download_album_media(messages)
        if not album_files:
            return

        try:
            for mapping in mappings:
                target = mapping.get("target_channel")
                target_entity = int(target) if (str(target).startswith("-") or str(target).isdigit()) else target

                caption, orig_url, conv_url, buttons = await self.pipeline.process_content(raw_caption, mapping)

                delay = mapping.get("post_delay_seconds", 2)
                if delay > 0:
                    await asyncio.sleep(delay)

                try:
                    await self.client.send_file(
                        target_entity,
                        file=album_files,
                        caption=caption
                    )
                    db.add_history({
                        "source_channel": chat_id,
                        "target_channel": str(target),
                        "original_url": orig_url,
                        "converted_url": conv_url,
                        "media_type": f"album_{len(album_files)}",
                        "status": "success"
                    })
                    print(f"[Forwarder] Posted album ({len(album_files)} files) to {target}")

                except FloodWaitError as fwe:
                    print(f"[Forwarder Alert] Telegram FloodWait: sleeping {fwe.seconds}s...")
                    await asyncio.sleep(fwe.seconds + 2)
                except Exception as e:
                    print(f"[Forwarder Error] Failed sending album to {target}: {e}")
                    db.add_history({
                        "source_channel": chat_id,
                        "target_channel": str(target),
                        "original_url": orig_url,
                        "converted_url": conv_url,
                        "media_type": f"album_{len(album_files)}",
                        "status": "error",
                        "error_message": str(e)
                    })

        finally:
            self.media_engine.cleanup_files(album_files)
