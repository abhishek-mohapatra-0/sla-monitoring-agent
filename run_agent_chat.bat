@echo off
REM Chat with the SLA agent in this window (type 'exit' to quit)
call "%~dp0scripts\setup_env.bat" || (pause & exit /b 1)
cd /d "%~dp0app"
".venv\Scripts\python.exe" run_agent.py chat
pause
