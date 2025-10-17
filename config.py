# config.py
import os

# --- Database Config ---
DB_SERVER = os.getenv("DB_SERVER", "0.0.0.0")
DB_NAME   = os.getenv("DB_NAME", "test_datadb")
DB_USER   = os.getenv("DB_USER", "Mani")
DB_PASS   = os.getenv("DB_PASS", "@ab12345")

# ODBC Driver (adjust if different in your system)
ODBC_DRIVER = os.getenv("ODBC_DRIVER", "{ODBC Driver 17 for SQL Server}")

# --- OpenAI Config ---
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY") or "<YOUR_REAL_KEY_FOR_DEV_ONLY>"

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

# --- Logging Config ---
LOG_DIR = os.getenv("LOG_DIR", "logs")
if not os.path.exists(LOG_DIR):
    os.makedirs(LOG_DIR)

# --- Retry Strategy ---
MAX_SQL_RETRIES = int(os.getenv("MAX_SQL_RETRIES", 2))
