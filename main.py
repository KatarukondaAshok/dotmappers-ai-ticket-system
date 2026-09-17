"""
main.py
-------
FastAPI entrypoint for the DOTMappers AI Engineer assessment.

Run with:  uvicorn main:app --reload
Docs at:   http://127.0.0.1:8000/docs
"""

from __future__ import annotations

import os
import sqlite3
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

load_dotenv()

from app.anomaly_detector import run_anomaly_detection  # noqa: E402
from app.data_loader import TABLE_NAME, build_sqlite_connection  # noqa: E402
from app.llm_engine import GROQ_API_KEY, GROQ_MODEL, answer_nl_question  # noqa: E402
from app.models import HealthResponse, QueryRequest, QueryResponse  # noqa: E402

DATA_PATH = Path(__file__).resolve().parent / "data" / "support_tickets.csv"

app = FastAPI(
    title="AI-Powered Support Ticket System",
    description="NL querying + anomaly detection over customer support tickets.",
    version="1.0.0",
)

# Permissive CORS so the Streamlit UI (a separate process/port) can call this API.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

_connection: sqlite3.Connection | None = None


def get_connection() -> sqlite3.Connection:
    """Lazily build (and cache) the in-memory SQLite connection.

    Lazy + cached rather than a global built at import time so that a bad
    CSV path fails inside a request (clean 500 with a message) instead of
    crashing the whole process at import.
    """
    global _connection
    if _connection is None:
        if not DATA_PATH.exists():
            raise HTTPException(status_code=500, detail=f"Dataset not found at {DATA_PATH}")
        _connection = build_sqlite_connection(DATA_PATH)
    return _connection


@app.get("/health", response_model=HealthResponse, tags=["System"])
def health() -> HealthResponse:
    conn = get_connection()
    count = conn.execute(f"SELECT COUNT(*) FROM {TABLE_NAME}").fetchone()[0]
    return HealthResponse(
        status="ok",
        rows_loaded=count,
        llm_configured=bool(GROQ_API_KEY),
        model=GROQ_MODEL,
    )


@app.post("/query", response_model=QueryResponse, tags=["Querying"])
def query(request: QueryRequest) -> QueryResponse:
    """Answer a natural-language question about the ticket data.

    Pipeline: question -> LLM generates SQL -> SQL executes read-only against
    SQLite -> LLM phrases the result in plain English. See app/llm_engine.py
    for the full design rationale.
    """
    conn = get_connection()
    result = answer_nl_question(conn, request.question)
    return QueryResponse(**result.__dict__)


@app.get("/anomalies", tags=["Anomaly Detection"])
def anomalies() -> dict:
    """Statistically-derived anomaly report (not LLM-based — see
    app/anomaly_detector.py for why)."""
    conn = get_connection()
    return run_anomaly_detection(conn).as_dict()


@app.get("/tickets", tags=["System"])  # bonus: raw filtered browsing, not required by the brief
def list_tickets(status: str | None = None, priority: str | None = None, limit: int = 50) -> dict:
    conn = get_connection()
    sql = f"SELECT * FROM {TABLE_NAME} WHERE 1=1"
    params: list[str] = []
    if status:
        sql += " AND status = ?"
        params.append(status)
    if priority:
        sql += " AND priority = ?"
        params.append(priority)
    sql += " LIMIT ?"
    params.append(min(limit, 500))
    cur = conn.execute(sql, params)
    cols = [c[0] for c in cur.description]
    rows = [dict(zip(cols, r)) for r in cur.fetchall()]
    return {"count": len(rows), "tickets": rows}


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("main:app", host="0.0.0.0", port=int(os.getenv("PORT", 8000)), reload=True)
