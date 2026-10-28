import json
import sqlite3
import datetime
import uuid
import os
from typing import List, Dict, Any, Optional
import config

try:
    from pymongo import MongoClient
    PYMONGO_AVAILABLE = True
except ImportError:
    PYMONGO_AVAILABLE = False


class UniversalDatabase:
    """
    Universal database layer that works seamlessly with:
    1. Remote MongoDB Atlas (Stores all credentials, settings, mappings, history)
    2. Local SQLite fallback (if MongoDB is unreachable)
    """

    def __init__(self):
        self.db_type = "sqlite"
        self.mongo_client = None
        self.mongo_db = None
        self.sqlite_path = "bot_data.db"
        self._init_backend()

    def _init_backend(self):
        # Connect to MongoDB Atlas
        if config.DATABASE_URL and (config.DATABASE_URL.startswith("mongodb://") or config.DATABASE_URL.startswith("mongodb+srv://")):
            if PYMONGO_AVAILABLE:
                try:
                    self.mongo_client = MongoClient(config.DATABASE_URL, serverSelectionTimeoutMS=5000)
                    # Verify connection
                    self.mongo_client.admin.command('ping')
                    self.mongo_db = self.mongo_client.get_default_database("tg_mirror_bot")
                    self.db_type = "mongodb"
                    print("[DB] Connected to MongoDB Atlas successfully.")
                    return
                except Exception as e:
                    print(f"[DB Warning] MongoDB connection failed: {e}. Falling back to SQLite.")
            else:
                print("[DB Warning] pymongo is not installed. Falling back to SQLite.")

        # Fallback: SQLite
        self.db_type = "sqlite"
        print(f"[DB] Initializing SQLite database at: {self.sqlite_path}")
        self._init_sqlite()

    def _init_sqlite(self):
        with sqlite3.connect(self.sqlite_path) as conn:
            c = conn.cursor()
            # Mappings table
            c.execute("""
            CREATE TABLE IF NOT EXISTS mappings (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                enabled INTEGER NOT NULL DEFAULT 1,
                source_channel TEXT NOT NULL,
                target_channel TEXT NOT NULL,
                converter_bot TEXT NOT NULL,
                url_filter_regex TEXT,
                header_text TEXT,
                footer_text TEXT,
                watermark_replacements TEXT,
                inline_buttons TEXT,
                strip_unconverted INTEGER DEFAULT 0,
                allow_albums INTEGER DEFAULT 1,
                post_delay_seconds INTEGER DEFAULT 2
            )
            """)
            # Processed messages deduplication table
            c.execute("""
            CREATE TABLE IF NOT EXISTS processed_messages (
                source_id TEXT NOT NULL,
                message_id INTEGER NOT NULL,
                content_hash TEXT,
                processed_at TEXT NOT NULL,
                PRIMARY KEY (source_id, message_id)
            )
            """)
            # History log table
            c.execute("""
            CREATE TABLE IF NOT EXISTS history (
                id TEXT PRIMARY KEY,
                timestamp TEXT NOT NULL,
                source_channel TEXT NOT NULL,
                target_channel TEXT NOT NULL,
                original_url TEXT,
                converted_url TEXT,
                media_type TEXT,
                status TEXT NOT NULL,
                error_message TEXT
            )
            """)
            # Global settings & config table
            c.execute("""
            CREATE TABLE IF NOT EXISTS settings (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL
            )
            """)
            # Global statistics table
            c.execute("""
            CREATE TABLE IF NOT EXISTS stats (
                key TEXT PRIMARY KEY,
                value INTEGER NOT NULL DEFAULT 0
            )
            """)
            conn.commit()

    # --------------------------------------------------------------------------
    # TELEGRAM SETTINGS & CREDENTIALS (Stored in MongoDB)
    # --------------------------------------------------------------------------
    def get_telegram_config(self) -> Dict[str, Any]:
        """Loads Telegram API credentials and settings directly from MongoDB."""
        defaults = {
            "api_id": 34009775,
            "api_hash": "9ba003127b7e7fc8db945491ba25f733",
            "string_session": "",
            "admin_user_id": 8898097352,
            "default_converter_bot": "DW2DW_LinkConverterBot",
            "bot_convert_timeout": 25,
            "album_buffer_time": 2.0
        }

        if self.db_type == "mongodb":
            doc = self.mongo_db.settings.find_one({"_id": "telegram_config"})
            if doc:
                return {
                    "api_id": int(doc.get("api_id", defaults["api_id"])),
                    "api_hash": str(doc.get("api_hash", defaults["api_hash"])),
                    "string_session": str(doc.get("string_session", "")),
                    "admin_user_id": int(doc.get("admin_user_id", defaults["admin_user_id"])),
                    "default_converter_bot": str(doc.get("default_converter_bot", defaults["default_converter_bot"])),
                    "bot_convert_timeout": int(doc.get("bot_convert_timeout", defaults["bot_convert_timeout"])),
                    "album_buffer_time": float(doc.get("album_buffer_time", defaults["album_buffer_time"]))
                }
        else:
            with sqlite3.connect(self.sqlite_path) as conn:
                c = conn.cursor()
                c.execute("SELECT value FROM settings WHERE key = 'telegram_config'")
                row = c.fetchone()
                if row:
                    try:
                        return json.loads(row[0])
                    except Exception:
                        pass

        return defaults

    def save_telegram_config(self, cfg: Dict[str, Any]):
        """Saves or updates Telegram API credentials and settings in MongoDB."""
        data = {
            "api_id": int(cfg.get("api_id", 34009775)),
            "api_hash": str(cfg.get("api_hash", "9ba003127b7e7fc8db945491ba25f733")).strip(),
            "string_session": str(cfg.get("string_session", "")).strip(),
            "admin_user_id": int(cfg.get("admin_user_id", 8898097352)),
            "default_converter_bot": str(cfg.get("default_converter_bot", "DW2DW_LinkConverterBot")).strip(),
            "bot_convert_timeout": int(cfg.get("bot_convert_timeout", 25)),
            "album_buffer_time": float(cfg.get("album_buffer_time", 2.0))
        }

        if self.db_type == "mongodb":
            self.mongo_db.settings.replace_one({"_id": "telegram_config"}, data, upsert=True)
        else:
            with sqlite3.connect(self.sqlite_path) as conn:
                c = conn.cursor()
                c.execute("INSERT OR REPLACE INTO settings (key, value) VALUES ('telegram_config', ?)", (json.dumps(data),))
                conn.commit()

        print("[DB] Telegram configuration updated in database.")

    # --------------------------------------------------------------------------
    # MAPPINGS CRUD
    # --------------------------------------------------------------------------
    def get_mappings(self) -> List[Dict[str, Any]]:
        if self.db_type == "mongodb":
            cursor = self.mongo_db.mappings.find({}, {"_id": 0})
            return list(cursor)
        else:
            with sqlite3.connect(self.sqlite_path) as conn:
                conn.row_factory = sqlite3.Row
                c = conn.cursor()
                c.execute("SELECT * FROM mappings")
                rows = c.fetchall()
                result = []
                for r in rows:
                    item = dict(r)
                    item["enabled"] = bool(item["enabled"])
                    item["strip_unconverted"] = bool(item["strip_unconverted"])
                    item["allow_albums"] = bool(item["allow_albums"])
                    item["watermark_replacements"] = json.loads(item["watermark_replacements"] or "{}")
                    item["inline_buttons"] = json.loads(item["inline_buttons"] or "[]")
                    result.append(item)
                return result

    def get_mapping_by_id(self, mapping_id: str) -> Optional[Dict[str, Any]]:
        mappings = self.get_mappings()
        for m in mappings:
            if m.get("id") == mapping_id:
                return m
        return None

    def get_mappings_by_source(self, source_channel: str) -> List[Dict[str, Any]]:
        clean_source = str(source_channel).strip()
        mappings = self.get_mappings()
        matched = []
        for m in mappings:
            src = str(m.get("source_channel", "")).strip()
            if src == clean_source or (src.startswith("@") and src[1:] == clean_source.lstrip("@")):
                if m.get("enabled", True):
                    matched.append(m)
        return matched

    def save_mapping(self, data: Dict[str, Any]) -> str:
        mapping_id = data.get("id") or f"map_{uuid.uuid4().hex[:8]}"
        data["id"] = mapping_id
        data["enabled"] = bool(data.get("enabled", True))
        data["source_channel"] = str(data.get("source_channel", "")).strip()
        data["target_channel"] = str(data.get("target_channel", "")).strip()
        data["converter_bot"] = data.get("converter_bot") or config.DEFAULT_CONVERTER_BOT
        data["url_filter_regex"] = data.get("url_filter_regex", r"https?://[^\s]+")
        data["header_text"] = data.get("header_text", "")
        data["footer_text"] = data.get("footer_text", "")
        data["watermark_replacements"] = data.get("watermark_replacements", {})
        data["inline_buttons"] = data.get("inline_buttons", [])
        data["strip_unconverted"] = bool(data.get("strip_unconverted", False))
        data["allow_albums"] = bool(data.get("allow_albums", True))
        data["post_delay_seconds"] = int(data.get("post_delay_seconds", 2))

        if self.db_type == "mongodb":
            self.mongo_db.mappings.update_one({"id": mapping_id}, {"$set": data}, upsert=True)
        else:
            with sqlite3.connect(self.sqlite_path) as conn:
                c = conn.cursor()
                c.execute("""
                INSERT INTO mappings (
                    id, name, enabled, source_channel, target_channel, converter_bot,
                    url_filter_regex, header_text, footer_text, watermark_replacements,
                    inline_buttons, strip_unconverted, allow_albums, post_delay_seconds
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    name=excluded.name,
                    enabled=excluded.enabled,
                    source_channel=excluded.source_channel,
                    target_channel=excluded.target_channel,
                    converter_bot=excluded.converter_bot,
                    url_filter_regex=excluded.url_filter_regex,
                    header_text=excluded.header_text,
                    footer_text=excluded.footer_text,
                    watermark_replacements=excluded.watermark_replacements,
                    inline_buttons=excluded.inline_buttons,
                    strip_unconverted=excluded.strip_unconverted,
                    allow_albums=excluded.allow_albums,
                    post_delay_seconds=excluded.post_delay_seconds
                """, (
                    mapping_id,
                    data.get("name", "Untitled Mapping"),
                    1 if data["enabled"] else 0,
                    data["source_channel"],
                    data["target_channel"],
                    data["converter_bot"],
                    data["url_filter_regex"],
                    data["header_text"],
                    data["footer_text"],
                    json.dumps(data["watermark_replacements"]),
                    json.dumps(data["inline_buttons"]),
                    1 if data["strip_unconverted"] else 0,
                    1 if data["allow_albums"] else 0,
                    data["post_delay_seconds"]
                ))
                conn.commit()
        return mapping_id

    def delete_mapping(self, mapping_id: str) -> bool:
        if self.db_type == "mongodb":
            res = self.mongo_db.mappings.delete_one({"id": mapping_id})
            return res.deleted_count > 0
        else:
            with sqlite3.connect(self.sqlite_path) as conn:
                c = conn.cursor()
                c.execute("DELETE FROM mappings WHERE id = ?", (mapping_id,))
                conn.commit()
                return c.rowcount > 0

    def toggle_mapping(self, mapping_id: str) -> Optional[bool]:
        m = self.get_mapping_by_id(mapping_id)
        if not m:
            return None
        new_state = not m.get("enabled", True)
        m["enabled"] = new_state
        self.save_mapping(m)
        return new_state

    # --------------------------------------------------------------------------
    # DEDUPLICATION
    # --------------------------------------------------------------------------
    def is_message_processed(self, source_id: str, message_id: int) -> bool:
        src = str(source_id).strip()
        if self.db_type == "mongodb":
            doc = self.mongo_db.processed_messages.find_one({"source_id": src, "message_id": message_id})
            return doc is not None
        else:
            with sqlite3.connect(self.sqlite_path) as conn:
                c = conn.cursor()
                c.execute("SELECT 1 FROM processed_messages WHERE source_id = ? AND message_id = ?", (src, message_id))
                return c.fetchone() is not None

    def mark_message_processed(self, source_id: str, message_id: int, content_hash: str = ""):
        src = str(source_id).strip()
        now = datetime.datetime.utcnow().isoformat()
        if self.db_type == "mongodb":
            self.mongo_db.processed_messages.update_one(
                {"source_id": src, "message_id": message_id},
                {"$set": {"content_hash": content_hash, "processed_at": now}},
                upsert=True
            )
        else:
            with sqlite3.connect(self.sqlite_path) as conn:
                c = conn.cursor()
                c.execute("""
                INSERT OR REPLACE INTO processed_messages (source_id, message_id, content_hash, processed_at)
                VALUES (?, ?, ?, ?)
                """, (src, message_id, content_hash, now))
                conn.commit()

    # --------------------------------------------------------------------------
    # POST HISTORY
    # --------------------------------------------------------------------------
    def add_history(self, record: Dict[str, Any]):
        rec_id = f"hist_{uuid.uuid4().hex[:10]}"
        now = datetime.datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S UTC")
        data = {
            "id": rec_id,
            "timestamp": now,
            "source_channel": str(record.get("source_channel", "")),
            "target_channel": str(record.get("target_channel", "")),
            "original_url": record.get("original_url", ""),
            "converted_url": record.get("converted_url", ""),
            "media_type": record.get("media_type", "text"),
            "status": record.get("status", "success"),
            "error_message": record.get("error_message", "")
        }

        if self.db_type == "mongodb":
            self.mongo_db.history.insert_one(data)
        else:
            with sqlite3.connect(self.sqlite_path) as conn:
                c = conn.cursor()
                c.execute("""
                INSERT INTO history (id, timestamp, source_channel, target_channel, original_url, converted_url, media_type, status, error_message)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    data["id"], data["timestamp"], data["source_channel"], data["target_channel"],
                    data["original_url"], data["converted_url"], data["media_type"], data["status"], data["error_message"]
                ))
                conn.commit()

        # Update stats
        if data["status"] == "success":
            self.increment_stat("posts_forwarded")
            if data["converted_url"]:
                self.increment_stat("links_converted")
        else:
            self.increment_stat("errors")

    def get_history(self, limit: int = 50, offset: int = 0) -> List[Dict[str, Any]]:
        if self.db_type == "mongodb":
            cursor = self.mongo_db.history.find({}, {"_id": 0}).sort("timestamp", -1).skip(offset).limit(limit)
            return list(cursor)
        else:
            with sqlite3.connect(self.sqlite_path) as conn:
                conn.row_factory = sqlite3.Row
                c = conn.cursor()
                c.execute("SELECT * FROM history ORDER BY timestamp DESC LIMIT ? OFFSET ?", (limit, offset))
                return [dict(r) for r in c.fetchall()]

    # --------------------------------------------------------------------------
    # METRICS & STATS
    # --------------------------------------------------------------------------
    def increment_stat(self, key: str, amount: int = 1):
        if self.db_type == "mongodb":
            self.mongo_db.stats.update_one({"key": key}, {"$inc": {"value": amount}}, upsert=True)
        else:
            with sqlite3.connect(self.sqlite_path) as conn:
                c = conn.cursor()
                c.execute("INSERT INTO stats (key, value) VALUES (?, ?) ON CONFLICT(key) DO UPDATE SET value = value + ?", (key, amount, amount))
                conn.commit()

    def get_stats(self) -> Dict[str, Any]:
        mappings = self.get_mappings()
        active_mappings = sum(1 for m in mappings if m.get("enabled", True))

        stats_dict = {
            "posts_forwarded": 0,
            "links_converted": 0,
            "errors": 0,
            "total_mappings": len(mappings),
            "active_mappings": active_mappings,
            "database_type": self.db_type.upper()
        }

        if self.db_type == "mongodb":
            for doc in self.mongo_db.stats.find({}):
                k = doc.get("key")
                if k in stats_dict:
                    stats_dict[k] = doc.get("value", 0)
        else:
            with sqlite3.connect(self.sqlite_path) as conn:
                c = conn.cursor()
                c.execute("SELECT key, value FROM stats")
                for k, v in c.fetchall():
                    if k in stats_dict:
                        stats_dict[k] = v

        return stats_dict


# Global Singleton Instance
db = UniversalDatabase()
