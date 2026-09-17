<div align="center">

# 🎫 AI-Powered Support Ticket System

**End-to-End AI System Sprint — DOTMappers IT Pvt. Ltd. AI Engineer Assessment**

Natural-language querying · Statistical anomaly detection · REST API · Web UI

[![Python](https://img.shields.io/badge/Python-3.11+-3776AB?logo=python&logoColor=white)](https://www.python.org/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.115-009688?logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com/)
[![Streamlit](https://img.shields.io/badge/Streamlit-1.38-FF4B4B?logo=streamlit&logoColor=white)](https://streamlit.io/)
[![Groq](https://img.shields.io/badge/LLM-Groq%20%7C%20gpt--oss--120b-F55036)](https://groq.com/)
[![Tests](https://img.shields.io/badge/tests-8%20passing-brightgreen)](#-running-tests)
[![Docker](https://img.shields.io/badge/Docker-ready-2496ED?logo=docker&logoColor=white)](#option-b--docker-compose)

</div>

---

## 📌 Overview

This system turns a static customer-support ticket CSV into an interactive AI application. It can:

- 📂 **Ingest** the CSV into a queryable, in-memory SQLite database
- 💬 **Answer questions in plain English** — an LLM converts the question to SQL, SQLite computes the exact answer, and a second LLM call phrases the result for a human
- 🚨 **Detect anomalies** — long resolution-time outliers and stale high-priority tickets, using deterministic statistics (no LLM involved)
- 🌐 **Expose everything** through a REST API **and** a Streamlit UI
- 🛡️ **Validate all generated SQL** before execution (read-only, single-statement only)
- 🧪 **Run offline** — 8 automated tests, and a zero-key fallback demo mode

The architecture deliberately separates *language understanding* (the LLM's job), *exact computation* (SQLite's job), and *statistical anomaly detection* (pandas' job) — rather than asking one LLM call to do everything.

| Brief requirement | Where it's implemented |
|---|---|
| Ingest CSV → make it queryable | [`app/data_loader.py`](app/data_loader.py) |
| Answer NL questions | [`app/llm_engine.py`](app/llm_engine.py) |
| Detect & flag anomalies | [`app/anomaly_detector.py`](app/anomaly_detector.py) |
| REST API **and** UI (both required) | [`main.py`](main.py) + [`ui/streamlit_app.py`](ui/streamlit_app.py) |
| Zero-cost, single-command start | Groq free tier + `./start.sh` / `docker-compose up` |

---

## 📋 Table of contents

- [Quick start](#-quick-start)
- [Tech stack](#-tech-stack)
- [Architecture](#-architecture)
- [Design rationale](#-design-rationale)
- [API reference](#-api-reference)
- [Example queries & outputs](#-example-queries--outputs)
- [Streamlit UI](#-streamlit-ui)
- [Running tests](#-running-tests)
- [Troubleshooting](#-troubleshooting)
- [Known limitations](#-known-limitations)
- [What I'd improve with more time](#-what-id-improve-with-more-time)
- [How this maps to the evaluation criteria](#-how-this-maps-to-the-evaluation-criteria)
- [Project structure](#-project-structure)

---

## 🚀 Quick start

### Prerequisites
- Python 3.11+
- A free [Groq API key](https://console.groq.com/keys) (optional — see fallback mode below)

### Option A — single command, no Docker

```bash
git clone https://github.com/KatarukondaAshok/dotmappers-ai-ticket-system.git
cd dotmappers-ai-ticket-system
pip install -r requirements.txt
cp .env.example .env          # then paste your free Groq key into .env
./start.sh                    # starts API on :8000 and UI on :8501
```

### Option B — Docker Compose

```bash
cp .env.example .env          # add your Groq key first
docker-compose up
```

| Service | URL |
|---|---|
| 🔌 API + interactive docs | http://localhost:8000/docs |
| 🖥️ Web UI | http://localhost:8501 |

> **No Groq key yet?** The app still runs at **zero setup, zero cost** — it falls back to a small keyword-matched demo mode covering the five sample questions from the assessment brief, so you can verify the API, data loading, and anomaly detection immediately. Full natural-language coverage of *any* question needs the free key above.

---

## 🧰 Tech stack

| Layer | Technology | Why |
|---|---|---|
| **LLM** | Groq — [`openai/gpt-oss-120b`](https://console.groq.com/docs/model/openai/gpt-oss-120b) | Free tier, fast inference (each query is *two* LLM calls), explicitly allowed by the brief. Groq's own recommended successor to `llama-3.3-70b-versatile`, decommissioned 16 Aug 2026 — configurable via `GROQ_MODEL` in `.env`, no code change needed to swap models |
| **Query surface** | SQLite (in-memory) | Gives the LLM a stable, standard target (SQL) instead of a custom DSL; zero DB server to install |
| **API** | FastAPI | Async-ready, auto-generated OpenAPI docs at `/docs`, Pydantic validation for free |
| **UI** | Streamlit | Fast to build for a 48-hour sprint; kept as a thin client over the API so both stay in sync |
| **Data processing** | pandas | CSV parsing/type coercion + all anomaly-detection math |
| **Testing** | pytest | 8 offline-safe tests |
| **Deployment** | Docker / Docker Compose | Reproducible, single-command startup |

---

## 🏗️ Architecture

```
                     ┌──────────────────────┐
                     │ support_tickets.csv   │
                     └──────────┬───────────┘
                                │  load_csv() + type coercion
                                ▼
                     ┌──────────────────────┐
                     │  SQLite (in-memory)   │  ← app/data_loader.py
                     │  table: tickets        │
                     └───┬───────────────┬───┘
                         │               │
           ┌─────────────┘               └─────────────┐
           ▼                                            ▼
┌────────────────────────┐               ┌───────────────────────────────┐
│ app/anomaly_detector.py │               │ app/llm_engine.py              │
│ • IQR outliers/category │               │ 1. NL question → LLM → SQL     │
│ • stale High/Critical   │               │ 2. SQL runs read-only vs SQLite│
│   tickets (>24h)        │               │ 3. Result rows → LLM → plain-  │
│ pure pandas — no LLM    │               │    English answer              │
│                          │              │ (→ app/fallback.py if no key)  │
└───────────┬─────────────┘               └────────────────┬───────────────┘
            │                                               │
            └───────────────────┬───────────────────────────┘
                                 ▼
                     ┌──────────────────────┐
                     │   FastAPI (main.py)   │
                     │  /health  /query       │
                     │  /anomalies  /tickets  │
                     └──────────┬───────────┘
                                │  HTTP
                                ▼
                     ┌──────────────────────┐
                     │ Streamlit UI           │
                     │ (ui/streamlit_app.py)  │
                     └──────────────────────┘
```

**Query flow, step by step:**

```
User question
   → LLM generates SQL (schema-aware, SELECT-only)
   → SQL validated (blocks writes, chained statements)
   → SQLite executes it (exact computation)
   → LLM turns the result rows into a plain-English answer
   → returned with the SQL attached, for full transparency
```

---

## 🧠 Design rationale

### Why text-to-SQL, not "hand the LLM the raw CSV"?

Feeding 500 rows into a prompt and asking the model to eyeball a count or average is unreliable — LLMs are not good at exact arithmetic over tabular data. Converting the question into SQL instead means:

- **Counting/averaging is done by SQLite** — always exact, never approximated.
- The **generated SQL is inspectable** in both the API response and the UI's "Show generated SQL" expander — useful for debugging and for the architecture walkthrough.
- It **scales** to far more than 500 rows without touching the design.

### Why a second LLM call to phrase the answer?

The first call's output is structured data (`3.42`), not a sentence a support-ops person wants to read (*"the average rating is 3.42 out of 5"*). The second, cheap call turns rows into a direct answer, and is explicitly told to lead with the number and state plainly when a result is empty rather than guess.

### Why is anomaly detection NOT LLM-based?

Outlier detection over numeric/time columns is a **statistics problem**. A quantile-based IQR fence and an age calculation are exact, deterministic, and free — no reason to spend an LLM call (or introduce LLM unreliability) on something pandas already does reliably.

| Rule | Logic |
|---|---|
| **Long resolution-time outliers** | Per `category`, resolved tickets with `resolution_time_hrs > Q3 + 1.5×IQR` (Tukey fence) — computed *per category* because "long" means something different for Billing vs. Technical |
| **Stale high-priority tickets** | Status `Open`/`Escalated` **and** priority `High`/`Critical` **and** created >24h before the dataset's latest timestamp (used as "now" so the rule is stable against a static historical CSV) |

### Safety: SQL-injection / prompt-injection guardrails

Every generated query is validated before execution (`app/llm_engine.py::_validate_sql`):

- ✅ Must start with `SELECT`
- 🚫 Blocks `INSERT / UPDATE / DELETE / DROP / ALTER / ATTACH / CREATE / PRAGMA / ...`
- 🚫 Must be a single statement — no `;`-chained second statement

This also stops a ticket's free-text `issue_summary` (untrusted content flowing into the LLM's context via query results) from being usable as a prompt-injection vector to make a *later* query mutate data.

---

## 🔌 API reference

| Method | Endpoint | Purpose |
|---|---|---|
| `GET` | `/health` | Rows loaded, whether an LLM key is configured, active model name |
| `POST` | `/query` | `{"question": "..."}` → generated SQL + result rows + natural-language answer |
| `GET` | `/anomalies` | Full anomaly report (both rule types) |
| `GET` | `/tickets` | Bonus — filter/browse raw tickets by `status` / `priority` |

Interactive, try-it-out docs live at **`/docs`** once the API is running.

<details>
<summary><b>curl examples</b></summary>

```bash
curl http://localhost:8000/health

curl -X POST http://localhost:8000/query \
  -H "Content-Type: application/json" \
  -d '{"question": "How many tickets are currently open?"}'

curl http://localhost:8000/anomalies

curl "http://localhost:8000/tickets?status=Open&priority=Critical&limit=10"
```
</details>

---

## 💬 Example queries & outputs

> Every figure below is from a **live run** against `data/support_tickets.csv` — reproducible via `pytest` or by hitting the endpoints yourself.

**Q: "How many tickets are currently open?"**
```json
{
  "sql": "SELECT COUNT(*) AS open_tickets FROM tickets WHERE status = 'Open'",
  "rows": [{ "open_tickets": 111 }],
  "answer": "There are 111 tickets currently open."
}
```

**Q: "Which agent resolved the most tickets?"**
```json
{
  "sql": "SELECT agent_id, COUNT(*) AS resolved_count FROM tickets WHERE status = 'Resolved' GROUP BY agent_id ORDER BY resolved_count DESC LIMIT 1",
  "answer": "AGT-12 resolved the most tickets, with 37 resolutions."
}
```

**Q: "What is the average customer rating for Technical category tickets?"**
```json
{
  "sql": "SELECT AVG(customer_rating) AS avg_rating FROM tickets WHERE category = 'Technical' AND customer_rating IS NOT NULL",
  "answer": "The average customer rating for Technical tickets is 3.74."
}
```

**`GET /anomalies` (excerpt)**
```json
{
  "long_resolution_outliers": {
    "count": 22,
    "tickets": [
      { "ticket_id": "TKT-108", "category": "General", "resolution_time_hrs": 119.7,
        "category_upper_fence_hrs": 48.65, "agent_id": "AGT-07" }
    ]
  },
  "stale_high_priority": {
    "count": 80,
    "tickets": [
      { "ticket_id": "TKT-233", "category": "Billing", "priority": "High",
        "status": "Open", "age_hours": 2118.6, "agent_id": "AGT-08" }
    ]
  }
}
```

---

## 🖥️ Streamlit UI

Three tabs, each a thin client over the API above:

| Tab | What it does |
|---|---|
| 💬 **Ask a question** | Type or pick a sample question; view the generated SQL, result table, and AI-phrased answer |
| 🚨 **Anomalies** | Run a live scan; browse both flagged sets in sortable tables |
| 📊 **Explore data** | Filter/browse raw tickets by status and priority |

---

## ✅ Running tests

```bash
pytest -v
```

All **8 tests** run fully offline (no Groq key required):

```
tests/test_basic.py::test_csv_loads_expected_row_count PASSED
tests/test_basic.py::test_csv_has_no_unexpected_nulls_in_required_columns PASSED
tests/test_basic.py::test_sqlite_table_row_count_matches_csv PASSED
tests/test_basic.py::test_anomaly_detection_returns_both_rule_types PASSED
tests/test_basic.py::test_health_endpoint PASSED
tests/test_basic.py::test_anomalies_endpoint PASSED
tests/test_basic.py::test_query_endpoint_falls_back_gracefully_without_key PASSED
tests/test_basic.py::test_tickets_endpoint_filters PASSED

======================== 8 passed ========================
```

---

## 🛠️ Troubleshooting

| Symptom | Fix |
|---|---|
| `model_not_found` / `404` from `/query` | `GROQ_MODEL` in `.env` no longer exists on Groq. Set it to `openai/gpt-oss-120b` (current default) or check Groq's [deprecations page](https://console.groq.com/docs/deprecations) |
| `llm_configured: false` on `/health` | `.env` is missing or `GROQ_API_KEY` is blank — confirm you copied `.env.example` → **`.env`** (not left it as `.env.example`), then restart the process |
| `streamlit: File does not exist: ui/streamlit_app.py` | You're inside the `ui/` folder. Either `cd ..` to the project root first, or run `streamlit run streamlit_app.py` from within `ui/` |
| A `venv`/`Lib/site-packages` folder shows up in `git status` | Your virtual environment was created *inside* the project folder. Add its name to `.gitignore` and run `git rm -r --cached <venv-folder>` to un-track it |

---

## ⚠️ Known limitations

- **Text-to-SQL is not 100% reliable.** Ambiguous or multi-hop questions can produce SQL that runs but doesn't answer what was meant. The SQL is always shown, so this is easy to catch — there's no automatic "does this SQL answer the question" verification step yet.
- **In-memory SQLite rebuilds from the CSV on every start.** Fine for this static dataset; a live-ticket system would need a persistent database and incremental ingestion instead.
- **Fallback mode only covers 5 canned questions** — a zero-setup smoke test, not a substitute for the LLM path.
- **No conversation memory** — each `/query` call is independent; no follow-up-question handling.
- **Anomaly thresholds are fixed** (`1.5× IQR`, `24h` staleness) rather than configurable per deployment.

## 🔮 What I'd improve with more time

- LLM-based sanity check on generated SQL before execution, to catch text-to-SQL misses automatically.
- Persist to an on-disk/managed database with incremental ingestion, for live ticket data.
- Cache repeated questions (same question → same SQL) to cut LLM calls and latency.
- API authentication before exposing beyond local/demo use.
- Multi-turn conversation support so follow-ups can reference the previous answer.

---

## 🎯 How this maps to the evaluation criteria

| Criterion (assessment weight) | How it's addressed |
|---|---|
| **Functionality — 30%** | All 4 brief requirements implemented and tested: CSV ingestion, NL querying, anomaly detection, REST API + UI |
| **Architecture & Design — 25%** | Deliberate separation of LLM (language), SQLite (computation), pandas (statistics) — see [Design rationale](#-design-rationale) for the reasoning behind every major choice |
| **Code Quality — 20%** | Modular `app/` package, Pydantic-validated schemas, 8 automated tests, docstrings explaining *why* not just *what* |
| **LLM Integration Quality — 15%** | Two-step text-to-SQL pipeline, schema-aware prompting, SQL validation/guardrails, graceful fallback mode |
| **README & Documentation — 10%** | This file — setup, architecture, model choice, example outputs, limitations, all in one place |

---

## 📁 Project structure

```
.
├── app/
│   ├── data_loader.py       # CSV → SQLite ingestion
│   ├── llm_engine.py        # NL → SQL → NL pipeline (Groq)
│   ├── fallback.py          # keyword fallback when no API key is set
│   ├── anomaly_detector.py  # IQR + staleness anomaly rules
│   └── models.py            # Pydantic request/response schemas
├── ui/
│   └── streamlit_app.py     # 3-tab UI: Ask / Anomalies / Explore
├── data/
│   └── support_tickets.csv
├── tests/
│   └── test_basic.py        # offline-safe tests, 8 cases
├── main.py                  # FastAPI app (4 endpoints)
├── requirements.txt
├── Dockerfile
├── docker-compose.yml
├── start.sh                 # single-command startup, no Docker
├── .env.example
└── README.md
```

---

<div align="center">

Built for the **DOTMappers IT Pvt. Ltd.** AI Engineer technical assessment.

**Ashok Katarukonda** · [GitHub](https://github.com/KatarukondaAshok) · [LinkedIn](https://linkedin.com/in/ashok-katarukonda)

</div>
