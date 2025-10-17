# tests/test_db_conn.py
import sys, os
# Ensure local packages/ and project root are always importable
BASE_DIR = os.path.dirname(__file__)
sys.path.insert(0, os.path.join(BASE_DIR, "packages"))
sys.path.insert(0, BASE_DIR)


import pyodbc
from config import DB_SERVER, DB_NAME, DB_USER, DB_PASS, ODBC_DRIVER
import traceback

def test_db_connection():
    conn_str = f"DRIVER={ODBC_DRIVER};SERVER={DB_SERVER};DATABASE={DB_NAME};UID={DB_USER};PWD={DB_PASS};TrustServerCertificate=yes;"
    try:
        conn = pyodbc.connect(conn_str, timeout=5)
        cursor = conn.cursor()
        cursor.execute("SELECT 1")
        row = cursor.fetchone()
        print("✅ Database connection successful:", row)
        conn.close()
    except Exception as e:
        print("❌ Database connection failed:", str(e))

if __name__ == "__main__":
    test_db_connection()
