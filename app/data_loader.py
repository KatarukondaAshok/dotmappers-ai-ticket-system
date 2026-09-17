"""
data_loader.py
---------------
Ingests the support_tickets.csv file and loads it into a SQLite database
so it can be queried with plain SQL (either by the anomaly detector or by
SQL generated from a natural-language question).

Why SQLite instead of just pandas?
- Gives the LLM a stable, well-known query surface (SQL) instead of us having
  to invent a custom DSL for "ask a question about a dataframe".
- Keeps ingestion and querying decoupled: swapping the CSV for a real database
  later only means changing this file.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pandas as pd

TABLE_NAME = "tickets"

# Canonical column names used inside the app. The CSV uses either
# response_time_hrs/resolution_time_hrs (per the written spec) or the
# shorter resp_time_hrs/resol_time_hrs (per the schema preview table) —
# we normalise both to the long form so the rest of the app only has to
# know one name.
COLUMN_ALIASES = {
    "resp_time_hrs": "response_time_hrs",
    "resol_time_hrs": "resolution_time_hrs",
}

EXPECTED_COLUMNS = [
    "ticket_id",
    "created_at",
    "category",
    "priority",
    "status",
    "response_time_hrs",
    "resolution_time_hrs",
    "agent_id",
    "customer_rating",
    "issue_summary",
]


def load_csv(csv_path: str | Path) -> pd.DataFrame:
    """Read the CSV, normalise column names/types, return a clean DataFrame."""
    df = pd.read_csv(csv_path)
    df = df.rename(columns=COLUMN_ALIASES)

    missing = set(EXPECTED_COLUMNS) - set(df.columns)
    if missing:
        raise ValueError(f"support_tickets.csv is missing expected columns: {missing}")

    df["created_at"] = pd.to_datetime(df["created_at"], errors="coerce")
    df["response_time_hrs"] = pd.to_numeric(df["response_time_hrs"], errors="coerce")
    df["resolution_time_hrs"] = pd.to_numeric(df["resolution_time_hrs"], errors="coerce")
    df["customer_rating"] = pd.to_numeric(df["customer_rating"], errors="coerce")

    for col in ["category", "priority", "status", "agent_id", "issue_summary", "ticket_id"]:
        df[col] = df[col].astype(str).str.strip()

    return df[EXPECTED_COLUMNS]


def build_sqlite_connection(csv_path: str | Path, db_path: str | Path = ":memory:") -> sqlite3.Connection:
    """Load the CSV and materialise it as a SQLite table.

    Using ':memory:' by default keeps the assessment's "single command start"
    requirement simple — no external DB service needed.
    """
    df = load_csv(csv_path)
    conn = sqlite3.connect(str(db_path), check_same_thread=False)
    df.to_sql(TABLE_NAME, conn, if_exists="replace", index=False)
    conn.execute(f"CREATE INDEX IF NOT EXISTS idx_status ON {TABLE_NAME}(status)")
    conn.execute(f"CREATE INDEX IF NOT EXISTS idx_priority ON {TABLE_NAME}(priority)")
    conn.execute(f"CREATE INDEX IF NOT EXISTS idx_agent ON {TABLE_NAME}(agent_id)")
    conn.commit()
    return conn


SCHEMA_DESCRIPTION = f"""
Table: {TABLE_NAME}
Columns:
  ticket_id            TEXT    -- unique ticket id, e.g. 'TKT-001'
  created_at           TEXT    -- ISO datetime string 'YYYY-MM-DD HH:MM:SS', ticket creation time
  category             TEXT    -- one of: Billing, Technical, General
  priority             TEXT    -- one of: Low, Medium, High, Critical
  status               TEXT    -- one of: Open, Resolved, Escalated
  response_time_hrs    REAL    -- hours from creation to first agent response
  resolution_time_hrs  REAL    -- hours from creation to resolution; NULL if unresolved
  agent_id             TEXT    -- e.g. 'AGT-04'
  customer_rating      REAL    -- 1-5 post-resolution rating; NULL if unresolved
  issue_summary        TEXT    -- free-text description of the issue
"""

if __name__ == "__main__":
    conn = build_sqlite_connection(Path(__file__).resolve().parent.parent / "data" / "support_tickets.csv")
    cur = conn.execute(f"SELECT COUNT(*) FROM {TABLE_NAME}")
    print(f"Loaded {cur.fetchone()[0]} rows into '{TABLE_NAME}'.")
