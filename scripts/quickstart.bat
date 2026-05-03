@echo off
REM IMS quickstart - no Docker, MongoDB Atlas only.
cd /d %~dp0\..

echo.
echo === IMS quickstart ===
echo.

echo [1/3] Backend deps...
pushd backend
pip install -e . -q
popd

echo.
echo [2/3] Frontend deps...
pushd frontend
call npm install --silent
popd

echo.
echo [3/3] Done. To run:
echo   1. Backend:   cd backend ^&^& python -m uvicorn app.main:app --reload
echo   2. Frontend:  cd frontend ^&^& npm run dev
echo   3. Browser:   http://localhost:5173
echo   4. Simulate:  python scripts\simulate_failure.py
echo.
