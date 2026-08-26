@echo off
REM Single process only: FastAPI hosts the ws_worker as asyncio task.
cd /d %~dp0
.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000
