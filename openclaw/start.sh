#!/bin/bash
set -e

echo "Starting OpenClaw backend (uvicorn) on port 9000..."
uvicorn main:app --host 0.0.0.0 --port 9000 &
UVICORN_PID=$!

echo "Starting Streamlit dashboard on port 8501..."
cd /app/data
streamlit run app.py \
  --server.port=8501 \
  --server.address=0.0.0.0 \
  --server.headless=true \
  --browser.gatherUsageStats=false \
  --theme.base=dark \
  2>&1 &
STREAMLIT_PID=$!

echo "Both services started. Uvicorn PID=$UVICORN_PID, Streamlit PID=$STREAMLIT_PID"

# Wait for either process to exit
wait -n $UVICORN_PID $STREAMLIT_PID
echo "A service exited. Shutting down..."
kill $UVICORN_PID $STREAMLIT_PID 2>/dev/null
