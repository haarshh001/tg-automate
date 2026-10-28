import asyncio
import re
from telethon import TelegramClient, events
from database import db
from converter import LinkConverterService
import config


class AdminCommandCenter:
    """
    Handles in-Telegram administration commands sent by Harsh (@haarshh001).
    Allows total mobile control over channel mappings, statistics, and tests.
    """

    def __init__(self, client: TelegramClient):
        self.client = client
        self.converter = LinkConverterService(client)

    def register_handlers(self):
        @self.client.on(events.NewMessage())
        async def admin_handler(event):
            # Only listen to private messages
            if not event.is_private:
                return

            sender_id = event.sender_id
            chat_id = event.chat_id
            admin_id = config.ADMIN_USER_ID

            # Security: Authorized if sent in "Saved Messages" (self-chat) OR from ADMIN_USER_ID
            if sender_id != admin_id and chat_id != admin_id:
                return

            text = event.raw_text.strip()
            if not text.startswith("/"):
                return

            parts = text.split(maxsplit=2)
            cmd = parts[0].split("@")[0].lower()
            print(f"[Admin] Received command '{cmd}' from {sender_id} in chat {chat_id}")

            if cmd in ["/start", "/help"]:
                help_msg = (
                    "⚡ **Autonomous Telegram Mirror Command Center** ⚡\n\n"
                    "**Available Commands:**\n"
                    "• `/channels` - List all your joined channels & their IDs\n"
                    "• `/mappings` - List all channel routes & status\n"
                    "• `/add <source> <target> [bot]` - Add new channel route\n"
                    "• `/del <id>` - Remove a channel route\n"
                    "• `/toggle <id>` - Pause or Resume a route\n"
                    "• `/set_header <id> <text>` - Set custom header\n"
                    "• `/set_footer <id> <text>` - Set custom footer\n"
                    "• `/stats` - View live system stats & counters\n"
                    "• `/test <source_id>` - Test conversion on latest post\n"
                )
                await event.reply(help_msg)

            elif cmd == "/channels":
                await event.reply("🔍 Scanning your joined channels and fetching IDs...")
                dialogs = await self.client.get_dialogs()
                lines = ["📢 **Your Joined Channels & Numeric IDs:**\n"]
                count = 0
                for d in dialogs:
                    if d.is_channel:
                        username = f"@{d.entity.username}" if getattr(d.entity, "username", None) else "Private (No @)"
                        lines.append(f"• **{d.name}**\n  ID: `{d.id}` | {username}\n")
                        count += 1
                if count == 0:
                    await event.reply("No channels found on this account.")
                else:
                    await event.reply("\n".join(lines))

            elif cmd == "/mappings":
                mappings = db.get_mappings()
                if not mappings:
                    await event.reply("ℹ️ No channel mappings found. Use `/add` to create one.")
                    return

                msg_lines = ["📋 **Active Channel Mappings:**\n"]
                for m in mappings:
                    status = "🟢 Active" if m.get("enabled", True) else "🔴 Paused"
                    msg_lines.append(
                        f"• **ID**: `{m['id']}` ({m.get('name', 'Route')})\n"
                        f"  Source: `{m['source_channel']}` ➔ Target: `{m['target_channel']}`\n"
                        f"  Bot: `@{m.get('converter_bot')}` | Status: {status}\n"
                    )
                await event.reply("\n".join(msg_lines))

            elif cmd == "/add":
                raw_args = text.split()
                if len(raw_args) < 3:
                    await event.reply("⚠️ Usage: `/add <source_channel> <target_channel> [converter_bot]`")
                    return
                src = raw_args[1]
                tgt = raw_args[2]
                c_bot = raw_args[3].lstrip("@") if len(raw_args) > 3 else config.DEFAULT_CONVERTER_BOT

                new_id = db.save_mapping({
                    "name": f"Route {src} -> {tgt}",
                    "source_channel": src,
                    "target_channel": tgt,
                    "converter_bot": c_bot,
                    "enabled": True
                })
                await event.reply(f"✅ Route added successfully!\nID: `{new_id}`\nSource: `{src}`\nTarget: `{tgt}`\nBot: `@{c_bot}`")

            elif cmd == "/del":
                raw_args = text.split()
                if len(raw_args) < 2:
                    await event.reply("⚠️ Usage: `/del <mapping_id>`")
                    return
                m_id = raw_args[1]
                deleted = db.delete_mapping(m_id)
                if deleted:
                    await event.reply(f"🗑️ Mapping `{m_id}` deleted.")
                else:
                    await event.reply(f"❌ Mapping `{m_id}` not found.")

            elif cmd == "/toggle":
                raw_args = text.split()
                if len(raw_args) < 2:
                    await event.reply("⚠️ Usage: `/toggle <mapping_id>`")
                    return
                m_id = raw_args[1]
                new_state = db.toggle_mapping(m_id)
                if new_state is None:
                    await event.reply(f"❌ Mapping `{m_id}` not found.")
                else:
                    state_str = "🟢 Active" if new_state else "🔴 Paused"
                    await event.reply(f"State for `{m_id}` updated: {state_str}")

            elif cmd == "/set_header":
                raw_args = text.split(maxsplit=2)
                if len(raw_args) < 3:
                    await event.reply("⚠️ Usage: `/set_header <mapping_id> <header_text>`")
                    return
                m_id, header = raw_args[1], raw_args[2]
                m = db.get_mapping_by_id(m_id)
                if not m:
                    await event.reply(f"❌ Mapping `{m_id}` not found.")
                    return
                m["header_text"] = header
                db.save_mapping(m)
                await event.reply(f"✅ Header updated for `{m_id}`.")

            elif cmd == "/set_footer":
                raw_args = text.split(maxsplit=2)
                if len(raw_args) < 3:
                    await event.reply("⚠️ Usage: `/set_footer <mapping_id> <footer_text>`")
                    return
                m_id, footer = raw_args[1], raw_args[2]
                m = db.get_mapping_by_id(m_id)
                if not m:
                    await event.reply(f"❌ Mapping `{m_id}` not found.")
                    return
                m["footer_text"] = footer
                db.save_mapping(m)
                await event.reply(f"✅ Footer updated for `{m_id}`.")

            elif cmd == "/stats":
                stats = db.get_stats()
                msg = (
                    "📊 **System Statistics & Health** 📊\n\n"
                    f"• **Database Engine**: `{stats['database_type']}`\n"
                    f"• **Active Routes**: `{stats['active_mappings']}` of `{stats['total_mappings']}`\n"
                    f"• **Posts Forwarded**: `{stats['posts_forwarded']}`\n"
                    f"• **Links Converted**: `{stats['links_converted']}`\n"
                    f"• **Errors**: `{stats['errors']}`\n"
                    "• **Service Status**: 🟢 Online & Healthy\n"
                )
                await event.reply(msg)

            elif cmd == "/test":
                raw_args = text.split()
                if len(raw_args) < 2:
                    await event.reply("⚠️ Usage: `/test <source_channel_id>`")
                    return
                src = raw_args[1]
                src_entity = int(src) if (src.startswith("-") or src.isdigit()) else src
                await event.reply(f"🔍 Fetching latest post from `{src}`...")
                try:
                    found = False
                    async for m in self.client.iter_messages(src_entity, limit=5):
                        raw_c = m.text or m.caption or ""
                        urls = re.findall(r'https?://[^\s]+', raw_c)
                        if urls:
                            found = True
                            first_url = urls[0]
                            await event.reply(f"Found link: `{first_url}`\nTesting conversion with @{config.DEFAULT_CONVERTER_BOT}...")
                            conv = await self.converter.convert_link(first_url)
                            if conv:
                                await event.reply(f"✅ Test Success!\nOriginal: `{first_url}`\nConverted: `{conv}`")
                            else:
                                await event.reply(f"❌ Failed to get reply from converter bot.")
                            break
                    if not found:
                        await event.reply(f"ℹ️ No messages with links found in recent 5 posts of `{src}`.")
                except Exception as e:
                    await event.reply(f"❌ Test error: {e}")
