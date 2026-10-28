import os
from dotenv import load_dotenv

# Load local .env if present
load_dotenv()

# ==============================================================================
# DATABASE CONFIGURATION
# ==============================================================================
# Read strictly from environment variable for security
DATABASE_URL = os.getenv("DATABASE_URL", "").strip()

# ==============================================================================
# FALLBACK TELEGRAM CREDENTIALS (Loaded from MongoDB / Env)
# ==============================================================================
DEFAULT_API_ID = int(os.getenv("TELEGRAM_API_ID", "34009775"))
DEFAULT_API_HASH = os.getenv("TELEGRAM_API_HASH", "9ba003127b7e7fc8db945491ba25f733")
DEFAULT_ADMIN_USER_ID = int(os.getenv("ADMIN_USER_ID", "8898097352"))
DEFAULT_CONVERTER_BOT = os.getenv("DEFAULT_CONVERTER_BOT", "DW2DW_LinkConverterBot")

# ==============================================================================
# WEB SERVER & SECURITY
# ==============================================================================
PORT = int(os.getenv("PORT", "10000"))
HOST = os.getenv("HOST", "0.0.0.0")
DASHBOARD_PASSWORD = os.getenv("DASHBOARD_PASSWORD", "admin123")
SECRET_KEY = os.getenv("SECRET_KEY", "tg-super-secret-key-2026")

# Maximum time (seconds) to wait for converter bot reply
BOT_CONVERT_TIMEOUT = int(os.getenv("BOT_CONVERT_TIMEOUT", "25"))

# Album aggregation window (seconds)
ALBUM_BUFFER_TIME = float(os.getenv("ALBUM_BUFFER_TIME", "2.0"))
