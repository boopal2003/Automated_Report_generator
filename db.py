# db.py
import pyodbc
import pandas as pd
import time
from typing import Tuple, Optional
from utils.logger import app_logger, exec_logger, sql_error_logger
from config import DB_SERVER, DB_NAME, DB_USER, DB_PASS, ODBC_DRIVER

def get_connection():
    """
    Returns a new pyodbc connection using config settings.
    Caller must close the connection.
    """
    conn_str = (
        f"DRIVER={ODBC_DRIVER};"
        f"SERVER={DB_SERVER};"
        f"DATABASE={DB_NAME};"
        f"UID={DB_USER};"
        f"PWD={DB_PASS};"
        "TrustServerCertificate=yes;"
    )
    app_logger.debug("Creating DB connection with conn_str (hidden creds).")
    return pyodbc.connect(conn_str, autocommit=False, timeout=30)

def execute_select(sql: str, params: Optional[tuple] = None, limit: Optional[int] = None) -> Tuple[pd.DataFrame, dict]:
    """
    Execute a SELECT SQL and return (dataframe, meta)
    meta contains: row_count, exec_time_secs
    """
    start = time.time()
    df = pd.DataFrame()
    meta = {"row_count": 0, "exec_time_secs": None, "error": None}

    try:
        if limit and isinstance(limit, int):
            # If SQL already has TOP or LIMIT we don't modify. Simple heuristic:
            lowered = sql.strip().lower()
            if not lowered.startswith("select top"):
                # Insert TOP after SELECT
                sql = sql.replace("SELECT", f"SELECT TOP {limit}", 1)

        conn = get_connection()
        try:
            df = pd.read_sql_query(sql, conn, params=params)
        finally:
            conn.close()

        meta["row_count"] = len(df)
        meta["exec_time_secs"] = round(time.time() - start, 3)
        exec_logger.info("SQL executed OK | rows=%s | time=%ss | sql=%s", meta["row_count"], meta["exec_time_secs"], sql)
        return df, meta

    except Exception as e:
        meta["error"] = str(e)
        sql_error_logger.exception("SQL execution failed: %s | sql=%s", str(e), sql)
        return pd.DataFrame(), meta
