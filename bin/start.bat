@echo off
REM ============================================================
REM  iHealth Plans - TLDCRM Dashboard launcher (Windows)
REM  Double-click this file to start the dashboard.
REM  A window opens, the browser pops to http://localhost:5050,
REM  and the dashboard keeps running until you press Ctrl+C.
REM ============================================================

REM Move to the project root (this file lives in bin\, so go up one level).
cd /d "%~dp0.."

REM Pick a Python: a local venv if you made one, else py, else python.
set "PY=python"
where py >nul 2>nul && set "PY=py"
if exist "venv\Scripts\python.exe" set "PY=venv\Scripts\python.exe"

echo Starting the iHealth dashboard at http://localhost:5050  (press Ctrl+C to stop)
echo.
"%PY%" src\app.py

echo.
echo Dashboard stopped.
pause
