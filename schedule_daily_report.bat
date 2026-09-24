@echo off
REM Registers a Windows scheduled task that runs the SLA agent's daily report every day.
setlocal
set "T=09:00"
set /p "T=Run the daily report at what time? (HH:MM, 24h) [09:00]: "
if "%T%"=="" set "T=09:00"
schtasks /Create /F /SC DAILY /ST %T% /TN "SLA Agent Daily Report" /TR "\"%~dp0run_daily_report.bat\" scheduled"
if errorlevel 1 (
    echo.
    echo Could not create the task. Try right-click - Run as administrator.
) else (
    echo.
    echo Done. The agent will build and send the report every day at %T%.
    echo See it in Task Scheduler - Task Scheduler Library - "SLA Agent Daily Report".
    echo Run it now to test:   schtasks /Run /TN "SLA Agent Daily Report"
    echo Remove it later:      schtasks /Delete /TN "SLA Agent Daily Report" /F
)
pause
