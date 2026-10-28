import os
import shutil
import uuid
import asyncio
from typing import List, Dict, Any, Callable, Optional
from telethon import TelegramClient
from telethon.tl.types import Message, MessageMediaPhoto, MessageMediaDocument
import config


class MediaEngine:
    """
    Handles media downloading, album aggregation (MediaGroups),
    bypassing forwarding restrictions, and safe temp cleanup.
    """

    def __init__(self, client: TelegramClient):
        self.client = client
        self.temp_base_dir = "temp_media"
        os.makedirs(self.temp_base_dir, exist_ok=True)
        # Album aggregation buffer: {grouped_id: {"messages": [], "timer": Task, "callback": func}}
        self._album_buffer = {}

    def get_media_type(self, message: Message) -> str:
        """Determines the broad media type of a message."""
        if not message.media:
            return "text"
        if isinstance(message.media, MessageMediaPhoto):
            return "photo"
        if isinstance(message.media, MessageMediaDocument):
            doc = message.media.document
            if doc and doc.mime_type:
                if doc.mime_type.startswith("video"):
                    return "video"
                if doc.mime_type.startswith("audio"):
                    return "audio"
            return "document"
        return "other_media"

    async def download_single_media(self, message: Message) -> Optional[str]:
        """Downloads a single message's media into a unique temp location."""
        if not message.media:
            return None

        job_dir = os.path.join(self.temp_base_dir, uuid.uuid4().hex[:12])
        os.makedirs(job_dir, exist_ok=True)

        try:
            downloaded_path = await message.download_media(file=job_dir)
            return downloaded_path
        except Exception as e:
            print(f"[MediaEngine] Error downloading media for message {message.id}: {e}")
            self.cleanup_path(job_dir)
            return None

    async def buffer_album_message(self, message: Message, on_album_ready: Callable):
        """
        Buffers messages that belong to a media group (album).
        Triggers `on_album_ready(messages_list)` once the buffer timer expires.
        """
        grouped_id = message.grouped_id
        if not grouped_id:
            return

        if grouped_id not in self._album_buffer:
            self._album_buffer[grouped_id] = {
                "messages": [],
                "task": None
            }

        self._album_buffer[grouped_id]["messages"].append(message)

        # Cancel previous timer if still running
        if self._album_buffer[grouped_id]["task"]:
            self._album_buffer[grouped_id]["task"].cancel()

        # Schedule new timer
        async def _trigger():
            await asyncio.sleep(config.ALBUM_BUFFER_TIME)
            data = self._album_buffer.pop(grouped_id, None)
            if data and data["messages"]:
                await on_album_ready(data["messages"])

        self._album_buffer[grouped_id]["task"] = asyncio.create_task(_trigger())

    async def download_album_media(self, messages: List[Message]) -> List[str]:
        """Downloads all media items in an album into a shared temp directory."""
        job_dir = os.path.join(self.temp_base_dir, uuid.uuid4().hex[:12])
        os.makedirs(job_dir, exist_ok=True)
        downloaded_files = []

        for msg in messages:
            if msg.media:
                try:
                    fpath = await msg.download_media(file=job_dir)
                    if fpath:
                        downloaded_files.append(fpath)
                except Exception as e:
                    print(f"[MediaEngine] Failed to download album item {msg.id}: {e}")

        return downloaded_files

    def cleanup_path(self, path: Optional[str]):
        """Safely removes a temporary file or directory."""
        if not path:
            return
        try:
            if os.path.isfile(path):
                os.remove(path)
                # Also remove parent job dir if empty
                parent = os.path.dirname(path)
                if os.path.isdir(parent) and parent.startswith(self.temp_base_dir):
                    shutil.rmtree(parent, ignore_errors=True)
            elif os.path.isdir(path):
                shutil.rmtree(path, ignore_errors=True)
        except Exception:
            pass

    def cleanup_files(self, paths: List[str]):
        """Cleans up a list of files."""
        for p in paths:
            self.cleanup_path(p)
