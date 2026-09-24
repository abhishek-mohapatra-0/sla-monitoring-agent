@echo off
REM Builds today's SLA report in the reports folder, e-mails / posts it if configured in app\.env
REM Windows Task Scheduler runs this with the argument "scheduled" (no pause, no browser, writes a log).
call "%~dp0scripts\setup_env.bat"
if errorlevel 1 (
    if /i not "%~1"=="scheduled" pause
    exit /b 1
)
cd /d "%~dp0app"
if /i "%~1"=="scheduled" (
    if not exist "..\reports" mkdir "..\reports"
    ".venv\Scripts\python.exe" run_agent.py report --send >> "..\reports\agent_log.txt" 2>&1
    exit /b %errorlevel%
)
".venv\Scripts\python.exe" run_agent.py report --send --open
pause
