#!/usr/bin/env python3
# extract_schema.py -- simple schema dumper (no backups), cursor-based sampling (no pandas.read_sql)

import os
import sys
# ensure config.py fallback and packages folder are importable if needed
BASE = os.path.dirname(__file__)
sys.path.insert(0, BASE)
sys.path.insert(0, os.path.join(BASE, "packages"))

import json
import pyodbc
from collections import defaultdict

try:
    import config  # optional
except Exception:
    config = None

# ---- Allowed tables ----
TABLE_ALLOWLIST = [
    "comp_link_table",
    "wp_package",
    "p_maone_forms_v1",
    "wp_template_config",
    "portal_user",
    "wp_instance",
    "wp_workitem",
    "wp_participant",
    "wp_transition",
    "wp_workitem_history",
    "wp_participant_history",
    "wp_transition_history",
]

# ---- DB connection (env or config.py) ----
DB_SERVER = os.environ.get("DB_SERVER") or (getattr(config, "DB_SERVER", None) if config else None)
DB_USER = os.environ.get("DB_USER") or (getattr(config, "DB_USER", None) if config else None)
DB_PASSWORD = os.environ.get("DB_PASSWORD") or (getattr(config, "DB_PASS", None) if config else None)
DB_NAME = os.environ.get("DB_NAME") or (getattr(config, "DB_NAME", None) if config else None)
ODBC_DRIVER = os.environ.get("ODBC_DRIVER") or (getattr(config, "ODBC_DRIVER", "ODBC Driver 17 for SQL Server") if config else "ODBC Driver 17 for SQL Server")

if not (DB_SERVER and DB_USER and DB_PASSWORD and DB_NAME):
    print("Please set DB_SERVER, DB_USER, DB_PASSWORD, DB_NAME in environment or config.py.")
    sys.exit(1)

# normalize driver to have single braces
drv = ODBC_DRIVER.strip()
if not (drv.startswith("{") and drv.endswith("}")):
    drv = "{" + drv + "}"

conn_str = (
    f"DRIVER={drv};"
    f"SERVER={DB_SERVER};DATABASE={DB_NAME};UID={DB_USER};PWD={DB_PASSWORD};"
    "TrustServerCertificate=yes;"
)

print(f"Connecting to {DB_SERVER}/{DB_NAME} as {DB_USER}...")
conn = pyodbc.connect(conn_str)
cur = conn.cursor()

# ---- Collect schema ----
print("Fetching schema for allowed tables...")
placeholders = ",".join(["?"] * len(TABLE_ALLOWLIST))
cur.execute(f"""
SELECT TABLE_SCHEMA, TABLE_NAME, COLUMN_NAME, DATA_TYPE
FROM INFORMATION_SCHEMA.COLUMNS
WHERE TABLE_NAME IN ({placeholders})
ORDER BY TABLE_SCHEMA, TABLE_NAME, ORDINAL_POSITION
""", TABLE_ALLOWLIST)

tables = defaultdict(list)
for row in cur.fetchall():
    tname = f"{row.TABLE_SCHEMA}.{row.TABLE_NAME}"
    tables[tname].append({
        "column": row.COLUMN_NAME,
        "type": row.DATA_TYPE
    })

# ---- Row counts + samples using cursor (no pandas.read_sql) ----
print("Counting rows and fetching samples (cursor-based)...")
samples = {}
row_counts = {}

def escape_table(t):
    if "." in t:
        schema, table = t.split(".", 1)
    else:
        schema, table = "dbo", t
    return f"[{schema.strip().strip('[]')}].[{table.strip().strip('[]')}]"

for t in list(tables.keys()):
    esc = escape_table(t)
    try:
        # COUNT(*)
        try:
            cur.execute(f"SELECT COUNT(*) FROM {esc}")
            cnt_row = cur.fetchone()
            cnt = cnt_row[0] if cnt_row is not None else 0
        except Exception as e_count:
            print(f"Warning: COUNT(*) failed for {t}: {e_count}")
            row_counts[t] = f"error: {str(e_count)}"
            samples[t] = []
            continue

        row_counts[t] = cnt

        # Fetch TOP 3 sample rows using cursor
        if cnt and int(cnt) > 0:
            try:
                cur.execute(f"SELECT TOP 3 * FROM {esc}")
                cols = [c[0] for c in cur.description] if cur.description else []
                rows = cur.fetchmany(3)
                recs = []
                for r in rows:
                    rec = {}
                    for i, col in enumerate(cols):
                        val = r[i]
                        if hasattr(val, "isoformat"):
                            rec[col] = val.isoformat()
                        else:
                            rec[col] = val
                    recs.append(rec)
                samples[t] = recs
            except Exception as e_sample:
                print(f"Warning: sample fetch failed for {t}: {e_sample}")
                samples[t] = []
        else:
            samples[t] = []
    except Exception as e:
        row_counts[t] = f"error: {str(e)}"
        samples[t] = []
        print(f"Error processing table {t}: {e}")

# ---- Save schema.json and schema.txt inside prompts/ ----
PROMPTS_DIR = os.path.join(BASE, "prompts")
os.makedirs(PROMPTS_DIR, exist_ok=True)

out = {
    "tables": tables,
    "row_counts": row_counts,
    "samples": samples
}
with open(os.path.join(PROMPTS_DIR, "schema.json"), "w", encoding="utf-8") as f:
    json.dump(out, f, indent=2, default=str)

lines = []
for t, cols in tables.items():
    cstr = ", ".join([f"{c['column']}({c['type']})" for c in cols])
    lines.append(f"{t}: {cstr} [rows={row_counts.get(t, '?')}]")
    if t in samples:
        lines.append("  sample: " + json.dumps(samples[t], default=str))

with open(os.path.join(PROMPTS_DIR, "schema.txt"), "w", encoding="utf-8") as f:
    f.write("\n".join(lines))

print("✅ Wrote prompts/schema.json and prompts/schema.txt")

cur.close()
conn.close()
