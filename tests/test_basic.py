"""
tests/test_basic.py
--------------------
Covers the parts of the system that don't require a live LLM call, so these
run offline and free in CI or on the evaluator's machine.

Run with: pytest -v
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest
from fastapi.testclient import TestClient

from app.anomaly_detector import run_anomaly_detection
from app.data_loader import build_sqlite_connection, load_csv
from main import app

DATA_PATH = Path(__file__).resolve().parent.parent / "data" / "support_tickets.csv"


@pytest.fixture(scope="module")
def conn():
    return build_sqlite_connection(DATA_PATH)


@pytest.fixture(scope="module")
def client():
    return TestClient(app)


def test_csv_loads_expected_row_count():
    df = load_csv(DATA_PATH)
    assert len(df) == 500


def test_csv_has_no_unexpected_nulls_in_required_columns():
    df = load_csv(DATA_PATH)
    for col in ["ticket_id", "created_at", "category", "priority", "status"]:
        assert df[col].notna().all(), f"{col} should never be null"


def test_sqlite_table_row_count_matches_csv(conn):
    count = conn.execute("SELECT COUNT(*) FROM tickets").fetchone()[0]
    assert count == 500


def test_anomaly_detection_returns_both_rule_types(conn):
    report = run_anomaly_detection(conn).as_dict()
    assert "long_resolution_outliers" in report
    assert "stale_high_priority" in report
    # Every flagged stale ticket must genuinely be Open/Escalated + High/Critical.
    for t in report["stale_high_priority"]["tickets"]:
        assert t["status"] in {"Open", "Escalated"}
        assert t["priority"] in {"High", "Critical"}
        assert t["age_hours"] > 24


def test_health_endpoint(client):
    resp = client.get("/health")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "ok"
    assert body["rows_loaded"] == 500


def test_anomalies_endpoint(client):
    resp = client.get("/anomalies")
    assert resp.status_code == 200
    assert "long_resolution_outliers" in resp.json()


def test_query_endpoint_falls_back_gracefully_without_key(client):
    # If GROQ_API_KEY isn't set in this test environment, the fallback path
    # must still return a well-formed 200 response, not a 500.
    resp = client.post("/query", json={"question": "How many tickets are currently open?"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["mode"] in {"llm", "fallback"}
    assert "answer" in body


def test_tickets_endpoint_filters(client):
    resp = client.get("/tickets", params={"status": "Open", "limit": 5})
    assert resp.status_code == 200
    body = resp.json()
    assert body["count"] <= 5
    assert all(t["status"] == "Open" for t in body["tickets"])
