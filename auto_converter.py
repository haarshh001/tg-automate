import os
import re
import sys
import asyncio
from telethon import TelegramClient, events

# ==============================================================================
# CONFIGURATION
# ==============================================================================
# Telegram API credentials (from your vault / my.telegram.org)
API_ID = 34009775
API_HASH = "9ba003127b7e7fc8db945491ba25f733"

# Session name (points to harsh.session in the same directory)
SESSION_NAME = "harsh"

# Source channel(s) to monitor for new posts.
# You can use numeric ID (e.g. -1003801941219) or username (e.g. 'source_channel')
SOURCE_CHANNELS = [
    -1003801941219,  # "Panjabhi bhabhi" (Channel identified from your screenshot)
]

# The bot that converts links (DiskWala converter bot)
CONVERTER_BOT = "DW2DW_LinkConverterBot"

# Your destination channel where the converted post + media will be published
# Examples from your account:
# -1004333951561 -> Gen-Z leaks (@genz454)
# -1004302237973 -> Bhabi Leaks (@bhabileaks)
# -1003781114997 -> Link wali (@bhableaks45)
TARGET_CHANNEL = -1004333951561  # Change to your desired target channel ID or username

# Regex to match URLs
URL_PATTERN = r'https?://[^\s]+'

# Lock to avoid concurrent conversation collisions with the converter bot
conversion_lock = asyncio.Lock()

# Track processed message IDs to prevent duplicates
processed_messages = set()

# ==============================================================================
# TELEGRAM CLIENT INITIALIZATION
# ==============================================================================
client = TelegramClient(SESSION_NAME, API_ID, API_HASH)


async def convert_url_with_bot(original_url: str) -> str | None:
    """
    Sends the original URL to the converter bot and waits for the converted link.
    Uses an asyncio lock so multiple incoming posts don't cross-talk with the bot.
    """
    async with conversion_lock:
        try:
            print(f"[>] Sending URL to @{CONVERTER_BOT}: {original_url}")
            async with client.conversation(CONVERTER_BOT, timeout=25) as conv:
                await conv.send_message(original_url)

                # Poll responses for up to 5 incoming messages from the bot
                for _ in range(5):
                    reply = await conv.get_response()
                    if reply and reply.text:
                        found_links = re.findall(URL_PATTERN, reply.text)
                        if found_links:
                            new_url = found_links[0]
                            print(f"[<] Converted link received: {new_url}")
                            return new_url
                    await asyncio.sleep(1)

        except asyncio.TimeoutError:
            print(f"[!] Timeout waiting for reply from @{CONVERTER_BOT}")
        except Exception as e:
            print(f"[!] Error during conversion with @{CONVERTER_BOT}: {e}")

    return None


async def process_and_forward(message, dry_run=False):
    """
    Extracts URLs, converts them via the bot, downloads media, and posts to target channel.
    """
    raw_text = message.text or message.caption or ""
    urls = re.findall(URL_PATTERN, raw_text)

    if not urls:
        print(f"[-] Message {message.id} has no links. Skipping.")
        return

    print(f"\n[+] Processing message {message.id} | Found {len(urls)} link(s)")
    updated_text = raw_text

    # Convert each unique link found in the post
    for url in set(urls):
        converted_url = await convert_url_with_bot(url)
        if converted_url:
            updated_text = updated_text.replace(url, converted_url)
        else:
            print(f"[!] Could not convert {url}, keeping original link.")

    if dry_run:
        print("\n--- [DRY-RUN RESULT] ---")
        print(f"Original Text: {raw_text}")
        print(f"Updated Text : {updated_text}")
        print(f"Has Media    : {bool(message.media)}")
        print("Dry-run complete (no message was posted to target channel).\n")
        return

    # Post to Target Channel
    temp_file = None
    try:
        if message.media:
            print("[*] Downloading media...")
            temp_file = await message.download_media()
            print(f"[*] Uploading to target channel ({TARGET_CHANNEL})...")
            await client.send_file(
                TARGET_CHANNEL,
                file=temp_file,
                caption=updated_text
            )
        else:
            print(f"[*] Posting text-only to target channel ({TARGET_CHANNEL})...")
            await client.send_message(
                TARGET_CHANNEL,
                updated_text
            )

        print(f"[OK] Successfully posted message {message.id} to your channel!\n")

    except Exception as e:
        print(f"[ERROR] Failed to send post to target channel: {e}")
    finally:
        # Clean up downloaded media file from disk
        if temp_file and os.path.exists(temp_file):
            try:
                os.remove(temp_file)
            except Exception:
                pass


@client.on(events.NewMessage(chats=SOURCE_CHANNELS))
async def on_new_channel_post(event):
    """Event triggered whenever a new message is posted in monitored source channels."""
    msg = event.message
    if msg.id in processed_messages:
        return
    processed_messages.add(msg.id)
    await process_and_forward(msg, dry_run=False)


async def dry_run_test():
    """Fetches recent messages from the source channel to test conversion without posting."""
    source = SOURCE_CHANNELS[0]
    print(f"[*] Dry-run mode: checking recent posts from source channel ({source})...")
    async for msg in client.iter_messages(source, limit=10):
        raw_text = msg.text or msg.caption or ""
        if re.findall(URL_PATTERN, raw_text):
            print(f"[+] Found message {msg.id} containing links.")
            await process_and_forward(msg, dry_run=True)
            return
    print("[!] No messages with links found in recent posts.")


async def main():
    print("=" * 60)
    print(" Telegram Auto-Forwarder & Link Converter ")
    print("=" * 60)
    
    await client.connect()
    if not await client.is_user_authorized():
        print("[!] Session not authorized. Please check your session file.")
        return

    me = await client.get_me()
    print(f"[+] Logged in as: {me.first_name} (@{me.username}) ID: {me.id}")
    print(f"[+] Monitoring source channels: {SOURCE_CHANNELS}")
    print(f"[+] Converter bot: @{CONVERTER_BOT}")
    print(f"[+] Target channel: {TARGET_CHANNEL}")

    if "--dry-run" in sys.argv:
        await dry_run_test()
        await client.disconnect()
        return

    print("\n[+] Bot is active and listening for new posts in background. Press Ctrl+C to stop.\n")
    await client.run_until_disconnected()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n[-] Stopped by user.")
