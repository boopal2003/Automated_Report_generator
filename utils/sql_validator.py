# utils/sql_validator.py
import re
import json
import os
from typing import Tuple, List

BASE_DIR = os.path.dirname(os.path.dirname(__file__))
SCHEMA_FILE = os.path.join(BASE_DIR, "prompts", "schema.json")

# Forbidden patterns (case-insensitive)
FORBIDDEN_KEYWORDS = [
    r"\bINSERT\b", r"\bUPDATE\b", r"\bDELETE\b", r"\bDROP\b", r"\bTRUNCATE\b",
    r"\bEXEC\b", r"\bEXECUTE\b", r"\bALTER\b", r"\bCREATE\b", r"\bMERGE\b",
    r";",  # prevent chaining multiple statements
]

SELECT_ONLY_RE = re.compile(r"^\s*(WITH\s+.*\s+)?SELECT\s", re.IGNORECASE | re.DOTALL)

def load_allowed_tables() -> List[str]:
    if not os.path.exists(SCHEMA_FILE):
        return []
    with open(SCHEMA_FILE, "r", encoding="utf-8") as f:
        data = json.load(f)
    tables = list(data.get("tables", {}).keys())
    # Normalize: store both with and without dbo. prefix
    normalized = []
    for t in tables:
        t_lower = t.lower()
        normalized.append(t_lower)
        # Also add without schema prefix
        if "." in t_lower:
            normalized.append(t_lower.split(".")[-1])
    return normalized

ALLOWED_TABLES = load_allowed_tables()

def contains_forbidden(sql: str) -> Tuple[bool, str]:
    for patt in FORBIDDEN_KEYWORDS:
        if re.search(patt, sql, flags=re.IGNORECASE):
            return True, patt
    return False, ""

def uses_only_allowed_tables(sql: str) -> Tuple[bool, List[str]]:
    """Return (ok, list_of_non_allowed_tables_found)"""
    # Remove comments first
    sql_clean = re.sub(r'--.*$', '', sql, flags=re.MULTILINE)
    
    # Extract table names after FROM/JOIN, optionally with schema prefix
    found = re.findall(r'\b(?:FROM|JOIN)\s+(?:dbo\.)?(\w+)', sql_clean, flags=re.IGNORECASE)
    
    bad = []
    for tbl in found:
        tbl_norm = tbl.lower()
        if tbl_norm not in ALLOWED_TABLES:
            bad.append(tbl)
    
    return (len(bad) == 0), bad

def validate_sql(sql: str) -> Tuple[bool, str]:
    """
    Validate SQL. Returns (ok, message). Message is empty when ok, otherwise explains why invalid.
    """
    if not SELECT_ONLY_RE.search(sql):
        return False, "Only SELECT queries are allowed."
    
    forbidden, patt = contains_forbidden(sql)
    if forbidden:
        return False, f"Forbidden pattern detected: {patt}"
    
    ok_tables, bad = uses_only_allowed_tables(sql)
    if not ok_tables:
        return False, f"Query references non-allowed tables: {', '.join(bad)}"
    
    return True, ""

if __name__ == "__main__":
    test_queries = [
        "SELECT * FROM dbo.wp_package;",
        "SELECT * FROM wp_package;",
        "SELECT name FROM orders WHERE id=1; DROP TABLE users;",
        "UPDATE users SET name='hacker' WHERE id=1;",
        "SELECT * FROM dbo.wp_package p JOIN dbo.wp_instance i ON p.package_id = i.package_id;",
        "SELECT * FROM unknown_table;",
    ]
    for q in test_queries:
        ok, msg = validate_sql(q)
        print(f"Query: {q[:60]}...\nValid: {ok}, Message: {msg}\n")