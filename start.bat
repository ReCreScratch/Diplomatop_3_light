@echo off
rem Starts the Diplomatio server and opens the game in the browser. Close this window (or Ctrl+C) to stop.
cd /d "%~dp0"
start "" /b cmd /c "timeout /t 2 >nul & start http://localhost:8000"
python -m uvicorn server.app:app --host 0.0.0.0 --port 8000
pause
