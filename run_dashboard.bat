@echo off
REM One-click launcher: web dashboard + AI agent at http://127.0.0.1:8050
call "%~dp0scripts\setup_env.bat" || (pause & exit /b 1)
cd /d "%~dp0app"
".venv\Scripts\python.exe" app.py
pause
