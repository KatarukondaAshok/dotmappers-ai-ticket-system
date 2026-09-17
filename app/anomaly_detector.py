"""
anomaly_detector.py
--------------------
Two independent, explainable anomaly rules (deliberately NOT LLM-based —
anomaly detection over numeric/time data is a job for statistics, not for
an LLM to eyeball; the LLM's job in this system is natural language, not
number crunching):

1. Long resolution-time outliers
   Per category, flag resolved tickets whose resolution_time_hrs sits above
   Q3 + 1.5 * IQR (the standard Tukey fence). Using an IQR per-category
   fence (instead of one global cutoff) matters because categories behave
   differently — a 20-hour Billing ticket is unusual, a 20-hour Technical
   ticket may not be.

2. Stale high-priority tickets
   Flag tickets that are still Open/Escalated, are High/Critical priority,
   and were created more than 24 hours ago (relative to the most recent
   timestamp in the dataset, so the rule is stable no matter when you run
   it against this static CSV).
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass, field

import pandas as pd

from app.data_loader import TABLE_NAME

STALE_HOURS_THRESHOLD = 24
IQR_MULTIPLIER = 1.5


@dataclass
class AnomalyReport:
    long_resolution_outliers: list[dict] = field(default_factory=list)
    stale_high_priority: list[dict] = field(default_factory=list)

    def as_dict(self) -> dict:
        return {
            "long_resolution_outliers": {
                "description": (
                    "Resolved tickets whose resolution time is an outlier "
                    "(> Q3 + 1.5*IQR) relative to other tickets in the same category."
                ),
                "count": len(self.long_resolution_outliers),
                "tickets": self.long_resolution_outliers,
            },
            "stale_high_priority": {
                "description": (
                    f"High/Critical priority tickets still Open or Escalated "
                    f"more than {STALE_HOURS_THRESHOLD}h after creation."
                ),
                "count": len(self.stale_high_priority),
                "tickets": self.stale_high_priority,
            },
        }


def _detect_long_resolution_outliers(df: pd.DataFrame) -> list[dict]:
    resolved = df[df["resolution_time_hrs"].notna()].copy()
    flagged_frames = []

    for _category, group in resolved.groupby("category"):
        if len(group) < 4:  # not enough points for a meaningful IQR
            continue
        q1 = group["resolution_time_hrs"].quantile(0.25)
        q3 = group["resolution_time_hrs"].quantile(0.75)
        iqr = q3 - q1
        upper_fence = q3 + IQR_MULTIPLIER * iqr
        outliers = group[group["resolution_time_hrs"] > upper_fence].copy()
        outliers["category_upper_fence_hrs"] = round(upper_fence, 2)
        flagged_frames.append(outliers)

    if not flagged_frames:
        return []

    flagged = pd.concat(flagged_frames).sort_values("resolution_time_hrs", ascending=False)
    cols = [
        "ticket_id", "category", "priority", "status",
        "resolution_time_hrs", "category_upper_fence_hrs", "agent_id", "issue_summary",
    ]
    return flagged[cols].to_dict(orient="records")


def _detect_stale_high_priority(df: pd.DataFrame) -> list[dict]:
    reference_time = df["created_at"].max()
    age_hours = (reference_time - df["created_at"]).dt.total_seconds() / 3600

    mask = (
        df["status"].isin(["Open", "Escalated"])
        & df["priority"].isin(["High", "Critical"])
        & (age_hours > STALE_HOURS_THRESHOLD)
    )
    stale = df[mask].copy()
    stale["age_hours"] = age_hours[mask].round(1)
    stale = stale.sort_values("age_hours", ascending=False)

    cols = ["ticket_id", "category", "priority", "status", "age_hours", "agent_id", "issue_summary"]
    return stale[cols].to_dict(orient="records")


def run_anomaly_detection(conn: sqlite3.Connection) -> AnomalyReport:
    df = pd.read_sql(f"SELECT * FROM {TABLE_NAME}", conn, parse_dates=["created_at"])
    return AnomalyReport(
        long_resolution_outliers=_detect_long_resolution_outliers(df),
        stale_high_priority=_detect_stale_high_priority(df),
    )
