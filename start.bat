@echo off
chcp 65001 >nul
cd /d "%~dp0"
echo Starting server: http://127.0.0.1:8001/
echo Close this window to stop.
python -m uvicorn main:app --host 127.0.0.1 --port 8001
pause
