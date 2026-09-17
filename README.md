# AI-Powered Support Ticket System

**DOTMappers IT Pvt. Ltd. — AI Engineer Technical Assessment (End-to-End AI System Sprint)**

An AI system that ingests a customer support ticket CSV, answers natural-language
questions about it, detects anomalies, and exposes everything through both a
REST API and a minimal UI.

---

## 1. What this system does

| Requirement (from the brief) | Implementation |
|---|---|
| Ingest CSV and make it queryable | `app/data_loader.py` loads `data/support_tickets.csv` into an in-memory SQLite table (`tickets`) at startup |
| Answer NL questions | `app/llm_engine.py` — LLM converts the question to SQL, SQL runs against SQLite, LLM phrases the result in plain English |
| Detect & flag anomalies | `app/anomaly_detector.py` — two independent statistical rules (see §4) |
| REST API **and** UI (both built) | `main.py` (FastAPI, 4 endpoints) + `ui/streamlit_app.py` (Streamlit, 3 tabs) |

---

## 2. Quick start

### Option A — one command, no Docker
```bash
git clone <this-repo>
cd dotmappers-ai-ticket-system
pip install -r requirements.txt
cp .env.example .env          # then paste a free Groq key into .env (see §3)
./start.sh                    # starts API on :8000 and UI on :8501
```

### Option B — Docker Compose (also a single command)
```bash
cp .env.example .env          # add your Groq key first
docker-compose up
```
- API: http://localhost:8000/docs (interactive Swagger UI)
- UI: http://localhost:8501

The system also runs with **zero setup and zero cost** even without a Groq key —
it boots into a small fallback mode that recognises the five sample questions
from the assessment brief, so the evaluator can smoke-test the plumbing (API up,
data loaded, anomalies working) in seconds. Full natural-language coverage of
*any* question requires the free key below.

### Running tests
```bash
pytest -v
```
All 8 tests run offline (no API key needed) and cover data loading, anomaly
rules, and every endpoint including the fallback path.

---

## 3. Model / tools used

| Component | Choice | Why |
|---|---|---|
| LLM | **Groq — Llama 3.3 70B Versatile** (`llama-3.3-70b-versatile`) | Free tier, no card required, fast inference (important for a text-to-SQL round-trip + summarisation round-trip per query), explicitly allowed by the brief |
| Query surface | **SQLite** (in-memory, loaded fresh from the CSV each run) | Gives the LLM a stable, well-known target (SQL) instead of inventing a custom query DSL; zero external DB service to install |
| API | **FastAPI** | Async-ready, automatic OpenAPI docs at `/docs`, Pydantic validation for free |
| UI | **Streamlit** | Fastest way to a usable UI for a 48-hour sprint; kept as a thin client over the API so the two never drift out of sync |
| Data | **pandas** | CSV parsing/type coercion before loading into SQLite |

Get a free Groq key: https://console.groq.com/keys → paste it into `.env` as `GROQ_API_KEY`.

---

## 4. Architecture

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
│ - IQR outliers per      │               │ 1. NL question → LLM → SQL     │
│   category (resolution  │               │ 2. SQL runs read-only vs SQLite│
│   time)                 │               │ 3. Result rows → LLM → plain-  │
│ - stale High/Critical   │               │    English answer              │
│   tickets (>24h)        │               │ (falls back to app/fallback.py │
│ pure pandas, no LLM     │               │  if no GROQ_API_KEY is set)    │
└───────────┬─────────────┘               └────────────────┬───────────────┘
            │                                               │
            └───────────────────┬───────────────────────────┘
                                 ▼
                     ┌──────────────────────┐
                     │   FastAPI (main.py)   │
                     │  /health  /query       │
                     │  /anomalies  /tickets  │
                     └──────────┬───────────┘
                                │  HTTP (requests)
                                ▼
                     ┌──────────────────────┐
                     │ Streamlit UI           │
                     │ (ui/streamlit_app.py)  │
                     └──────────────────────┘
```

### Why text-to-SQL, not "let the LLM read the CSV and answer directly"?
Feeding 500 rows into a prompt and asking the LLM to eyeball an average or a
count is unreliable — LLMs are not good at exact arithmetic over tabular data,
and it wastes context on every single query. Converting the question into SQL
instead means:
- The **counting/averaging is done by SQLite**, which is always exact.
- The generated **SQL is inspectable** (shown in both the API response and the
  UI's "Show generated SQL" expander) — useful for debugging a wrong answer
  and for the architecture walkthrough.
- It scales to a dataset far larger than 500 rows without touching the design.

### Why a second LLM call to phrase the answer?
The first call's output (SQL result rows) is structured data, not a sentence a
support-ops person would actually want to read (e.g. "3.42" instead of "the
average rating is 3.42 out of 5"). A second, cheap call turns the raw rows
into a direct, human answer, and is told explicitly to lead with the number
and to say plainly when a result is empty rather than guess.

### Why is anomaly detection NOT LLM-based?
Outlier detection over numeric/time columns is a statistics problem, not a
language problem — pandas' quantile-based IQR fence and a straightforward age
calculation are exact, deterministic, and don't burn LLM calls (or introduce
LLM unreliability) for something a few lines of pandas does reliably. The two
rules implemented:

1. **Long resolution-time outliers** — for each `category`, resolved tickets
   with `resolution_time_hrs > Q3 + 1.5×IQR` (the standard Tukey fence),
   computed *per category* because "long" means something different for
   Billing vs. Technical tickets.
2. **Stale high-priority tickets** — status `Open`/`Escalated`, priority
   `High`/`Critical`, and created more than 24 hours before the latest
   timestamp in the dataset (used as "now" so the rule is stable against a
   static historical CSV, rather than comparing to the wall-clock date you
   happen to run it on).

### SQL-injection / prompt-injection guardrails
The generated SQL is validated before execution (`app/llm_engine.py::_validate_sql`):
it must start with `SELECT`, must not contain `INSERT/UPDATE/DELETE/DROP/ALTER/
ATTACH/CREATE/PRAGMA/...`, and must be a single statement (no `;`-chained
second statement). This also blocks a ticket's free-text `issue_summary`
(untrusted user-authored content that flows into the LLM's context via query
results) from being used as a prompt-injection vector to make the *next*
query mutate data.

---

## 5. API reference

| Method | Endpoint | Purpose |
|---|---|---|
| `GET` | `/health` | Rows loaded, whether an LLM key is configured, model name |
| `POST` | `/query` | `{"question": "..."}` → SQL + result rows + natural-language answer |
| `GET` | `/anomalies` | Full anomaly report (both rule types) |
| `GET` | `/tickets` | Bonus: filter/browse raw tickets by `status`/`priority` |

Full interactive docs (try-it-out) at `/docs` once the API is running.

---

## 6. Example queries with outputs

**Q: "How many tickets are currently open?"**
```json
{
  "sql": "SELECT COUNT(*) AS open_tickets FROM tickets WHERE status = 'Open'",
  "rows": [{"open_tickets": 111}],
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

**`GET /anomalies` (excerpt)**
```json
{
  "long_resolution_outliers": {
    "count": 22,
    "tickets": [
      {"ticket_id": "TKT-108", "category": "General", "resolution_time_hrs": 119.7,
       "category_upper_fence_hrs": 48.65, "agent_id": "AGT-07"}
    ]
  },
  "stale_high_priority": {
    "count": 80,
    "tickets": [
      {"ticket_id": "TKT-233", "category": "Billing", "priority": "High",
       "status": "Open", "age_hours": 2118.6, "agent_id": "AGT-08"}
    ]
  }
}
```
(Exact counts above are from a live run against `data/support_tickets.csv`
with `pytest`/`TestClient` — reproducible by running the test suite or hitting
`/anomalies` yourself.)

---

## 7. Known limitations

- **Text-to-SQL is not 100% reliable.** Very ambiguous or multi-hop questions
  (e.g. comparisons requiring a self-join, or vague date ranges) can produce
  SQL that runs but doesn't answer what was meant. The generated SQL is always
  shown so this is easy to catch, but there's no automatic "does this SQL
  actually answer the question" verification step in this version.
- **In-memory SQLite is rebuilt from the CSV on every process start** — this
  is intentional for a static assessment dataset (keeps the "single command"
  requirement simple) but means it is not the right pattern for a system with
  live, continuously-updated tickets; that would call for a persistent
  database and an ingestion job instead of a full reload.
- **Fallback mode only covers 5 canned questions.** It exists purely so the
  app is demoable at zero setup; it is not a substitute for the LLM path and
  makes no attempt at broader NL coverage.
- **No conversation memory.** Each `/query` call is independent — there's no
  follow-up-question handling ("what about last week?" referring to a prior
  answer).
- **Anomaly thresholds are fixed** (`1.5× IQR`, `24h` staleness) rather than
  configurable per deployment; reasonable defaults for this dataset, but a
  production version would expose them as parameters.

## 8. What I'd improve with more time
- A lightweight LLM-based sanity check on the generated SQL before execution
  (e.g. "does this SQL plausibly answer the question?") to catch text-to-SQL
  misses automatically instead of relying on the user to notice.
- Persist to an on-disk/managed database and add an incremental ingestion
  endpoint instead of a full CSV reload, for a system with live ticket data.
- Cache repeated questions (same question → same SQL) to cut LLM calls.
- Add authentication on the API before exposing it beyond local/demo use.

---

## 9. Project structure
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
└── .env.example
```
#   d o t m a p p e r s - a i - t i c k e t - s y s t e m  
 