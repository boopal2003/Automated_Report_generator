# llm.py (modified: audit log, df_records, SQL-only prompt, robust extraction)
import os
import sys
BASE = os.path.dirname(__file__)
# ensure vendor packages are on path (your extracted embedded packages folder)
sys.path.insert(0, os.path.join(BASE, "packages"))

import re
import json
import time
import pandas as pd
import logging.handlers
from typing import Tuple, Optional
from utils.logger import app_logger, sql_error_logger, exec_logger
from utils.sql_validator import validate_sql
from db import execute_select
from config import OPENAI_API_KEY, MAX_SQL_RETRIES
from openai import OpenAI
from datetime import datetime

# load prompts
PROMPTS_DIR = os.path.join(os.path.dirname(__file__), "prompts")
SCHEMA_TXT = os.path.join(PROMPTS_DIR, "schema.txt")
SQL_EXAMPLES = os.path.join(PROMPTS_DIR, "sql_examples.txt")
SYSTEM_PROMPT = os.path.join(PROMPTS_DIR, "system_prompt.txt")    # long summarizer
SQL_SYSTEM_PROMPT = os.path.join(PROMPTS_DIR, "sql_system.txt")   # strict SQL-only prompt (optional file)

AUDIT_FILE = os.path.join(os.path.dirname(__file__), "logs", "audit.jsonl")
os.makedirs(os.path.join(os.path.dirname(__file__), "logs"), exist_ok=True)

def _read_file(path: str) -> str:
    if not os.path.exists(path):
        return ""
    with open(path, "r", encoding="utf-8") as f:
        return f.read()

# prepare system prompt pieces
_schema_txt = _read_file(SCHEMA_TXT)
_sql_examples = _read_file(SQL_EXAMPLES)
_system_prompt_text = _read_file(SYSTEM_PROMPT)
_sql_system_prompt_text = _read_file(SQL_SYSTEM_PROMPT)

# ---------------------
# SQL sanitizer & extractor
# ---------------------
def _extract_sql_from_text(text: str) -> str:
    """
    Extract SQL from LLM reply:
      - Prefer triple-backtick fences ```sql ... ```
      - Else find first occurrence of WITH ... SELECT or SELECT ... and return from that point.
      - Remove surrounding prose, trailing semicolons.
    Returns empty string if nothing found.
    """
    if not text:
        return ""
    # prefer code fence
    m = re.search(r"```(?:sql)?\s*([\s\S]*?)\s*```", text, re.IGNORECASE)
    if m:
        candidate = m.group(1).strip()
    else:
        # fallback: capture from first SELECT or WITH ... SELECT
        m2 = re.search(r"((?:WITH\b[\s\S]*?\bSELECT|SELECT)[\s\S]*)", text, re.IGNORECASE)
        candidate = m2.group(1).strip() if m2 else ""
    if not candidate:
        return ""
    # remove leading explanatory lines up to the SELECT/ WITH
    candidate = re.sub(r"^[\s\S]*?(SELECT|WITH\b)", lambda mo: mo.group(1), candidate, count=1, flags=re.IGNORECASE)
    # normalize newlines and strip fences/quotes
    candidate = candidate.strip().strip("` \n\r\t")
    # remove trailing semicolons & whitespace
    candidate = candidate.rstrip("; \t\n\r")
    # collapse multiple spaces & trim each line
    candidate = "\n".join(re.sub(r"[ \t]+", " ", ln).strip() for ln in candidate.splitlines() if ln.strip() != "")
    return candidate.strip()

def sanitize_sql(sql: str) -> str:
    """
    Normalize SQL:
      - Strip fences/backticks
      - Remove trailing semicolons
      - Convert LIMIT N to SELECT TOP N (SQL Server) if no TOP present
      - Remove weird whitespace
    """
    if not sql:
        return sql
    s = sql.strip()
    # strip code fences if present
    if s.startswith("```") and s.endswith("```"):
        parts = s.splitlines()
        if len(parts) >= 3:
            s = "\n".join(parts[1:-1])
        else:
            s = s.strip("`")
    s = s.strip("` \n\r\t")
    # normalize CRLF
    s = s.replace("\r\n", "\n").replace("\r", "\n")
    # remove trailing semicolon(s)
    s = s.rstrip().rstrip(";")
    # normalize spaces within lines
    lines = [re.sub(r"[ \t]+", " ", ln).strip() for ln in s.splitlines() if ln.strip()]
    s = "\n".join(lines)
    # convert trailing LIMIT N to TOP N (only if no TOP present)
    m = re.search(r"LIMIT\s+(\d+)\s*$", s, flags=re.IGNORECASE)
    if m and not re.search(r"^\s*SELECT\s+TOP\b", s, flags=re.IGNORECASE):
        limit_n = int(m.group(1))
        # Replace the first SELECT with SELECT TOP X
        s = re.sub(r"^\s*SELECT\s+", f"SELECT TOP {limit_n} ", s, count=1, flags=re.IGNORECASE)
        s = re.sub(r"\s+LIMIT\s+\d+\s*$", "", s, flags=re.IGNORECASE)
    return s.strip()

# ---------------------
# audit helper
# ---------------------
def _audit_append(record: dict):
    try:
        with open(AUDIT_FILE, "a", encoding="utf-8") as f:
            f.write(json.dumps(record, default=str) + "\n")
    except Exception as e:
        app_logger.exception("Failed to write audit record: %s", str(e))

# ---------------------
# DB error classifier
# ---------------------
def _classify_db_error(err_msg: str) -> str:
    """
    Return 'transient' | 'semantic' | 'auth' | 'unknown' depending on message keywords.
    """
    if not err_msg:
        return "unknown"
    em = err_msg.lower()
    if any(k in em for k in ["timeout", "timed out", "could not open a connection", "login timeout", "deadlock", "transport-level", "network-related", "connection refused"]):
        return "transient"
    if any(k in em for k in ["invalid column", "invalid object", "column not found", "does not exist", "cannot find column", "invalid column name", "no such column", "invalid column name", "syntax error", "failed to execute"]):
        return "semantic"
    if any(k in em for k in ["login failed", "permission", "permission denied", "access denied", "credential"]):
        return "auth"
    return "unknown"

# ---------------------
# LLM orchestrator
# ---------------------
class LLMOrchestrator:
    def __init__(self, model: str = "gpt-4o"):
        if not OPENAI_API_KEY:
            app_logger.warning("OPENAI_API_KEY not set - LLM calls will fail until set.")
        # instantiate the OpenAI client (modern client)
        self.client = OpenAI(api_key=OPENAI_API_KEY)
        self.model = model

    def _build_sql_generation_prompt(self, user_query: str, prev_attempts: Optional[str] = None) -> list:
        """
        Build messages for strict SQL generation. Use sql_system.txt if present; otherwise use an embedded minimal SQL prompt.
        Then append a compact schema + sql_examples to give the model column names.
        """
        # load strict SQL system prompt (prefer file if present)
        sql_system_text = _sql_system_prompt_text or (
            "You are a strict SQL generator for SQL Server. OUTPUT ONLY the SQL SELECT statement in a single triple-backtick code block labeled sql (```sql ... ```). "
            "Do not output any explanatory text, JSON, or prose. Use only tables/columns from the provided schema. "
            "If you cannot produce a valid SELECT because fields are missing, return exactly: UNABLE_TO_GENERATE_SQL: missing <table.field> ."
        )

        # compact schema and examples (avoid huge prompt)
        schema_block = "\n\nSchema (table -> columns):\n" + (_schema_txt or "NO SCHEMA PROVIDED")
        examples_block = "\n\nSQL examples:\n" + (_sql_examples or "NO EXAMPLES PROVIDED")
        system_message = sql_system_text + schema_block + examples_block

        user_msg = f"User natural-language request (generate SQL only): {user_query}"
        if prev_attempts:
            user_msg += "\n\nPrevious attempt feedback: " + prev_attempts

        return [
            {"role": "system", "content": system_message},
            {"role": "user", "content": user_msg},
        ]

    def generate_sql(self, user_query: str, feedback: Optional[str] = None) -> str:
        """
        Generate SQL strictly. Returns sanitized SQL string or raises an exception with clear message.
        """
        messages = self._build_sql_generation_prompt(user_query, prev_attempts=feedback)
        app_logger.info("Requesting SQL from LLM for query: %s", user_query)
        try:
            resp = self.client.chat.completions.create(
                model=self.model,
                messages=messages,
                max_tokens=800,
                temperature=0.0,
            )
            choice = resp.choices[0]
            content = ""
            if getattr(choice, "message", None):
                content = choice.message.content
            else:
                content = getattr(choice, "text", "") or str(choice)

            app_logger.debug("Raw LLM response (first 1000 chars): %s", (content[:1000] + "...") if len(content) > 1000 else content)

            # Check for explicit inability token
            if content.strip().upper().startswith("UNABLE_TO_GENERATE_SQL"):
                raise ValueError(content.strip())

            # Extract SQL
            sql_candidate = _extract_sql_from_text(content)
            if not sql_candidate:
                # If we couldn't find SQL, return error with raw reply excerpt (so feedback is helpful)
                raise ValueError("No SQL found in LLM response; raw reply excerpt: " + (content[:500].replace("\n", " ")))

            # sanitize
            sql_sanitized = sanitize_sql(sql_candidate)
            app_logger.debug("Sanitized SQL:\n%s", sql_sanitized)

            # Basic safety checks
            if re.search(r"\b(INSERT|UPDATE|DELETE|DROP|ALTER|TRUNCATE|CREATE|EXEC|MERGE)\b", sql_sanitized, re.IGNORECASE):
                raise ValueError("Forbidden non-SELECT statement detected in SQL candidate.")

            if not re.search(r"^\s*(WITH\b.*\bSELECT|SELECT\b)", sql_sanitized, re.IGNORECASE | re.DOTALL):
                raise ValueError("SQL candidate does not begin with SELECT/CTE.")

            # final return
            return sql_sanitized

        except Exception as e:
            app_logger.exception("LLM SQL generation failed: %s", str(e))
            raise

    def summarize_results(self, user_query: str, df: pd.DataFrame, meta: dict) -> str:
        """
        Summarize the results into an executive summary using the long system prompt (system_prompt.txt).
        If prompts/system_prompt.txt is present, use it as the system message; otherwise use compact fallback.
        """
        sample = df.head(6).to_dict(orient="records")
        stats = {
            "rows_returned": meta.get("row_count", 0),
            "exec_time_secs": meta.get("exec_time_secs"),
        }

        system_text = _system_prompt_text or (
            "You are an expert report writer for workflow data. Generate a concise executive summary (4-8 sentences), followed by 3 bullet insights. "
            "Be factual, include provenance tokens for key facts if available, and avoid hallucination."
        )

        # Compose user payload with stats and sample
        user_msg = f"Original user request: {user_query}\n\nStats: {json.dumps(stats)}\n\nSample rows (up to 6): {json.dumps(sample, default=str)}\n\nProvide a concise executive summary (4-8 sentences) and 3 bullet-point insights (if any)."

        try:
            resp = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": system_text},
                    {"role": "user", "content": user_msg}
                ],
                max_tokens=400,
                temperature=0.0
            )
            choice = resp.choices[0]
            if getattr(choice, "message", None):
                return choice.message.content.strip()
            return getattr(choice, "text", str(choice)).strip()
        except Exception as e:
            app_logger.exception("LLM summarization failed: %s", str(e))
            return "Failed to generate summary due to LLM error."

    def run_query(self, user_query: str, max_retries: Optional[int] = None) -> dict:
        """
        Full pipeline: NL -> SQL -> validate -> execute -> summarize.
        Returns dict: {ok, sql, df_html, summary, meta, attempts, df_records}
        """
        attempts = []
        feedback = None
        max_retries = max_retries if max_retries is not None else (MAX_SQL_RETRIES or 2)

        for attempt in range(max_retries + 1):
            try:
                sql = self.generate_sql(user_query, feedback)
            except Exception as e:
                err = f"LLM generation error: {str(e)}"
                app_logger.exception(err)
                return {"ok": False, "error": err, "attempts": attempts}

            attempts.append({"attempt": attempt + 1, "sql": sql})

            # Validate SQL (this should enforce allowed tables & basic safety)
            ok, msg = validate_sql(sql)
            if not ok:
                sql_error_logger.warning("SQL validation failed: %s | reason: %s | sql=%s", user_query, msg, sql)
                # pass validator message back as feedback to LLM to fix SQL
                feedback = f"Validation failed: {msg}. Regenerate a correct SELECT using the schema and examples. Return SQL only."
                continue

            # Execute
            df, meta = execute_select(sql)
            # meta may include error or row_count and exec_time_secs
            if meta.get("error"):
                err_msg = meta.get("error")
                kind = _classify_db_error(err_msg)
                sql_error_logger.warning("SQL execution error (%s): %s | sql=%s", kind, err_msg, sql)

                if kind == "transient":
                    # transient: try again (simple backoff) without asking LLM to change SQL
                    time.sleep(1 + attempt)
                    feedback = None
                    continue

                # semantic or other: pass database error back to LLM for SQL repair
                feedback = f"Execution failed with error: {err_msg}. Please regenerate SQL avoiding the error (likely column/table issue)."
                continue

            # Success: summarize and return
            summary = self.summarize_results(user_query, df, meta)
            html_table = df.to_html(index=False, classes="table table-sm", border=0, escape=False)
            exec_logger.info("Completed pipeline for query: %s | rows=%s", user_query, meta.get("row_count"))

            # Audit record
            try:
                audit = {
                    "timestamp": datetime.utcnow().isoformat() + "Z",
                    "user_query": user_query,
                    "sanitized_sql": sql,
                    "rows": int(meta.get("row_count", 0)) if meta.get("row_count") is not None else None,
                    "exec_time_secs": meta.get("exec_time_secs"),
                    "error": meta.get("error"),
                    "attempts": attempts
                }
                _audit_append(audit)
            except Exception:
                app_logger.exception("Failed to write audit record.")

            # Provide df_records for client-side charting
            try:
                df_records = df.to_dict(orient="records")
            except Exception:
                df_records = []

            return {
                "ok": True,
                "sql": sql,
                "df_html": html_table,
                "summary": summary,
                "meta": meta,
                "attempts": attempts,
                "df_records": df_records
            }

        # exhausted retries
        app_logger.warning("All retries exhausted for query: %s | attempts: %s", user_query, attempts)
        # audit failure
        try:
            _audit_append({
                "timestamp": datetime.utcnow().isoformat() + "Z",
                "user_query": user_query,
                "sanitized_sql": attempts[-1]["sql"] if attempts else None,
                "rows": None,
                "exec_time_secs": None,
                "error": "Failed after retries",
                "attempts": attempts
            })
        except Exception:
            pass

        return {"ok": False, "error": "Failed after retries", "attempts": attempts}
