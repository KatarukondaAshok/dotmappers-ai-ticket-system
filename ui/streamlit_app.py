"""
streamlit_app.py
-----------------
Minimal UI on top of the FastAPI backend. Kept as a thin client — all logic
lives in the API, so the UI just calls it and renders the response. This
means the API can be evaluated independently (curl/Postman/docs) and the UI
never drifts out of sync with the "real" system.

Run with: streamlit run ui/streamlit_app.py
Expects the API to already be running (default: http://localhost:8000).
"""

import os

import pandas as pd
import requests
import streamlit as st

API_BASE = os.getenv("API_BASE_URL", "http://localhost:8000")

st.set_page_config(page_title="AI Support Ticket System", page_icon="🎫", layout="wide")
st.title("🎫 AI-Powered Support Ticket System")
st.caption("DOTMappers AI Engineer Assessment — End-to-End AI System Sprint")

# ---- Sidebar: system health -------------------------------------------------
with st.sidebar:
    st.subheader("System status")
    try:
        health = requests.get(f"{API_BASE}/health", timeout=5).json()
        st.success(f"API online — {health['rows_loaded']} tickets loaded")
        if health["llm_configured"]:
            st.info(f"LLM: {health['model']} (Groq)")
        else:
            st.warning(
                "No GROQ_API_KEY set — running in fallback demo mode.\n\n"
                "Add a free key from console.groq.com/keys to .env for full "
                "natural-language querying of any question."
            )
    except requests.exceptions.RequestException:
        st.error(f"Cannot reach API at {API_BASE}. Is `uvicorn main:app` running?")
        st.stop()

tab_query, tab_anomalies, tab_explore = st.tabs(
    ["💬 Ask a question", "🚨 Anomalies", "📊 Explore data"]
)

# ---- Tab 1: NL query ---------------------------------------------------------
with tab_query:
    st.write("Ask anything about the support ticket data in plain English.")
    sample_questions = [
        "How many tickets are currently open?",
        "Which agent resolved the most tickets?",
        "Show me all Critical tickets not resolved within 12 hours.",
        "What is the average customer rating for Technical category tickets?",
        "Which category has the most escalated tickets?",
    ]
    picked = st.selectbox("Try a sample question, or type your own below:", [""] + sample_questions)
    question = st.text_input("Your question", value=picked)

    if st.button("Ask", type="primary") and question.strip():
        with st.spinner("Thinking..."):
            try:
                resp = requests.post(f"{API_BASE}/query", json={"question": question}, timeout=60)
                resp.raise_for_status()
                data = resp.json()
            except requests.exceptions.RequestException as e:
                st.error(f"Request failed: {e}")
                data = None

        if data:
            st.markdown(f"**Answer:** {data['answer']}")
            if data.get("sql"):
                with st.expander("Show generated SQL"):
                    st.code(data["sql"], language="sql")
            if data["rows"]:
                st.dataframe(pd.DataFrame(data["rows"]), use_container_width=True)
            st.caption(f"Mode: {data['mode']} · Rows returned: {data['row_count']}")

# ---- Tab 2: Anomalies --------------------------------------------------------
with tab_anomalies:
    st.write("Statistically-derived anomalies — recomputed live from current data.")
    if st.button("Run anomaly scan"):
        with st.spinner("Scanning..."):
            try:
                resp = requests.get(f"{API_BASE}/anomalies", timeout=30)
                resp.raise_for_status()
                report = resp.json()
            except requests.exceptions.RequestException as e:
                st.error(f"Request failed: {e}")
                report = None

        if report:
            col1, col2 = st.columns(2)
            with col1:
                lro = report["long_resolution_outliers"]
                st.metric("Long-resolution outliers", lro["count"])
                st.caption(lro["description"])
                if lro["tickets"]:
                    st.dataframe(pd.DataFrame(lro["tickets"]), use_container_width=True)
            with col2:
                shp = report["stale_high_priority"]
                st.metric("Stale high-priority tickets", shp["count"])
                st.caption(shp["description"])
                if shp["tickets"]:
                    st.dataframe(pd.DataFrame(shp["tickets"]), use_container_width=True)

# ---- Tab 3: Raw data browser --------------------------------------------------
with tab_explore:
    st.write("Browse and filter the raw ticket data.")
    c1, c2, c3 = st.columns(3)
    status_filter = c1.selectbox("Status", ["(any)", "Open", "Resolved", "Escalated"])
    priority_filter = c2.selectbox("Priority", ["(any)", "Low", "Medium", "High", "Critical"])
    limit = c3.slider("Rows to show", 10, 500, 50)

    params = {"limit": limit}
    if status_filter != "(any)":
        params["status"] = status_filter
    if priority_filter != "(any)":
        params["priority"] = priority_filter

    try:
        resp = requests.get(f"{API_BASE}/tickets", params=params, timeout=15)
        resp.raise_for_status()
        tickets = resp.json()["tickets"]
        st.dataframe(pd.DataFrame(tickets), use_container_width=True)
    except requests.exceptions.RequestException as e:
        st.error(f"Request failed: {e}")
