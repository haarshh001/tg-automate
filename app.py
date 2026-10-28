import os
import sys

# Ensure UTF-8 output on Windows consoles
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

import asyncio
import uvicorn
from telethon import TelegramClient
from telethon.sessions import StringSession
import config
from database import db
from forwarder import ChannelForwarderService
from admin_bot import AdminCommandCenter
from web_server import app as fastapi_app


def get_telegram_client() -> TelegramClient:
    """
    Initializes Telethon using credentials stored in MongoDB Atlas:
    - string_session, api_id, api_hash
    If MongoDB is empty or local, falls back to string_session.txt or harsh.session.
    """
    tg_cfg = db.get_telegram_config()
    api_id = tg_cfg.get("api_id") or config.DEFAULT_API_ID
    api_hash = tg_cfg.get("api_hash") or config.DEFAULT_API_HASH
    session_string = (tg_cfg.get("string_session") or "").strip()

    # Update runtime settings directly from MongoDB
    config.ADMIN_USER_ID = tg_cfg.get("admin_user_id") or config.DEFAULT_ADMIN_USER_ID
    config.DEFAULT_CONVERTER_BOT = tg_cfg.get("default_converter_bot") or "DW2DW_LinkConverterBot"
    config.BOT_CONVERT_TIMEOUT = tg_cfg.get("bot_convert_timeout") or 25
    config.ALBUM_BUFFER_TIME = tg_cfg.get("album_buffer_time") or 2.0

    if session_string:
        print("[Auth] Initializing Telethon with StringSession loaded from MongoDB...")
        session_obj = StringSession(session_string)
        return TelegramClient(session_obj, api_id, api_hash)
    elif os.path.exists("string_session.txt"):
        with open("string_session.txt", "r") as f:
            session_str = f.read().strip()
        print("[Auth] Initializing Telethon with StringSession from string_session.txt...")
        return TelegramClient(StringSession(session_str), api_id, api_hash)
    else:
        print(f"[Auth] Initializing Telethon with local session file: harsh.session...")
        return TelegramClient("harsh", api_id, api_hash)


async def main():
    print("=" * 65)
    print(" Autonomous Telegram Mirror & Link Converter Engine")
    print("=" * 65)

    # 1. Initialize Telegram Client from MongoDB credentials
    client = get_telegram_client()
    await client.connect()

    if not await client.is_user_authorized():
        print("[!] ERROR: Telegram session is not authorized.")
        print("    Open the Web Dashboard to enter your Telegram credentials into MongoDB.")
    else:
        me = await client.get_me()
        print(f"[+] Connected to Telegram as: {me.first_name} (@{me.username}) ID: {me.id}")
        print(f"[+] Admin ID: {config.ADMIN_USER_ID}")
        print(f"[+] Database: {db.db_type.upper()}")

        # 2. Attach Forwarder & Admin Command Center
        forwarder = ChannelForwarderService(client)
        forwarder.register_handlers()
        print("[+] Channel Forwarder & Album Aggregator registered.")

        admin_center = AdminCommandCenter(client)
        admin_center.register_handlers()
        print("[+] In-Telegram Admin Command Center registered.")

    # 3. Setup FastAPI Web Server on PORT
    server_config = uvicorn.Config(
        app=fastapi_app,
        host=config.HOST,
        port=config.PORT,
        log_level="warning",
        loop="asyncio"
    )
    server = uvicorn.Server(server_config)

    print(f"[+] Web Dashboard & Health endpoint active at http://{config.HOST}:{config.PORT}")
    print(f"[+] Health check ping ready at http://{config.HOST}:{config.PORT}/health")
    print("\n[+] All systems fully autonomous and operational. Running 24/7...\n")

    # 4. Run Telethon and FastAPI concurrently
    await asyncio.gather(
        client.run_until_disconnected(),
        server.serve()
    )


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        print("\n[-] Service gracefully terminated.")
