#!/usr/bin/env bash
# IMS quickstart — no Docker, MongoDB Atlas only.
set -e
cd "$(dirname "$0")/.."

echo "=== IMS quickstart ==="

echo "[1/3] Backend deps..."
pip install -e ./backend -q

echo "[2/3] Frontend deps..."
( cd frontend && npm install --silent )

echo "[3/3] Done. To run:"
echo "  1. Backend:   cd backend && python -m uvicorn app.main:app --reload"
echo "  2. Frontend:  cd frontend && npm run dev"
echo "  3. Browser:   http://localhost:5173"
echo "  4. Simulate:  python scripts/simulate_failure.py"
