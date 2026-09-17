from __future__ import annotations

from pydantic import BaseModel, Field


class QueryRequest(BaseModel):
    question: str = Field(..., min_length=3, examples=["How many tickets are currently open?"])


class QueryResponse(BaseModel):
    question: str
    sql: str
    row_count: int
    rows: list[dict]
    answer: str
    mode: str  # "llm" | "fallback" | "error"


class HealthResponse(BaseModel):
    status: str
    rows_loaded: int
    llm_configured: bool
    model: str
