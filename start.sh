#!/usr/bin/env bash
# Starts the API and UI together with a single command, no Docker required.
# Usage: ./start.sh
set -e

echo "Starting FastAPI backend on :8000 ..."
uvicorn main:app --host 0.0.0.0 --port 8000 &
API_PID=$!

# Give the API a moment to boot before the UI's first health check.
sleep 2

echo "Starting Streamlit UI on :8501 ..."
streamlit run ui/streamlit_app.py --server.address 0.0.0.0 --server.port 8501 &
UI_PID=$!

trap "echo 'Stopping...'; kill $API_PID $UI_PID" EXIT INT TERM
wait
