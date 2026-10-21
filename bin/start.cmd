@echo off
rem iHealth Plans dashboard launcher for Windows.
rem Double-click this file to start the dashboard. A window opens and your
rem browser follows. Keep the window open while you use the dashboard;
rem closing it (or pressing Ctrl+C) stops the server.

cd /d "%~dp0.."

echo Starting the iHealth Plans dashboard...
echo Your browser will open at http://localhost:5050 in a moment.
echo Keep this window open while you use it. Close it (or press Ctrl+C) to stop.
echo.

if not exist node_modules call npm install --no-audit --no-fund
call npm start
pause
