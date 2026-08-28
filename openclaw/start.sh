#!/bin/bash

echo "Starting OpenClaw backend (uvicorn) on port 9000..."
uvicorn main:app --host 0.0.0.0 --port 9000 &
UVICORN_PID=$!

echo "Dashboard en http://localhost:9000/dashboard  ·  Panel de campanas en /campaign"

# Restart loop: if uvicorn dies, restart it
while true; do
  wait -n $UVICORN_PID 2>/dev/null
  EXIT_CODE=$?

  if ! kill -0 $UVICORN_PID 2>/dev/null; then
    echo "Uvicorn died (exit $EXIT_CODE), restarting..."
    uvicorn main:app --host 0.0.0.0 --port 9000 &
    UVICORN_PID=$!
  fi

  sleep 2
done