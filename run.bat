@echo off
cd /d %~dp0
uv run uvicorn app.main:app --host 0.0.0.0 --port 8000
pause
