@echo off
echo Starting DataSense AI...

echo Starting Backend (FastAPI)...
start cmd /k "cd backend && venv\Scripts\activate && python -m uvicorn main:app --reload --port 8000"

echo Starting Frontend (Next.js)...
start cmd /k "cd frontend && npm run dev"

echo Both servers are starting up!
echo Please wait a few seconds, then open http://localhost:3000 in your browser.
